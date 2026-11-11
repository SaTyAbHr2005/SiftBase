"""The picker writer: the model only chooses which source sentences answer each task, and the answer quotes them."""
from kb.query.answer import generate_answer, verify_answer, render_verified
from kb.query.types import Evidence
from .helpers import MemoryStore, FakeLLM, settings
from .test_lean_payloads import task_plan

DOCS={'heston':['The parameter sigma raises the kurtosis of spot returns by 20% in the 1993 sample.\n\n'
                'The correlation parameter rho sets the skewness of returns in 61% of the test cases.'],
      'bergomi':['The rough Bergomi model has 4 parameters and 11 in its piecewise constant form.']}
QUERY='Which parameters of the volatility model control the smile?'


def run(tmp_path,respond,docs=DOCS,n_tasks=1):
    store=MemoryStore(docs)
    ev={f'E{i+1}':Evidence(el,['a1']) for i,el in enumerate(store.elements)}
    cards={c.doc_id:c for c in store._cards}
    llm=FakeLLM(respond)
    s=settings(tmp_path,analytical_writer_mode='pick')
    draft=generate_answer(llm,QUERY,task_plan(QUERY,n_tasks),ev,cards,s)
    return draft,llm,ev,cards,s


def picker(choose):
    """A fake picker: `choose(units)` maps the offered units to {task_id: [unit ids]}."""
    def respond(name,p):
        if name=='answer' and 'documents' in p:
            units=[u for d in p['documents'] for u in d['units']]
            return {'tasks':[{'task_id':t,'unit_ids':ids} for t,ids in choose(units).items()]}
        return FakeLLM.default(name,p)
    return respond


def unit(units,word):
    return next(u['id'] for u in units if word in u['text'])


def test_the_picker_sees_source_sentences_under_their_document_names(tmp_path):
    _,llm,*_=run(tmp_path,picker(lambda us:{'T1':[]}))
    p=next(p for name,p in llm.calls if name=='answer')
    assert {d['document'] for d in p['documents']}=={'heston.pdf','bergomi.pdf'}
    assert all({'id','page','text'}<=set(u) for d in p['documents'] for u in d['units'])
    assert 'facts' not in p and 'max_statements' not in p  # it chooses; it never writes


def test_picked_sentences_become_the_answer_word_for_word(tmp_path):
    draft,llm,ev,cards,s=run(tmp_path,picker(lambda us:{'T1':[unit(us,'kurtosis')]}))
    [c]=draft.claims
    assert c.text=='The parameter sigma raises the kurtosis of spot returns by 20% in the 1993 sample.'
    assert c.verification=='picked' and c.requirement_ids==['T1'] and c.section==''
    assert any(c.text in q['quote'] for q in c.quotes)
    checked,report=verify_answer(llm,draft,ev,s,query=QUERY)
    assert [x.claim_id for x in checked.claims]==[c.claim_id]
    assert not any(name=='answer_verify' for name,_ in llm.calls)  # its own source text needs no wording check
    assert '[heston.pdf p1]' in render_verified(checked,ev,cards)[0]


def test_a_sentence_a_longer_one_already_contains_is_not_offered(tmp_path):
    docs={'d':['As the notes say, the model has 4 parameters.\n\nThe model has 4 parameters.']}
    _,llm,*_=run(tmp_path,picker(lambda us:{'T1':[]}),docs=docs)
    p=next(p for name,p in llm.calls if name=='answer')
    assert [u['text'] for d in p['documents'] for u in d['units']]==['As the notes say, the model has 4 parameters.']


def test_picks_over_the_task_budget_and_unknown_ids_are_dropped(tmp_path):
    docs={'d':['\n\n'.join(f'Fund {i} returned {10+i}% in the year to March.' for i in range(9))]}
    # Two tasks share the writer's budget of 12 statements: 6 each.
    choose=lambda us:{'T1':[u['id'] for u in us]+['U99'],'T2':[us[0]['id'],us[-1]['id']]}
    draft,*_=run(tmp_path,picker(choose),docs=docs,n_tasks=2)
    t1=[c for c in draft.claims if 'T1' in c.requirement_ids];t2=[c for c in draft.claims if 'T2' in c.requirement_ids]
    assert len(t1)==6 and len(draft.claims)==7  # the sentence both tasks chose is shown once
    assert [c.text for c in t2]==['Fund 0 returned 10% in the year to March.','Fund 8 returned 18% in the year to March.']


def test_a_sentence_leaning_on_the_one_before_keeps_it(tmp_path):
    docs={'d':['The routine prices options by simulation with 60,000 paths per test case. It took 2 milliseconds per '
               'evaluation in the 2020 tests.']}
    draft,*_=run(tmp_path,picker(lambda us:{'T1':[unit(us,'milliseconds')]}),docs=docs)
    assert [c.text for c in draft.claims]==['The routine prices options by simulation with 60,000 paths per test case. '
                                            'It took 2 milliseconds per evaluation in the 2020 tests.']


def test_abbreviations_do_not_end_a_sentence(tmp_path):
    from kb.query.answer import _UNIT_SPLIT
    for s in ('U.S. Treasury yields rose 5% in 2020.','Peers, e.g. Acme Ltd. and Beta Inc. grew 4%.'):
        assert _UNIT_SPLIT.split(s)==[s]


