// The pan's data model: one gravel chip per page (or per `step` pages on phones), laid out
// in one wedge per document, and where each chip sits at any point of the scroll story.
// Pure TypeScript, so the scene only copies these numbers into instance matrices.

export type Corpus = { documents: { name: string; pages: number }[] };
export type RunPages = { routed: string[]; gathered: Record<string, number[]>; kept: Record<string, number[]>; cited: Record<string, number[]>;
  order: (string | number)[][] };
export type Chip = {
  doc: number; page: number; x: number; z: number; seed: number;
  role: number; rank: number; kept: number; cited: number;
};

// How far a chip got: ruled out at routing, routed, gathered as a passage, kept by verification, cited.
export const ROLE = { out: 0, routed: 1, gathered: 2, kept: 3, cited: 4 } as const;
export const PAN_RADIUS = 4.3;

// The pour, then the ten trace steps; `step` matches STEPS in content.ts (1-based).
export const BEATS = [{ from: 0, to: 0.08, step: 0 }, ...Array.from({ length: 10 }, (_, i) => ({
  from: +(0.08 + i * 0.092).toFixed(3), to: i === 9 ? 1 : +(0.08 + (i + 1) * 0.092).toFixed(3), step: i + 1,
}))];

export const beatAt = (p: number) => Math.max(0, BEATS.findLastIndex((b) => p >= b.from));

