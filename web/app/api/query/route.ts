// Server-side proxy to the SiftBase API. The API key lives only in the Vercel
// environment; the browser calls this route and never sees it.
// The API's own limits (per key per hour, shared per day) cap what the site can spend.

// Vercel Hobby allows 300 s: about 1 min for Render to wake plus up to ~3 min per query.
export const maxDuration = 300;

const MIN_QUERY = 8;
const MAX_QUERY = 500;
const HEADERS = { "Content-Type": "application/json", "X-Content-Type-Options": "nosniff" };

const fail = (status: number, code: string, message: string, retryable = false, extra: Record<string, string> = {}) =>
  new Response(JSON.stringify({ error: { code, message, retryable } }), { status, headers: { ...HEADERS, ...extra } });

// Only what the page reads leaves the server: no config hashes, ids, usage or file paths.
type Up = Record<string, unknown>;
function publicResult(r: Up) {
  const chunks = Array.isArray(r.chunks) ? (r.chunks as Up[]) : [];
  const trace = Array.isArray(r.trace) ? (r.trace as Up[]) : [];
  return {
    status: r.status,
    answer: typeof r.answer === "string" ? r.answer : "",
    latency_ms: r.latency_ms,
    coverage: { limitations: (r.coverage as Up | undefined)?.limitations ?? [] },
    chunks: chunks.map((c) => ({ document: c.document, page: c.page, text: c.text, cited_by_claim_ids: c.cited_by_claim_ids ?? [] })),
    trace: trace.map((s) => ({ step_name: s.step_name, description: s.description, output: s.output })),
  };
}

function apiBase(): string | null {
  try {
    const url = new URL(process.env.SIFTBASE_API_URL ?? "");
    const local = url.hostname === "localhost" || url.hostname === "127.0.0.1";
    return url.protocol === "https:" || (local && url.protocol === "http:") ? url.href.replace(/\/+$/, "") : null;
  } catch {
    return null;
  }
}

export async function POST(request: Request): Promise<Response> {
  // A JSON content type forces a CORS preflight, which this route never answers, so other sites cannot post here.
  if (!request.headers.get("Content-Type")?.startsWith("application/json"))
    return fail(415, "UNSUPPORTED_MEDIA_TYPE", "Send the question as JSON.");
  if (request.headers.get("Sec-Fetch-Site") === "cross-site") return fail(403, "CROSS_SITE", "Requests from other sites are not accepted.");

  const base = apiBase();
  const key = process.env.SIFTBASE_API_KEY;
  if (!base || !key) return fail(503, "NOT_CONFIGURED", "The live demo is not connected to the API yet.");

  let query: unknown;
  try {
    query = (await request.json())?.query;
  } catch {
    return fail(400, "INVALID_JSON", "The request body must be JSON.");
  }
  if (typeof query !== "string" || query.trim().length < MIN_QUERY || query.trim().length > MAX_QUERY)
    return fail(422, "INVALID_QUERY", `Ask a question of ${MIN_QUERY} to ${MAX_QUERY} characters.`);

  let upstream: Response;
  try {
    upstream = await fetch(`${base}/query`, {
      method: "POST",
      redirect: "error", // a redirect would carry the key to another host
      headers: { "Content-Type": "application/json", "X-API-Key": key },
      body: JSON.stringify({ collection_name: process.env.SIFTBASE_COLLECTION || "train", query: query.trim() }),
      signal: AbortSignal.any([request.signal, AbortSignal.timeout((maxDuration - 10) * 1000)]),
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "TimeoutError")
      return fail(504, "UPSTREAM_TIMEOUT", "The query took longer than the demo allows.", true);
    return fail(502, "UPSTREAM_UNREACHABLE", "The SiftBase API could not be reached.", true);
  }

  let body: Up;
  try {
    body = await upstream.json();
  } catch {
    return fail(502, "UPSTREAM_BAD_RESPONSE", "The SiftBase API is starting or unavailable. Try again in a minute.", true);
  }
  const retry = upstream.headers.get("Retry-After");
  const extra: Record<string, string> = retry ? { "Retry-After": retry } : {};
  if (upstream.ok) return new Response(JSON.stringify(publicResult(body)), { status: 200, headers: HEADERS });

  const err = (body?.error ?? {}) as Up;
  const code = typeof err.code === "string" ? err.code : "QUERY_FAILED";
  // Server-side messages can name providers and URLs; visitors get a fixed one.
  const message = upstream.status >= 500 && code !== "AT_CAPACITY"
    ? "The answer service had a problem with this question."
    : typeof err.message === "string" ? err.message : "The query was not accepted.";
  return fail(upstream.status, code, message, err.retryable === true, extra);
}
