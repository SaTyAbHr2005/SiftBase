# SiftBase project guide

Start here. This covers what the project is, how to run it, how the code is organised, what is done and what is left.

Last reviewed at the 10-stage task-worksheet code (2026-10-31).

## What it is

A knowledge base for AI agents that goes beyond top-k RAG. A query is planned, routed to the documents it needs, searched page by page, checked against exact source text, and answered with document and page citations.

The API has exactly two routes:

- `POST /index`: multipart `file` (ZIP of PDFs) and `collection_name`. Blocks until the collection is live.
- `POST /query`: JSON `{"collection_name": "...", "query": "..."}`. Returns the answer, source chunks with physical pages, a 10-step trace, coverage, usage and cost.

## Current status

| Area | Status |
|---|---|
| Ingestion, indexing, collections | Working. 35 PDFs / 6,970 pages took 18.1 min on a 16-thread PC |
| Query pipeline | Code complete, but needs a model provider |
| Model provider | **None. OpenCode access has ended, so `/query` returns 503 until a new provider is added** |
| Offline tests | 277 passed, 2 skipped, 7 slow deselected |
| Accuracy target (0.95) | **Not met** |
| Latency target (30 s) | **Not met** on analytical queries (43 to 106 s measured) |

Without a provider, `/index` still works but builds weaker fallback document cards with no issuer or entities. Dry-run mode runs the whole flow with placeholder answers.

### Latest measured scores

Scored with the unmodified official evaluator, using Qwen3.8 Flash for answers and GLM 5.3 Flash as judge. These are small development runs, not a full benchmark.

| Case | Answer P / R | Context P / R | Query time |
|---|---|---|---|
| C18 | 34.78% / 82.76% | not recorded here | 75.97 s |
| C26 (best completed run) | 80.00% / 34.21% | 100.00% / 90.62% | 106.34 s |
| C32 (latest) | 75.00% / 50.00% | 0% / 0% | 43.32 s |

First-pass answer P / R on documents not used before tuning: C26 11.76% / 25%, A20 52.63% / 30.91%, A21 11.11% / 2.04%, C32 0% / 0%. Generalisation is still weak.

## Run it

Python 3.10 to 3.12. RapidOCR needs a version below 3.13.

```bash
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
.venv/bin/python -m pytest -q
```

On Windows use `.venv\Scripts\python`. `requirements.lock.py312-macos.txt` applies to macOS only.

Run with no model and no network:

```bash
KB_LLM_MODE=dryrun KB_REQUIRE_LANGFUSE=0 .venv/bin/python -m scripts.serve --env-file .env --host 127.0.0.1 --port 8000
```

`/query` returns 503 without Langfuse keys unless `KB_REQUIRE_LANGFUSE=0`. Deployment steps are in [DEPLOY.md](DEPLOY.md).

Not in this repo, and needed for benchmarks: the training PDFs, the benchmark file and `Evaluation.ipynb`, all under the ignored `Train/` folder. Never modify the evaluation notebook.

## Query pipeline

| # | Trace step | What it does | Main file |
|---|---|---|---|
| 1 | `query_planning` | LLM turns the question into aspects, tasks and candidate documents | `kb/query/plan.py` |
| 2 | `routing_guard` | Checks document identity and period | `kb/query/plan.py` |
| 3 | `candidate_pages` | Per-document BM25 and vector search with fair page quotas | `kb/query/candidates.py` |
| 4 | `page_survey` | Picks pages locally by default; `KB_PAGE_SELECTION=llm` uses the LLM | `kb/query/screen.py` |
| 5 | `element_retrieval` | Gathers paragraphs and tables from chosen pages | `kb/query/candidates.py` |
| 6 | `element_triage` | MiniLM cross-encoder orders candidates; scores never prove anything | `kb/query/triage.py` |
| 7 | `element_verification` | LLM checks source fragments, kept items need exact source spans | `kb/query/screen.py` |
| 8 | `answer_generation` | Writes claims linked to verified evidence and a task worksheet | `kb/query/answer.py`, `kb/query/worksheet.py` |
| 9 | `answer_verification` | LLM and arithmetic checks remove unsupported claims | `kb/query/answer.py` |
| 10 | `citation_render` | Adds `[file.pdf pN]` citations from source-owned data | `kb/query/answer.py` |

