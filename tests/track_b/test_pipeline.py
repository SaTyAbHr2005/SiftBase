from dataclasses import replace
import json
import pytest
from kb.query.pipeline import answer_query,STEP_NAMES
from kb.query.runtime import QueryRuntime
from kb.query.errors import QueryError,BudgetExceeded
from kb.query.observability import LocalSink
from .helpers import MemoryStore,FakeLLM,settings,Card


def run(tmp_path,store=None,llm=None,**kw):
    return answer_query("demo","capital ratio",store=store or MemoryStore({"a":["Capital ratio was 14 percent."]}),
                        generation_id="g1",settings=settings(tmp_path,**kw),llm=llm or FakeLLM(),sink=LocalSink())


def test_ten_stage_trace_and_source_fidelity(tmp_path):
    store=MemoryStore({"a":["Capital ratio was 14 percent."]})
    result=run(tmp_path,store)
    assert [t["step_name"] for t in result["trace"]]==STEP_NAMES
    assert all(set(t)=={"step_name","description","input","output"} for t in result["trace"])
    assert result["chunks"][0]["content"]==store.elements[0].text
    assert result["status"]=="answered"
    assert result["usage"]["cost_usd"] is None
    assert result["usage"]["input_tokens"]==400  # plan, verify, extractive answer, claim check
    assert (tmp_path/"runs"/result["request_id"]/"writer_context.json").exists()


def test_no_candidates_no_model_answer_and_all_trace_steps(tmp_path):
    llm=FakeLLM()
    result=answer_query("demo","xyz absent",store=MemoryStore({}),generation_id="g1",settings=settings(tmp_path),llm=llm,sink=LocalSink())
    assert result["status"]=="no_answer" and not result["chunks"]
    assert len(result["trace"])==10
    assert "answer" not in [name for name,p in llm.calls]


def test_provider_failure_never_reads_as_not_found_in_the_documents(tmp_path):
    def respond(n,p):
        if n=="verify": raise RuntimeError("provider offline")
        return FakeLLM.default(n,p)
    result=run(tmp_path,llm=FakeLLM(respond))
    assert result["status"]=="no_answer" and "model providers" in result["answer"] and "No supporting information" not in result["answer"]
    assert "Verification stopped after a provider/schema failure" in result["coverage"]["limitations"]


def test_writer_visible_unused_context_is_returned(tmp_path):
    store=MemoryStore({"a":["Capital ratio was 14 percent.\n\nCapital buffer was 3 percent."]})
    def respond(n,p):
        result=FakeLLM.default(n,p)
        if n=="answer" and "sections" in result: result["sections"][0]["statements"]=result["sections"][0]["statements"][:1]
        elif n=="answer": result["selections"]=result["selections"][:1]
        return result
    result=run(tmp_path,store,FakeLLM(respond))
    assert len(result["chunks"])==2
    assert any(c["evidence_role"]=="writer_context" for c in result["chunks"])


def test_missing_period_keeps_the_only_source_and_states_the_limitation(tmp_path):
    # No other version exists, and a 2024 plan can still state a 2025 target, so the source stays and the gap is reported.
    cards=[Card("old","old.pdf",period_year=2024)]
    result=answer_query("demo","Example Bank 2025 capital",store=MemoryStore({"old":["Capital 12 in FY2024."]},cards),generation_id="g1",settings=settings(tmp_path),llm=FakeLLM(),sink=LocalSink())
    assert "Requested period 2025 not confirmed in routed source metadata" in result["coverage"]["limitations"]


def test_other_documents_are_only_searched_when_routing_is_unsettled(tmp_path):
    cards=[Card("a","a.pdf",issuer="Acme Works"),Card("b","b.pdf",issuer="Beta Works")]
    store=MemoryStore({"a":["Capital ratio was 14 percent."],"b":["Capital ratio was 9 percent."]},cards)
    routed=lambda n,p:{**FakeLLM.default(n,p),"documents":[{"doc_id":"a"}]} if n=="plan" else FakeLLM.default(n,p)
    result=answer_query("demo","capital ratio",store=store,generation_id="g1",settings=settings(tmp_path),llm=FakeLLM(routed),sink=LocalSink())
    step=next(s for s in result["trace"] if s["step_name"]=="candidate_pages")
    assert step["output"]["escape_pages"]==[] and {c["doc_id"] for c in result["chunks"]}=={"a"}


def test_query_past_its_deadline_returns_a_response_not_an_error(tmp_path):
    def respond(n,p):
        import time
        if n=="plan":time.sleep(0.2)
        return FakeLLM.default(n,p)
    result=run(tmp_path,llm=FakeLLM(respond),query_deadline_s=0.1,verify_min_s=0)
    assert result["status"]=="no_answer" and len(result["trace"])==10
    assert "No evidence verified before the verification budget was exhausted" in result["coverage"]["limitations"]


