"""Response trace (exactly four keys per step) and a Langfuse facade that never breaks a request."""
import logging
import os
import re
from contextlib import contextmanager
from typing import Any

log = logging.getLogger("kb.tracing")
TRACE_KEYS = ("step_name", "description", "input", "output")


def clip(value: Any, max_str: int = 500, max_list: int = 50) -> Any:
    if isinstance(value, str):
        return value if len(value) <= max_str else value[:max_str] + "..."
    if isinstance(value, dict):
        return {k: clip(v, max_str, max_list) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        items = [clip(v, max_str, max_list) for v in value[:max_list]]
        if len(value) > max_list:
            items.append(f"... (+{len(value) - max_list} more)")
        return items
    return value


class StepTrace:
    def __init__(self):
        self._steps: list[dict] = []

    def add(self, step_name: str, description: str, input: Any, output: Any) -> None:
        self._steps.append({"step_name": step_name, "description": description,
                            "input": clip(input), "output": clip(output)})

    def to_list(self) -> list[dict]:
        return [dict(s) for s in self._steps]


class _Noop:
    def update(self, **kwargs) -> None:
        pass


SAFE_KEY = re.compile(r"[A-Za-z0-9_.:-]{1,40}")  # ids and field names; a key with spaces may be query or document text


def mask_private(*, data: Any, **kwargs) -> Any:
    """Langfuse mask: in private mode (KB_PRIVATE) every text value becomes its length, so prompts, documents and
    answers never reach the tracing service; structure, numbers, token counts and timings stay. Anything that is not
    a number, bool, None, dict or list is redacted, so an unexpected type cannot carry text out."""
    from kb.model_api import private_mode
    if not private_mode() or data is None or isinstance(data, (bool, int, float)):
        return data
    if isinstance(data, str):
        return f"[redacted: {len(data)} chars]"
    if isinstance(data, dict):
        return {(k if isinstance(k, str) and SAFE_KEY.fullmatch(k) else f"[redacted key {i}]"): mask_private(data=v)
                for i, (k, v) in enumerate(data.items())}
    if isinstance(data, (list, tuple)):
        return [mask_private(data=v) for v in data]
    return f"[redacted: {type(data).__name__}]"


def error_text(exc: BaseException) -> str:
    """What a trace may say about an error: its message, or only its type in private mode (a message can quote data)."""
    from kb.model_api import private_mode
    return type(exc).__name__ if private_mode() else str(exc)[:300]


_client = None
_client_checked = False


def _lf():
    """Langfuse client if keys are configured, else None. Created once per process."""
    global _client, _client_checked
    if not _client_checked:
        _client_checked = True
        if os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get("LANGFUSE_SECRET_KEY"):
            try:
                from langfuse import Langfuse
                _client = Langfuse(mask=mask_private)
            except Exception as e:  # observability must never break serving
                log.warning("langfuse disabled: %s", e)
    return _client


@contextmanager
def _observation(as_type: str, name: str, **kwargs):
    client = _lf()
    if client is None:
        yield _Noop()
        return
    try:
        cm = client.start_as_current_observation(name=name, as_type=as_type, **kwargs)
        obs = cm.__enter__()
    except Exception as e:
        log.warning("langfuse observation failed: %s", e)
        yield _Noop()
        return
    safe = _Safe(obs)
    try:
        yield safe
    finally:
        try:
            cm.__exit__(None, None, None)
        except Exception as e:
            log.warning("langfuse close failed: %s", e)


class _Safe:
    def __init__(self, obs):
        self._obs = obs

    def update(self, **kwargs) -> None:
        try:
            self._obs.update(**kwargs)
        except Exception as e:
            log.warning("langfuse update failed: %s", e)


@contextmanager
def lf_span(name: str, input: Any = None, metadata: dict | None = None):
    with _observation("span", name, input=input, metadata=metadata) as obs:
        yield obs


@contextmanager
def lf_generation(name: str, model: str, input: Any):
    with _observation("generation", name, model=model, input=input) as obs:
        yield obs


def lf_trace_id() -> str | None:
    client = _lf()
    if client is None:
        return None
    try:
        return client.get_current_trace_id()
    except Exception:
        return None


def lf_flush() -> None:
    client = _lf()
    if client is not None:
        try:
            client.flush()
        except Exception as e:
            log.warning("langfuse flush failed: %s", e)
