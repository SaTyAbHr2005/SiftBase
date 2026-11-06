// The scroll story's timeline: eleven beats (the falls, then the ten trace steps) over one pinned
// track, shown in three photographs. The falls carry beats 0-3, a dive into the pool carries 4-8,
// and the rise to the kingfisher carries 9-10. Pure numbers, shared by the DOM side and the shader.

export type Scene = "falls" | "pool" | "bird";
export type RunPages = {
  routed: string[]; gathered: Record<string, number[]>; kept: Record<string, number[]>; cited: Record<string, number[]>;
  order: (string | number)[][];
};
export type Corpus = { documents: { name: string; pages: number }[] };

const N = 11;
export const BEATS = Array.from({ length: N }, (_, i) => ({ from: i / N, to: (i + 1) / N }));
export const DIVE = BEATS[4].from;
export const RISE = BEATS[9].from;
const HALF = 0.035; // each transition spans 7% of the track, centred on its beat boundary

const clamp = (v: number) => (v < 0 ? 0 : v > 1 ? 1 : v);
const smooth = (a: number, b: number, x: number) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };

export const beatAt = (p: number) => Math.min(N - 1, Math.floor(clamp(p) * N));
export const sceneOfBeat = (i: number): Scene => (i < 4 ? "falls" : i < 9 ? "pool" : "bird");

// dive / rise: 0 to 1 across each transition. falls / pool / bird: progress through that scene's
// own span, which drives its camera move.
export function timeline(p: number) {
  return {
    dive: smooth(DIVE - HALF, DIVE + HALF, p),
    rise: smooth(RISE - HALF, RISE + HALF, p),
    falls: clamp(p / DIVE),
    pool: clamp((p - DIVE) / (RISE - DIVE)),
    bird: clamp((p - RISE) / (1 - RISE)),
  };
}
