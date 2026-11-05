import AskConsole from "@/components/AskConsole.tsx";
import CitedAnswer from "@/components/CitedAnswer.tsx";
import PanStage from "@/components/PanStage.tsx";
import SmoothScroll from "@/components/SmoothScroll.tsx";
import { Count, CoverForm, DepthGauge } from "@/components/River.tsx";
import { CORPUS, RECORDED, RUNS } from "@/lib/content.ts";
import { plainLimit } from "@/lib/answer.ts";

const REPO = "https://github.com/SaTyAbHr2005/SiftBase";
const PAGES = CORPUS.documents.reduce((t, d) => t + d.pages, 0).toLocaleString("en-US");
const STACK = [
  "FastAPI on Render", "MongoDB Atlas", "SQLite FTS5", "BGE-small vectors", "MiniLM reranker",
  "Cloudflare Workers AI", "Groq", "Langfuse traces", "Next.js on Vercel", "Three.js", "GSAP", "Lenis",
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
          <svg viewBox="0 0 20 20" aria-hidden="true"><path d="M3 8c0-1 1-2 3-2h8c2 0 3 1 3 2l-2 6c-.4 1.2-1.4 2-2.7 2H7.7C6.4 16 5.4 15.2 5 14z" /><circle cx="12.5" cy="10.5" r="1.6" /></svg>
          SiftBase
        </a>
        <nav aria-label="Site">
          <a className="quartz-link" href={REPO}>Source</a>
          <a className="nugget nugget--sm" href="#ask">Ask<span className="wide">a question</span></a>
        </nav>
      </header>
      <DepthGauge />

      <main>
        <section id="cover" className="cover" aria-labelledby="cover-h">
          <div className="poster" aria-hidden="true" />
          <div className="copy still">
            <h1 id="cover-h">
              <span className="line"><span>Pan {PAGES} pages.</span></span>
              <span className="line"><span>Keep the <em>gold</em>.</span></span>
            </h1>
            <p className="lede">
              A knowledge base for AI agents. It checks every claim against the exact source text, drops what it
              cannot prove, and cites the page that holds the rest.
            </p>
            <CoverForm />
          </div>
        </section>

        <PanStage corpus={CORPUS} run={RECORDED} />

        <section id="specimen" className="section" aria-labelledby="specimen-h">
          <Waterline />
          <div className="wrap">
            <div className="head">
              <h2 id="specimen-h" className="h2">The gold, with the pages it came from.</h2>
              <p className="lede">
                The recorded answer from the pan above, as the API returned it on {RECORDED.recorded_at}. Choose a gold
                flake to bring its source page up beside the claim.
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
                Four runs on the same 8 development questions, scored by the unmodified official evaluator with one judge
                model. Purity is answer precision: how much of the answer the judge accepts. Recall is how much of the
                expected answer it covers.
              </p>
            </div>
            <div className="assay stone stone--c">
              {RUNS.map((r, i) => (
                <div className="slip assay-slip" key={r.name} style={{ ["--fan" as string]: `${(i - (RUNS.length - 1) / 2) * 4}deg` }}>
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
                landed 26 points apart on purity. One run is not a measurement: over the three runs on comparable code
                (run_fix4, run_wait8b, run_rep_b) the mean is 55.6% purity and 27.1% recall.
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
            <div className="console stone stone--a">
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
            Free tiers only: no paid model, host or service. River light, riverbed and pan steel scanned by{" "}
            <a href="https://polyhaven.com">Poly Haven</a> (CC0).
          </p>
        </div>
      </footer>
    </>
  );
}
