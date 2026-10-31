"""One tiny free call to each configured provider, so a bad key or model shows up before a real query.

    python scripts/check_llm.py
"""
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from kb.config import get_settings  # noqa: E402
from kb.llm import ChainLLM, LLMError  # noqa: E402


def main() -> None:
    s = get_settings()
    if not s.providers:
        sys.exit("No provider key found. Add at least one to .env (see .env.example).")
    failed = 0
    for provider in s.providers:
        llm = ChainLLM(replace(s, providers=(provider,), llm_cache=False, llm_max_retries=1))  # a cached reply would prove nothing
        try:
            out = llm.complete_json("Respond only with JSON.", 'Return {"ok": true}', name="check", max_tokens=400)
            print(f"ok    {provider.label}  {json.dumps(out)}  tokens={llm.usage.input_tokens}+{llm.usage.output_tokens}")
        except LLMError as exc:
            failed += 1
            print(f"FAIL  {provider.label}  {exc}")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
