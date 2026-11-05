# SiftBase project guide

Start here. This covers what the project is, how to run it, how the code is organised, what is done and what is left.

Last updated 2026-11-05.

## What it is

A knowledge base for AI agents that goes beyond top-k RAG, for documents of any kind. A query is planned, routed to the documents it needs, searched page by page, checked against exact source text, and answered with document and page citations.

The API has exactly two routes:

- `POST /index`: multipart `file` (ZIP of PDF, Word, PowerPoint, Excel, image or text files) and `collection_name`. Blocks until the collection is live.
- `POST /query`: JSON `{"collection_name": "...", "query": "..."}`. Returns the answer, source chunks with physical pages, a 10-step trace, coverage, usage (including which models answered) and cost.

## Current status

| Area | Status |
|---|---|
| Ingestion, indexing, collections | Working. 35 PDFs / 6,970 pages took 18.1 min on a 16-thread PC |
| Query pipeline | Working on free models only |
| Model providers | Free-tier chain; private mode keeps documents with Cloudflare and Groq |
| Access | API keys, per-key and shared daily rate limits, `AT_CAPACITY` when the free answer model is used up |
| Tests | 408 passed, 1 skipped, 7 slow deselected; run on every push by GitHub Actions |
| Accuracy target (80% answer precision and recall on the 8-question set) | **Not met** (below) |
| Latency target (30 s) | **Not met.** Median 40-44 s in the two latest runs |

## Measured results

All runs use the same 8 development questions (B30, C17, C18, C26, C31, C32, A20, A21), all 35 training documents and the unmodified official evaluator. Every score comes from the same judge, Groq `openai/gpt-oss-120b`. Answers come almost entirely from Cloudflare's `@cf/qwen/qwen3-30b-a3b-fp8`.

| Run | Code | Answer P / R | Context P / R | Median / slowest query |
|---|---|---|---|---|
| Baseline, 2026-10-31 | before the recall work | 53% / 22% | 50% / 53% | 31 s / 163 s |
| `run_fix4`, 2026-11-02 | `310f4f6` | 72.5% / 32.2% | 52.7% / 64.1% | 44 s / 183 s |
| `run_wait8b`, 2026-11-04 | `0cf3941` | 46.2% / 26.5% | 54.3% / 62.9% | 40 s / 76 s |

**One run is not a measurement.** `run_fix4` and `run_wait8b` used the same retrieval and writing code with no provider failures, yet answer precision differs by 26 points. The planner, the source check and the writer all give different outputs from run to run, and the judge splits the same benchmark answer into a different number of points each time. Compare the mean of at least 2-3 runs per version, and say how many runs a number comes from.

**Context scores cover a subset.** Since `452ede5` the runner submits the passages cited in the answer first and stops at what one judge call can score, so `run_wait8b`'s context scores cover the first 44-54 of 45-58 passages on four questions. Each row records `submitted_chunks` and `total_chunks`.

**What limits recall.** Most benchmark points that answers miss are analysis across several passages, not facts any single passage states. A larger writer model (Cloudflare `gpt-oss-120b`) wrote more on the same evidence but matched no more points.

## Run it

Python 3.10 to 3.12 (CI and Render use 3.10). RapidOCR needs a version below 3.13.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

On Windows use `.venv\Scripts\python`. `requirements.lock.py312-macos.txt` applies to macOS only.

Add a Cloudflare or Groq key to `.env` (see the README for names), then test them:

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

Free tiers only. `kb/model_api.py` holds the list, and every provider takes the same OpenAI-style request.

| Use | Default order | With `KB_PRIVATE` on (the default) |
|---|---|---|
| Planning, verification | Cloudflare qwen3-30b, Groq gpt-oss-20b, OpenRouter, Mistral, Gemini | Cloudflare, then Groq |
| Writing and claim checks | Cloudflare qwen3-30b, Groq qwen3.8-27b, OpenRouter, Mistral, Gemini, Groq gpt-oss-20b | Cloudflare, then Groq |
| Judge (scoring only) | Groq gpt-oss-120b, never switched | same |

In practice only Cloudflare's qwen3-30b can write answers: writer prompts are 20k-50k tokens, Groq allows 7,500 tokens per call, and the other free fallbacks failed on writer and verification calls when tried.

`ChainLLM` in `kb/llm.py` tries the providers in order for each call:

