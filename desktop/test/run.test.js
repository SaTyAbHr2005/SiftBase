const test = require('node:test');
const assert = require('node:assert');
const { toRun } = require('../lib/run');

const body = {
  status: 'partial', latency_ms: 21400,
  answer: '## Short answer\n- Notice is three months. [Lease.pdf p7]\n- Lock-in is 18 months. [Lease.pdf p7; Amend.pdf p2]\nPlain line without a bullet.',
  chunks: [
    { document: 'Lease.pdf', page: 7, text: 'Clause 14.2 early termination.', cited_by_claim_ids: ['c1'] },
    { document: 'Lease.pdf', page: 7, text: 'Three months notice.', cited_by_claim_ids: ['c2'] },
    { document: 'Amend.pdf', page: 2, text: 'Lock-in is 18 months.', cited_by_claim_ids: ['c2'] },
    { document: 'Lease.pdf', page: 9, text: 'Kept, not cited.', cited_by_claim_ids: [] },
  ],
  coverage: { limitations: ['Floor plan has no text.'] },
  usage: { models: ['cloudflare:@cf/google/gemma-4-26b-a4b-it'] },
  trace: [
    { step_name: 'query_planning', output: { duration_ms: 3100 } },
    { step_name: 'routing_guard', output: { routed_doc_ids: ['d1', 'd2'], duration_ms: 0 } },
    { step_name: 'candidate_pages', output: { documents: { d1: { available: 18 }, d2: { available: 3 } }, duration_ms: 420 } },
    { step_name: 'page_survey', output: { picked_pages: 6 } },
    { step_name: 'element_retrieval', output: { total: 38, duration_ms: 980 } },
    { step_name: 'element_triage', output: { duration_ms: 610 } },
    { step_name: 'element_verification', output: { elements_seen: 38, elements_kept: 9, duration_ms: 5200 } },
    { step_name: 'answer_generation', output: { draft_claims: 4, duration_ms: 7400 } },
    { step_name: 'answer_verification', output: { accepted: 3, rejected: 1, duration_ms: 3600 } },
    { step_name: 'citation_render', output: {} },
  ],
};

test('toRun turns a /query response into the replayed run', () => {
  const r = toRun(body, 'When can the tenant leave?', { d1: 'Lease.pdf', d2: 'Amend.pdf' });
  assert.equal(r.question, 'When can the tenant leave?');
  assert.deepEqual(r.routed, ['Lease.pdf', 'Amend.pdf']);
  assert.deepEqual([r.candidates, r.picked, r.passages, r.kept, r.claims, r.withdrawn], [21, 6, 38, 9, 4, 1]);
  assert.deepEqual(r.cited.map((c) => [c.doc, c.page, c.text]),
    [['Lease.pdf', 7, 'Clause 14.2 early termination.\n\nThree months notice.'], ['Amend.pdf', 2, 'Lock-in is 18 months.']]);
  assert.equal(r.answer[0].heading, 'Short answer');
  assert.deepEqual(r.answer[0].lines[1], { text: 'Lock-in is 18 months.', cites: [{ doc: 'Lease.pdf', page: 7 }, { doc: 'Amend.pdf', page: 2 }] });
  assert.equal(r.answer[0].lines[2].text, 'Plain line without a bullet.');
  assert.equal(r.steps.length, 10);
  assert.deepEqual([r.steps[0].label, r.steps[0].ms, r.steps[0].count], ['Plan', 3100, null]);
  assert.deepEqual([r.steps[6].count, r.steps[6].unit], [9, 'kept']);
  assert.equal(r.model, 'Cloudflare gemma-4-26b-a4b-it');
  assert.deepEqual(r.limitations, ['Floor plan has no text.']);
});

test('a file name with brackets still gives its citation', () => {
  const r = toRun({ answer: '- Fees rose 4%. [Report [final].pdf p3]', trace: [] }, 'q', {});
  assert.deepEqual(r.answer[0].lines[0], { text: 'Fees rose 4%.', cites: [{ doc: 'Report [final].pdf', page: 3 }] });
});

test('control characters from the source are dropped', () => {
  const r = toRun({ answer: '- 2) \u0007Use of harvested rainwater. [a.pdf p9]', trace: [] }, 'q', {});
  assert.equal(r.answer[0].lines[0].text, '2) Use of harvested rainwater.');
});

test('an answer with no heading still gets one section', () => {
  const r = toRun({ answer: 'Nothing found in these documents.', trace: [] }, 'q', {});
  assert.deepEqual(r.answer, [{ heading: 'Answer', lines: [{ text: 'Nothing found in these documents.', cites: [] }] }]);
  assert.equal(r.steps.length, 0);
  assert.equal(r.model, 'model unknown');
});
