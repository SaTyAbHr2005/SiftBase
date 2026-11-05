// Shapes of the SiftBase POST /query response that the page reads.
export type Chunk = { document: string; page: number; text: string; cited_by_claim_ids?: string[] };
export type TraceStep = { step_name: string; description: string; input?: unknown; output: unknown };
export type QueryResult = {
  status: "answered" | "partial" | "no_answer";
  answer: string;
  chunks: Chunk[];
  trace: TraceStep[];
  coverage?: { limitations?: string[] };
  latency_ms?: number;
};
export type QueryError = { error: { code: string; message: string; retryable?: boolean } };

export type Ref = { document: string; page: number };
export type Part = { kind: "text"; text: string } | { kind: "cite"; refs: Ref[] };
export type Block = { kind: "h" | "li" | "p"; parts: Part[] };
export type Exhibit = Ref & { texts: string[] };

// The API ends each claim with "[file.ext pN]" or, for several pages, "[a.pdf p3; b.pdf p5]".
// Plain answers put one claim per paragraph; sectioned ones use "## Heading" and "- claim" lines.
const CITE = /\[((?:[^\[\];]+?\.[A-Za-z0-9]{2,5} p\d+)(?:; [^\[\];]+?\.[A-Za-z0-9]{2,5} p\d+)*)\]/g;
const REF = /^(.+?\.[A-Za-z0-9]{2,5}) p(\d+)$/;

function parts(line: string): Part[] {
  const out: Part[] = [];
  let last = 0;
  for (const m of line.matchAll(CITE)) {
    if (m.index > last) out.push({ kind: "text", text: line.slice(last, m.index) });
    const refs = m[1].split("; ").map((r) => r.match(REF)!).map((r) => ({ document: r[1], page: Number(r[2]) }));
    out.push({ kind: "cite", refs });
    last = m.index + m[0].length;
  }
  if (last < line.length) out.push({ kind: "text", text: line.slice(last) });
  return out;
}

export function parseAnswer(answer: string): Block[] {
  return answer
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line): Block =>
      line.startsWith("## ") ? { kind: "h", parts: parts(line.slice(3)) }
      : line.startsWith("- ") ? { kind: "li", parts: parts(line.slice(2)) }
      : { kind: "p", parts: parts(line) });
}

// One exhibit per cited page, in the order first cited, holding every returned passage on that page.
export function exhibitsFor(blocks: Block[], chunks: Chunk[]): Exhibit[] {
  const seen = new Map<string, Exhibit>();
  for (const b of blocks)
    for (const p of b.parts)
      if (p.kind === "cite")
        for (const r of p.refs) {
          const key = `${r.document}\u0000${r.page}`;
          if (!seen.has(key))
            seen.set(key, { ...r, texts: chunks.filter((c) => c.document === r.document && c.page === r.page).map((c) => c.text) });
        }
  return [...seen.values()];
}

export const exhibitIndex = (exhibits: Exhibit[], r: Ref) =>
  exhibits.findIndex((e) => e.document === r.document && e.page === r.page);

// PDF extraction leaves inline tags (<sup>2</sup>) and markdown heading marks in passages; show text only.
export const plainSource = (t: string) =>
  t.replace(/<\/?(?:sup|sub|br|b|i|u|em|strong|span)\b[^>]*>/gi, "").replace(/^#{1,6}\s*|\s*#{2,}\s*$/gm, "");

// The pipeline's coverage limitations, said in plain words. Unknown ones pass through unchanged.
const LIMITS: [RegExp, string][] = [
  [/^(\d+) selected pages omitted by raw-read budget$/, "$1 chosen pages were not read: the reading budget ran out."],
  [/^(\d+) verified fragments omitted from writer context$/, "$1 checked passages did not fit in what the writer could read."],
  [/^Requested topics not fully supported by final claims: (.*)$/, "Not fully covered: $1"],
  [/^Some requested operations remain unresolved; see task worksheet$/, "Part of what the question asked for was left unanswered."],
];
export const plainLimit = (l: string) => LIMITS.reduce((s, [re, to]) => (re.test(s) ? s.replace(re, to) : s), l);
