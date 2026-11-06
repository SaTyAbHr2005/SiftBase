import AskConsole from "@/components/AskConsole.tsx";
import CitedAnswer from "@/components/CitedAnswer.tsx";
import StreamStage from "@/components/StreamStage.tsx";
import SmoothScroll from "@/components/SmoothScroll.tsx";
import { Count, CoverForm, DepthGauge } from "@/components/River.tsx";
import { CORPUS, RECORDED, RUNS } from "@/lib/content.ts";
import { plainLimit } from "@/lib/answer.ts";

const REPO = "https://github.com/SaTyAbHr2005/SiftBase";
const PAGES = CORPUS.documents.reduce((t, d) => t + d.pages, 0).toLocaleString("en-US");
const STACK = [
  "FastAPI on Render", "MongoDB Atlas", "SQLite FTS5", "BGE-small vectors", "MiniLM reranker",
  "Cloudflare Workers AI", "Groq", "Langfuse traces", "Next.js on Vercel", "WebGL2", "GSAP", "Lenis",
];

function Waterline() {
  return (
    <div className="waterline" aria-hidden="true">
      <svg viewBox="0 0 2400 24" preserveAspectRatio="none">
        <path d="M0 12 Q150 2 300 12 T600 12 T900 12 T1200 12 T1500 12 T1800 12 T2100 12 T2400 12" />
      </svg>
    </div>
  );
}

