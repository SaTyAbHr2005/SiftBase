import { test, beforeEach } from "node:test";
import assert from "node:assert/strict";
import { POST } from "./route.ts";

const ask = (body: unknown, headers: Record<string, string> = { "Content-Type": "application/json" }) =>
  POST(new Request("http://site/api/query", { method: "POST", headers, body: JSON.stringify(body) }));
const Q = { query: "What changed in the plan?" };

const FULL = {
  status: "answered", answer: "A [a.pdf p1]", latency_ms: 1200,
  chunks: [{ document: "a.pdf", page: 1, text: "A.", cited_by_claim_ids: ["c1"], source_path: "/srv/a.pdf", doc_id: "x" }],
  coverage: { limitations: ["none"], aspects: [] },
  trace: [{ step_name: "query_planning", description: "d", input: { q: 1 }, output: { n: 2 } }],
  config_sha256: "abc", generation_id: "g", request_id: "r", trace_id: "t", usage: { cost_usd: 0 },
};

let sent: { url: string; init: RequestInit }[] = [];
let reply = () => Response.json(FULL);

beforeEach(() => {
  sent = [];
  reply = () => Response.json(FULL);
  process.env.SIFTBASE_API_URL = "https://api.example/";
  process.env.SIFTBASE_API_KEY = "secret-key";
  delete process.env.SIFTBASE_COLLECTION;
  globalThis.fetch = (async (url: string, init: RequestInit) => {
    sent.push({ url, init });
    return reply();
  }) as typeof fetch;
});

test("forwards the query with the key, no redirects, to the fixed path", async () => {
  const res = await ask(Q);
  assert.equal(res.status, 200);
  assert.equal(sent[0].url, "https://api.example/query");
  assert.equal((sent[0].init.headers as Record<string, string>)["X-API-Key"], "secret-key");
  assert.equal(sent[0].init.redirect, "error");
  assert.deepEqual(JSON.parse(sent[0].init.body as string), { collection_name: "train", ...Q });
});

test("returns only the fields the page reads", async () => {
  const body = await (await ask(Q)).json();
  assert.deepEqual(Object.keys(body).sort(), ["answer", "chunks", "coverage", "latency_ms", "status", "trace"]);
  assert.deepEqual(body.chunks[0], { document: "a.pdf", page: 1, text: "A.", cited_by_claim_ids: ["c1"] });
  assert.deepEqual(body.coverage, { limitations: ["none"] });
  assert.deepEqual(body.trace[0], { step_name: "query_planning", description: "d", output: { n: 2 } });
});

test("rejects a too-short or non-string query without calling the API", async () => {
  assert.equal((await ask({ query: "hi" })).status, 422);
  assert.equal((await ask({ query: 42 })).status, 422);
  assert.equal((await ask({ query: "x".repeat(501) })).status, 422);
  assert.equal((await ask(null)).status, 422);
  assert.equal(sent.length, 0);
});

test("refuses requests other sites can send without a preflight", async () => {
  assert.equal((await ask(Q, { "Content-Type": "text/plain" })).status, 415);
  assert.equal((await ask(Q, { "Content-Type": "application/json", "Sec-Fetch-Site": "cross-site" })).status, 403);
  assert.equal(sent.length, 0);
});

test("passes capacity replies through with Retry-After", async () => {
  reply = () => Response.json({ error: { code: "AT_CAPACITY", message: "used up", retryable: true } }, { status: 503, headers: { "Retry-After": "3600" } });
  const res = await ask(Q);
  assert.equal(res.status, 503);
  assert.equal(res.headers.get("Retry-After"), "3600");
  assert.equal((await res.json()).error.code, "AT_CAPACITY");
});

test("hides upstream 5xx details behind a fixed message", async () => {
  reply = () => Response.json({ error: { code: "PROVIDER_UNAVAILABLE", message: "Model unavailable: cloudflare: https://api.cloudflare.com/acct123", retryable: true } }, { status: 503 });
  const body = await (await ask(Q)).json();
  assert.equal(body.error.code, "PROVIDER_UNAVAILABLE");
  assert.ok(!body.error.message.includes("acct123"));
});

test("turns a non-JSON upstream page into a clean 502", async () => {
  reply = () => new Response("<html>Bad gateway</html>", { status: 502, headers: { "Content-Type": "text/html" } });
  const res = await ask(Q);
  assert.equal(res.status, 502);
  assert.equal(res.headers.get("Content-Type")?.startsWith("application/json"), true);
  assert.equal(res.headers.get("X-Content-Type-Options"), "nosniff");
  assert.equal((await res.json()).error.code, "UPSTREAM_BAD_RESPONSE");
});

test("answers 503 NOT_CONFIGURED when the key is missing or the URL is not https", async () => {
  delete process.env.SIFTBASE_API_KEY;
  assert.equal((await (await ask(Q)).json()).error.code, "NOT_CONFIGURED");
  process.env.SIFTBASE_API_KEY = "secret-key";
  process.env.SIFTBASE_API_URL = "http://api.example";
  assert.equal((await (await ask(Q)).json()).error.code, "NOT_CONFIGURED");
  assert.equal(sent.length, 0);
  process.env.SIFTBASE_API_URL = "http://localhost:8000";
  assert.equal((await ask(Q)).status, 200);
});

test("answers 502 when the API cannot be reached and 504 when it times out", async () => {
  globalThis.fetch = (async () => { throw new TypeError("fetch failed"); }) as typeof fetch;
  assert.equal((await (await ask(Q)).json()).error.code, "UPSTREAM_UNREACHABLE");
  globalThis.fetch = (async () => { throw new DOMException("t", "TimeoutError"); }) as typeof fetch;
  const res = await ask(Q);
  assert.equal(res.status, 504);
  assert.equal((await res.json()).error.code, "UPSTREAM_TIMEOUT");
});
