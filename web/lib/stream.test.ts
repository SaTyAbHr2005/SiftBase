import { test } from "node:test";
import assert from "node:assert/strict";
import { BEATS, DIVE, RISE, beatAt, sceneOfBeat, timeline } from "./stream.ts";

test("eleven beats tile the stream from 0 to 1 with no gap", () => {
  assert.equal(BEATS.length, 11);
  assert.equal(BEATS[0].from, 0);
  assert.equal(BEATS.at(-1)!.to, 1);
  BEATS.slice(1).forEach((b, i) => assert.equal(b.from, BEATS[i].to));
});

test("beatAt finds the beat under the progress, clamped at both ends", () => {
  assert.equal(beatAt(-0.2), 0);
  assert.equal(beatAt(0), 0);
  assert.equal(beatAt(BEATS[4].from + 1e-6), 4);
  assert.equal(beatAt(1), 10);
  assert.equal(beatAt(1.4), 10);
});

test("the falls carry the first four beats, the pool the next five, the kingfisher the last two", () => {
  assert.deepEqual(BEATS.map((_, i) => sceneOfBeat(i)), ["falls", "falls", "falls", "falls", "pool", "pool", "pool", "pool", "pool", "bird", "bird"]);
  assert.equal(DIVE, BEATS[4].from);
  assert.equal(RISE, BEATS[9].from);
});

test("timeline: the dive and the rise are halfway at their beat boundaries and settled either side", () => {
  const start = timeline(0), end = timeline(1);
  assert.deepEqual([start.dive, start.rise, start.falls], [0, 0, 0]);
  assert.deepEqual([end.dive, end.rise, end.bird], [1, 1, 1]);
  assert.ok(Math.abs(timeline(DIVE).dive - 0.5) < 1e-9);
  assert.ok(Math.abs(timeline(RISE).rise - 0.5) < 1e-9);
  assert.equal(timeline(BEATS[2].from).dive, 0);
  assert.equal(timeline(BEATS[6].from).dive, 1);
  assert.equal(timeline(BEATS[6].from).rise, 0);
});

test("timeline values never move backwards as the reader scrolls down", () => {
  let prev = timeline(0);
  for (let i = 1; i <= 400; i++) {
    const t = timeline(i / 400);
    for (const k of ["dive", "rise", "falls", "pool", "bird"] as const) assert.ok(t[k] >= prev[k] - 1e-12, `${k} at ${i / 400}`);
    prev = t;
  }
});
