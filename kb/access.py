"""API keys and rate limits for every route.

KB_API_KEYS: comma-separated keys; when set, every request needs one in `X-API-Key` or `Authorization: Bearer`
(generate each with `python -c "import secrets; print(secrets.token_urlsafe(32))"`). On a hosted deploy (Render sets
RENDER) with no keys, every request gets 503 unless KB_AUTH=off says to run open on purpose.
Limits, counted on POST only: KB_QUERY_PER_HOUR (default 20) and KB_INDEX_PER_DAY (default 5) per key, or per
client address when no keys are set, and KB_QUERIES_PER_DAY (default 25) for all callers together, sized to the free
model quota. 0 turns a limit off. Read on every request, so a change to the environment applies without a restart.
"""
import hashlib
import hmac
import math
import os
import threading
import time
from collections import deque

from kb.errors import KBError

# path -> [(limit variable, default, window seconds, shared by all callers)]
LIMITS = {"/query": [("KB_QUERY_PER_HOUR", 20, 3600, False), ("KB_QUERIES_PER_DAY", 25, 86400, True)],
          "/index": [("KB_INDEX_PER_DAY", 5, 86400, False)]}

# ponytail: one process's memory, so counts reset when the service restarts (Render free sleeps after 15 idle minutes)
# and are per worker; keep them in Atlas if a restart must not reset them. The provider quota still caps total use.
_hits: dict[tuple[str, str, str], deque] = {}
_lock = threading.Lock()


def _keys() -> list[str]:
    return [k.strip() for k in os.environ.get("KB_API_KEYS", "").split(",") if k.strip()]


def _presented(headers) -> str:
    bearer = headers.get("authorization", "")
    return headers.get("x-api-key") or (bearer[7:].strip() if bearer[:7].lower() == "bearer " else "")


def _limit(variable: str, default: int) -> int:
    raw = os.environ.get(variable, "").strip()
    return int(raw) if raw.isdigit() else default


def check(method: str, path: str, headers, client_host: str) -> tuple[KBError, dict] | None:
    """The error and extra headers to send instead of serving this request, or None to serve it."""
    keys, given = _keys(), _presented(headers)
    if keys:
        # Compare against every key so the time taken does not reveal which one nearly matched.
        if not any([hmac.compare_digest(given.encode(), k.encode()) for k in keys]):
            return KBError("UNAUTHORIZED", "Missing or invalid API key.", 401), {"WWW-Authenticate": "Bearer"}
        client = "key:" + hashlib.sha256(given.encode()).hexdigest()[:16]  # never keep the key itself
    elif os.environ.get("RENDER") and os.environ.get("KB_AUTH", "").strip().lower() != "off":
        return KBError("AUTH_NOT_CONFIGURED", "The service has no API keys configured.", 503), {}
    else:
        client = "ip:" + (client_host or "unknown")
    if method != "POST":
        return None
    now = time.monotonic()
    with _lock:
        buckets = []
        for variable, default, window, shared in LIMITS.get(path, []):
            limit = _limit(variable, default)
            if limit <= 0:
                continue
            key = ("all" if shared else client, path, variable)
            hits = _hits.get(key) or deque()  # stored only when a hit is counted, so refusals leave nothing behind
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= limit:
                wait = max(1, math.ceil(window - (now - hits[0])))  # (t + w) - t can round above w
                return (KBError("RATE_LIMITED", f"Limit of {limit} requests reached; try again later.", 429,
                                retryable=True, details={"limit": limit, "window_s": window, "retry_after_s": wait}),
                        {"Retry-After": str(wait)})
            buckets.append((key, hits))
        for key, hits in buckets:  # count only once every limit has room
            hits.append(now)
            _hits[key] = hits
        for key in [k for k, v in _hits.items() if not v]:
            del _hits[key]
    return None
