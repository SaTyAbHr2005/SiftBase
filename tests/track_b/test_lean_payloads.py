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


SOURCES=['Revenue from operations rose to 11,011.18 lakhs from 8,139.32 lakhs.',
         'The output floor is 65% from 1 January 2025.',
         'Management expects demand to stay strong.']


def write(tmp_path,query,statements,heading='Findings'):
    store=MemoryStore({'d':SOURCES})
    ev={f'E{i+1}':Evidence(el,['a1']) for i,el in enumerate(store.elements)}
    plan=task_plan(query)
    def respond(name,p):
        return {'sections':[{'heading':heading,'statements':[{'kind':'finding','text':text,'obligation_ids':['a1'],
                'cites':[{'evidence_id':eid,'span_ids':['S1']}]} for text,eid in statements]}],'task_results':[]}
    draft=generate_answer(FakeLLM(respond),query,plan,ev,{},settings(tmp_path,analytical_writer_mode='synthesis'))
    return [c.text for c in draft.claims]


def test_a_statement_that_drops_every_figure_of_its_source_is_written_in_the_source_words(tmp_path):
    assert write(tmp_path,'How did sales develop?',[('Sales grew strongly over the year.','E1')])==[SOURCES[0]]


def test_a_statement_borrowing_unsupported_question_wording_is_written_in_the_source_words(tmp_path):
    q='Under the original December 2017 timetable, what was the floor in 2025?'
    echo='Under the original December 2017 timetable, the floor was 65% in 2025.'
    assert write(tmp_path,q,[(echo,'E2')])==[SOURCES[1]]
    assert write(tmp_path,q,[(echo,'E2')],heading='Short answer')==[SOURCES[1]]  # wrong in a summary too


def test_statements_that_keep_a_figure_or_cite_no_figures_stay_as_written(tmp_path):
    kept=[('Revenue reached 11,011.18 lakhs, up from the year before.','E1'),('Management expects strong demand.','E3')]
    assert write(tmp_path,'How did sales develop?',kept)==[t for t,_ in kept]


def test_a_derived_figure_in_the_question_wording_stays_as_written(tmp_path):
    q='How much did sales grow in percent terms of last year?'
    derived='Sales were 135.3% in percent terms of last year.'
    assert write(tmp_path,q,[(derived,'E1')])==[derived]


def test_a_short_answer_summary_stays_as_written(tmp_path):
    store=MemoryStore({'d':SOURCES})
    ev={f'E{i+1}':Evidence(el,['a1']) for i,el in enumerate(store.elements)}
    plan=task_plan('How did sales develop?')
    def respond(name,p):
        return {'sections':[{'heading':'Short answer','statements':[{'kind':'finding','text':'Sales grew strongly.',
                'obligation_ids':['a1'],'cites':[{'evidence_id':'E1','span_ids':['S1']}]}]}],'task_results':[]}
    draft=generate_answer(FakeLLM(respond),plan.aspects[0].text,plan,ev,{},settings(tmp_path,analytical_writer_mode='synthesis'))
    assert [c.text for c in draft.claims]==['Sales grew strongly.']


def test_a_source_sentence_taken_from_a_table_cell_reads_as_plain_text():
    from kb.query.answer import _plain_span
    cell='|Output floor<br>|• <br>1 January 2025: 65%<br>• <br>1 January 2026: 70%|'
    assert _plain_span(cell)=='Output floor; 1 January 2025: 65%; 1 January 2026: 70%'
    assert _plain_span('It used 60 _,_ 000 paths.<sup>5</sup> It ran in C++.')=='It used 60,000 paths. It ran in C++.'


def test_two_statements_rewritten_to_the_same_source_sentence_appear_once(tmp_path):
    vague=[('Sales grew strongly.','E1'),('The company saw healthy growth in revenue.','E1')]
    assert write(tmp_path,'How did sales develop?',vague)==[SOURCES[0]]