function rng(seed: number) {
  return () => {
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function buildChips(corpus: Corpus, run: { pages: RunPages }, step = 1): Chip[] {
  const rand = rng(6970);
  const total = corpus.documents.reduce((n, d) => n + d.pages, 0);
  // `order` lists every gathered page once, in the reranker's order across documents, best first.
  const rankOf = new Map(run.pages.order.map(([doc, page], i) => [`${doc}|${page}`, i]));
  const hit = (m: Record<string, number[]>, doc: string, from: number, to: number) => (m[doc] ?? []).some((p) => p >= from && p < to);
  const chips: Chip[] = [];
  let angle = 0;
  corpus.documents.forEach((d, doc) => {
    const wedge = (d.pages / total) * Math.PI * 2;
    for (let page = 1; page <= d.pages; page += step) {
      const end = page + step;
      const r = PAN_RADIUS * 0.97 * Math.sqrt(0.003 + 0.997 * rand());
      const t = angle + wedge * rand() - Math.PI;
      const role = hit(run.pages.cited, d.name, page, end) ? ROLE.cited
        : hit(run.pages.kept, d.name, page, end) ? ROLE.kept
        : hit(run.pages.gathered, d.name, page, end) ? ROLE.gathered
        : run.pages.routed.includes(d.name) ? ROLE.routed : ROLE.out;
      const ranks = Array.from({ length: step }, (_, i) => rankOf.get(`${d.name}|${page + i}`)).filter((x) => x !== undefined);
      chips.push({ doc, page, x: r * Math.cos(t), z: r * Math.sin(t), seed: rand(), role,
        rank: role >= ROLE.gathered && ranks.length ? Math.min(...ranks) : -1, kept: -1, cited: -1 });
    }
    angle += wedge;
  });
  // Dense indexes for the rings, the ridge and the final row.
  chips.filter((c) => c.rank >= 0).sort((a, b) => a.rank - b.rank).forEach((c, i) => { c.rank = i; });
  chips.filter((c) => c.role >= ROLE.kept).forEach((c, i) => { c.kept = i; });
  chips.filter((c) => c.role === ROLE.cited).forEach((c, i) => { c.cited = i; });
  return chips;
}

export type Totals = { gathered: number; kept: number; cited: number; docs: number };
export const totals = (chips: Chip[], docs: number): Totals => ({
  gathered: chips.filter((c) => c.rank >= 0).length,
  kept: chips.filter((c) => c.kept >= 0).length,
  cited: chips.filter((c) => c.cited >= 0).length,
  docs,
});

// Where a chip is at stage progress p (0 to 1): position, scale (0 = washed out), gold (0 to 1),
// darkening for ruled-out material, light on routed material, and a flip angle as verification turns it over.
export type ChipPose = { x: number; y: number; z: number; s: number; gold: number; dim: number; lit: number; flip: number };

const clamp = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const span = (p: number, a: number, b: number) => clamp((p - a) / (b - a));
const ease = (t: number) => 1 - Math.pow(1 - t, 3);
const mix = (a: number, b: number, t: number) => a + (b - a) * t;
const beat = (step: number) => BEATS[step];

// `pour` (0 to 1) is the load-time fall of the gravel into the pan, separate from scroll.
export function pose(c: Chip, p: number, t: Totals, out: ChipPose, pour = 1): ChipPose {
  let x = c.x, z = c.z, y = 0, s = 1, gold = 0, dim = 0, lit = 0, flip = 0;

  // Pour: documents fall in one after another and settle.
  const start = (c.doc / t.docs) * 0.55 + c.seed * 0.05;
  const fall = ease(span(pour, start, start + 0.4));
  y += (1 - fall) * 5;
  if (pour < start) s = 0;

  // Steps 1-2: routed documents rise and catch the light, the rest darken.
  const route = ease(span(p, beat(1).from, beat(2).to));
  if (c.role >= ROLE.routed) { y += 0.12 * route; lit = route; } else dim = route;

  // A wash: the chip slides out over the lip, staggered by its seed, and is gone.
  const wash = (a: number, b: number) => {
    const w = ease(span(p, mix(a, b, c.seed * 0.5), mix(a, b, 0.5 + c.seed * 0.5)));
    const k = 1 + 0.55 * w;
    x *= k; z *= k; y -= 0.9 * w; s *= 1 - w;
  };
  if (c.role < ROLE.routed) wash(beat(3).from, beat(4).to);
  else if (c.role < ROLE.gathered) wash(beat(4).from, beat(5).to);

  // Step 6: the reranker's order, best passage at the centre, in a golden-angle spiral.
  if (c.rank >= 0) {
    const o = ease(span(p, beat(6).from, beat(6).to));
    const r = 0.35 + 2.4 * Math.sqrt((c.rank + 0.5) / Math.max(1, t.gathered)), a = c.rank * 2.39996;
    x = mix(x, r * Math.cos(a), o); z = mix(z, r * Math.sin(a), o); y = mix(y, 0.18, o);
  }

  // Step 7: verification turns each passage over; kept ones show gold, the rest wash out.
  if (c.role === ROLE.gathered) wash(beat(7).from, beat(7).to);
  if (c.kept >= 0) {
    const v = ease(span(p, mix(beat(7).from, beat(7).to, c.seed * 0.4), beat(7).to));
    flip = v * Math.PI; gold = v;
    // Steps 8-9: the flakes gather along the far ridge, one place per kept page.
    const g = ease(span(p, beat(8).from, beat(9).from));
    const a = -Math.PI / 2 + (c.kept / Math.max(1, t.kept - 1) - 0.5) * 1.9;
    x = mix(x, 3.45 * Math.cos(a), g); z = mix(z, 3.45 * Math.sin(a), g); y = mix(y, 0.35, g);
    // Step 10: cited pages lift toward the camera and line up; the others sink back.
    const lift = ease(span(p, beat(10).from, beat(10).from + (beat(10).to - beat(10).from) * 0.7));
    if (c.cited >= 0) {
      x = mix(x, (c.cited - (t.cited - 1) / 2) * 0.62, lift); z = mix(z, 1.4, lift); y = mix(y, 1.9, lift);
      flip = mix(flip, Math.PI * 1.5, lift);
    } else { y -= 0.25 * lift; gold *= 1 - 0.6 * lift; }
  }

  out.x = x; out.y = y; out.z = z; out.s = s; out.gold = gold; out.dim = dim; out.lit = lit; out.flip = flip;
  return out;
}
