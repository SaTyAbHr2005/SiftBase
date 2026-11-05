import type { QueryResult } from "./answer.ts";
import type { RunPages } from "./pan.ts";
import corpus from "../data/corpus.json";
import run from "../data/recorded-run.json";

// The ten trace steps, as docs/PROJECT.md describes them.
export const STEPS = [
  { name: "query_planning", short: "Plan", title: "Plan the question", model: true,
    what: "A model turns the question into the aspects it asks about, the tasks to answer it, and the documents likely to hold the answer.",
    hands: "Aspects, tasks and candidate documents." },
  { name: "routing_guard", short: "Route", title: "Guard the routing", model: false,
    what: "Checks document identity and version. A document with another year is ruled out only when a version with the requested year exists, read from its own text.",
    hands: "The documents allowed into the search." },
  { name: "candidate_pages", short: "Pages", title: "Find candidate pages", model: false,
    what: "BM25 and vector search inside each document, with a fair page quota per document so one long file cannot crowd out the rest.",
    hands: "Candidate pages per document." },
  { name: "page_survey", short: "Survey", title: "Survey the pages", model: false,
    what: "Picks pages locally from the rankings and the matches for each requested item. A model survey is available as an option.",
    hands: "The pages worth reading." },
  { name: "element_retrieval", short: "Gather", title: "Gather the passages", model: false,
    what: "Pulls the paragraphs and tables from the chosen pages, keeping each one's document, page and position.",
    hands: "Candidate passages with exact locations." },
  { name: "element_triage", short: "Order", title: "Order the work", model: false,
    what: "A MiniLM cross-encoder puts the most relevant passages first. Its scores set the order and never count as proof.",
    hands: "A ranked queue for verification." },
  { name: "element_verification", short: "Verify", title: "Verify the evidence", model: true,
    what: "A model checks source passages against the question in waves of batches, and stops when a wave stops finding new evidence.",
    hands: "Verified evidence." },
  { name: "answer_generation", short: "Write", title: "Write the claims", model: true,
    what: "Writes the answer as claims, each linked to verified evidence, with a worksheet for every task the plan asked for.",
    hands: "Draft claims tied to evidence." },
  { name: "answer_verification", short: "Check", title: "Check every claim", model: true,
    what: "A model and plain arithmetic check each claim against its evidence. Claims that fail are removed from the answer.",
    hands: "Only the claims that held." },
  { name: "citation_render", short: "Cite", title: "Stamp the citations", model: false,
    what: "Adds a [file pN] citation to each claim from source-owned data, so a citation can only point at a page that was actually read.",
    hands: "The answer, its chunks and this trace." },
] as const;

// Measured on the same 8 development questions, unmodified official evaluator,
// one judge (Groq openai/gpt-oss-120b). Source: docs/PROJECT.md.
export const RUNS = [
  { name: "Baseline", date: "2026-10-31", code: "before the recall work", ap: 53, ar: 22, cp: "50%", cr: "53%", time: "31 s / 163 s" },
  { name: "run_fix4", date: "2026-11-02", code: "310f4f6", ap: 72.5, ar: 32.2, cp: "52.7%", cr: "64.1%", time: "44 s / 183 s" },
  { name: "run_wait8b", date: "2026-11-04", code: "0cf3941", ap: 46.2, ar: 26.5, cp: "54.3%", cr: "62.9%", time: "40 s / 76 s" },
  { name: "run_rep_b", date: "2026-11-05", code: "61a8118", ap: 48.2, ar: 22.7, cp: "41.7%", cr: "59.0%", time: "34 s / 56 s" },
] as const;

// Written for this site; never taken from the benchmark file.
export const EXAMPLES = [
  "How does the Heston model describe volatility?",
  "What does the CECL standard change about how credit losses are estimated?",
  "Which risks does Infosys describe in its latest annual report?",
  "What do the annual reports say about wind turbine orders?",
];

// One recorded run of a question written for this site (never a benchmark question),
// made with scripts/record_run.py. Every count in the pan comes from it.
export const RECORDED = run as unknown as QueryResult & {
  question: string; recorded_at: string; funnel: Record<string, number>; pages: RunPages;
};

const f = RECORDED.funnel;
const n = (v: number) => v.toLocaleString("en-US");
const routed = RECORDED.pages.routed.map((d) => d.replace(/\.pdf$/i, ""));
const keptPages = Object.values(RECORDED.pages.kept).reduce((t, p) => t + p.length, 0);
const gatheredPages = RECORDED.pages.order.length;
const pages = corpus.documents.reduce((t, d) => t + d.pages, 0);

// The pan's captions: the pour, then one per trace step, each with the run's real count.
export const BEAT_TEXT = [
  { id: "pour", n: "00", title: "The pour", count: pages, label: "pages in the pan",
    line: `${corpus.documents.length} documents, ${n(pages)} pages. One chip of gravel for every page.` },
  { count: pages, label: "pages, nothing ruled out yet",
    line: `A model reads the question “${RECORDED.question}” and plans its aspects, tasks and likely documents.` },
  { count: f.documents_routed, label: "documents kept in the search",
    line: `${routed.join(", ")}. The other ${corpus.documents.length - f.documents_routed} documents sink and darken.` },
  { count: f.candidate_pages, label: "candidate pages",
    line: "The first wash: every page outside those documents goes over the lip." },
  { count: f.pages_picked, label: "pages picked by the survey",
    line: "Chosen locally from the rankings and term matches, before a single passage is read." },
  { count: f.passages_gathered, label: "passages gathered",
    line: `Paragraphs and tables from ${gatheredPages} pages, each with its document, page and position.` },
  { count: f.passages_gathered, label: "passages in order",
    line: "The reranker sorts them, best at the centre. The order is a queue to check, never proof." },
  { count: f.passages_kept, label: `of ${f.passages_checked} passages kept`,
    line: `A model checks each one against the question. ${f.passages_kept} hold, from ${keptPages} pages; ${f.passages_checked - f.passages_kept} wash out.` },
  { count: f.claims_drafted, label: "claims written",
    line: `The writer makes ${f.claims_drafted} claims, each tied to evidence that passed the check.` },
  { count: f.claims_accepted, label: `of ${f.claims_drafted} claims held`,
    line: f.claims_withdrawn
      ? `${f.claims_withdrawn} claim had no support. It dulled to pyrite and was removed.`
      : "Every claim is checked against its evidence. One without support would dull to pyrite and be removed; in this run none was." },
  { count: f.pages_cited, label: "pages cited",
    line: "The gold left in the pan. Each citation points at a page that was actually read." },
].map((b, i) => ({
  id: i ? `step-${i}` : "pour", n: String(i).padStart(2, "0"), title: i ? STEPS[i - 1].title : "The pour",
  name: i ? STEPS[i - 1].name : "", ...b,
}));

export const CORPUS = corpus;
