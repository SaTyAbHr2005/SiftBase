# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

Next.js on Vercel, in a `web/` folder of this repo. One free Vercel project serves the page and a server-side proxy route that holds the API key and forwards queries to the SiftBase API on Render. The browser never sees the key.

## Users

- Recruiters and hiring managers looking at the project from a resume link. They have a few minutes and want to see what it does, how it works, and whether the numbers are honest.
- Engineers who want to try it: ask a question of the indexed documents and inspect the answer, the cited source chunks and the trace.

The page serves the first group first; the live console sits below the showcase for the second.

## Product Purpose

SiftBase is a knowledge base for AI agents. It indexes a ZIP of documents (PDF, Word, PowerPoint, Excel, images, text) and answers questions with citations to document and physical page. Success for the site: a visitor understands the mechanism within a minute and can run a real query and read the evidence behind the answer.

## Positioning

Instead of returning the top-k nearest chunks, SiftBase plans each query, routes it to the documents it needs, searches them page by page, checks every claim against the exact source text, drops unsupported claims, and says what it could not cover. Every query returns a ten-step trace. It runs entirely on free model tiers, and its evaluation numbers are published as measured, including the misses.

## Operating Context

- API: `POST /query` with `{"collection_name", "query"}` returns `answer`, `chunks` (document, page, text), a ten-step `trace` (each step has `step_name`, `description`, `input`, `output`), coverage, `usage` (including which models answered) and a Langfuse `trace_id`. `POST /index` is not exposed to the public site.
- Hosting: the API runs on Render's free tier; it sleeps after 15 idle minutes and takes about 1 minute to wake. Queries take a median of 40-44 s and up to about 3 minutes. The Vercel proxy must allow for cold start plus query time (Vercel's limit is 300 s per request).
- Capacity: about 25-30 answered queries a day across all visitors (Cloudflare free allowance; `KB_QUERIES_PER_DAY` 25). Over the limit the API answers 429 with `Retry-After`; when the answer model's allowance is used up it answers 503 `AT_CAPACITY` with `Retry-After`. Both are expected states, not crashes.
- Demo collection: the 35 training documents (the user chose this; publish only if the hackathon organisers allow it).

## Capabilities and Constraints

- Everything must be free: hosting, fonts, libraries, assets.
- The site must never show the organisers' benchmark questions or answers (the reason `docs/diagnostics` stays unpublished). Example questions on the site must be written fresh, not taken from the benchmark file.
- No assistant or AI-tool authorship mentions in the site, commits or repo.
- The API key lives only in the Vercel environment; the proxy forwards `/query` only.
- Works for any document type; copy must not present it as finance-only.

## Brand Commitments

- Name: SiftBase.
- Honesty about results: quote only measured scores, say how many runs a number comes from, and state that the 80% accuracy target is not met.

## Evidence on Hand

- Measured runs on the 8-question development set (docs/PROJECT.md): baseline answer P/R 53% / 22%; `run_fix4` 72.5% / 32.2%; `run_wait8b` 46.2% / 26.5%; run-to-run variance of 26 points of answer precision.
- Ingest: 35 PDFs / 6,970 pages in 18.1 min on a 16-thread PC.
- 408 offline tests, run in CI on every push.
- The ten trace steps and their descriptions (docs/PROJECT.md, "Query pipeline").
- No testimonials, users, customers or press exist. Do not invent any.

## Product Principles

1. Show the evidence, not a claim about it: every answer on the site links to its source chunk and page.
2. Honest numbers beat flattering ones: measured results with their variance, misses included.
3. Waiting and limits are part of the product: cold starts, long queries and daily capacity get designed states.
4. Document-agnostic: nothing on the site should suggest it only handles one domain.

## Accessibility & Inclusion

WCAG AA contrast, keyboard access, visible focus, and full content under `prefers-reduced-motion`.
