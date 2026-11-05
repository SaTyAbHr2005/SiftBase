# SiftBase site

The public page for SiftBase: a WebGL pan that washes the 35 indexed documents (6,970 pages) down to the pages one recorded answer cites, then the recorded answer, the measured scores and a live question box. Next.js on Vercel. The design is in `../DESIGN.md`.

## Run it

```bash
npm install
npm run dev        # http://localhost:3000
npm test           # node --test: the proxy, the answer parser and the pan layout
npm run build && npx next start
```

## Live questions

`app/api/query/route.ts` forwards questions to the SiftBase API and keeps the key on the server. Set these in Vercel (or in `.env.local` for local runs):

| Variable | Meaning |
|---|---|
| `SIFTBASE_API_URL` | Base URL of the API, `https://` only (`http://localhost` is allowed) |
| `SIFTBASE_API_KEY` | The API key; never sent to the browser |
| `SIFTBASE_COLLECTION` | Collection to ask, default `train` |

Without them the console says the live demo is not connected and the rest of the page still works.

## Data and assets

- `data/corpus.json`: document names and page counts, exported from the local index.
- `data/recorded-run.json`: one recorded answer to a question written for the site, made with `python -m scripts.record_run` from the repository root. It keeps only public fields.
- `public/assets/`: Poly Haven scans (CC0) and a generated caustic tile, made by `python scripts/prepare_assets.py`. `public/assets/SOURCES.md` lists each source and resize.

With reduced motion, without WebGL2, or on a device too slow for the scene, the pan's ten steps render as a column of stones with the same counts.
