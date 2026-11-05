"""The only door to the LLM: retries, JSON parsing, usage/cost accounting, Langfuse generations.

Credit savers: a disk response cache (identical prompt -> no second payment) and a dry-run mode
(KB_LLM_MODE=dryrun) that answers with cheap heuristics in the prompts' formats and records ESTIMATED tokens/cost.
"""
import hashlib
import json
import random
import re
import sqlite3
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable

import requests

from kb.config import Settings
from kb.textutil import tokens
from kb.tracing import clip, error_text, lf_generation


class LLMError(RuntimeError):
    pass


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = 0.0
    cache_hits: int = 0


class ResponseCache:
    """sqlite map sha256(model, json_mode, max_tokens, system, user) -> raw content. Temperature is 0, so reuse is safe."""

    _locks: dict[str, threading.Lock] = {}

    def __init__(self, settings: Settings):
        self.path = settings.llm_cache_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = ResponseCache._locks.setdefault(str(self.path), threading.Lock())
        with self._lock, sqlite3.connect(self.path) as c:
            c.execute("CREATE TABLE IF NOT EXISTS responses(key TEXT PRIMARY KEY, name TEXT, content TEXT, ts REAL)")

    @staticmethod
    def key(model: str, json_mode: bool, max_tokens: int, system: str, user: str) -> str:
        return hashlib.sha256(json.dumps([model, json_mode, max_tokens, system, user]).encode("utf-8")).hexdigest()

    def get(self, key: str) -> str | None:
        with self._lock, sqlite3.connect(self.path) as c:
            row = c.execute("SELECT content FROM responses WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def put(self, key: str, name: str, content: str) -> None:
        with self._lock, sqlite3.connect(self.path) as c:
            c.execute("INSERT OR REPLACE INTO responses VALUES (?,?,?,?)", (key, name, content, time.time()))


def parse_json_content(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON object in model output")
        out = json.loads(text[start:end + 1])
    if not isinstance(out, dict):
        raise ValueError("model JSON is not an object")
    return out


class LLM:
    """Base class. Subclasses implement _complete(system, user, name, model, max_tokens, json_mode) -> (text, in_tok, out_tok)."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.usage = Usage()
        self._lock = threading.Lock()

    def _account(self, in_tok: int, out_tok: int) -> None:
        s = self.settings
        with self._lock:
            self.usage.calls += 1
            self.usage.input_tokens += in_tok
            self.usage.output_tokens += out_tok
            if self.usage.cost_usd is not None:
                if s.price_input_per_m is None or s.price_output_per_m is None:
                    self.usage.cost_usd = None
                else:
                    self.usage.cost_usd += in_tok * s.price_input_per_m / 1e6 + out_tok * s.price_output_per_m / 1e6

    def complete_json(self, system: str, user: str, *, name: str, model: str | None = None, max_tokens: int = 8000) -> dict:
        return self._complete(system, user, name, model or self.settings.llm_model, max_tokens, True)

    def complete_text(self, system: str, user: str, *, name: str, model: str | None = None, max_tokens: int = 16000) -> str:
        return self._complete(system, user, name, model or self.settings.llm_model, max_tokens, False)

    def scoped(self) -> "LLM":
        raise NotImplementedError

    def _complete(self, system, user, name, model, max_tokens, json_mode):
        raise NotImplementedError


_semaphores: dict[int, threading.BoundedSemaphore] = {}
_sem_lock = threading.Lock()
_ledger_lock = threading.Lock()
_ledger_totals: dict[str, float] = {}


def spent_usd(settings: Settings) -> float:
    """Total recorded spend in the ledger file (read once per process, then tracked in memory)."""
    # ponytail: per-process running total; concurrent processes each see the file total at their start
    path = settings.ledger_path()
    key = str(path.resolve())
    with _ledger_lock:
        if key not in _ledger_totals:
            total = 0.0
            if path.is_file():
                for line in path.read_text(encoding="utf-8").splitlines():
                    try:
                        total += float(json.loads(line).get("cost_usd") or 0)
                    except ValueError:
                        continue
            _ledger_totals[key] = total
        return _ledger_totals[key]


def _record_spend(settings: Settings, name: str, model: str, in_tok: int, out_tok: int, cost: float | None) -> None:
    path = settings.ledger_path()
    spent_usd(settings)  # make sure the running total is initialised from the file
    with _ledger_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.time(), "name": name, "model": model, "input_tokens": in_tok,
                                "output_tokens": out_tok, "cost_usd": cost}) + "\n")
        _ledger_totals[str(path.resolve())] += cost or 0.0


def _semaphore(n: int) -> threading.BoundedSemaphore:
    with _sem_lock:
        if n not in _semaphores:
            _semaphores[n] = threading.BoundedSemaphore(n)
        return _semaphores[n]


_cooldowns: dict[str, float] = {}
_cooldown_lock = threading.Lock()
# ponytail: counts this process only, so another process sharing a key can still hit the limit; a 429 still cools it down.
_token_log: dict[str, deque] = {}
PACE_WINDOW_S = 60
PACE_OUTPUT_TOKENS = 400  # share of the output limit counted up front: most calls use far less than they may
PACE_POLL_S = 0.5
MAX_PACE_WAIT_S = 60
WRITER_CALLS = ("answer", "answer_verify")
SPLIT_CALLS = WRITER_CALLS + ("verify",)  # callers that split a request cut off at the output limit
RATE_LIMIT_COOLDOWN_S = 60
SERVER_ERROR_COOLDOWN_S = 30
DEADLINE_CUT_COOLDOWN_S = 5
PLAN_FIRST_SHARE = 0.6  # of a 20 s planner deadline: 12 s, above the 8.4 s slowest successful Cloudflare plan seen
BAD_KEY_COOLDOWN_S = 3600


def _cooling_until(provider) -> float:
    with _cooldown_lock:
        return _cooldowns.get(provider.label, 0.0)


def _cool(provider, seconds: float) -> None:
    with _cooldown_lock:
        _cooldowns[provider.label] = max(_cooldowns.get(provider.label, 0.0), time.monotonic() + seconds)


def _take_tokens(provider, tokens: int) -> bool:
    """Reserve per-minute tokens, or False when this call would go over the provider's limit and be refused."""
    if provider.max_total is None:
        return True
    now = time.monotonic()
    with _cooldown_lock:
        log = _token_log.setdefault(provider.label, deque())
        while log and log[0][0] <= now - PACE_WINDOW_S:
            log.popleft()
        if log and sum(n for _, n in log) + tokens > provider.max_total:
            return False
        log.append((now, tokens))
        return True


def _http_cooldown(resp) -> float:
    """How long to skip a provider after this response; 0 means only this request was bad."""
    if resp.status_code == 429:
        after = str(resp.headers.get("Retry-After") or "")
        return float(after) if after.isdigit() else RATE_LIMIT_COOLDOWN_S
    if resp.status_code in (401, 402, 403):
        return BAD_KEY_COOLDOWN_S
    return SERVER_ERROR_COOLDOWN_S if resp.status_code >= 500 else 0


class ChainLLM(LLM):
    """Tries each free provider in order; a rate limit, outage, bad key or invalid reply moves to the next one."""

    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.cache = ResponseCache(settings) if settings.llm_cache else None

    def scoped(self) -> "ChainLLM":
        return ChainLLM(self.settings)

    def _complete(self, system, user, name, model, max_tokens, json_mode):
        s = self.settings
        self.last_usage=None
        self.last_response=None
        providers = (s.writer_providers or s.providers) if name in WRITER_CALLS else s.providers
        if not providers:
            raise LLMError(f"{name}: no model provider configured; add a provider key to .env")
        for provider in providers:
            out = self._from_cache(provider, name, system, user, max_tokens, json_mode)
            if out is not None:
                return out
        if s.budget_usd is not None and (s.price_input_per_m is None or s.price_output_per_m is None):
            raise LLMError(f"{name}: KB_BUDGET_USD is set but PRICE_INPUT_PER_M/PRICE_OUTPUT_PER_M are blank, "
                           "so the cap cannot be enforced; set the prices")
        if s.budget_usd is not None and spent_usd(s) >= s.budget_usd:
            raise LLMError(f"{name}: spend cap KB_BUDGET_USD={s.budget_usd} reached ({spent_usd(s):.4f} USD recorded)")
        from kb.model_api import fit_output
        self.last_usage={"input_tokens":0,"output_tokens":0,"cost_usd":0.0}  # a rejected request used nothing
        estimate = (len(system) + len(user)) // 4
        usable = [(p, fit_output(p, estimate, max_tokens)) for p in providers]
        usable = [(p, limit) for p, limit in usable if limit is not None]
        if not usable:
            raise LLMError(f"{name}: about {estimate} input tokens fit no configured provider")
        errors: list[str] = []
        failed_here: set[str] = set()
        for attempt in range(1, s.llm_max_retries + 1):
            # With every provider busy, wait for one to free up rather than fail a call that could have run seconds later.
            for _ in range(int(MAX_PACE_WAIT_S / PACE_POLL_S)):
                tried = False
                for i, (provider, limit) in enumerate(usable):
                    # A writer's fallbacks are far weaker: wait out a short pause another call put on a better provider,
                    # if it ends within the poll budget and leaves that provider at least half the time left to write.
                    now = time.monotonic()
                    wait = min(MAX_PACE_WAIT_S - 1, (getattr(self, "deadline", float("inf")) - now) / 2)
                    if name in WRITER_CALLS and any(p.label not in failed_here and now < _cooling_until(p) <= now + wait
                                                    for p, _ in usable[:i]):
                        break
                    if _cooling_until(provider) > now or not _take_tokens(provider, estimate + min(limit, PACE_OUTPUT_TOKENS)):
                        continue
                    tried = True
                    if getattr(self, "deadline", float("inf")) <= time.monotonic():
                        raise LLMError(f"{name}: query deadline reached: {'; '.join(errors[-5:])}")
                    # A planner stuck on one slow provider would use its whole deadline: keep time for the next one.
                    share = PLAN_FIRST_SHARE if name == "plan" and i < len(usable) - 1 else 1.0
                    try:
                        return self._attempt(provider, system, user, name, limit, max_tokens, json_mode, share)
                    except (requests.RequestException, LLMError, ValueError, KeyError, IndexError) as e:
                        errors.append(f"{provider.label}: {str(e)[:120]}")
                        failed_here.add(provider.label)
                        # A reply cut off with the full output limit would be cut off on every provider: for calls whose
                        # caller splits a cut request, stop here and keep the reply so the split can run in time.
                        if (name in SPLIT_CALLS and limit >= max_tokens
                                and (self.last_response or {}).get("finish_reason") == "length"):
                            raise LLMError(f"{name}: reply cut off at {limit} output tokens") from e
                now = time.monotonic()
                if tried or getattr(self, "deadline", float("inf")) <= now or all(_cooling_until(p) - now > MAX_PACE_WAIT_S for p, _ in usable):
                    break
                time.sleep(PACE_POLL_S)
            if attempt < s.llm_max_retries:
                soonest = min(_cooling_until(p) for p, _ in usable) - time.monotonic()
                time.sleep(max(soonest, min(30, 2 ** attempt) + random.random()) if soonest <= 30 else 0)
        raise LLMError(f"{name}: every provider failed: {'; '.join(errors[-5:]) or 'all rate limited'}")

    def _from_cache(self, provider, name, system, user, max_tokens, json_mode):
        if not self.cache:
            return None
        hit = self.cache.get(ResponseCache.key(provider.label, json_mode, max_tokens, system, user))
        if hit is None:
            return None
        try:
            out = parse_json_content(hit) if json_mode else hit
        except ValueError:
            return None  # corrupt entry: fall through to a live call
        self.last_usage={"input_tokens":0,"output_tokens":0,"cost_usd":0.0,"model":provider.label}
        self.last_response={"content":hit,"finish_reason":"cache_hit","output_limit":max_tokens,"model":provider.label}
        with self._lock:
            self.usage.cache_hits += 1
        return out

    def _attempt(self, provider, system, user, name, limit, max_tokens, json_mode, share=1.0):
        from kb.model_api import request_spec, response_parts
        s = self.settings
        endpoint,headers,payload=request_spec(provider,system,user,limit,json_mode)
        self.last_response=None
        with lf_generation(name, provider.model, {"system": clip(system, 2000), "user": clip(user, 4000)}) as gen:
            try:
                with _semaphore(s.llm_concurrency):
                    remaining=min(s.llm_timeout_s,max(0.001,getattr(self,"deadline",time.monotonic()+s.llm_timeout_s)-time.monotonic()))*share
                    try:
                        resp = requests.post(endpoint, headers=headers, json=payload, timeout=(min(5, remaining), remaining))
                    except requests.RequestException as exc:
                        # A reply cut off by the query's own deadline may only be slow: a short pause lets the next
                        # stage retry a working provider while still moving later stages past a hung one.
                        cut_short = isinstance(exc, requests.ReadTimeout) and remaining < s.llm_timeout_s
                        _cool(provider, DEADLINE_CUT_COOLDOWN_S if cut_short else SERVER_ERROR_COOLDOWN_S)
                        raise
                if resp.status_code >= 400:
                    _cool(provider, _http_cooldown(resp))
                    raise LLMError(f"HTTP {resp.status_code}")
                content,finish_reason,in_tok,out_tok=response_parts(resp.json())
                # Some free endpoints omit usage: estimate so limits and traces stay meaningful.
                in_tok = in_tok if isinstance(in_tok,int) else (len(system)+len(user))//4
                out_tok = out_tok if isinstance(out_tok,int) else len(content or "")//4
                self._account(in_tok,out_tok)
                cost = self._cost(in_tok, out_tok)
                total = cost["total"] if cost else None
                earlier = self.last_usage or {}  # a call that falls back still used the tokens of its failed attempts
                self.last_usage={"input_tokens":earlier.get("input_tokens",0)+in_tok,"output_tokens":earlier.get("output_tokens",0)+out_tok,
                                 "cost_usd":None if total is None else earlier.get("cost_usd",0.0)+total,"model":provider.label}
                self.last_response={"content":content,"finish_reason":finish_reason,"output_limit":max_tokens,"model":provider.label}
                _record_spend(s, name, provider.label, in_tok, out_tok, total)
                gen.update(output=clip(content or "", 4000), usage_details={"input": in_tok, "output": out_tok},
                           **({"cost_details": cost} if cost else {}))
                if not content:
                    raise LLMError(f"empty content, finish_reason={finish_reason}")
                out = parse_json_content(content) if json_mode else content
                if self.cache:
                    self.cache.put(ResponseCache.key(provider.label, json_mode, max_tokens, system, user), name, content)
                return out
            except (requests.RequestException, LLMError, ValueError, KeyError, IndexError) as e:
                gen.update(level="ERROR", status_message=error_text(e))
                raise

    def _cost(self, in_tok: int, out_tok: int) -> dict | None:
        s = self.settings
        if s.price_input_per_m is None or s.price_output_per_m is None:
            return None
        ci, co = in_tok * s.price_input_per_m / 1e6, out_tok * s.price_output_per_m / 1e6
        return {"input": ci, "output": co, "total": ci + co}


class FakeLLM(LLM):
    """Test double. responder(name, system, user) -> dict | str, may raise LLMError. Counts 100 in / 10 out tokens per call."""

    def __init__(self, responder: Callable[[str, str, str], dict | str], settings: Settings | None = None,
                 _calls: list | None = None):
        super().__init__(settings or Settings())
        self.responder = responder
        self.calls: list[tuple[str, str, str]] = _calls if _calls is not None else []

    def scoped(self) -> "FakeLLM":
        return FakeLLM(self.responder, self.settings, self.calls)

    def _complete(self, system, user, name, model, max_tokens, json_mode):
        with self._lock:
            self.calls.append((name, system, user))
        self._account(100, 10)
        out = self.responder(name, system, user)
        if json_mode and isinstance(out, str):
            return parse_json_content(out)
        return out


def parallel_map(fn: Callable, items: list, max_workers: int) -> list:
    """Order-preserving map over threads; an exception is returned in its slot, never raised."""
    if not items:
        return []

    def safe(item):
        try:
            return fn(item)
        except Exception as e:  # noqa: BLE001 - caller inspects the slot
            return e

    with ThreadPoolExecutor(max_workers=max(1, min(max_workers, len(items)))) as pool:
        return list(pool.map(safe, items))


_DRY_OUTPUT_TOKENS = {"doc_card": 350, "page_card": 700, "plan": 450, "survey": 300, "verify": 450, "answer": 1800, "answer_verify": 300}


def _between(text: str, start: str, end: str | None) -> str:
    i = text.rfind(start) if end is None else text.find(start)
    if i < 0:
        return ""
    rest = text[i + len(start):]
    j = rest.find(end) if end else -1
    return (rest[:j] if j >= 0 else rest).strip()


def _dry_json_payload(name: str, p: dict) -> dict:
    """Dry-run answers for the query track's JSON payloads (kb/query: plan, survey, verify, answer, answer_verify)."""
    query = p.get("query", "")
    q = set(tokens(query))
    aspect_ids = re.findall(r"^(\S+):", p.get("aspects", ""), re.M) or ["a1"]

    def hit(text: str) -> bool:
        return len(q & set(tokens(text or ""))) >= max(2, min(5, len(q) // 5))

    def quote(text: str) -> str:
        return (text or "").strip()[:200].strip()

    if name == "plan":
        return {"intent": "analytical", "notes": "dryrun", "documents": [],
                "aspects": [{"text": query, "keywords": tokens(query)[:8], "entity": None, "period": None, "scope": None}]}
    if name == "survey":
        return {"pages": [{"page_no": c["page_no"], "aspects": aspect_ids, "strength": "medium"} for c in p.get("cards", [])
                          if hit(" ".join([c.get("summary", ""), " ".join(c.get("topics", []))]))]}
    if name == "verify":
        kept=[]
        for e in p.get("elements",[]):
            spans=e.get("source_spans")
            text="".join(spans.values()) if isinstance(spans,dict) else e.get("text","")
            if hit(text) and quote(text):
                kept.append({"id":e["id"],"aspects":aspect_ids,**({"support_span_ids":list(spans)} if spans else {"quotes":[quote(text)],"note":"dryrun lexical overlap"})})
        return {"keep":kept}
    if name == "answer" and "max_statements" in p:  # cited-synthesis writer: first span of each evidence, cited
        return {"status":"partial","limitations":["dryrun answer"],"sections":[{"heading":"Findings","statements":[
            {"kind":"finding","text":next(iter(e["source_spans"].values())),"obligation_ids":e.get("obligation_ids",[])[:1],
             "cites":[{"evidence_id":e["id"],"span_ids":list(e["source_spans"])[:1]}]}
            for e in p.get("evidence",[])[:8] if e.get("source_spans")]}]}
    if name == "answer" and any("source_spans" in e for e in p.get("evidence",[])):
        return {"status":"partial","limitations":["dryrun answer"],"selections":[
            {"obligation_id":e["obligation_ids"][0],"evidence_id":e["id"],"span_ids":list(e["source_spans"])[:1]}
            for e in p.get("evidence",[])[:8] if e.get("obligation_ids") and e.get("source_spans")]}
    if name == "answer":
        ev = [e for e in p.get("evidence", []) if quote(e.get("content"))][:8]
        ob = [o["id"] for o in p.get("obligations", [])]
        return {"status": "answered" if ev else "no_answer", "limitations": ["dryrun answer"],
                "claims": [{"id": f"c{i}", "text": quote(e["content"]), "evidence_ids": [e["id"]], "aspect_ids": ob,
                            "quotes": [{"evidence_id": e["id"], "quote": quote(e["content"])}], "calculation": None}
                           for i, e in enumerate(ev, 1)]}
    if name == "answer_verify":
        return {"verdicts": [{"claim_id": c["claim_id"], "verdict": "supported", "reason": "dryrun"} for c in p.get("claims", [])]}
    return {}


def _dry_responder(name: str, system: str, user: str):
    """Heuristic stand-in for each prompt. Card calls fail on purpose so ingestion uses its deterministic fallbacks."""
    if name in ("doc_card", "page_card"):
        raise LLMError("dryrun: cards use deterministic fallbacks")
    if user.startswith("{"):
        return _dry_json_payload(name, json.loads(user))
    if name == "plan":
        query = _between(user, "Question: ", None)
        return {"intent": "analytical", "answerable": True, "notes": "dryrun",
                "aspects": [{"id": "a1", "text": query, "keywords": tokens(query)[:8]}], "documents": []}
    if name == "survey":
        return {"pages": []}
    query = set(tokens(_between(user, "Question: ", "\n\n")))
    blocks = re.findall(r"\[E(\d+)\][^\n]*\n(.*?)(?=\n\[E\d+\]|\Z)", user, re.S)
    if name == "verify":
        need = max(2, len(query) // 5)
        return {"keep": [{"id": f"E{n}", "aspects": ["a1"], "note": "dryrun lexical overlap"}
                         for n, text in blocks if len(query & set(tokens(text))) >= need]}
    if name == "answer":
        lines = [f"- {' '.join(text.split())[:160]} [E{n}]" for n, text in blocks[:8]]
        return "Dry-run answer built from the top evidence.\n" + "\n".join(lines) + "\nSTATUS: answered"
    return {}


class DryRunLLM(LLM):
    """KB_LLM_MODE=dryrun: no network, no spend; usage holds ESTIMATED tokens (chars/4 in, nominal out) and cost."""

    def scoped(self) -> "DryRunLLM":
        return DryRunLLM(self.settings)

    def _complete(self, system, user, name, model, max_tokens, json_mode):
        self._account((len(system) + len(user)) // 4, min(max_tokens, _DRY_OUTPUT_TOKENS.get(name, 300)))
        out = _dry_responder(name, system, user)
        return out


def get_llm(settings: Settings) -> LLM:
    return DryRunLLM(settings) if settings.llm_mode == "dryrun" else ChainLLM(settings)
