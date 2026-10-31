"""The free-provider fallback chain: order, skipping, cooldowns, cache and accounting."""
import pytest

import kb.llm as llm_mod
from kb.config import get_settings
from kb.llm import ChainLLM, LLMError
from kb.model_api import Provider, build_providers, fit_output, request_spec, response_parts

A = Provider("a", "https://a.test/chat", "model-a", "key-a")
B = Provider("b", "https://b.test/chat", "model-b", "key-b")


class Reply:
    def __init__(self, status=200, content='{"ok": true}', headers=None, usage=True):
        self.status_code, self.content, self.headers = status, content, headers or {}
        self.usage = usage

    def json(self):
        out = {"choices": [{"message": {"content": self.content}, "finish_reason": "stop"}]}
        return {**out, "usage": {"prompt_tokens": 10, "completion_tokens": 2}} if self.usage else out


@pytest.fixture
def post(monkeypatch):
    """Scripted replies by URL; records the order providers were called in."""
    calls, replies = [], {}

    def fake(url, headers=None, json=None, timeout=None):
        calls.append(url)
        reply = replies[url]
        reply = reply.pop(0) if isinstance(reply, list) else reply
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(llm_mod.requests, "post", fake)
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: None)
    return calls, replies


def chain(tmp_path, *providers, **kw):
    kw.setdefault("llm_max_retries", 1)
    return ChainLLM(get_settings(data_dir=tmp_path, providers=providers, llm_cache=kw.pop("llm_cache", False), **kw))


def test_first_provider_answers_and_later_ones_are_untouched(tmp_path, post):
    calls, replies = post
    replies[A.url] = Reply()
    llm = chain(tmp_path, A, B)
    assert llm.complete_json("s", "u", name="plan") == {"ok": True}
    assert calls == [A.url] and llm.last_usage["model"] == "a:model-a" and llm.last_usage["cost_usd"] == 0


@pytest.mark.parametrize("failure", [Reply(429), Reply(503), Reply(401), Reply(400), Reply(content="not json"), Reply(content=None),
                                     llm_mod.requests.ConnectionError("down"), llm_mod.requests.Timeout("slow")])
def test_any_provider_failure_falls_through_to_the_next(tmp_path, post, failure):
    calls, replies = post
    replies[A.url], replies[B.url] = failure, Reply()
    llm = chain(tmp_path, A, B)
    assert llm.complete_json("s", "u", name="plan") == {"ok": True}
    assert calls == [A.url, B.url] and llm.last_usage["model"] == "b:model-b"


def test_every_provider_failing_is_an_error_naming_them(tmp_path, post):
    _, replies = post
    replies[A.url], replies[B.url] = Reply(429), Reply(503)
    with pytest.raises(LLMError, match="a:model-a: HTTP 429.*b:model-b: HTTP 503"):
        chain(tmp_path, A, B).complete_json("s", "u", name="plan")


def test_rate_limited_provider_is_skipped_until_its_cooldown_ends(tmp_path, post, monkeypatch):
    calls, replies = post
    replies[A.url], replies[B.url] = Reply(429, headers={"Retry-After": "120"}), Reply()
    now = [1000.0]
    monkeypatch.setattr(llm_mod.time, "monotonic", lambda: now[0])
    llm = chain(tmp_path, A, B)
    llm.complete_json("s", "u", name="plan")
    llm.complete_json("s", "u2", name="plan")
    assert calls == [A.url, B.url, B.url]  # the second call never waited on the limited provider
    now[0] += 121
    replies[A.url] = Reply()
    llm.complete_json("s", "u3", name="plan")
    assert calls[-1] == A.url


def test_a_rejected_request_does_not_bench_the_provider(tmp_path, post):
    calls, replies = post
    replies[A.url], replies[B.url] = [Reply(400), Reply()], Reply()
    llm = chain(tmp_path, A, B)
    llm.complete_json("s", "u", name="plan")
    llm.complete_json("s", "u2", name="plan")
    assert calls == [A.url, B.url, A.url]


def test_a_call_too_big_for_a_provider_skips_it_without_a_request(tmp_path, post):
    calls, replies = post
    small = Provider("small", "https://small.test/chat", "m", "k", max_total=1000)
    replies[B.url] = Reply()
    chain(tmp_path, small, B).complete_json("s", "x" * 8000, name="answer", max_tokens=500)
    assert calls == [B.url]
    with pytest.raises(LLMError, match="fit no configured provider"):
        chain(tmp_path, small).complete_json("s", "x" * 8000, name="answer", max_tokens=500)


def test_output_limit_shrinks_to_fit_but_never_below_a_useful_size():
    small = Provider("small", "u", "m", "k", max_total=1000)
    assert fit_output(small, 400, 4000) == 600
    assert fit_output(small, 900, 4000) is None
    assert fit_output(small, 900, 50) == 50
    assert fit_output(A, 400, 20000) == A.max_output


