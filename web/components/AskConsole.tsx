"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import CitedAnswer from "./CitedAnswer.tsx";
import { EXAMPLES } from "@/lib/content.ts";
import { plainLimit, type QueryError, type QueryResult, type TraceStep } from "@/lib/answer.ts";

export const ASK_EVENT = "siftbase:ask";

const MIN = 8;

type State =
  | { kind: "idle" }
  | { kind: "running"; query: string; started: number }
  | { kind: "done"; query: string; result: QueryResult; n: number }
  | { kind: "failed"; query: string; status: number; code: string; message: string; retryAt?: Date };

const STATUS_LABEL: Record<string, string> = { answered: "Answered", partial: "Partly answered", no_answer: "No answer found" };

export default function AskConsole() {
  const [text, setText] = useState("");
  const [hint, setHint] = useState(false);
  const [state, setState] = useState<State>({ kind: "idle" });
  const [now, setNow] = useState(0);
  const abort = useRef<AbortController | null>(null);
  const runs = useRef(0);
  const input = useRef<HTMLTextAreaElement>(null);
  const result = useRef<HTMLDivElement>(null);

  // Reads only refs, so the window listener below can hold it without going stale.
  async function run(raw: string) {
    const query = raw.trim();
    if (query.length < MIN) return setHint(true);
    setHint(false);
    if (abort.current) return; // one question at a time; Cancel stops the current one
    const controller = new AbortController();
    abort.current = controller;
    const started = Date.now();
    setNow(started);
    setState({ kind: "running", query, started });
    let next: State;
    try {
      const res = await fetch("/api/query", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }), signal: controller.signal,
      });
      const body = await res.json().catch(() => null);
      if (controller.signal.aborted) throw new DOMException("cancelled", "AbortError");
      if (res.ok && typeof body?.answer === "string") {
        const r = body as QueryResult;
        next = { kind: "done", query, n: ++runs.current, result: { ...r, chunks: r.chunks ?? [], trace: r.trace ?? [] } };
      } else {
        const err = (body as QueryError | null)?.error;
        const wait = Number(res.headers.get("Retry-After"));
        next = {
          kind: "failed", query, status: res.status,
          code: err?.code ?? (res.status === 429 ? "RATE_LIMITED" : "QUERY_FAILED"),
          message: err?.message ?? "The server did not return an answer.",
          retryAt: wait > 0 ? new Date(Date.now() + wait * 1000) : undefined,
        };
      }
    } catch (e) {
      next = (e as Error).name === "AbortError"
        ? { kind: "idle" }
        : { kind: "failed", query, status: 0, code: "NETWORK", message: "Your browser could not reach the site." };
    }
    if (abort.current !== controller) return;
    abort.current = null;
    setState(next);
  }

  // The cover's question box hands its question over here.
  useEffect(() => {
    const onAsk = (e: Event) => {
      const q = (e as CustomEvent<string>).detail;
      setText(q);
      input.current?.focus({ preventScroll: true });
      run(q);
    };
    window.addEventListener(ASK_EVENT, onAsk);
    return () => window.removeEventListener(ASK_EVENT, onAsk);
  }, []);

  useEffect(() => {
    if (state.kind !== "running") return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [state.kind]);

  useEffect(() => {
    if (state.kind === "done") result.current?.focus();
  }, [state]);

  const running = state.kind === "running";
  const elapsed = running ? Math.max(0, Math.floor((now - state.started) / 1000)) : 0;
  const announce =
    state.kind === "running" ? "Checking your question. This takes up to a few minutes."
    : state.kind === "done" ? "The answer is ready."
    : state.kind === "failed" ? "The question could not be answered." : "";

  return (
    <>
      <form className="ask-form" noValidate onSubmit={(e) => { e.preventDefault(); run(text); }}>
        <label htmlFor="ask-q" className="sr-only">Your question</label>
        <div className="row">
          <textarea
            id="ask-q" className="pool" ref={input} value={text} maxLength={500} aria-describedby="ask-hint"
            aria-invalid={hint || undefined}
            onChange={(e) => { setText(e.target.value); if (hint && e.target.value.trim().length >= MIN) setHint(false); }}
            placeholder="Ask the 35 documents"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); run(text); }
            }}
          />
          <button className="nugget" type="submit" aria-disabled={running || undefined}>Pan it</button>
        </div>
        <p id="ask-hint" className={hint ? "hint hint--warn" : "hint"}>
          {hint ? `Write at least ${MIN} characters.` : "8 to 500 characters. Enter sends, Shift+Enter starts a new line."}
        </p>
        <div className="examples">
          {EXAMPLES.map((q) => (
            <button key={q} type="button" aria-disabled={running || undefined} onClick={() => { setText(q); run(q); }}>{q}</button>
          ))}
        </div>
      </form>

      <p className="sr-only" aria-live="polite">{announce}</p>

      {state.kind === "running" && (
        <div className="waiting caustic">
          <span className="clock" aria-hidden="true">
            {Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, "0")}
          </span>
          <p>
            Checking “{state.query}”. The server sleeps when idle and takes about a minute to wake.
            A query then takes 40 seconds to 3 minutes.
          </p>
          <button className="quartz" type="button" onClick={() => abort.current?.abort()}>Cancel</button>
        </div>
      )}

      {state.kind === "failed" && <Failure state={state} retry={() => run(state.query)} />}

      {state.kind === "done" && (
        <div className="result" ref={result} tabIndex={-1} aria-label="Answer">
          <CitedAnswer key={`answer-${state.n}`} result={state.result} question={state.query} />
          <div className="meta">
            <span>{STATUS_LABEL[state.result.status] ?? state.result.status}</span>
            {state.result.latency_ms !== undefined && <span>{(state.result.latency_ms / 1000).toFixed(1)} s on the server</span>}
            <span>{state.result.chunks.length} source passages checked</span>
          </div>
          {!!state.result.coverage?.limitations?.length && (
            <ul className="limits" aria-label="What the answer could not cover">
              {state.result.coverage.limitations.map((l) => <li key={l}>{plainLimit(l)}</li>)}
            </ul>
          )}
          {state.result.trace.length > 0 && <TraceTabs key={`trace-${state.n}`} steps={state.result.trace} />}
        </div>
      )}
    </>
  );
}