def test_every_provider_down_still_returns_a_response(tmp_path):
    from kb.query.pipeline import BUDGET_TEXT
    def down(n,p): raise RuntimeError("all rate limited")
    result=run(tmp_path,llm=FakeLLM(down))
    assert result["status"]=="no_answer" and result["answer"]==BUDGET_TEXT and len(result["trace"])==10


@pytest.mark.parametrize("failing",["answer","answer_verify"])
def test_answer_step_failure_keeps_the_verified_evidence(tmp_path,failing):
    def respond(n,p):
        if n==failing: raise RuntimeError("all rate limited")
        return FakeLLM.default(n,p)
    result=run(tmp_path,llm=FakeLLM(respond))
    assert result["status"]=="partial" and result["chunks"]
    assert any("could not be" in x for x in result["coverage"]["limitations"])


def test_slow_planner_still_leaves_verification_time_for_an_answer(tmp_path):
    def respond(n,p):
        import time
        if n=="plan":time.sleep(0.2)
        return FakeLLM.default(n,p)
    result=run(tmp_path,llm=FakeLLM(respond),query_deadline_s=0.1)
    assert result["status"]=="answered"


def test_verify_call_cut_off_by_the_deadline_is_not_reported_as_a_provider_failure(tmp_path):
    import time
    def respond(n,p):
        if n=="verify":
            time.sleep(0.25);raise RuntimeError("read timed out")
        return FakeLLM.default(n,p)
    result=run(tmp_path,llm=FakeLLM(respond),query_deadline_s=0.2,verify_min_s=0)
    assert result["status"]=="no_answer"
    step=next(s for s in result["trace"] if s["step_name"]=="element_verification")["output"]
    assert step["failed_batches"]==0 and "Verification stopped after a provider/schema failure" not in step["limitations"]
    assert result["usage"]["input_tokens"] is not None


def test_strict_observability_cannot_use_noop_sink(tmp_path):
    with pytest.raises(QueryError,match="Langfuse"):
        run(tmp_path,strict_observability=True)


def test_deadline_checked_before_model_call(tmp_path):
    runtime=QueryRuntime(settings(tmp_path),FakeLLM(),LocalSink());runtime.deadline=0
    with pytest.raises(BudgetExceeded): runtime.call("plan","system",{},100)
    assert runtime.calls==0


def test_budget_does_not_silently_become_corpus_absence(tmp_path):
    from kb.query.pipeline import BUDGET_TEXT
    result=run(tmp_path,max_llm_calls=1)  # a normal response (HTTP 200), not a 504 that scores zero
    assert result["status"]=="no_answer" and result["answer"]==BUDGET_TEXT
    assert "No evidence verified before the verification budget was exhausted" in result["coverage"]["limitations"]


def test_same_source_in_two_collections_keeps_generation(tmp_path):
    store=MemoryStore({"a":["Capital ratio was 14 percent."]})
    a=answer_query("one","capital",store=store,generation_id="generation_one",settings=settings(tmp_path),llm=FakeLLM(),sink=LocalSink())
    b=answer_query("two","capital",store=store,generation_id="generation_two",settings=settings(tmp_path),llm=FakeLLM(),sink=LocalSink())
    assert a["generation_id"]=="generation_one" and b["generation_id"]=="generation_two"
    assert a["request_id"]!=b["request_id"]


def test_survey_reads_most_relevant_pages_first(tmp_path):
    # 30 filler pages, the only relevant one last: page order would survey it last and lose it to the budget.
    from kb.query.candidates import candidate_pages
    from kb.query.screen import survey_pages
    from kb.query.types import QueryPlan,Aspect
    store=MemoryStore({"a":["Unrelated filler text."]*29+["Capital ratio was 14 percent."]})
    plan=QueryPlan("analytical",[Aspect("a1","capital ratio",["capital","ratio"])],["a"])
    pool,lexical,_=candidate_pages(store,plan,"capital ratio",None,settings(tmp_path))
    assert pool["a"][0]==30
    seen=[]
    def responder(name,p):
        seen.extend(c["page_no"] for c in p["cards"]);return {"pages":[]}
    survey_pages(FakeLLM(responder),store,plan,"capital ratio",pool,{},settings(tmp_path,survey_batch_cards=5))
    assert seen[0]==30


