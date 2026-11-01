# SiftBase

A smart knowledge base for AI agents that goes beyond top-k RAG. The API exposes exactly POST /index and POST /query. The query path has ten stages, exact source fragments, coverage limitations, structured claim verification, and separate Langfuse observations.

No 0.95 accuracy result or production readiness is claimed.

**Read [the project guide](docs/PROJECT.md) first** for the code structure, current status, known bugs and next steps.

## Setup

Python 3.12 is verified locally; the pinned RapidOCR package requires Python below 3.13. Use an isolated environment and install the shared requirements:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Create `.env` and add a key for at least one free provider, plus your Langfuse credentials. Never commit `.env`.

| Provider | Add to `.env` | Default model |
|---|---|---|
| Cloudflare Workers AI | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | `@cf/qwen/qwen3-30b-a3b-fp8` |
| Groq | `GROQ_API_KEY` | `openai/gpt-oss-120b`, then `openai/gpt-oss-20b` |
| OpenRouter | `OPENROUTER_API_KEY` | `openrouter/free` |
| Mistral | `MISTRAL_API_KEY` | `ministral-14b-latest`, then `ministral-8b-latest` |
| Gemini | `GEMINI_API_KEY` | `gemini-3.5-flash` |

Each call tries the providers in that order and moves on after a rate limit, outage, bad key or invalid reply. Providers without a key are skipped. To change the order or models, set `KB_LLM_PROVIDERS`, for example `groq,gemini:gemini-3.5-flash-lite`. Mistral and Gemini free tiers can use your content for training, so leave them out for private documents. `python scripts/check_llm.py` makes one small call to each provider to test your keys.

```bash
.venv/bin/python -m scripts.serve --env-file .env --host 127.0.0.1 --port 8000
```

POST /index takes multipart `file` (a ZIP of PDF, DOCX, PPTX, XLSX, image, TXT or MD files) and `collection_name`. It blocks until the current ingestion implementation activates the collection. POST /query takes JSON `{"collection_name":"demo","query":"What does the report disclose about capital?"}`. It returns answer, actual source chunks with physical pages, ten four-field trace steps, coverage, resource usage and generation/config identity. Provider failures are HTTP errors; a semantic search miss is separately reported. No public health or documentation routes are added.

Local indexing through the existing CLI:

```bash
.venv/bin/python -m scripts.index_local --src /path/to/documents --collection demo
```

That CLI reads process environment variables; the server launcher loads `.env`. The source dataset remains external to the repository.

## Validation

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/test_embed.py::test_fast_models_load_and_score -m slow -q
.venv/bin/python -m pytest tests/track_b/test_retrieval.py::test_real_fastembed_adapter_counts_unseen_tail_and_scores_windows -m slow -q
.venv/bin/python -m scripts.check_langfuse --env-file .env
```

The default suite uses synthetic model replies, while PDF/SQLite/collection integration uses real adapters. Explicit slow model checks load pretrained weights and can download them. Langfuse connectivity is a separate explicit live check; it emits no fake inference usage.

### How model use stays low

Page selection now uses the initial source FTS/vector rankings and per-obligation lexical matches locally. `KB_PAGE_SELECTION=llm` opts back into paid page-card surveying. The ten trace stages remain present. Local navigation does not establish factual support; source evidence and final claims still undergo semantic verification.

BGE-small embeddings, MiniLM cross-encoder reranking, SQLite FTS5, extractive page cards, citation validation and arithmetic already run locally. No additional generative local model is required for these steps. Final-stage token reservations include both answer generation and claim verification, using the same model limits as actual calls.

The current serving environment defaults to the `synthesis` writer; bare `QuerySettings()` remains extractive, and `KB_ANALYTICAL_WRITER=ledger` is opt-in. The official judge uses one model only (`KB_JUDGE_PROVIDERS`, default `groq`), so scores stay comparable: it waits out rate limits, and a judge that stays down leaves a question unscored. Compare scores only between runs that report the same `judge_models`.
