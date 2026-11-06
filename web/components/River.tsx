"use client";

// The small interactive parts around the stream: the section gauge, the score counters
// and the cover's question box.
import { useEffect, useRef, useState } from "react";
import { ASK_EVENT } from "./AskConsole.tsx";

const SECTIONS = [
  { id: "cover", name: "The falls" },
  { id: "stream", name: "The stream" },
  { id: "specimen", name: "The answer" },
  { id: "measured", name: "The assay" },
  { id: "ask", name: "Ask" },
  { id: "source", name: "Source" },
];
const IDS = SECTIONS.map((s) => s.id);

// Marks whichever section crosses the middle band of the viewport.
function useActive(ids: string[]) {
  const [active, setActive] = useState(ids[0]);
  useEffect(() => {
    const io = new IntersectionObserver(
      (entries) => entries.forEach((e) => e.isIntersecting && setActive(e.target.id)),
      { rootMargin: "-45% 0px -50% 0px" },
    );
    ids.forEach((id) => { const el = document.getElementById(id); if (el) io.observe(el); });
    return () => io.disconnect();
  }, [ids]);
  return active;
}

// A measuring staff down the right edge; on narrow screens, a row of small stones under the bar.
export function DepthGauge() {
  const active = useActive(IDS);
  return (
    <>
      <nav className="gauge" aria-label="Sections">
        <ol>
          {SECTIONS.map((s) => (
            <li key={s.id}>
              <a href={`#${s.id}`} aria-current={s.id === active ? "true" : undefined}><span className="name">{s.name}</span></a>
            </li>
          ))}
        </ol>
      </nav>
      <nav className="stones" aria-label="Sections">
        {SECTIONS.map((s) => (
          <a key={s.id} href={`#${s.id}`} aria-current={s.id === active ? "true" : undefined}>{s.name}</a>
        ))}
      </nav>
    </>
  );
}

// Counts up to the measured value once, when it first scrolls into view. Until then, and in
// print, screenshots or with reduced motion, it shows the real number.
export function Count({ value, decimals = 0 }: { value: number; decimals?: number }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(value);
  useEffect(() => {
    const el = ref.current;
    if (!el || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (el.getBoundingClientRect().top < innerHeight) return; // already on screen at load
    let frame = 0;
    // Fires just before it scrolls into view, so the reset to 0 is never seen.
    const io = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      io.disconnect();
      setShown(0);
      const start = performance.now();
      const tick = (t: number) => {
        const k = Math.min(1, (t - start) / 900);
        setShown(value * (1 - Math.pow(1 - k, 4)));
        if (k < 1) frame = requestAnimationFrame(tick);
      };
      frame = requestAnimationFrame(tick);
    }, { rootMargin: "0px 0px 10% 0px" });
    io.observe(el);
    return () => { io.disconnect(); cancelAnimationFrame(frame); };
  }, [value]);
  return <span ref={ref}>{shown.toFixed(decimals)}</span>;
}

export function CoverForm() {
  const [q, setQ] = useState("");
  const [hint, setHint] = useState(false);
  return (
    <form
      className="ask-form" noValidate
      onSubmit={(e) => {
        e.preventDefault();
        if (q.trim().length < 8) return setHint(true);
        document.getElementById("ask")?.scrollIntoView();
        window.dispatchEvent(new CustomEvent(ASK_EVENT, { detail: q }));
      }}
    >
      <label htmlFor="cover-q" className="sr-only">Your question</label>
      <div className="row">
        <input id="cover-q" className="pool" value={q} maxLength={500} aria-describedby="cover-hint" aria-invalid={hint || undefined}
          onChange={(e) => { setQ(e.target.value); if (e.target.value.trim().length >= 8) setHint(false); }}
          placeholder="Ask the 35 documents" />
        <button className="nugget" type="submit">Pan it</button>
      </div>
      <p id="cover-hint" className={hint ? "hint hint--warn" : "hint"} aria-live="polite">
        {hint ? "Write at least 8 characters." : "A real query on free models: the answer, the pages it cites and the full trace."}
      </p>
    </form>
  );
}
