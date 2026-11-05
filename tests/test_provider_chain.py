"""The free-provider fallback chain: order, skipping, cooldowns, cache and accounting."""
import pytest

import kb.llm as llm_mod
from kb.config import get_settings
from kb.llm import ChainLLM, LLMError
from kb.model_api import WRITER_CHAIN, Provider, build_providers, fit_output, request_spec, response_parts

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


def test_a_reply_cut_off_by_the_query_deadline_only_pauses_the_provider(tmp_path, post):
    _, replies = post
    replies[A.url] = llm_mod.requests.ReadTimeout("cut short")
    llm = chain(tmp_path, A)
    llm.deadline = llm_mod.time.monotonic() + 20
    with pytest.raises(LLMError):
        llm.complete_json("s", "u", name="plan")
    left = llm_mod._cooling_until(A) - llm_mod.time.monotonic()
    assert 0 < left <= llm_mod.DEADLINE_CUT_COOLDOWN_S


def test_a_provider_timing_out_on_its_own_gets_the_full_cooldown(tmp_path, post):
    _, replies = post
    replies[A.url] = llm_mod.requests.ReadTimeout("slow")
    with pytest.raises(LLMError):
        chain(tmp_path, A).complete_json("s", "u", name="plan")
    assert llm_mod._cooling_until(A) - llm_mod.time.monotonic() > llm_mod.DEADLINE_CUT_COOLDOWN_S


def test_a_timeout_without_a_deadline_gets_the_full_cooldown_even_when_the_clock_ticks(tmp_path, post, monkeypatch):
    _, replies = post
    replies[A.url] = llm_mod.requests.ReadTimeout("slow")
    clock = iter(range(1000, 2000))  # every reading of the clock is a little later than the last
    monkeypatch.setattr(llm_mod.time, "monotonic", lambda: next(clock) / 10)
    with pytest.raises(LLMError):
        chain(tmp_path, A).complete_json("s", "u", name="answer")
    assert llm_mod._cooldowns[A.label] - llm_mod.time.monotonic() > llm_mod.DEADLINE_CUT_COOLDOWN_S


@pytest.mark.parametrize("failure", [llm_mod.requests.ConnectTimeout("no route"), llm_mod.requests.ConnectionError("down")])
def test_a_provider_that_cannot_be_reached_gets_the_full_cooldown_inside_a_deadline(tmp_path, post, failure):
    _, replies = post
    replies[A.url] = failure
    llm = chain(tmp_path, A)
    llm.deadline = llm_mod.time.monotonic() + 20
    with pytest.raises(LLMError):
        llm.complete_json("s", "u", name="plan")
    assert llm_mod._cooling_until(A) - llm_mod.time.monotonic() > llm_mod.DEADLINE_CUT_COOLDOWN_S


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


def test_a_provider_is_not_sent_more_than_its_tokens_per_minute(tmp_path, post, monkeypatch):
    calls, replies = post
    now = [1000.0]
    monkeypatch.setattr(llm_mod.time, "monotonic", lambda: now[0])
    paced = Provider("p", "https://p.test/chat", "model-p", "key-p", max_total=1000)
    replies[paced.url], replies[B.url] = Reply(), Reply()
    llm = chain(tmp_path, paced, B)
    prompt = "x" * 1600  # about 400 tokens, plus the output share
    llm.complete_json("s", prompt, name="plan", max_tokens=100)
    llm.complete_json("s", prompt + "2", name="plan", max_tokens=100)
    llm.complete_json("s", prompt + "3", name="plan", max_tokens=100)
    assert calls == [paced.url, paced.url, B.url]  # the third would go over, so no request is wasted on a rate limit
    now[0] += 61
    llm.complete_json("s", prompt + "4", name="plan", max_tokens=100)
    assert calls[-1] == paced.url


def test_a_slow_planner_provider_leaves_time_for_the_next_one(tmp_path, monkeypatch):
    waits = []

    def fake(url, headers=None, json=None, timeout=None):
        waits.append((url, timeout[1]))
        if url == A.url:
            raise llm_mod.requests.ReadTimeout("slow")
        return Reply()

    monkeypatch.setattr(llm_mod.requests, "post", fake)
    llm = chain(tmp_path, A, B)
    llm.deadline = llm_mod.time.monotonic() + 20
    assert llm.complete_json("s", "u", name="plan") == {"ok": True}
    assert [u for u, _ in waits] == [A.url, B.url] and waits[0][1] <= 20 * llm_mod.PLAN_FIRST_SHARE


