// Turns a POST /query response into the run the Ask table replays: counts and pages at each step, the answer as
// sections of cited lines, and the real step timings. Same fields as scripts/record_run.py's public().
const LABELS = {
  query_planning: 'Plan', routing_guard: 'Route', candidate_pages: 'Candidates', page_survey: 'Survey',
  element_retrieval: 'Passages', element_triage: 'Triage', element_verification: 'Verify',
  answer_generation: 'Write', answer_verification: 'Check', citation_render: 'Cite',
};
// The writer ends a cited line with " [a.pdf p3; b.pdf p5]" (kb/query render). Anchored at the end of the line, so a
// file name that itself contains "]" still parses.
const CITE = /\s*\[(.+?\.\w+ p\d+(?:; .+?\.\w+ p\d+)*)\]\s*$/;

function parseAnswer(text) {
  const sections = [];
  let cur = null;
  // Control characters copied from source PDFs (e.g. \u0007 before a list item) carry no text.
  for (const raw of String(text || '').replace(/[\u0000-\u0008\u000b-\u001f\u007f]/g, '').split('\n')) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith('## ')) { cur = { heading: line.slice(3).trim(), lines: [] }; sections.push(cur); continue; }
    if (!cur) { cur = { heading: 'Answer', lines: [] }; sections.push(cur); }
    const cites = [];
    const m = line.match(CITE);
    for (const part of m ? m[1].split('; ') : []) {
      const c = part.trim().match(/^(.+\.\w+) p(\d+)$/);
      if (c) cites.push({ doc: c[1], page: Number(c[2]) });
    }
    cur.lines.push({ text: line.replace(/^[-*]\s+/, '').replace(CITE, '').trim(), cites });
  }
  return sections;
}

function modelLabel(usage) {
  const m = (usage && usage.models && usage.models[0]) || '';
  if (!m) return 'model unknown';
  const [provider, ...rest] = m.split(':');
  const name = rest.join(':').split('/').pop();
  return `${provider[0].toUpperCase()}${provider.slice(1)} ${name}`;
}

function toRun(body, question, names) {
  const t = Object.fromEntries((body.trace || []).map((s) => [s.step_name, s.output || {}]));
  const get = (step, key) => (t[step] || {})[key] || 0;
  const chunks = body.chunks || [];
  const routedIds = get('routing_guard', 'routed_doc_ids') || [];
  const docs = get('candidate_pages', 'documents') || {};
  const cited = new Map();
  for (const c of chunks) {
    if (!(c.cited_by_claim_ids || []).length) continue;
    const k = `${c.document}\u0000${c.page}`;
    if (!cited.has(k)) cited.set(k, { doc: c.document, page: Number(c.page), text: [] });
    cited.get(k).text.push(c.text || '');
  }
  const counts = {
    routing_guard: [routedIds.length, 'documents'],
    candidate_pages: [Object.values(docs).reduce((a, d) => a + (d.available || 0), 0), 'pages'],
    page_survey: [get('page_survey', 'picked_pages'), 'pages picked'],
    element_retrieval: [get('element_retrieval', 'total'), 'passages'],
    element_triage: [get('element_verification', 'elements_seen'), 'ranked'],
    element_verification: [get('element_verification', 'elements_kept'), 'kept'],
    answer_generation: [get('answer_generation', 'draft_claims'), 'claims'],
    answer_verification: [get('answer_verification', 'accepted'), 'accepted'],
    citation_render: [cited.size, 'pages cited'],
  };
  return {
    question,
    status: body.status || '',
    latency_ms: Number(body.latency_ms) || 0,
    steps: (body.trace || []).map((s) => {
      const [count, unit] = counts[s.step_name] || [null, ''];
      return { id: s.step_name, label: LABELS[s.step_name] || s.step_name, ms: (s.output || {}).duration_ms || 0, count, unit };
    }),
    routed: routedIds.map((id) => names[id] || id),
    candidates: counts.candidate_pages[0],
    picked: counts.page_survey[0],
    passages: counts.element_retrieval[0],
    kept: counts.element_verification[0],
    claims: counts.answer_generation[0],
    withdrawn: get('answer_verification', 'rejected'),
    cited: [...cited.values()].map((c) => ({ ...c, text: c.text.join('\n\n') })),
    answer: parseAnswer(body.answer),
    limitations: ((body.coverage || {}).limitations || []).map(String),
    model: modelLabel(body.usage),
  };
}

module.exports = { toRun, parseAnswer };
