"use client";

// The small interactive parts around the pan: the depth gauge, the score counters
// and the cover's question pool. Replaces the binder's tab rail.
import { useEffect, useRef, useState } from "react";
import { ASK_EVENT, TRACE_EVENT } from "./AskConsole.tsx";
import { STEPS } from "@/lib/content.ts";

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

const TICKS: { id: string; name: string; major: boolean; step?: number }[] = [
  { id: "cover", name: "Cover", major: true },
  ...STEPS.map((s, i) => ({ id: `step-${i + 1}`, name: `${i + 1} ${s.short}`, step: i + 1, major: false })),
  { id: "specimen", name: "Specimen", major: true },
  { id: "measured", name: "Assay", major: true },
  { id: "ask", name: "Ask", major: true },
  { id: "source", name: "Source", major: true },
];
const TICK_IDS = TICKS.map((t) => t.id);
const STONES = TICKS.filter((t) => t.major || t.step === 1).map((t) => (t.step ? { id: "pan", name: "The pan", major: true } : t));
const STONE_IDS = STONES.map((t) => t.id);

// A river's measuring staff down the right edge; on narrow screens, a row of small stones.
export function DepthGauge() {
  const active = useActive(TICK_IDS);
  const strip = useActive(STONE_IDS);
  // After a live answer, the step ticks open that step of its trace instead of the pan.
  const [traced, setTraced] = useState(0);
  useEffect(() => {
    const on = (e: Event) => setTraced((e as CustomEvent<number>).detail);
    window.addEventListener(TRACE_EVENT, on);
    return () => window.removeEventListener(TRACE_EVENT, on);
  }, []);
  return (
    <>
      <nav className="gauge" aria-label="Sections">
        <ol>
          {TICKS.map((t) => {
            const live = !!t.step && t.step <= traced;
            return (
              <li key={t.id} className={t.major ? "major" : undefined}>
                <a
                  href={live ? `#trace-${t.step}` : `#${t.id}`} className={live ? "traced" : undefined}
                  aria-current={t.id === active ? "true" : undefined}
                  aria-label={live ? `Step ${t.step} of your answer's trace` : t.name}
                >
                  <span className="name">{t.name}</span>
                </a>
              </li>
            );
          })}
        </ol>
      </nav>
      <nav className="stones" aria-label="Sections">
        {STONES.map((t) => (
          <a key={t.id} href={`#${t.id}`} aria-current={t.id === strip ? "true" : undefined}>{t.name}</a>
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
