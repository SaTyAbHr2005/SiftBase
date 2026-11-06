"use client";

// The pinned stream: a tall track that scroll scrubs through the falls and the ten steps. The
// caption, odometer and pebble rail stay pinned while the WebGL stream, fixed behind the page,
// reads the progress from `stage`. Without the scene (reduced motion, no WebGL2, too slow) the
// same beats render under three still photographs; see `.has-scene` in globals.css.
import dynamic from "next/dynamic";
import { Component, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { ScrambleTextPlugin } from "gsap/ScrambleTextPlugin";
import { useGSAP } from "@gsap/react";
import { BEATS, beatAt, sceneOfBeat, type Scene } from "@/lib/stream.ts";
import { BEAT_TEXT } from "@/lib/content.ts";
import { NO_SCENE, stage } from "@/lib/stage.ts";

gsap.registerPlugin(ScrollTrigger, ScrambleTextPlugin, useGSAP);

const StreamScene = dynamic(() => import("./StreamScene.tsx"), { ssr: false });

const REACHES: { scene: Scene; alt: string }[] = [
  { scene: "falls", alt: "A rainforest waterfall pours into a staircase of mossy rock pools." },
  { scene: "pool", alt: "One pool up close: brown silt washes over a stone lip while gold nuggets stay between the pebbles." },
  { scene: "bird", alt: "A kingfisher bursts out of the last pool with a gold nugget in its beak." },
];

// A scene that throws (a missing asset, a context it cannot create) hands over to the still photos.
class SceneBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { window.dispatchEvent(new Event(NO_SCENE)); }
  render() { return this.state.failed ? null : this.props.children; }
}

export default function StreamStage() {
  const [scene, setScene] = useState(false);
  const [ready, setReady] = useState(false);
  const [active, setActive] = useState(true);
  const [beat, setBeat] = useState(0);
  const track = useRef<HTMLDivElement>(null);
  const water = useRef<HTMLDivElement>(null);
  const title = useRef<HTMLSpanElement>(null);

  // The inline script in layout.tsx sets .has-scene before paint; load the scene once idle.
  useEffect(() => {
    if (!document.documentElement.classList.contains("has-scene")) return;
    const off = () => {
      // The track shrinks from 1100svh to normal flow: keep the reader on the beat they were reading.
      const box = track.current?.getBoundingClientRect();
      const inside = box && box.top <= 0 && box.bottom > innerHeight;
      const id = inside ? BEAT_TEXT[beatAt(stage.p)].id : null;
      document.documentElement.classList.remove("has-scene");
      setScene(false);
      setReady(false);
      requestAnimationFrame(() => {
        ScrollTrigger.refresh();
        if (id) document.getElementById(id)?.scrollIntoView({ block: "center" });
      });
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
    ScrollTrigger.create({ trigger: "#cover", start: "top top", end: "bottom top", onUpdate: (s) => { stage.cover = s.progress; } });
    ScrollTrigger.create({
      trigger: track.current, start: "top top", end: "bottom bottom",
      onUpdate: (s) => { stage.p = s.progress; setBeat(beatAt(s.progress)); },
    });
    // Past the stream the water fades out and stops rendering; the sections below sit on moss.
    ScrollTrigger.create({
      trigger: track.current, start: "bottom bottom", end: "bottom 35%",
      // Only once the fade has begun: an inline "1" written early would show the canvas before its first frame.
      onUpdate: (s) => { if (water.current) water.current.style.opacity = s.progress > 0 ? String(1 - s.progress) : ""; },
      onLeave: () => setActive(false), onEnterBack: () => setActive(true),
    });
  }, { dependencies: [scene] });

  useGSAP(() => {
    if (!scene || !title.current) return;
    gsap.to(title.current, { duration: 0.6, ease: "none", overwrite: true, scrambleText: { text: BEAT_TEXT[beat].title, chars: "lowerCase", speed: 0.6 } });
  }, { dependencies: [beat, scene] });

  const onReady = useCallback(() => setReady(true), []);
  const b = BEAT_TEXT[beat];

  return (
    <section id="stream" className="stream" aria-labelledby="stream-h">
      <div className={`scene${ready ? " is-ready" : ""}`} ref={water} aria-hidden="true">
        {scene && <SceneBoundary><StreamScene active={active} onReady={onReady} /></SceneBoundary>}
        <div className="shade" />
      </div>

      <div className="track" ref={track}>
        <h2 id="stream-h" className="h2 stream-h">How one question ran down the stream</h2>
        {REACHES.map((r) => (
          <div className="reach" key={r.scene}>
            <figure className="reach-photo">
              {/* eslint-disable-next-line @next/next/no-img-element -- pre-sized WebP; next/image would add Vercel's metered optimiser */}
              <img src={`/assets/stream/${r.scene}.webp`} alt={r.alt} width={1376} height={768} loading="lazy" decoding="async" />
            </figure>
            <ol className="beats">
              {BEAT_TEXT.map((t, i) => sceneOfBeat(i) === r.scene && (
                <li key={t.id} id={t.id} className="beat stone" style={{ ["--from" as string]: BEATS[i].from, ["--to" as string]: BEATS[i].to }}>
                  <span className="beat-n" aria-hidden="true">{t.n}</span>
                  <h3>{t.title}</h3>
                  {t.name && <code>{t.name}</code>}
                  <p>{t.line}</p>
                  <p className="beat-count"><b>{t.count.toLocaleString("en-US")}</b> {t.label}</p>
                </li>
              ))}
            </ol>
          </div>
        ))}

        <div className="pin" aria-hidden="true">
          <div className="caption">
            <span className="beat-title" ref={title}>{BEAT_TEXT[0].title}</span>
            {b.name && <code>{b.name}</code>}
            <p key={beat} className="beat-line">{b.line}</p>
          </div>
          <div className="odo">
            <Odometer value={b.count} />
            <span className="odo-label">{b.label}</span>
            <span className="rail">
              {BEAT_TEXT.slice(1).map((t, i) => (
                <i key={t.id} className={i + 1 < beat ? "past" : i + 1 === beat ? "here" : undefined} />
              ))}
            </span>
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
