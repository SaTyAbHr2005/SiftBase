# Deployment

The free setup indexes on your own PC, stores the index in MongoDB Atlas and serves `/query` from Render. [PROJECT.md](PROJECT.md) describes what the service does and how well it works.

## Measured on the dev PC (16 logical cores), 2026-10-24

| Quantity | Value |
|---|---|
| Full fresh ingest of the 6,970-page training corpus (classic parse, extractive page cards, no LLM) | 18.1 min (parse 14.0 min, embeddings 4.0 min). The layout parser took 31.6 min. |
| Re-index of unchanged files (content-hash cache) | seconds for parsing |
| Ingestion CPU work | about 75 CPU-minutes (parse + 110 OCR pages + embeddings) |
| Query-side RAM (FastAPI + embedder + cross-encoder + index vectors) | about 490 MB (about 390 MB with `KB_RERANKER=0`) |
| One generation of the training index | 155 MB raw (smaller gzipped in Atlas) |

| Host (free tier) | Limits | Consequence |
|---|---|---|
| Render | 512 MB RAM, 0.1 CPU, sleeps after 15 min idle (about 1 min to wake), ephemeral disk | Serves queries fine. Indexing a 7k-page ZIP would take hours at 0.1 CPU, so index on your PC. |
| Vercel | serverless, 300 s max per request, 2 GB RAM, 500 MB Python bundle | Can't run a multi-minute `/index`, and every cold start would download the models and the index again. Use it for a static UI only. |
| Atlas | one free cluster, about 512 MB storage | Holds the active generation of each collection, so about 3 collections the size of the training set fit. |
| Cloudflare Workers AI | 10,000 neurons per rolling 24 h | About 30 answered queries a day. After that `/query` answers `AT_CAPACITY`. |

## Steps

1. Put the keys in `.env` at the repo root, never in git:
   - `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` for the answer model, and `GROQ_API_KEY` for the fallback and the judge.
   - `MONGODB_URI` (see below).
   - `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_HOST`. `/query` returns 503 without them unless `KB_REQUIRE_LANGFUSE=0`.
2. Index on your PC, where the heavy CPU work belongs. With `MONGODB_URI` set, the result is uploaded to Atlas:
   ```bash
   python scripts/index_local.py --src /path/to/documents --collection demo
   ```
   To push an existing local index without re-indexing (no model calls):
   ```bash
   python scripts/push_collection.py --collection demo
   ```
3. Make one API key for each person or app that will call the service:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```
4. Deploy on Render from `render.yaml` (Render dashboard, New, Blueprint, this repo). The dashboard then asks for the secret values: `KB_API_KEYS` (comma-separated), the Cloudflare and Groq keys, `MONGODB_URI` and the Langfuse keys.
   - Without `KB_API_KEYS`, every request gets 503 `AUTH_NOT_CONFIGURED`, so the service never runs open by accident.
   - The build bakes the CPU models into `./models` (`scripts/prefetch_models.py`).
   - The service starts with `KB_RERANKER=0` and `KB_PARSE_WORKERS=1` to fit in 512 MB.
5. Call it with a key:
   ```bash
   curl -X POST https://YOUR-SERVICE.onrender.com/query -H "X-API-Key: YOUR_KEY" -H "Content-Type: application/json" -d '{"collection_name":"demo","query":"What does the report say about capital?"}'
   ```
6. Expect a slow first query after a cold start. Render wakes (about 1 min), downloads the active generation from Atlas into `/tmp/kb-data`, then answers. Later queries use the local copy until the instance sleeps again.

The README covers rate limits and private mode under "Access and limits" and "Private documents".

## MongoDB Atlas setup

1. Create a free cluster, then a database user.
2. Under Network Access, allow `0.0.0.0/0`, because Render's outbound IPs are not fixed.
3. Copy the `mongodb+srv://...` connection string into `MONGODB_URI`. The database name defaults to `knowledge_base` (`MONGODB_DB`).

The GridFS bucket `kb_files` holds `<collection>/<generation>/<file>.gz`, and the `collections` collection holds one pointer document per collection. The pointer switches only after every file has uploaded, so a failed upload never activates a partial index. The stored files include the chunk text, so private documents in Atlas are only as private as the cluster.

## Checking a deployment

`scripts/smoke_http.py` indexes a small ZIP and runs one query. It checks the answer, that every chunk has a document and page, the 4-key trace steps, the citations and the Langfuse trace id, and that `/health`, `/docs` and `/openapi.json` are not exposed.

```bash
SIFTBASE_API_KEY=YOUR_KEY python scripts/smoke_http.py --url http://SERVER:8000 --zip one_doc.zip --collection smoke --query "Which rating agency rates the company?"
```

It reads the key from `SIFTBASE_API_KEY` (or `--api-key`), which keeps it out of your shell history.

## Vercel (optional)

Vercel can host a static page that calls the Render API's `/query` and shows the answer, the cited chunks and the trace. Don't host the Python API itself there, because of the 300 s limit and the cold-start downloads. A browser page can't keep an API key secret, so the page needs a small server-side proxy or per-user sign-in, and the API needs CORS for the page's origin.
