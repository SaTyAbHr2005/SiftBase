"use client";

// An answer on a river stone whose citations are gold flakes. Choosing a flake, or a source
// in the slip's list, brings that cited page up on a wet field slip beside the answer.
// Interaction model adapted from 21st's Source Citation Rail: marker and source stay
// in sync, arrow keys rove the sources, and the active state is never colour alone.
import { Fragment, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { exhibitIndex, exhibitsFor, parseAnswer, plainSource, type Part, type QueryResult } from "@/lib/answer.ts";

type Props = { result: QueryResult; question: string; withdrawn?: string };


export default function CitedAnswer({ result, question, withdrawn }: Props) {
  const slipId = useId();
  const blocks = parseAnswer(result.answer);
  const sources = exhibitsFor(blocks, result.chunks);
  const [active, setActive] = useState(0);
  const sourceRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const shown = sources[active];

  function rove(e: KeyboardEvent) {
    const last = sources.length - 1;
    const next =
      e.key === "ArrowRight" || e.key === "ArrowDown" ? Math.min(last, active + 1)
      : e.key === "ArrowLeft" || e.key === "ArrowUp" ? Math.max(0, active - 1)
      : e.key === "Home" ? 0 : e.key === "End" ? last : null;
    if (next === null) return;
    e.preventDefault();
    setActive(next);
    sourceRefs.current[next]?.focus();
  }

  function render(parts: Part[]): ReactNode {
    return parts.map((part, i) => {
      if (part.kind === "text") {
        const claim = parts[i + 1]?.kind === "cite";
        return claim ? <span key={i} className="claim">{part.text}</span> : <Fragment key={i}>{part.text}</Fragment>;
      }
      return (
        <Fragment key={i}>
          {part.refs.map((r) => {
            const n = exhibitIndex(sources, r);
            if (!sources[n].texts.length)
              return (
                <span key={n} className="flake flake--bare" title="This page was cited but its passage was not returned">
                  {r.document} p{r.page}
                </span>
              );
            const on = n === active;
            return (
              <button
                key={n} type="button" className="flake" aria-pressed={on} aria-controls={slipId}
                aria-label={`Source ${n + 1}: ${r.document}, page ${r.page}${on ? ", shown" : ""}`}
                onClick={() => setActive(n)}
              >
                p{r.page}
              </button>
            );
          })}
        </Fragment>
      );
    });
  }

  // Consecutive list items share one <ul>.
  const body: ReactNode[] = [];
  for (let i = 0; i < blocks.length; i++) {
    const b = blocks[i];
    if (b.kind === "h") body.push(<h4 key={i} className="section">{render(b.parts)}</h4>);
    else if (b.kind === "p") body.push(<p key={i}>{render(b.parts)}</p>);
    else {
      const items = [];
      while (i < blocks.length && blocks[i].kind === "li") items.push(<li key={i}>{render(blocks[i++].parts)}</li>);
      i--;
      body.push(<ul key={`ul${i}`}>{items}</ul>);
    }
  }

  return (
    <div className="cited">
      <article className="answer stone stone--a">
        <h3 className="q">{question}</h3>
        <div className="body">
          {body}
          {withdrawn && (
            <p className="withdrawn">
              <s>{withdrawn}</s>
              <span className="pyrite" aria-label="Withdrawn: no source supports this claim">Withdrawn</span>
            </p>
          )}
        </div>
      </article>

      <aside className="sources" aria-label="Cited pages">
        {sources.length > 0 && (
          <div className="source-list" role="group" aria-label="Sources">
            {sources.map((s, i) => (
              <button
                key={i} type="button" ref={(el) => { sourceRefs.current[i] = el; }}
                tabIndex={i === active ? 0 : -1} aria-pressed={i === active} aria-controls={slipId}
                aria-label={`Source ${i + 1}: ${s.document}, page ${s.page}`}
                onClick={() => setActive(i)} onKeyDown={rove}
              >
                {i + 1}
              </button>
            ))}
          </div>
        )}
        <div className="slip source-slip" id={slipId} key={active}>
          {shown ? (
            <>
              <div className="where">
                <b>{shown.document}</b>
                <span>page {shown.page}</span>
              </div>
              {shown.texts.length ? (
                shown.texts.map((t, i) => <blockquote key={i}>{plainSource(t)}</blockquote>)
              ) : (
                <p className="empty">This page was cited, but its passage was not returned with the answer.</p>
              )}
            </>
          ) : (
            <p className="empty">This answer cites no source page, so there is nothing to bring up.</p>
          )}
        </div>
      </aside>
    </div>
  );
}
