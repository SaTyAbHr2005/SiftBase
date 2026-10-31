# SiftBase project guide

Start here. This covers what the project is, how to run it, how the code is organised, what is done and what is left.

Last updated 2026-10-31.

## What it is

A knowledge base for AI agents that goes beyond top-k RAG, for documents of any kind. A query is planned, routed to the documents it needs, searched page by page, checked against exact source text, and answered with document and page citations.

The API has exactly two routes:

- `POST /index`: multipart `file` (ZIP of PDFs) and `collection_name`. Blocks until the collection is live.
- `POST /query`: JSON `{"collection_name": "...", "query": "..."}`. Returns the answer, source chunks with physical pages, a 10-step trace, coverage, usage (including which models answered) and cost.

## Current status

| Area | Status |
|---|---|
| Ingestion, indexing, collections | Working. 35 PDFs / 6,970 pages took 18.1 min on a 16-thread PC |
| Query pipeline | Working with fake providers. **Not yet run against a live free model** |
| Model providers | Free-tier fallback chain built. Needs your keys in `.env` |
| Offline tests | 308 passed, 1 skipped, 7 slow deselected |
| Accuracy target (0.95) | **Not met.** Needs re-measuring on free models |
| Latency target (30 s) | **Not met** on analytical queries in past runs (43 to 106 s) |

### Last measured scores

These came from the previous paid model (Qwen3.8 Flash, judged by GLM 5.3 Flash), before the changes in this version. They won't carry over to free models.

| Case | Answer P / R | Context P / R | Query time |
|---|---|---|---|
| C18 | 34.78% / 82.76% | not recorded here | 75.97 s |
| C26 (best completed run) | 80.00% / 34.21% | 100.00% / 90.62% | 106.34 s |
| C32 (latest) | 75.00% / 50.00% | 0% / 0% | 43.32 s |

First-pass answer P / R on documents not used before tuning: C26 11.76% / 25%, A20 52.63% / 30.91%, A21 11.11% / 2.04%, C32 0% / 0%. Generalisation is still weak.

### Model use per query

Across 12 fully measured past runs, the median query used 31.5 calls, about 98,000 tokens and 58 s.

Replaying those runs through the new verification rule, with no model calls, saved a median of 7 verification calls on runs with more than 8 batches. Every benchmark page those runs had reached was still reached, and 96% of passages kept on those pages stayed. This covers only 4 questions (B30, C17, C18, C31), so re-test it on a live model. Writers and claim checks now take twice as much per call, which should also reduce calls.

## Run it

Python 3.10 to 3.12. RapidOCR needs a version below 3.13.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

On Windows use `.venv\Scripts\python`. `requirements.lock.py312-macos.txt` applies to macOS only.

Add at least one provider key to `.env` (see the README for names), then test them:

```bash
python scripts/check_llm.py
```

Run with no model and no network:

```bash
KB_LLM_MODE=dryrun KB_REQUIRE_LANGFUSE=0 .venv/bin/python -m scripts.serve --env-file .env --host 127.0.0.1 --port 8000
```

`/query` returns 503 without Langfuse keys unless `KB_REQUIRE_LANGFUSE=0`. Deployment steps are in [DEPLOY.md](DEPLOY.md).

Not in this repo, and needed for benchmarks: the training PDFs, the benchmark file and `Evaluation.ipynb`, all under the ignored `Train/` folder. Never modify the evaluation notebook.

## Model providers

Free tiers only. `kb/model_api.py` holds the list, and every provider takes the same OpenAI-style request. The default order is Cloudflare, Groq (two models), OpenRouter, Mistral (two models), then Gemini, skipping any without a key.

`ChainLLM` in `kb/llm.py` tries them in order for each call:

- **Moves on after:** a rate limit, server error, timeout, bad key, rejected request or invalid reply.
- **Skips for a while:** a rate-limited provider until its `Retry-After` (or 60 s), one with server errors or timeouts for 30 s, and one with a bad key for an hour.
- **Skips without a request:** a provider whose per-minute limit is too small for the call.
- **Records:** each answer's provider and model in `usage.models`, and each step's in the run's `attempts.json`.

Free limits change often, so check them on each provider's own page. Mistral and Gemini free tiers can use your content for training, so remove them from `KB_LLM_PROVIDERS` for private documents.

## Query pipeline