def test_only_the_planner_splits_its_time_and_the_last_provider_gets_all_of_it(tmp_path, monkeypatch):
    waits = []
    monkeypatch.setattr(llm_mod.requests, "post", lambda url, headers=None, json=None, timeout=None: waits.append(timeout[1]) or Reply())
    for name, providers in (("verify", (A, B)), ("plan", (A,))):
        llm = chain(tmp_path, *providers)
        llm.deadline = llm_mod.time.monotonic() + 20
        llm.complete_json("s", name, name=name)
    assert all(w > 19 for w in waits)


def test_a_call_waits_for_capacity_instead_of_failing_at_once(tmp_path, post, monkeypatch):
    calls, replies = post
    now = [1000.0]
    monkeypatch.setattr(llm_mod.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: now.__setitem__(0, now[0] + s))
    replies[A.url] = [Reply(429, headers={"Retry-After": "5"}), Reply()]
    llm = chain(tmp_path, A)
    with pytest.raises(LLMError):
        llm.complete_json("s", "u", name="plan")
    assert llm.complete_json("s", "u2", name="plan") == {"ok": True}
    assert now[0] >= 1005


def test_a_call_gives_up_waiting_at_the_query_deadline(tmp_path, post, monkeypatch):
    calls, replies = post
    now = [1000.0]
    monkeypatch.setattr(llm_mod.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: now.__setitem__(0, now[0] + s))
    llm_mod._cool(A, 500)
    llm = chain(tmp_path, A)
    llm.deadline = now[0] + 3
    with pytest.raises(LLMError):
        llm.complete_json("s", "u", name="plan")
    assert calls == [] and now[0] <= 1004


def test_a_call_does_not_wait_on_a_provider_blocked_for_longer_than_it_would_wait(tmp_path, post, monkeypatch):
    sleeps = []
    monkeypatch.setattr(llm_mod.time, "sleep", sleeps.append)
    llm_mod._cool(A, llm_mod.BAD_KEY_COOLDOWN_S)
    with pytest.raises(LLMError):
        chain(tmp_path, A).complete_json("s", "u", name="plan")
    assert sleeps == []


def test_a_writer_waits_out_a_short_pause_of_a_better_provider(tmp_path, post, monkeypatch):
    calls, replies = post
    now = [1000.0]
    monkeypatch.setattr(llm_mod.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: now.__setitem__(0, now[0] + s))
    replies[A.url], replies[B.url] = Reply(), Reply()
    llm_mod._cool(A, llm_mod.SERVER_ERROR_COOLDOWN_S)
    llm = chain(tmp_path, A, B)
    assert llm.complete_json("s", "u", name="answer") == {"ok": True}
    assert calls == [A.url] and now[0] >= 1000 + llm_mod.SERVER_ERROR_COOLDOWN_S
    llm_mod._cool(A, llm_mod.SERVER_ERROR_COOLDOWN_S)
    llm.complete_json("s", "u2", name="verify")
    assert calls[-1] == B.url  # other calls keep moving to the next provider