def test_a_sentence_answering_two_tasks_is_shown_once_and_counts_for_both(tmp_path):
    draft,llm,ev,cards,s=run(tmp_path,picker(lambda us:{'T1':[unit(us,'kurtosis')],'T2':[unit(us,'kurtosis')]}),n_tasks=2)
    [c]=draft.claims
    assert c.requirement_ids==['T1','T2']
    checked,_=verify_answer(llm,draft,ev,s,query=QUERY)
    assert all(t['status']=='supported' for t in checked.requested_topics)


def test_a_task_nothing_was_picked_for_stays_unresolved(tmp_path):
    draft,llm,ev,cards,s=run(tmp_path,picker(lambda us:{'T1':[unit(us,'kurtosis')],'T2':[]}),n_tasks=2)
    checked,_=verify_answer(llm,draft,ev,s,query=QUERY)
    assert [t['completion'] for t in checked.worksheet]==['supported','unresolved'] and checked.status=='partial'


def anchored_plan(query,anchors):
    """A plan whose task descriptions restate the query with a premise the sources never confirm."""
    from kb.query.types import Aspect, QueryPlan
    from kb.query.worksheet import compile_tasks
    aspects=[Aspect('a1',query,[query])]
    tasks=compile_tasks(query,aspects,[{'operation':'lookup','description':f'Identify the {a} as set out in the original 2017 timetable',
                                        'query_anchor':a,'obligation_ids':['a1'],'source_roles':[a]} for a in anchors])
    return QueryPlan('analytical',aspects,['d'],tasks=tasks)


SURROGATE={'paper':['The surrogate matched the pricer within 0.35% in the 2020 tests.\n\n'
                    'The surrogate ran 40,000 times faster than the pricer in the 2020 tests.']}


def answer_for(tmp_path,query,anchors,choose):
    store=MemoryStore(SURROGATE)
    ev={f'E{i+1}':Evidence(el,['a1']) for i,el in enumerate(store.elements)}
    cards={c.doc_id:c for c in store._cards}
    draft=generate_answer(FakeLLM(picker(choose)),query,anchored_plan(query,anchors),ev,cards,
                          settings(tmp_path,analytical_writer_mode='pick'))
    return draft,render_verified(draft,ev,cards)[0]


def test_headings_are_the_readers_own_topic_words_never_the_planners_sentence(tmp_path):
    # The picked sentences are the source's words; a heading must not add a claim the source does not make.
    query='What accuracy and what speed did the surrogate reach under the original 2017 timetable?'
    draft,text=answer_for(tmp_path,query,['accuracy','speed'],
                          lambda us:{'T1':[unit(us,'0.35%')],'T2':[unit(us,'40,000')]})
    assert [c.section for c in draft.claims]==['accuracy','speed']
    assert '## Accuracy\n- The surrogate matched' in text and '## Speed\n- The surrogate ran' in text
    assert '2017 timetable' not in text and 'Identify' not in text


def test_no_heading_when_a_task_is_named_by_a_clause_or_stands_alone(tmp_path):
    query='What accuracy did the surrogate reach under the original 2017 timetable and how fast was it?'
    # A clause from the query can carry its premise, so it is not a heading; then no task gets one.
    draft,text=answer_for(tmp_path,query,['accuracy','reach under the original 2017 timetable and how fast was it'],
                          lambda us:{'T1':[unit(us,'0.35%')],'T2':[unit(us,'40,000')]})
    assert [c.section for c in draft.claims]==['','']
    assert '##' not in text and '2017 timetable' not in text
    # One task has nothing to separate.
    draft,text=answer_for(tmp_path,query,['accuracy'],lambda us:{'T1':[unit(us,'0.35%')]})
    assert [c.section for c in draft.claims]==[''] and '##' not in text and 'Identify' not in text
    # Two tasks under one phrase, or a phrase with no word in it, name nothing.
    both=lambda us:{'T1':[unit(us,'0.35%')],'T2':[unit(us,'40,000')]}
    for anchors in (['accuracy','accuracy'],['accuracy','?']):
        draft,text=answer_for(tmp_path,query,anchors,both)
        assert [c.section for c in draft.claims]==['',''] and '##' not in text


def test_a_malformed_task_id_from_the_picker_does_not_crash_the_query(tmp_path):
    def respond(name,p):
        if name=='answer' and 'documents' in p:
            return {'tasks':[{'task_id':['T1'],'unit_ids':['U1']},{'task_id':{'id':'T1'},'unit_ids':['U1']}]}
        return FakeLLM.default(name,p)
    draft,llm,*_=run(tmp_path,respond)
    assert all(c.verification!='picked' for c in draft.claims)  # nothing usable was picked: the task writer ran
    assert any(name=='answer' and 'max_statements' in p for name,p in llm.calls)


def test_a_failed_picker_falls_back_to_the_task_writer(tmp_path):
    def respond(name,p):
        return {'unexpected':True} if name=='answer' and 'documents' in p else FakeLLM.default(name,p)
    draft,llm,*_=run(tmp_path,respond)
    assert any(name=='answer' and 'max_statements' in p for name,p in llm.calls)
    assert all(c.verification!='picked' for c in draft.claims)
