"""The evidence check names each document once per call, and the writer never asks for more output than the
provider allows."""
from kb.query.answer import generate_answer, _writer_limit
from kb.query.screen import verify_elements
from kb.query.types import Aspect, QueryPlan, Candidate, Evidence
from kb.query.worksheet import compile_tasks
from .helpers import MemoryStore, FakeLLM, settings


def task_plan(query, n_tasks=1):
    aspects=[Aspect('a1',query,[query])]
    tasks=compile_tasks(query,aspects,[{'operation':'assess','description':f'{query} part {i}','query_anchor':query,
                                        'obligation_ids':['a1'],'source_roles':[query]} for i in range(n_tasks)])
    return QueryPlan('analytical',aspects,['d','e'],tasks=tasks)


def test_verify_payload_names_each_document_once(tmp_path):
    store=MemoryStore({'d':[f'Trial count {i}.' for i in range(5)],'e':[f'Trial total {i}.' for i in range(5)]})
    candidates=[Candidate(el,['a1'],['fts']) for el in store.elements]
    seen=[]
    def respond(name,p):
        seen.append(p);return {'keep':[]}
    verify_elements(FakeLLM(respond),store,task_plan('Assess trials'),'Assess trials',candidates,settings(tmp_path))
    p=seen[0]
    assert all('navigation_metadata' not in e for e in p['elements'])
    assert set(p['documents'])=={e['doc_id'] for e in p['elements']}
    assert p['documents']['d']['title']=='d'


def test_worksheet_never_asks_for_more_output_than_the_provider_allows(tmp_path):
    store=MemoryStore({'d':[f'Revenue in year {i} was {1000+i},011.18 lakhs.' for i in range(10)]})
    ev={f'E{i+1}':Evidence(el,['a1']) for i,el in enumerate(store.elements)}
    plan=task_plan('Assess revenue',n_tasks=8)
    seen=[]
    def respond(name,p):
        if name=='answer':
            seen.append(p);return {'sections':[],'task_results':[]}
        return {'verdicts':[]}
    generate_answer(FakeLLM(respond),plan.aspects[0].text,plan,ev,{},settings(tmp_path,analytical_writer_mode='synthesis'))
    assert len(plan.tasks)==8
    assert _writer_limit(seen[0])<=8192  # Cloudflare's output ceiling; above it a cut-off reply can no longer split
