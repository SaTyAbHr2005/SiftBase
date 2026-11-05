import { test } from "node:test";
import assert from "node:assert/strict";
import { BEATS, PAN_RADIUS, ROLE, beatAt, buildChips } from "./pan.ts";
import corpus from "../data/corpus.json" with { type: "json" };
import run from "../data/recorded-run.json" with { type: "json" };

const count = (role: number, chips = buildChips(corpus, run)) => chips.filter((c) => c.role >= role).length;
const pagesOf = (m: Record<string, number[]>) => Object.values(m).reduce((n, p) => n + p.length, 0);

test("one chip per page carries the recorded run's real counts", () => {
  const chips = buildChips(corpus, run);
  assert.equal(chips.length, 6970);
  const routedPages = corpus.documents.filter((d) => run.pages.routed.includes(d.name)).reduce((n, d) => n + d.pages, 0);
  assert.equal(count(ROLE.routed, chips), routedPages);
  assert.equal(count(ROLE.gathered, chips), pagesOf(run.pages.gathered));
  assert.equal(count(ROLE.kept, chips), pagesOf(run.pages.kept));
  assert.equal(count(ROLE.cited, chips), run.funnel.pages_cited);
});

test("phones get one chip per ten pages and still show cited gold", () => {
  const chips = buildChips(corpus, run, 10);
  assert.equal(chips.length, corpus.documents.reduce((n, d) => n + Math.ceil(d.pages / 10), 0));
  const cited = count(ROLE.cited, chips);
  assert.ok(cited >= 1 && cited <= run.funnel.pages_cited);
});

test("chips sit inside the pan, grouped by document, the same on every load", () => {
  const a = buildChips(corpus, run);
  assert.deepEqual(a, buildChips(corpus, run));
  for (const c of a) assert.ok(Math.hypot(c.x, c.z) <= PAN_RADIUS);
  // Each document fills one wedge: its chips' angles never interleave with another document's.
  const span = new Map<number, [number, number]>();
  for (const c of a) {
    const t = Math.atan2(c.z, c.x) + Math.PI, s = span.get(c.doc) ?? [t, t];
    span.set(c.doc, [Math.min(s[0], t), Math.max(s[1], t)]);
  }
  const sorted = [...span.values()].sort((x, y) => x[0] - y[0]);
  for (let i = 1; i < sorted.length; i++) assert.ok(sorted[i][0] >= sorted[i - 1][1] - 1e-9);
});

test("gathered chips are ranked best first, the rest unranked", () => {
  const chips = buildChips(corpus, run);
  const ranks = chips.filter((c) => c.role >= ROLE.gathered).map((c) => c.rank).sort((x, y) => x - y);
  assert.deepEqual(ranks, ranks.map((_, i) => i));
  assert.ok(chips.filter((c) => c.role < ROLE.gathered).every((c) => c.rank === -1));
});

test("beats cover the whole stage in order", () => {
  assert.equal(BEATS[0].from, 0);
  assert.equal(BEATS.at(-1)!.to, 1);
  for (let i = 1; i < BEATS.length; i++) assert.equal(BEATS[i].from, BEATS[i - 1].to);
  assert.equal(beatAt(0), 0);
  assert.equal(beatAt(1), BEATS.length - 1);
  assert.equal(beatAt(BEATS[3].from + 0.001), 3);
});