`kb/query/pipeline.py` runs these steps, and `kb/query/runtime.py` enforces the deadline and the token, call and cost budgets.

## Code map

| Path | Purpose |
|---|---|
| `kb/api.py`, `kb/routes/` | FastAPI app and the two routes |
| `kb/config.py` | Environment settings. `kb/query/settings.py` adds query defaults, and shared values override them |
| `kb/llm.py`, `kb/model_api.py`, `kb/opencode_auth.py` | Model calls, wire format, retries, spend ledger and response cache |
| `kb/ingest/` | ZIP to collection: parse, OCR, segment, metadata cards, navigation |
| `kb/store.py`, `kb/registry.py`, `kb/remote.py` | SQLite FTS5 and vectors, atomic generations, optional MongoDB Atlas copy |
| `kb/embed.py` | BGE-small embeddings and MiniLM reranker on CPU |
| `kb/tracing.py`, `kb/query/observability.py` | Response trace and Langfuse |
| `kb/query/` | Query pipeline |
| `evaluation/`, `scripts/` | Benchmark runner, official evaluator loader, indexing, serving and smoke-test tools |
| `tests/` | Offline tests. Slow tests download real models |

Design notes: [METADATA_RETRIEVAL.md](METADATA_RETRIEVAL.md) covers document navigation, and [TASK_WORKSHEET.md](TASK_WORKSHEET.md) covers the current writer.

## Known bugs

Confirmed during the code review, none fixed yet. Listed by priority.

1. **The routing guard's year and ID checks never fire.** `confirmed()` in `kb/query/plan.py` reads `metadata_provenance`, which real `DocCard` objects don't have. A 2025 question kept both FY2025 and FY2026 documents. "Latest" selection is affected too. Tests pass only because their fake card has the field.
2. **Deadline cut-offs are reported as provider failures.** With a healthy 6 s per call stub and the 30 s deadline, 7 of 31 verify calls were cut off and traced as a provider or schema failure, and `cost_usd` became unknown.
3. **Unrelated documents are always added.** `global_escape` is computed in `kb/query/plan.py` but `kb/query/pipeline.py` always calls `escape_pages`, which spends verification budget on the wrong documents.
4. **A stage starting past the deadline fails the whole query** with HTTP 504 and no partial answer.
5. **False limitation text.** "No evidence verified" can appear when the recovery pass kept evidence.
6. **Smaller:** `select_portfolio` passes aspect text to `narrow_factoid` where the query belongs, and `/index` accepts a collection name with a trailing newline (`match` with `$` instead of `fullmatch`).

Not confirmed: Langfuse may record each model call's cost twice (`kb/llm.py` and the query tracing both log usage).

Other risks: neither route has authentication, so don't expose it publicly without adding some. PyMuPDF is AGPL or paid commercial. The default `QuerySettings()` writer is `extractive` while the serving default is `synthesis`, so many tests cover a different mode from production.

## Next steps

1. **Add a model provider.** Change `kb/model_api.py` and the model lock in `kb/config.py` first (also env names and prices), simplify `kb/llm.py` auth and delete `kb/opencode_auth.py`. Then update `evaluation/official.py`'s judge transport, `scripts/`, `render.yaml`, `.env.example` and the affected tests (`tests/conftest.py`, `test_foundation.py`, `track_b/test_evaluation.py`, `track_b/test_judge_model.py`, `track_b/test_provider.py`).
2. **Add the provider to the response cache key,** and start a new `data/spend.jsonl`. The cache key would otherwise reuse old answers for the same model name, and past spend counts toward `KB_BUDGET_USD`.
3. **Fix bugs 1 to 4.**
4. **Re-measure scores.** Prompts and time limits were tuned for Qwen, so the numbers above won't carry over to a new model.
5. **Remove unused code:** duplicate types in `kb/models.py`, `OpenCodeJSONClient`, `write_answer`, `StepTrace`, `kb/query/demo_app.py`. The ledger writer (`kb/query/ledger.py`) is optional and measured worse.