- **Moves on after:** a rate limit, server error, timeout, bad key, rejected request or invalid reply.
- **Skips for a while:** a rate-limited provider until its `Retry-After` (or 60 s), one with server errors or timeouts for 30 s, one with a bad key for an hour, and Cloudflare for an hour after it reports its free allocation used up.
- **Waits instead of falling back:** a writer waits out a short pause another call put on a better provider, if the pause ends within half its remaining time.
- **Splits instead of falling back:** a writer or verification reply cut off at its output limit stops the chain, and the caller splits the job in half.
- **Records:** each answer's provider and model in `usage.models`, and each step's in the run's `attempts.json`.

**Free limits (measured):** Cloudflare Workers AI gives 10,000 neurons per rolling 24 hours, and a full 8-question run uses about 2,600. The judge has 200,000 tokens a day and 7,500 per call, and a full scoring uses about 40,000.

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

`kb/query/pipeline.py` runs these steps, and `kb/query/runtime.py` enforces the deadline and the token, call and cost budgets. The planner gets a 20 s deadline, and the first provider gets 60% of it so a slow one leaves time for the next.

**Routing rule:** a document with a different year is ruled out only when another version of the same document has the requested year, and that year was read from the document's own text. Otherwise it stays, because a year in a question can name events inside a source. Other documents are searched only when routing couldn't settle on a source.

**Verification rule:** 8 batches run first, then 4 at a time, up to 16. Another wave runs only if the last one kept something and either a requested topic has no evidence, or the wave found a new page with a keep rate of at least 30%.

## Code map

| Path | Purpose |
|---|---|
| `kb/api.py`, `kb/routes/` | FastAPI app and the two routes |
| `kb/access.py` | API keys and rate limits for every route |
| `kb/config.py` | Environment settings. `kb/query/settings.py` adds query defaults, and shared values override them |
| `kb/model_api.py`, `kb/llm.py` | Provider list, private mode, wire format, fallback chain, spend ledger and response cache |
| `kb/ingest/` | ZIP to collection: parse, OCR, segment, metadata cards, navigation |
| `kb/store.py`, `kb/registry.py`, `kb/remote.py` | SQLite FTS5 and vectors, atomic generations, optional MongoDB Atlas copy |
| `kb/embed.py` | BGE-small embeddings and MiniLM reranker on CPU |
| `kb/tracing.py`, `kb/query/observability.py` | Response trace and Langfuse, with text redacted in private mode |
| `kb/query/` | Query pipeline |
| `evaluation/`, `scripts/` | Benchmark runner, official evaluator loader, indexing, serving and smoke-test tools |
| `tests/` | Offline tests. Slow tests download real models |
| `.github/workflows/tests.yml` | Runs the offline tests on every push and pull request |

Design notes: [METADATA_RETRIEVAL.md](METADATA_RETRIEVAL.md) covers document navigation, and [TASK_WORKSHEET.md](TASK_WORKSHEET.md) covers the current writer.

## Known risks

- **Capacity:** the free Cloudflare allowance covers about 30 answered queries a day. After that `/query` answers `AT_CAPACITY` until it frees up.
- **Run-to-run variance:** single runs differ by up to 26 points of answer precision, so a change is only measured by the mean of several runs.
- **Limits reset on restart:** rate-limit counts live in memory, so a restart (Render free sleeps after 15 idle minutes) resets them. Cloudflare's own cap still stops runaway use.
- **Atlas holds document text:** with `MONGODB_URI` set, the full index, chunk text included, is stored in MongoDB Atlas. Private mode does not cover it.
- **Old indexes:** collections built before source-confirmed years have their year checks off until they are re-indexed.
- **Langfuse cost:** each model call may be recorded twice (`kb/llm.py` and the query tracing both log usage). Not confirmed.
- **Licence:** PyMuPDF is AGPL or paid commercial.
- **Test coverage:** the default `QuerySettings()` writer is `extractive` while the serving default is `synthesis`, so many tests cover a different mode from production.

## Next steps

1. **Measure the current code properly:** run the 8 questions 2-3 times and report the mean and spread.
2. **Fix the weakest cases:** C32 keeps none of the ~64 passages it checks in every run, and in one run the claim check rejected every statement on C31 and C32.
3. **Raise recall** with answers that combine facts across passages, measured on questions not used for tuning.
4. **Write `DESIGN.md` and build the frontend,** then add CORS for its origin.
5. **Keep rate-limit counts in Atlas** so a restart does not reset them.
6. **Remove unused code:** duplicate types in `kb/models.py`, `write_answer`, `StepTrace`, `kb/query/demo_app.py`. The ledger writer (`kb/query/ledger.py`) is optional and measured worse.
