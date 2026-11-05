import { test } from "node:test";
import assert from "node:assert/strict";
import { exhibitsFor, parseAnswer, plainLimit, plainSource, type Chunk } from "./answer.ts";

const chunks: Chunk[] = [
  { document: "report.pdf", page: 12, text: "Revenue rose 8%.", cited_by_claim_ids: ["c1"] },
  { document: "report.pdf", page: 12, text: "Costs held flat.", cited_by_claim_ids: [] },
  { document: "notes.docx", page: 3, text: "Staff grew to 40.", cited_by_claim_ids: ["c2"] },
  { document: "other.pdf", page: 1, text: "Never cited.", cited_by_claim_ids: [] },
];

test("plain answers: one paragraph per claim, citations split from text", () => {
  const blocks = parseAnswer("Revenue rose [report.pdf p12].\n\nStaff grew [notes.docx p3].");
  assert.deepEqual(blocks, [
    { kind: "p", parts: [{ kind: "text", text: "Revenue rose " }, { kind: "cite", refs: [{ document: "report.pdf", page: 12 }] }, { kind: "text", text: "." }] },
    { kind: "p", parts: [{ kind: "text", text: "Staff grew " }, { kind: "cite", refs: [{ document: "notes.docx", page: 3 }] }, { kind: "text", text: "." }] },
  ]);
});

test("one bracket can cite several pages", () => {
  const [block] = parseAnswer("Both rose [report.pdf p12; notes.docx p3]");
  assert.deepEqual(block.parts[1], { kind: "cite", refs: [{ document: "report.pdf", page: 12 }, { document: "notes.docx", page: 3 }] });
});

test("sectioned answers keep headings and list items", () => {
  const blocks = parseAnswer("## Costs\n- Flat [report.pdf p12]\n- Staff up [notes.docx p3]\n\n## Other\n- None");
  assert.deepEqual(blocks.map((b) => b.kind), ["h", "li", "li", "h", "li"]);
  assert.deepEqual(blocks[0].parts, [{ kind: "text", text: "Costs" }]);
});

test("brackets that are not citations are plain text", () => {
  assert.deepEqual(parseAnswer("A [note] here"), [{ kind: "p", parts: [{ kind: "text", text: "A [note] here" }] }]);
});

test("exhibits are the cited pages in order, with every passage on that page", () => {
  const ex = exhibitsFor(parseAnswer("A [notes.docx p3]. B [report.pdf p12; notes.docx p3]. C [gone.pdf p9]"), chunks);
  assert.deepEqual(ex, [
    { document: "notes.docx", page: 3, texts: ["Staff grew to 40."] },
    { document: "report.pdf", page: 12, texts: ["Revenue rose 8%.", "Costs held flat."] },
    { document: "gone.pdf", page: 9, texts: [] },
  ]);
});

test("an answer with no citations has no exhibits, even with chunks returned", () => {
  assert.deepEqual(exhibitsFor(parseAnswer("No answer found."), chunks), []);
});

test("source passages lose extraction tags and markdown heading marks", () => {
  assert.equal(plainSource("CVA<sup>2</sup> and <u>x</u>"), "CVA2 and x");
  assert.equal(plainSource("## Minimum capital requirements ####\nBody"), "Minimum capital requirements\nBody");
  assert.equal(plainSource("a < b and c > d"), "a < b and c > d");
});

test("pipeline limitations read as plain sentences", () => {
  assert.equal(plainLimit("6 selected pages omitted by raw-read budget"), "6 chosen pages were not read: the reading budget ran out.");
  assert.equal(plainLimit("20 verified fragments omitted from writer context"), "20 checked passages did not fit in what the writer could read.");
  assert.equal(plainLimit("Requested topics not fully supported by final claims: Compare A and B."), "Not fully covered: Compare A and B.");
  assert.equal(plainLimit("Some requested operations remain unresolved; see task worksheet"), "Part of what the question asked for was left unanswered.");
  assert.equal(plainLimit("Something new"), "Something new");
});
