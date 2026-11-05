"use client";

// The pinned pan: a tall track that scroll scrubs through the pour and the ten steps. The
// caption and odometer stay pinned in a still pool while the WebGL scene, fixed behind the
// page, reads the progress from `stage`. Without the scene (reduced motion, no WebGL, too
// slow) the same beats render as a column of river stones; see `.has-scene` in globals.css.
import dynamic from "next/dynamic";
import { Component, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { ScrambleTextPlugin } from "gsap/ScrambleTextPlugin";
import { useGSAP } from "@gsap/react";
import { BEATS, beatAt, type Corpus, type RunPages } from "@/lib/pan.ts";
import { BEAT_TEXT } from "@/lib/content.ts";
import { NO_SCENE, stage } from "@/lib/stage.ts";

gsap.registerPlugin(ScrollTrigger, ScrambleTextPlugin, useGSAP);

const PanScene = dynamic(() => import("./PanScene.tsx"), { ssr: false });

type Props = { corpus: Corpus; run: { pages: RunPages } };

// A scene that throws (a missing asset, a context R3F cannot create) hands over to the flat steps.
class SceneBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { window.dispatchEvent(new Event(NO_SCENE)); }
  render() { return this.state.failed ? null : this.props.children; }
}

export default function PanStage({ corpus, run }: Props) {
  const [scene, setScene] = useState(false);
  const [ready, setReady] = useState(false);
  const [active, setActive] = useState(true);
  const [beat, setBeat] = useState(0);
  const [hoverDoc, setHoverDoc] = useState(-1);
  const tag = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLDivElement>(null);
  const caption = useRef<HTMLDivElement>(null);
  const title = useRef<HTMLSpanElement>(null);

  // The inline script in layout.tsx sets .has-scene before paint; load the scene once idle.
  useEffect(() => {
    if (!document.documentElement.classList.contains("has-scene")) return;
    const off = () => {
      document.documentElement.classList.remove("has-scene");
      setScene(false);
      setReady(false);
      ScrollTrigger.refresh();
    };
    window.addEventListener(NO_SCENE, off);
    // A scene still not drawn after 10 s of the tab being visible (a hung asset load) counts as one
    // that cannot run. Time in a background tab does not count: browsers pause rendering there.
    let waited = 0;
    const check = () => {
      if (document.querySelector(".scene.is-ready")) return;
      if (!document.hidden) waited += 1000;
      if (waited >= 10000) off(); else late = setTimeout(check, 1000);
    };
    let late = setTimeout(check, 1000);
    const go = () => setScene(true);
    const id = "requestIdleCallback" in window ? requestIdleCallback(go, { timeout: 1500 }) : setTimeout(go, 300);
    return () => {
      window.removeEventListener(NO_SCENE, off);
      clearTimeout(late);
      if ("cancelIdleCallback" in window) cancelIdleCallback(id as number); else clearTimeout(id);
    };
  }, []);

  useGSAP(() => {
    if (!scene) return;
    // The still pool follows whichever text sits over the water: the cover's, then the caption.
    const pool = () => {
      const el = stage.cover < 1 && stage.p === 0 ? document.querySelector(".cover .copy") : caption.current;
      const r = el?.getBoundingClientRect();
      if (r) stage.pool = [r.x, r.y, r.width, r.height];
    };
    ScrollTrigger.create({ trigger: "#cover", start: "top top", end: "bottom top", onUpdate: (s) => { stage.cover = s.progress; pool(); } });
    ScrollTrigger.create({
      trigger: track.current, start: "top top", end: "bottom bottom",
      onUpdate: (s) => { stage.p = s.progress; setBeat(beatAt(s.progress)); pool(); },
    });
    // Past the pan the water stays, dimmed to 20%, and stops rendering.
    ScrollTrigger.create({
      trigger: track.current, start: "bottom bottom", end: "bottom 20%",
      // It also sinks a third of the screen, so the dimmed flakes sit below the section headings.
      onUpdate: (s) => {
        stage.dim = s.progress;
        if (canvas.current) Object.assign(canvas.current.style, { opacity: String(1 - 0.8 * s.progress), transform: `translateY(${s.progress * 34}vh)` });
      },
      onLeave: () => setActive(false), onEnterBack: () => setActive(true),
    });
    pool();
  }, { dependencies: [scene] });

  useGSAP(() => {
    if (!scene || !title.current) return;
    gsap.to(title.current, { duration: 0.6, ease: "none", scrambleText: { text: BEAT_TEXT[beat].title, chars: "upperCase", speed: 0.6 } });
  }, { dependencies: [beat, scene] });

  const onReady = useCallback(() => setReady(true), []);
  // The tag follows the cursor by transform; React re-renders only when the document changes.
  const onHover = useCallback((doc: number | null, x: number, y: number) => {
    setHoverDoc(doc ?? -1);
    if (tag.current) tag.current.style.transform = `translate(${x + 14}px, ${y + 14}px)`;
  }, []);
  const b = BEAT_TEXT[beat];
  const doc = corpus.documents[hoverDoc];

  return (
    <section id="pan" className="pan" aria-labelledby="pan-h">
      <div className={`scene${ready ? " is-ready" : ""}`} aria-hidden="true">
        <div className="scene-dim" ref={canvas}>
          {scene && <SceneBoundary><PanScene corpus={corpus} run={run} onHover={onHover} onReady={onReady} active={active} /></SceneBoundary>}
        </div>
      </div>
      <div className="assay-tag" ref={tag} hidden={!doc} aria-hidden="true">
        {doc && <><b>{doc.name}</b> {doc.pages.toLocaleString("en-US")} pages</>}
      </div>

      <div className="track" ref={track}>
        <h2 id="pan-h" className="h2 pan-h">How one question was panned</h2>
        <ol className="beats">
          {BEAT_TEXT.map((t, i) => (
            <li key={t.id} id={t.id} className="beat stone" style={{ ["--from" as string]: BEATS[i].from, ["--to" as string]: BEATS[i].to }}>
              <span className="beat-n" aria-hidden="true">{t.n}</span>
              <h3>{t.title}{t.name && <code>{t.name}</code>}</h3>
              <p>{t.line}</p>
              <p className="beat-count"><b>{t.count.toLocaleString("en-US")}</b> {t.label}</p>
            </li>
          ))}
        </ol>
        <div className="pin" aria-hidden="true">
          <div className="caption still" ref={caption}>
            <span className="beat-n">{b.n}</span>
            <span className="beat-title" ref={title}>{BEAT_TEXT[0].title}</span>
            {b.name && <code>{b.name}</code>}
            <p key={beat} className="beat-line">{b.line}</p>
          </div>
          <div className="odo still">
            <Odometer value={b.count} />
            <span className="odo-label">{b.label}</span>
          </div>
        </div>
      </div>
    </section>
  );
}

// Digits roll like an odometer: each column is a strip of 0-9 moved by transform.
function Odometer({ value }: { value: number }) {
  const text = value.toLocaleString("en-US");
  return (
    <span className="odometer">
      {[...text].map((ch, i) =>
        /\d/.test(ch) ? (
          <span key={text.length - i} className="digit">
            <span className="sizer">{ch}</span>
            <span className="strip" style={{ transform: `translateY(${-Number(ch)}em)` }}>{"0123456789".split("").map((d) => <span key={d}>{d}</span>)}</span>
          </span>
        ) : <span key={`s${text.length - i}`}>{ch}</span>,
      )}
    </span>
  );
}
