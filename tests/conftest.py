import os

import pytest

# Tests never read the developer's real .env, never export to Langfuse and never see real keys.
os.environ["KB_ENV_FILE"] = os.path.join(os.path.dirname(__file__), "__no_env_file__")
for _key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST", "KB_BUDGET_USD",
             "CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID", "OPENROUTER_API_KEY", "MISTRAL_API_KEY", "GEMINI_API_KEY",
             "PRICE_INPUT_PER_M", "PRICE_OUTPUT_PER_M", "MONGODB_URI",
             "KB_LLM_MODE", "KB_PAGE_CARDS", "KB_RERANKER", "KB_DATA_DIR"):
    os.environ.pop(_key, None)
# One fake provider by default, so a test's stubbed requests.post is what answers.
os.environ["KB_LLM_PROVIDERS"] = "groq"
os.environ["GROQ_API_KEY"] = "test"
os.environ["KB_VISION_PAGES"] = "0"  # tests never send page images anywhere

from kb.config import get_settings  # noqa: E402


@pytest.fixture(autouse=True)
def clear_provider_cooldowns():
    from kb.llm import _cooldowns, _token_log
    _cooldowns.clear()
    _token_log.clear()
    yield
    _cooldowns.clear()
    _token_log.clear()


@pytest.fixture
def settings(tmp_path):
    return get_settings(data_dir=tmp_path / "data", llm_concurrency=4, price_input_per_m=0.15, price_output_per_m=0.47)
