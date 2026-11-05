# SiftBase

[![tests](https://github.com/SaTyAbHr2005/SiftBase/actions/workflows/tests.yml/badge.svg)](https://github.com/SaTyAbHr2005/SiftBase/actions/workflows/tests.yml)

SiftBase is a knowledge base for AI agents. Instead of handing back the top-k nearest chunks, it runs each question through ten stages, checks claims against the exact source text, reports what it could not cover, and logs every stage to Langfuse. The API has two routes: POST /index and POST /query.

It runs entirely on free model tiers. The accuracy target (80% answer precision and recall on the 8-question development set) is not met yet. [The project guide](docs/PROJECT.md) lists every measured run and how much runs vary.

Start with [the project guide](docs/PROJECT.md) for the code structure, current status, known bugs and next steps. Deployment is in [docs/DEPLOY.md](docs/DEPLOY.md).

## Setup

Use Python 3.10 to 3.12 (CI and Render use 3.10); the pinned RapidOCR package needs a version below 3.13. Install the requirements in an isolated environment:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Create `.env` with your provider keys and Langfuse credentials. Never commit `.env`.

| Provider | Add to `.env` | Used for |
|---|---|---|
| Cloudflare Workers AI | `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID` | `@cf/qwen/qwen3-30b-a3b-fp8` plans, checks sources and writes answers. Needed for usable answers. |
| Groq | `GROQ_API_KEY` | Fallback (`openai/gpt-oss-20b`, `qwen/qwen3.8-27b`) and the scoring judge (`openai/gpt-oss-120b`) |
| OpenRouter, Mistral, Gemini | `OPENROUTER_API_KEY`, `MISTRAL_API_KEY`, `GEMINI_API_KEY` | Extra fallbacks, used only with `KB_PRIVATE=0` (they may log or train on your documents) |

Each call tries the providers in order and moves to the next one after a rate limit, outage, bad key or invalid reply. Providers without a key are skipped. Set `KB_LLM_PROVIDERS` to change the order or models, for example `cloudflare,groq:openai/gpt-oss-20b`. `python scripts/check_llm.py` makes one small call to each provider to test your keys.

```bash
.venv/bin/python -m scripts.serve --env-file .env --host 127.0.0.1 --port 8000
```

POST /index takes a multipart `file` (a ZIP of PDF, DOCX, PPTX, XLSX, image, TXT or MD files) and a `collection_name`, and returns once the collection is live. POST /query takes JSON such as `{"collection_name":"demo","query":"What does the report disclose about capital?"}`. It returns the answer, the source chunks with their physical pages, a trace of ten steps with four fields each, coverage, resource usage, and the generation and config that answered. A provider failure comes back as an HTTP error, and a search that finds nothing is reported separately. The service has no health or documentation routes.

To index from the command line:

```bash
.venv/bin/python -m scripts.index_local --src /path/to/documents --collection demo
```

This CLI reads process environment variables, while the server launcher loads `.env`. The documents themselves stay outside the repository.

### Access and limits

| Variable | Default | What it does |
|---|---|---|
| `KB_API_KEYS` | none | Comma-separated keys. When set, every request needs one in `X-API-Key` or `Authorization: Bearer`. Make each with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `KB_AUTH` | none | On Render (`RENDER` set) a service with no keys answers 503. Set `off` only to run it open on purpose. |
| `KB_QUERY_PER_HOUR` | 20 | Queries per key per hour (per client address without keys). |
| `KB_QUERIES_PER_DAY` | 25 | Queries per 24 hours for all callers together, sized to the free model quota (about 30 answered queries a day). |
| `KB_INDEX_PER_DAY` | 5 | Uploads per key per 24 hours. |

A request over a limit gets HTTP 429 with `Retry-After`, and `0` turns a limit off. The counts live in the server's memory, so a restart resets them.

When the answer model (the first in the writer chain, Cloudflare by default) reports that its free daily allowance is used up, `/query` answers HTTP 503 `AT_CAPACITY` with `Retry-After` for the next hour. It does this straight away instead of running on fallbacks that cannot write answers. The query that first hits the limit still runs to the end. `/health` answers 404, or 401 when keys are set.

### Private documents

`KB_PRIVATE` is on by default (any value except `0`, `false` or `no`). It sends document text only to providers that keep none of it: Cloudflare Workers AI (no retention, no training) and Groq (no retention by default; turn off its abuse logging in Groq's Data Controls). OpenRouter's free models, Mistral and Gemini drop out of the default chains, and the service stops with an error if one of them is named in `KB_LLM_PROVIDERS`, `KB_WRITER_PROVIDERS`, `KB_VISION_PROVIDER` or `KB_JUDGE_PROVIDERS`. Langfuse traces keep their structure, counts and timings, but every text value is replaced by its length, such as `[redacted: 1234 chars]`. Set `KB_PRIVATE=0` only for public documents.

Private mode does not cover MongoDB: with `MONGODB_URI` set, the full index, chunk text included, is stored in your Atlas cluster.

## Validation

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m pytest tests/test_embed.py::test_fast_models_load_and_score -m slow -q
.venv/bin/python -m pytest tests/track_b/test_retrieval.py::test_real_fastembed_adapter_counts_unseen_tail_and_scores_windows -m slow -q
.venv/bin/python -m scripts.check_langfuse --env-file .env
```

The default suite uses synthetic model replies but real adapters for PDF, SQLite and collection integration. The slow checks load pretrained weights and may download them. The Langfuse check is a separate live test and records no fake inference usage.

### How model use stays low

Page selection runs locally by default, from the first full-text and vector rankings and the lexical matches for each requested item. `KB_PAGE_SELECTION=llm` switches back to page cards surveyed by the model. All ten trace stages still appear either way. Picking a page locally proves nothing about its facts: source evidence and final claims still go through model verification.

BGE-small embeddings, MiniLM cross-encoder reranking, SQLite FTS5, extractive page cards, citation checks and arithmetic all run locally, with no extra generative model. The token budget for the final stage covers both writing the answer and checking its claims, using the same model limits as the real calls.

The server defaults to the `synthesis` writer. A bare `QuerySettings()` is extractive, and `KB_ANALYTICAL_WRITER=ledger` is opt-in. Scoring uses one judge model only (`KB_JUDGE_PROVIDERS`, default `groq`) so scores stay comparable. The judge waits out rate limits, and if it stays down, the question is left unscored. Compare scores only between runs that report the same `judge_models`.