function Failure({ state, retry }: { state: Extract<State, { kind: "failed" }>; retry: () => void }) {
  const at = state.retryAt?.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const when = at ? ` It frees up again around ${at}.` : " Please try again later.";
  if (state.code === "AT_CAPACITY")
    return (
      <div className="notice stone stone--b" role="status">
        <b>Today’s free allowance is used up.</b>
        <p>The demo runs on free model tiers, about 25 checked questions a day for everyone.{when} The recorded answer above shows a full one meanwhile.</p>
        <a className="quartz" href="#specimen">See the recorded answer</a>
      </div>
    );
  if (state.status === 429)
    return (
      <div className="notice stone stone--c" role="status">
        <b>Too many questions in a short time.</b>
        <p>The demo shares a small hourly and daily allowance between all visitors.{when}</p>
      </div>
    );
  if (state.code === "NOT_CONFIGURED")
    return (
      <div className="notice stone stone--a" role="status">
        <b>The live demo is not connected yet.</b>
        <p>The API is being deployed. The recorded answer above shows what a checked answer looks like.</p>
      </div>
    );
  return (
    <div className="error-pool" role="alert">
      <b>The query failed{state.status ? ` (HTTP ${state.status})` : ""}.</b>
      <p>{state.message}</p>
      <button className="nugget" type="button" onClick={retry}>Try again</button>
    </div>
  );
}

const LIMIT = 4000;

function TraceTabs({ steps }: { steps: TraceStep[] }) {
  const [sel, setSel] = useState(0);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const step = steps[sel];
  const json = JSON.stringify(step.output ?? null, null, 2) ?? "null";

  // Links to #trace-N open that step.
  useEffect(() => {
    const open = () => {
      const m = location.hash.match(/^#trace-(\d+)$/);
      const n = m ? Number(m[1]) - 1 : -1;
      if (n >= 0 && n < steps.length) { setSel(n); tabs.current[n]?.focus({ preventScroll: true }); }
    };
    open();
    window.addEventListener("hashchange", open);
    return () => window.removeEventListener("hashchange", open);
  }, [steps.length]);

  function rove(e: KeyboardEvent) {
    const next =
      e.key === "ArrowRight" ? (sel + 1) % steps.length
      : e.key === "ArrowLeft" ? (sel - 1 + steps.length) % steps.length
      : e.key === "Home" ? 0 : e.key === "End" ? steps.length - 1 : null;
    if (next === null) return;
    e.preventDefault();
    setSel(next);
    tabs.current[next]?.focus();
  }

  return (
    <section className="trace" aria-label="Trace of this query">
      <h3 className="label">The trace, step by step</h3>
      <div role="tablist" className="stepping" aria-label="Trace steps" onKeyDown={rove}>
        {steps.map((s, i) => (
          <button
            key={s.step_name} role="tab" id={`trace-${i + 1}`} aria-controls="trace-panel" aria-selected={i === sel}
            aria-label={`Step ${i + 1}: ${s.step_name}`} tabIndex={i === sel ? 0 : -1}
            ref={(el) => { tabs.current[i] = el; }} style={{ ["--i" as string]: i }} onClick={() => setSel(i)}
          >
            {i + 1}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="stone stone--b" id="trace-panel" aria-labelledby={`trace-${sel + 1}`}>
        <h4>{sel + 1}. {step.step_name}</h4>
        <p className="muted">{step.description}</p>
        <pre tabIndex={0} aria-label={`Output of step ${sel + 1}`}>
          {json.length > LIMIT ? `${json.slice(0, LIMIT)}\n… ${json.length - LIMIT} more characters not shown` : json}
        </pre>
      </div>
    </section>
  );
}