def test_failed_attempts_still_count_their_tokens(tmp_path, post):
    _, replies = post
    replies[A.url], replies[B.url] = Reply(content="not json"), Reply()
    llm = chain(tmp_path, A, B)
    llm.complete_json("s", "u", name="plan")
    assert llm.last_usage["input_tokens"] == 20 and llm.last_usage["output_tokens"] == 4 and llm.usage.calls == 2


def test_missing_usage_is_estimated_not_fatal(tmp_path, post):
    _, replies = post
    replies[A.url] = Reply(usage=False)
    llm = chain(tmp_path, A)
    assert llm.complete_json("s" * 40, "u" * 40, name="plan") == {"ok": True}
    assert llm.last_usage["input_tokens"] == 20 and llm.last_usage["output_tokens"] == 3


def test_cached_answer_from_a_later_provider_costs_no_call(tmp_path, post):
    calls, replies = post
    replies[A.url], replies[B.url] = Reply(503), Reply()
    chain(tmp_path, A, B, llm_cache=True).complete_json("s", "u", name="plan")
    llm_mod._cooldowns.clear()
    again = chain(tmp_path, A, B, llm_cache=True)
    assert again.complete_json("s", "u", name="plan") == {"ok": True}
    assert len(calls) == 2 and again.usage.cache_hits == 1 and again.last_usage["model"] == "b:model-b"


def test_cache_is_not_shared_with_a_different_model(tmp_path, post):
    calls, replies = post
    other = Provider("a", A.url, "model-c", "key-a")
    replies[A.url] = Reply()
    chain(tmp_path, A, llm_cache=True).complete_json("s", "u", name="plan")
    chain(tmp_path, other, llm_cache=True).complete_json("s", "u", name="plan")
    assert len(calls) == 2


def test_past_query_deadline_stops_before_calling(tmp_path, post):
    calls, replies = post
    replies[A.url] = Reply()
    llm = chain(tmp_path, A)
    llm.deadline = llm_mod.time.monotonic() - 1
    with pytest.raises(LLMError, match="deadline"):
        llm.complete_json("s", "u", name="verify")
    assert calls == []


def test_no_provider_is_a_clear_error(tmp_path):
    with pytest.raises(LLMError, match="no model provider configured"):
        chain(tmp_path).complete_json("s", "u", name="plan")


def test_build_providers_keeps_order_and_skips_missing_keys():
    env = {"KB_LLM_PROVIDERS": "cloudflare,groq,groq:openai/gpt-oss-20b,gemini", "GROQ_API_KEY": "g", "GEMINI_API_KEY": "m",
           "CLOUDFLARE_API_TOKEN": "c"}  # no account ID, so Cloudflare is left out
    assert [p.label for p in build_providers(env)] == ["groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b", "gemini:gemini-2.5-flash"]
    env["CLOUDFLARE_ACCOUNT_ID"] = "acct"
    first = build_providers(env)[0]
    assert first.name == "cloudflare" and "/accounts/acct/" in first.url and first.key == "c"
    assert "key=" not in repr(first)  # keys stay out of logs and tracebacks
    with pytest.raises(ValueError, match="unknown provider"):
        build_providers({"KB_LLM_PROVIDERS": "nope"})


def test_default_chain_uses_only_keys_that_exist():
    assert build_providers({}) == ()
    assert [p.name for p in build_providers({"GEMINI_API_KEY": "m", "GROQ_API_KEY": "g"})] == ["groq", "groq", "gemini"]


def test_wire_format_is_openai_style_and_turns_thinking_down():
    url, headers, payload = request_spec(Provider("c", "https://c.test", "@cf/qwen/qwen3-30b-a3b-fp8", "k"), "s", "u", 100)
    assert url == "https://c.test" and headers["Authorization"] == "Bearer k" and payload["temperature"] == 0
    assert payload["messages"][1] == {"role": "user", "content": "u"} and payload["messages"][0]["content"].endswith("/no_think")
    assert "JSON" in payload["messages"][0]["content"]
    _, _, oss = request_spec(Provider("g", "u", "openai/gpt-oss-120b", "k"), "s", "u", 100, json_mode=False)
    assert oss["reasoning_effort"] == "low" and oss["messages"][0]["content"] == "s"


def test_thinking_text_is_removed_from_replies():
    body = {"choices": [{"message": {"content": '<think>hmm {"no": 1}</think>\n{"ok": true}'}, "finish_reason": "stop"}]}
    assert response_parts(body)[0] == '{"ok": true}'


def test_judge_runs_the_chain_in_reverse_and_reuses_saved_verdicts(tmp_path, monkeypatch, post):
    from evaluation.official import OfficialJudgeTransport
    calls, replies = post
    settings = get_settings(data_dir=tmp_path, providers=(A, B))
    monkeypatch.setattr("kb.config.get_settings", lambda: settings)
    replies[B.url] = Reply(content='{"points": ["a"]}')
    judge = OfficialJudgeTransport()
    assert judge.call_structured("s", "u", max_tokens=512) == {"points": ["a"]}
    assert judge.call_structured("s", "u", max_tokens=512) == {"points": ["a"]}
    assert calls == [B.url] and judge.models == {"b:model-b"} and judge.log[1]["cached"]