def test_a_writer_does_not_wait_away_the_time_it_needs_to_write(tmp_path, post, monkeypatch):
    calls, replies = post
    now = [1000.0]
    monkeypatch.setattr(llm_mod.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(llm_mod.time, "sleep", lambda s: now.__setitem__(0, now[0] + s))
    replies[A.url], replies[B.url] = Reply(), Reply()
    llm = chain(tmp_path, A, B)
    for pause, deadline, first in ((30, 45, B.url), (30, 150, A.url), (llm_mod.MAX_PACE_WAIT_S, 1000, B.url)):
        now[0] += 1000
        llm_mod._cool(A, pause)
        llm.deadline = now[0] + deadline
        llm.complete_json("s", f"u{pause}{deadline}", name="answer")
        assert calls[-1] == first, (pause, deadline)


def test_a_writer_whose_better_provider_fails_on_this_call_still_moves_on(tmp_path, post):
    calls, replies = post
    replies[A.url], replies[B.url] = Reply(503), Reply()
    assert chain(tmp_path, A, B).complete_json("s", "u", name="answer") == {"ok": True}
    assert calls == [A.url, B.url]


def test_a_writer_moves_on_when_the_better_provider_is_out_for_longer(tmp_path, post):
    calls, replies = post
    replies[B.url] = Reply()
    llm_mod._cool(A, llm_mod.BAD_KEY_COOLDOWN_S)
    assert chain(tmp_path, A, B).complete_json("s", "u", name="answer") == {"ok": True}
    assert calls == [B.url]


def _cut_reply():
    cut = Reply(content='{"sections": [{"text": "unfinished')
    cut.json = lambda: {"choices": [{"message": {"content": cut.content}, "finish_reason": "length"}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5400}}
    return cut


def test_a_cut_reply_still_falls_through_when_the_provider_had_less_room_or_the_caller_cannot_split(tmp_path, post):
    calls, replies = post
    small = Provider("s", "https://s.test/chat", "model-s", "key-s", max_total=1000)
    replies[small.url], replies[A.url], replies[B.url] = _cut_reply(), _cut_reply(), Reply()
    assert chain(tmp_path, small, B).complete_json("s", "u", name="answer", max_tokens=2000) == {"ok": True}
    assert calls == [small.url, B.url]  # the small provider was given under 1,000 of the 2,000 asked
    assert chain(tmp_path, A, B).complete_json("s", "u", name="doc_card") == {"ok": True}
    assert calls[-2:] == [A.url, B.url]  # ingest calls have no split to fall back on


def test_a_reply_cut_off_at_the_output_limit_stops_the_chain_so_the_caller_can_split(tmp_path, post):
    calls, replies = post
    cut = _cut_reply()
    replies[A.url], replies[B.url] = cut, Reply()
    llm = chain(tmp_path, A, B)
    with pytest.raises(LLMError, match="cut off"):
        llm.complete_json("s", "u", name="answer")
    assert calls == [A.url] and llm.last_response["finish_reason"] == "length"
    from kb.query.errors import QueryError
    from kb.query.provider import SharedQueryClient
    with pytest.raises(QueryError) as caught:  # what the writer splits on
        SharedQueryClient(chain(tmp_path, A, B)).complete_json("s", "u2", name="answer", max_tokens=5400)
    assert caught.value.code == "MODEL_SCHEMA" and calls == [A.url, A.url]


def test_writing_uses_its_own_model_order(tmp_path, post):
    calls, replies = post
    replies[A.url], replies[B.url] = Reply(), Reply()
    llm = chain(tmp_path, A, writer_providers=(B,))
    llm.complete_json("s", "u", name="verify")
    llm.complete_json("s", "u", name="answer")
    llm.complete_json("s", "u2", name="answer_verify")
    assert calls == [A.url, B.url, B.url]


def test_the_judge_model_is_not_in_the_default_answer_chains():
    env = {"GROQ_API_KEY": "k", "MISTRAL_API_KEY": "m"}
    labels = [p.label for chain_ in (build_providers(env), build_providers(env, "KB_WRITER_PROVIDERS", WRITER_CHAIN)) for p in chain_]
    assert "groq:openai/gpt-oss-120b" not in labels and "groq:qwen/qwen3.8-27b" in labels


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


ALL_KEYS = {"CLOUDFLARE_API_TOKEN": "c", "CLOUDFLARE_ACCOUNT_ID": "a", "GROQ_API_KEY": "g", "OPENROUTER_API_KEY": "o",
            "MISTRAL_API_KEY": "m", "GEMINI_API_KEY": "e"}


def test_private_mode_is_the_default_and_keeps_documents_with_no_retention_providers():
    for chain_ in (build_providers(ALL_KEYS), build_providers(ALL_KEYS, "KB_WRITER_PROVIDERS", WRITER_CHAIN)):
        assert chain_ and {p.name for p in chain_} <= {"cloudflare", "groq"}
    opened = {p.name for p in build_providers({**ALL_KEYS, "KB_PRIVATE": "0"})}
    assert {"openrouter", "mistral", "gemini"} <= opened


def test_naming_a_provider_that_may_train_on_data_fails_in_private_mode():
    for variable in ("KB_LLM_PROVIDERS", "KB_WRITER_PROVIDERS"):
        with pytest.raises(ValueError, match="KB_PRIVATE"):
            build_providers({**ALL_KEYS, variable: "cloudflare,gemini"}, variable)
    with pytest.raises(ValueError, match="KB_PRIVATE"):  # the writer chain falls back to an explicit KB_LLM_PROVIDERS
        build_providers({**ALL_KEYS}, "KB_WRITER_PROVIDERS", "mistral")
    assert [p.name for p in build_providers({**ALL_KEYS, "KB_LLM_PROVIDERS": "groq,cloudflare"})] == ["groq", "cloudflare"]


def test_build_providers_keeps_order_and_skips_missing_keys():
    env = {"KB_LLM_PROVIDERS": "cloudflare,groq,groq:openai/gpt-oss-20b,gemini", "GROQ_API_KEY": "g", "GEMINI_API_KEY": "m",
           "CLOUDFLARE_API_TOKEN": "c", "KB_PRIVATE": "0"}  # no account ID, so Cloudflare is left out
    assert [p.label for p in build_providers(env)] == ["groq:openai/gpt-oss-120b", "groq:openai/gpt-oss-20b", "gemini:gemini-3.5-flash"]
    env["CLOUDFLARE_ACCOUNT_ID"] = "acct"
    first = build_providers(env)[0]
    assert first.name == "cloudflare" and "/accounts/acct/" in first.url and first.key == "c"
    assert "key=" not in repr(first)  # keys stay out of logs and tracebacks
    with pytest.raises(ValueError, match="unknown provider"):
        build_providers({"KB_LLM_PROVIDERS": "nope"})


def test_default_chain_uses_only_keys_that_exist():
    assert build_providers({}) == ()
    assert [p.name for p in build_providers({"GEMINI_API_KEY": "m", "GROQ_API_KEY": "g", "KB_PRIVATE": "0"})] == ["groq", "gemini"]


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


def _judge(tmp_path, monkeypatch, **kw):
    from evaluation.official import OfficialJudgeTransport
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setattr("kb.config.get_settings", lambda: get_settings(data_dir=tmp_path))
    return OfficialJudgeTransport(wait_s=0, **kw)


def test_judge_uses_one_model_and_reuses_saved_verdicts(tmp_path, monkeypatch, post):
    calls, replies = post
    judge = _judge(tmp_path, monkeypatch)
    url = judge.client.settings.providers[0].url
    replies[url] = Reply(content='{"points": ["a"]}')
    assert judge.call_structured("s", "u", max_tokens=512) == {"points": ["a"]}
    assert judge.call_structured("s", "u", max_tokens=512) == {"points": ["a"]}
    assert calls == [url] and judge.models == {"groq:openai/gpt-oss-120b"} and judge.log[1]["cached"]


def test_judge_waits_out_a_rate_limit_and_never_switches_model(tmp_path, monkeypatch, post):
    calls, replies = post
    judge = _judge(tmp_path, monkeypatch)
    url = judge.client.settings.providers[0].url
    replies[url] = [Reply(429, headers={"Retry-After": "0"}), Reply(503), Reply(content='{"ok": 1}')]
    monkeypatch.setattr(llm_mod, "SERVER_ERROR_COOLDOWN_S", 0)
    assert judge.call_structured("s", "u") == {"ok": 1} and calls == [url] * 3


def test_judge_that_stays_down_fails_instead_of_switching(tmp_path, monkeypatch, post):
    calls, replies = post
    judge = _judge(tmp_path, monkeypatch, attempts=2)
    url = judge.client.settings.providers[0].url
    replies[url] = Reply(400)
    with pytest.raises(LLMError):
        judge.call_structured("s", "u")
    assert calls == [url] * 2


def test_audit_accepts_points_returned_as_objects():
    from evaluation.audit import judge_consistency
    point = {"claim": "x", "source": "a.pdf, page 6"}
    metrics = {"answer_detail": {"benchmark_points": {"bp1": point}, "agent_points": {"ap1": point}, "matched_ids": [], "missing_ids": ["bp1"], "extra_ids": []}}
    assert judge_consistency(metrics, "text [a.pdf p6]")["official_scores_unchanged"]


def test_a_collection_name_with_a_trailing_newline_is_refused(tmp_path):
    from kb.errors import KBError
    from kb.ingest.pipeline import index_collection
    settings = get_settings(data_dir=tmp_path)
    with pytest.raises(KBError, match="collection_name"):
        index_collection(tmp_path / "none.zip", "name\n", settings=settings, llm=None, embedder=None)
