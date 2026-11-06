# SiftBase site

The public page for SiftBase. One recorded question runs down a rainforest stream of ten pools, one pool per pipeline step, from the 35 indexed documents (6,970 pages) to the 10 pages its answer cites. The stream is three photographs brought to life in WebGL2. Below it are the recorded answer, the measured scores and a live question box. Next.js on Vercel. The design is in `../DESIGN.md`.

## Run it

```bash
npm install
npm run dev        # http://localhost:3000
npm test           # node --test: the proxy, the answer parser and the stream timeline
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
- `public/assets/stream/`: the three stream photographs (generated with Google Stitch), a depth map for each (Depth Anything V2 Small, run locally) and a water mask that says where water pours, ripples or holds gold. One Poly Haven texture (CC0) and a generated caustic tile sit in `public/assets/`. All of it is made by `python scripts/prepare_assets.py --photos DIR` from the repository root, and `public/assets/SOURCES.md` lists each file's source.

With reduced motion, without WebGL2, or on a device too slow for the scene, the stream shows the three still photographs with the ten steps under them and the same counts.
