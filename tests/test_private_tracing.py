"""Private mode keeps document text out of Langfuse traces."""
import kb.tracing as tracing
from kb.query.observability import LangfuseSink

DATA = {"system": "secret doc text", "usage": {"input": 12}, "items": ["a b", 3, True, None]}


def test_private_mode_replaces_every_text_value_with_its_length(monkeypatch):
    monkeypatch.delenv("KB_PRIVATE", raising=False)
    assert tracing.mask_private(data=DATA) == {"system": "[redacted: 15 chars]", "usage": {"input": 12},
                                               "items": ["[redacted: 3 chars]", 3, True, None]}
    assert tracing.mask_private(data="plain text") == "[redacted: 10 chars]"
    monkeypatch.setenv("KB_PRIVATE", "0")
    assert tracing.mask_private(data=DATA) == DATA


def test_text_in_keys_and_in_other_types_is_redacted_too(monkeypatch):
    from dataclasses import dataclass

    @dataclass
    class Note:
        text: str

    monkeypatch.delenv("KB_PRIVATE", raising=False)
    out = tracing.mask_private(data={"t1:revenue grew": 1, "E1": 2, "notes": {"s1"}, "note": Note("x"), "raw": b"y"})
    assert out == {"[redacted key 0]": 1, "E1": 2, "notes": "[redacted: set]", "note": "[redacted: Note]",
                   "raw": "[redacted: bytes]"}


def test_error_text_sent_to_langfuse_is_only_the_type_in_private_mode(monkeypatch):
    monkeypatch.delenv("KB_PRIVATE", raising=False)
    assert tracing.error_text(ValueError("cell 'Revenue 11,011' is not a number")) == "ValueError"
    monkeypatch.setenv("KB_PRIVATE", "0")
    assert tracing.error_text(ValueError("detail")) == "detail"


def test_the_query_sink_does_not_record_exception_text_in_private_mode(monkeypatch):
    monkeypatch.delenv("KB_PRIVATE", raising=False)
    exits, updates = [], []

    class Span:
        def update(self, **kwargs):
            updates.append(kwargs)

    class Manager:
        def __enter__(self):
            return Span()

        def __exit__(self, *args):
            exits.append(args)

    class Client:
        def start_as_current_observation(self, **kwargs):
            return Manager()

        def get_current_trace_id(self):
            return "t"

    sink = LangfuseSink(client=Client())
    try:
        with sink.span("stage"):
            raise ValueError("secret document text")
    except ValueError:
        pass
    assert exits == [(None, None, None)] and updates == [{"level": "ERROR", "status_message": "ValueError"}]


def test_both_langfuse_clients_are_built_with_the_mask(monkeypatch):
    masks = []

    class FakeLangfuse:
        def __init__(self, **kwargs):
            masks.append(kwargs.get("mask"))

    monkeypatch.setattr("langfuse.Langfuse", FakeLangfuse)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "p")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "s")
    monkeypatch.setattr(tracing, "_client", None)
    monkeypatch.setattr(tracing, "_client_checked", False)
    tracing._lf()
    LangfuseSink()
    assert masks == [tracing.mask_private, tracing.mask_private]