| # | Trace step | What it does | Main file |
|---|---|---|---|
| 1 | `query_planning` | LLM turns the question into aspects, tasks and candidate documents | `kb/query/plan.py` |
| 2 | `routing_guard` | Checks document identity and version | `kb/query/plan.py` |
| 3 | `candidate_pages` | Per-document BM25 and vector search with fair page quotas | `kb/query/candidates.py` |
| 4 | `page_survey` | Picks pages locally by default; `KB_PAGE_SELECTION=llm` uses the LLM | `kb/query/screen.py` |
| 5 | `element_retrieval` | Gathers paragraphs and tables from chosen pages | `kb/query/candidates.py` |
| 6 | `element_triage` | MiniLM cross-encoder orders candidates; scores never prove anything | `kb/query/triage.py` |
| 7 | `element_verification` | LLM checks source fragments in waves and stops when a wave stops helping | `kb/query/screen.py` |
| 8 | `answer_generation` | Writes claims linked to verified evidence and a task worksheet | `kb/query/answer.py`, `kb/query/worksheet.py` |
| 9 | `answer_verification` | LLM and arithmetic checks remove unsupported claims | `kb/query/answer.py` |
| 10 | `citation_render` | Adds `[file.pdf pN]` citations from source-owned data | `kb/query/answer.py` |

`kb/query/pipeline.py` runs these steps, and `kb/query/runtime.py` enforces the deadline and the token, call and cost budgets.

**Routing rule:** a document with a different year is ruled out only when another version of the same document has the requested year, and that year was read from the document's own text. Otherwise it stays, because a year in a question can name events inside a source. Other documents are searched only when routing couldn't settle on a source.

**Verification rule:** 8 batches run first, then 4 at a time, up to 16. Another wave runs only if the last one kept something and either a requested topic has no evidence, or the wave found a new page with a keep rate of at least 30%.

## Code map

| Path | Purpose |
|---|---|
| `kb/api.py`, `kb/routes/` | FastAPI app and the two routes |
| `kb/config.py` | Environment settings. `kb/query/settings.py` adds query defaults, and shared values override them |
| `kb/model_api.py`, `kb/llm.py` | Provider list, wire format, fallback chain, spend ledger and response cache |
| `kb/ingest/` | ZIP to collection: parse, OCR, segment, metadata cards, navigation |
| `kb/store.py`, `kb/registry.py`, `kb/remote.py` | SQLite FTS5 and vectors, atomic generations, optional MongoDB Atlas copy |
| `kb/embed.py` | BGE-small embeddings and MiniLM reranker on CPU |
| `kb/tracing.py`, `kb/query/observability.py` | Response trace and Langfuse |
| `kb/query/` | Query pipeline |
| `evaluation/`, `scripts/` | Benchmark runner, official evaluator loader, indexing, serving and smoke-test tools |
| `tests/` | Offline tests. Slow tests download real models |

Design notes: [METADATA_RETRIEVAL.md](METADATA_RETRIEVAL.md) covers document navigation, and [TASK_WORKSHEET.md](TASK_WORKSHEET.md) covers the current writer.

## Known risks

- **Not tested live:** the chain's endpoints, default models and thinking settings come from provider docs. `scripts/check_llm.py` is the first check.
- **Mixed models:** one answer can use several models, so quality may vary between queries. The judge uses one model, and scores should only be compared between runs with the same `judge_models`.
- **Old indexes:** collections built before this version have no source-confirmed years, so their year checks stay off until they are re-indexed.
- **Langfuse cost:** each model call may be recorded twice (`kb/llm.py` and the query tracing both log usage). Not confirmed.
- **Authentication:** neither route has any, so don't expose it publicly without adding some.
- **Licence:** PyMuPDF is AGPL or paid commercial.
- **Test coverage:** the default `QuerySettings()` writer is `extractive` while the serving default is `synthesis`, so many tests cover a different mode from production.

## Next steps

1. **Add keys and run `scripts/check_llm.py`,** then fix any endpoint or model problems it shows.
2. **Re-index and measure a baseline** on a fixed set: B30, C17, C18, C26, C32 and the unseen-document cases. Free limits mean this takes several days of daily allowance.
3. **Test each call reduction against that baseline,** and drop any that lowers accuracy.
4. **Work on precision.** C18's low precision with many kept passages on the right pages points at the writing step.
5. **Add production basics:** authentication, rate limits and a Docker setup.
6. **Write `DESIGN.md` and build the frontend.**
7. **Remove unused code:** duplicate types in `kb/models.py`, `write_answer`, `StepTrace`, `kb/query/demo_app.py`. The ledger writer (`kb/query/ledger.py`) is optional and measured worse.
