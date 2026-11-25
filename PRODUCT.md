# Product

<!-- impeccable:product-schema 1 -->

## Platform

desktop (Electron on Windows first; macOS and Linux builds from the same code)

## Stack

An Electron app in a new `desktop/` folder. The renderer is Vite + React + TypeScript with Three.js (React Three Fiber), GSAP and Lenis. The main process starts the local SiftBase API (`python -m scripts.serve` on 127.0.0.1, a free port and a fresh API key per launch) and stops it on quit. Every font, library, model and asset ships inside the app: no CDN, no hosted font, no remote script. The old `web/` site is retired and nothing from it is reused.

## Users

- The owner, running SiftBase on their own PC against their own document collections.
- Engineers who clone the repo and want to index a folder of documents and question it without writing API calls.

## Product Purpose

SiftBase is a knowledge base for documents of any kind. It indexes a folder or ZIP (PDF, Word, PowerPoint, Excel, images, text) and answers questions with citations to the document and physical page. The app's job: index a collection, ask it questions, see which documents and pages were used and which were thrown out, and read the evidence behind every answer.

## Positioning

SiftBase does not return the top-k nearest chunks. It plans each question, routes it to the documents it needs, searches them page by page, checks the findings against the exact source text, drops claims it cannot support and says what it could not cover. The app makes that visible: a whole collection on the table, and only the pages that earned their place pulled out and used.

## Operating Context

- Local API: `POST /index` (multipart ZIP + `collection_name`, blocking until live) and `POST /query` (`collection_name`, `query`; returns `answer`, `chunks` with document and page, a ten-step `trace` with timings, `coverage.limitations`, `usage`). Both are blocking: the app gets no progress events until the response arrives.
- Runs on the user's PC. Indexing, search, embeddings and reranking are local. Planning, verification and answer writing call free cloud models (Cloudflare Workers AI, then Groq), so answers need internet. The app shows model status plainly; with no internet, the library and past answers still work.
- Queries take a median of about 35-40 s and up to about 3 minutes. Cloudflare's free allowance covers about 30 answered queries a day; over it the API answers 503 `AT_CAPACITY` with `Retry-After`. Both are designed states.
- Collections can be any size: one 3-page memo or hundreds of documents and tens of thousands of pages. Nothing in the UI may assume the 35-document training set.

## Capabilities and Constraints

- Free only: libraries, fonts, assets, services.
- Each user brings their own API keys, asked for on first run. Free providers are the default; a user who pays for a stronger model may add it for the writer and the judge. The app never needs a paid service to work.
- Fully offline packaging of the app itself (models are the only network use).
- Document-agnostic: no copy, example or icon that suggests one domain.
- No assistant or AI-tool authorship mentions in the app, commits or repo.
- Never show the hackathon benchmark questions or answers in the app or its screenshots.
- Do not edit `kb/query` from app work; app needs from the pipeline (for example stage progress events) are requested separately.

## Brand Commitments

- Name: SiftBase.
- Honest results: show what was not covered, which claims were withdrawn and how long each step took. Quote only measured numbers.

## Product Principles

1. Show the evidence: every answer line links to its document and page, and the page opens with the passage marked.
2. Relevance is visible: the user sees the whole collection, then watches it narrow to the few pages actually used.
3. Waiting and limits are part of the product: long queries, offline models and daily capacity each get a designed state.
4. Any collection: layouts, counts and 3D scale come from the collection's real numbers.

## Accessibility & Inclusion

WCAG AA contrast, full keyboard use, visible focus, screen-reader text for every 3D state (the scene is never the only place a fact lives), and full content under `prefers-reduced-motion`.