export default function Home() {
  return (
    <>
      <SmoothScroll />
      <a className="skip" href="#ask">Skip to the question box</a>
      <header className="bar">
        <a className="wordmark" href="#cover">
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M2 6c3 0 3 3 6 3s3-3 6-3 3 3 4 3M2 12c3 0 3 3 6 3s3-3 6-3 3 3 4 3" /><circle cx="14.5" cy="12.6" r="1.7" /></svg>
          SiftBase
        </a>
        <nav aria-label="Site">
          <a className="link" href={REPO}>Source</a>
          <a className="nugget nugget--sm" href="#ask">Ask<span className="wide">a question</span></a>
        </nav>
      </header>
      <DepthGauge />

      <main>
        <section id="cover" className="cover" aria-labelledby="cover-h">
          {/* eslint-disable-next-line @next/next/no-img-element -- pre-sized WebP from scripts/prepare_assets.py; next/image would add Vercel's metered optimiser */}
          <img className="cover-photo" src="/assets/stream/falls.webp" alt="" width={1376} height={768} fetchPriority="high" decoding="async" />
          <div className="copy">
            <h1 id="cover-h">
              <span className="line"><span>{PAGES} pages go in.</span></span>
              <span className="line"><span>Only the <em>gold</em> comes out.</span></span>
            </h1>
            <p className="lede">
              A knowledge base for AI agents. It checks every claim against the exact source text, washes away what it
              cannot prove, and cites the page that holds the rest.
            </p>
            <CoverForm />
          </div>
          <p className="scroll-cue" aria-hidden="true">Scroll to follow one question down the stream</p>
        </section>

        <StreamStage />

        <section id="specimen" className="section" aria-labelledby="specimen-h">
          <Waterline />
          <div className="wrap">
            <div className="head">
              <h2 id="specimen-h" className="h2">The gold, with the pages it came from.</h2>
              <p className="lede">
                The answer at the end of the stream, as the API returned it on {RECORDED.recorded_at}. Choose a gold
                citation to bring its source page up beside the claim.
              </p>
            </div>
            <CitedAnswer result={RECORDED} question={RECORDED.question} />
            <p className="run-meta">
              {RECORDED.status === "partial" ? "Partly answered" : "Answered"} in {(RECORDED.latency_ms! / 1000).toFixed(0)} s on
              free models · {RECORDED.chunks.length} passages returned · {RECORDED.coverage?.limitations?.length ?? 0} gaps reported
            </p>
            {!!RECORDED.coverage?.limitations?.length && (
              <div className="limits-note">
                <h3 className="label" id="limits-h">What this answer did not cover</h3>
                <ul className="limits" aria-labelledby="limits-h">
                  {RECORDED.coverage.limitations.map((l) => <li key={l}>{plainLimit(l)}</li>)}
                </ul>
              </div>
            )}
          </div>
        </section>

        <section id="measured" className="section" aria-labelledby="measured-h">
          <Waterline />
          <div className="wrap">
            <div className="head">
              <h2 id="measured-h" className="h2">The assay, misses included.</h2>
              <p className="lede">
                Five runs on the same 8 development questions, scored by the unmodified official evaluator with one judge
                model. Purity is answer precision: how much of the answer the judge accepts. Recall is how much of the
                expected answer it covers.
              </p>
            </div>
            <div className="assay stone">
              {RUNS.map((r, i) => (
                <div className="slip assay-slip" key={r.name} style={{ ["--fan" as string]: `${(i - (RUNS.length - 1) / 2) * 3}deg` }}>
                  <span className="slip-name">{r.name}</span>
                  <span className="slip-when">{r.date} · {r.code}</span>
                  {i === 1 && <span className="assay-stamp">Target 80% · not met</span>}
                  <div className="purity">
                    <span className="big"><Count value={r.ap} decimals={r.ap % 1 ? 1 : 0} /><small>%</small></span>
                    <span className="label">Purity</span>
                  </div>
                  <dl>
                    <dt>Recall</dt><dd>{r.ar}%</dd>
                    <dt>Context P / R</dt><dd>{r.cp} / {r.cr}</dd>
                    <dt>Median / slowest</dt><dd>{r.time}</dd>
                  </dl>
                </div>
              ))}
            </div>
            <div className="variance">
              <p>
                run_fix4 and run_wait8b used the same retrieval and writing code with no provider failures, and still
                landed 26 points apart on purity. One run is not a measurement: over the four runs on comparable code
                (run_fix4, run_wait8b, run_rep_b, run_rep_c) the mean is 53.6% purity and 23.2% recall.
              </p>
              <p className="muted">
                Most missed points are analysis across several passages, not a fact any single page states. Context scores
                cover the passages that fit in one judge call.
              </p>
            </div>
          </div>
        </section>

        <section id="ask" className="section" aria-labelledby="ask-h">
          <Waterline />
          <div className="wrap">
            <div className="head">
              <h2 id="ask-h" className="h2">Pan your own question.</h2>
              <p className="lede">
                The same {CORPUS.documents.length} documents: annual reports, banking regulation and quantitative finance
                papers. SiftBase takes any kind of document; this is the set it was evaluated on.
              </p>
            </div>
            <div className="console stone">
              <AskConsole />
            </div>
          </div>
        </section>
      </main>

      <footer id="source" className="riverbed" aria-labelledby="source-h">
        <div className="marquee" aria-hidden="true">
          <div>{[...STACK, ...STACK].map((s, i) => <span key={i}>{s}</span>)}</div>
        </div>
        <div className="wrap">
          <h2 id="source-h" className="h2">The source</h2>
          <div className="cols">
            <div>
              <h3>Code</h3>
              <ul>
                <li><a href={REPO}>GitHub repository</a></li>
                <li><a href={`${REPO}/blob/main/docs/PROJECT.md`}>Project guide and every measured run</a></li>
                <li><a href={`${REPO}/blob/main/docs/DEPLOY.md`}>How it is deployed</a></li>
              </ul>
            </div>
            <div>
              <h3>Stack</h3>
              <ul>
                <li>FastAPI on Render, index in MongoDB Atlas</li>
                <li>SQLite FTS5, BGE-small vectors, MiniLM reranker</li>
                <li>Cloudflare Workers AI and Groq, free tiers</li>
                <li>Langfuse traces; this site on Vercel</li>
              </ul>
            </div>
            <div>
              <h3>Checks</h3>
              <ul>
                <li>408 offline tests on every push</li>
                <li>Scores from the unmodified official evaluator</li>
                <li>Private mode sends document text only to Cloudflare and Groq</li>
              </ul>
            </div>
          </div>
          <p className="credit">
            Free tiers only: no paid model, host or service. The stream photographs were generated for this site with
            Google Stitch and brought to life in WebGL2 with depth maps from Depth Anything V2. Riverbed texture by{" "}
            <a href="https://polyhaven.com/a/ganges_river_pebbles">Poly Haven</a> (CC0).
          </p>
        </div>
      </footer>
    </>
  );
}