def test_call_many_runs_concurrently_and_keeps_budget_order(tmp_path):
    import time
    def slow(name,p):
        time.sleep(0.3);return {"ok":p["i"]}
    runtime=QueryRuntime(settings(tmp_path,max_llm_calls=3),FakeLLM(slow),LocalSink())  # answer calls have their own pool
    t=time.monotonic();out=runtime.call_many("verify","system",[{"i":i} for i in range(4)],100)
    assert time.monotonic()-t<0.8  # three 0.3 s calls at once, not 0.9 s in a row
    assert out[:3]==[{"ok":0},{"ok":1},{"ok":2}] and isinstance(out[3],BudgetExceeded)
    assert [e["call"] for e in runtime.events]==[1,2,3] and runtime.calls==3


def test_failed_claim_check_batch_removes_only_its_claims(tmp_path):
    from kb.query.answer import verify_answer
    from kb.query.types import AnswerDraft,Claim,Evidence
    store=MemoryStore({"a":["x"]})
    numbered={"E1":Evidence(store.elements[0],["a1"])}
    claims=[Claim(f"c{i}","x",["E1"],["a1"],[{"evidence_id":"E1","quote":"x"}]) for i in range(1,13)]
    def respond(name,p):
        ids=[c["claim_id"] for c in p["claims"]]
        if "c1" in ids:
            raise QueryError("MODEL_SCHEMA","bad",503)
        return {"verdicts":[{"claim_id":i,"verdict":"supported"} for i in ids]}
    draft,report=verify_answer(FakeLLM(respond),AnswerDraft(claims,"answered"),numbered,settings(tmp_path))
    assert report["accepted"]==6 and "1 claim-check batches failed" in draft.limitations


def _wave_case(tmp_path,keep,**kw):
    """60 candidates (8 batches = 8 per batch) across 60 pages; keep(batch_number, element) decides what is kept."""
    from kb.query.screen import verify_elements
    from kb.query.types import QueryPlan,Aspect,Candidate
    store=MemoryStore({"a":[f"Fact number {i} about pumps." for i in range(160)]})
    plan=QueryPlan("analytical",[Aspect("a1","pumps",["pumps"])],["a"])
    middle=[Candidate(e,["a1"],["survey_high"]) for e in store.elements]
    batches=[]
    def respond(n,p):
        with_lock.append(1);number=len(with_lock)
        batches.append(number)
        return {"keep":[{"id":e["id"],"aspects":["a1"],"support_span_ids":list(e["source_spans"])[:1],"relevance":"direct"}
                        for e in p["elements"] if keep(number,e)]}
    with_lock=[]
    return verify_elements(FakeLLM(respond),store,plan,"pumps",middle,settings(tmp_path,verify_chars_total=10**7,**kw)),batches


def test_verification_stops_after_a_wave_that_adds_nothing(tmp_path):
    (kept,report),batches=_wave_case(tmp_path,lambda n,e:n<=4)
    assert len(batches)==8+4 and report["stopped_early"]  # first wave, then one more wave proves nothing new
    assert report["elements_seen"]==12*8 and report["remaining_candidates"]==160-12*8


def test_verification_continues_while_new_pages_keep_appearing_up_to_the_cap(tmp_path):
    (kept,report),batches=_wave_case(tmp_path,lambda n,e:True)
    assert len(batches)==16 and report["stopped_early"] and len(kept)==16*8


def test_verification_stops_when_later_waves_rarely_keep_anything(tmp_path):
    (kept,report),batches=_wave_case(tmp_path,lambda n,e:n<=8 or int(e["id"][1:])==1)
    assert len(batches)==12 and report["stopped_early"]


def test_a_requested_topic_without_evidence_earns_another_wave(tmp_path):
    from kb.query.screen import verify_elements
    from kb.query.types import QueryPlan,Aspect,Candidate
    store=MemoryStore({"a":[f"Fact number {i} about pumps." for i in range(160)]})
    tasks=[{"id":"T1","text":"pump pressure","operation":"lookup","obligation_ids":["a1"],"source_roles":[],"query_anchor":"pumps"}]
    plan=QueryPlan("analytical",[Aspect("a1","pumps",["pumps"])],["a"],tasks=tasks)
    calls=[]
    def respond(n,p):
        calls.append(1)
        tagged=[] if len(calls)<=12 else ["T1"]
        return {"keep":[{"id":e["id"],"aspects":["a1"],"support_span_ids":list(e["source_spans"])[:1],"relevance":"direct","requirement_ids":tagged} for e in p["elements"][:1]]}
    kept,report=verify_elements(FakeLLM(respond),store,plan,"pumps",[Candidate(e,["a1"],["survey_high"]) for e in store.elements],settings(tmp_path,verify_chars_total=10**7))
    assert len(calls)==16  # a keep rate this low would have stopped at 12 without the uncovered topic
