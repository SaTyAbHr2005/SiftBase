from dataclasses import replace
import json
import pytest
from kb.query.errors import BudgetExceeded
from kb.query.plan import plan_query,guard_routing,query_hints
from kb.query.runtime import QueryRuntime
from kb.query.types import QueryPlan,Aspect
from .helpers import Card,MemoryStore,FakeLLM,settings


def test_preserves_explicit_comparison_scopes(tmp_path):
    cards=[Card("a24","a24.pdf",issuer="Acme Holdings",period_year=2024),Card("a25","a25.pdf",issuer="Acme Holdings",period_year=2025),
           Card("b25","b25.pdf",issuer="Beta Group",period_year=2025)]
    store=MemoryStore({c.doc_id:["capital ratio"] for c in cards},cards)
    query="Compare Acme Holdings 2024 and 2025 with Beta Group 2025 capital ratio"
    cfg=settings(tmp_path,router_max_docs=1)
    plan=plan_query(FakeLLM(),query,cards,cfg)
    guarded,report=guard_routing(plan,query,cards,store,cfg)
    assert set(guarded.doc_ids)=={"a24","a25","b25"}
    assert len(plan.aspects)>=4


def test_confirmed_wrong_period_cannot_reenter_route(tmp_path):
    cards=[Card("old","old.pdf",period_year=2024,sibling_group="example"),Card("new","new.pdf",period_year=2025,sibling_group="example")]
    store=MemoryStore({c.doc_id:["Example Bank capital ratio"] for c in cards},cards)
    plan=QueryPlan("analytical",[Aspect("a1","capital ratio",["capital"])],["old","new"])
    guarded,report=guard_routing(plan,"Example Bank 2025 capital ratio",cards,store,settings(tmp_path))
    assert guarded.doc_ids==["new"]
    assert report["excluded"][0]["doc_id"]=="old"


def test_legacy_uncertain_metadata_is_soft(tmp_path):
    card=Card("old","old.pdf",period_year=2024,metadata_provenance={})
    store=MemoryStore({"old":["capital ratio"]},[card])
    plan=QueryPlan("analytical",[Aspect("a1","capital",["capital"])],["old"])
    guarded,_=guard_routing(plan,"Example Bank 2025 capital",[card],store,settings(tmp_path))
    assert guarded.doc_ids==["old"]
    assert guarded.limitations


def test_model_no_answer_does_not_stop_search(tmp_path):
    card=Card("d","d.pdf")
    store=MemoryStore({"d":["capital ratio 14 percent"]},[card])
    llm=FakeLLM(lambda n,p:{"answerable":False,"aspects":[],"documents":[]})
    plan=plan_query(llm,"capital ratio",[card],settings(tmp_path))
    guarded,report=guard_routing(plan,"capital ratio",[card],store,settings(tmp_path))
    assert guarded.answerable and guarded.doc_ids==["d"] and report["fallback"]


def test_planner_failure_falls_back_and_preserves_negation(tmp_path):
    def fail(n,p): raise RuntimeError("offline")
    plan=plan_query(FakeLLM(fail),"Which loans are not eligible?",[],settings(tmp_path))
    assert "not" in plan.aspects[0].keywords
    assert "planner_failed" in plan.notes


def test_large_catalogue_still_reaches_the_planner_with_the_relevant_document(tmp_path):
    cards=[Card(f"d{i}",f"d{i}.pdf",topics=["topic "*200]) for i in range(60)]
    store=MemoryStore({c.doc_id:["capital ratio" if c.doc_id=="d59" else "weather report"] for c in cards},cards)
    cfg=settings(tmp_path)
    ctx=QueryRuntime(cfg,FakeLLM())
    plan=plan_query(ctx.llm,"capital ratio",cards,cfg,ctx=ctx,store=store)
    assert "planner_failed" not in plan.notes
    sent=json.loads((ctx.path/"call_1_input.json").read_text(encoding="utf-8"))["payload"]["catalogue"]
    assert any('"d59"' in line for line in sent) and len(sent)<len(cards)


def test_planner_time_is_capped_and_verification_always_gets_time(tmp_path):
    class Timed(FakeLLM):
        deadlines=[]
        def scoped(self): return self
        def set_request_deadline(self,deadline): self.deadlines.append(deadline)
    cfg=settings(tmp_path,query_deadline_s=30,plan_deadline_s=10,verify_min_s=15)
    ctx=QueryRuntime(cfg,Timed())
    ctx.call("plan","system",{"query":"q"},100)
    assert Timed.deadlines[-1]==pytest.approx(ctx.started+10)
    ctx.deadline=ctx.started-1
    with pytest.raises(BudgetExceeded):
        ctx.check("verify")
    ctx.allow_verification()
    ctx.check("verify")


def test_planner_failure_records_why(tmp_path):
    def fail(n,p): raise RuntimeError("offline")
    plan=plan_query(FakeLLM(fail),"capital ratio",[],settings(tmp_path))
    assert "RuntimeError" in plan.notes


def test_obligation_overflow_is_visible(tmp_path):
    llm=FakeLLM(lambda n,p:{"aspects":[{"text":str(i)} for i in range(10)]})
    plan=plan_query(llm,"all risks",[],settings(tmp_path,max_obligations=2))
    assert len(plan.aspects)==2 and plan.limitations


def test_different_identifier_not_an_alias(tmp_path):
    cards=[Card("a","a.pdf",identifiers=["FR Doc. 2030-11111"]),Card("b","b.pdf",identifiers=["FR Doc. 2030-22222"])]
    store=MemoryStore({c.doc_id:["capital proposal"] for c in cards},cards)
    plan=QueryPlan("analytical",[Aspect("a1","proposal",["proposal"])],["a","b"])
    guarded,_=guard_routing(plan,"FR Doc. 2030-11111 capital proposal",cards,store,settings(tmp_path))
    assert guarded.doc_ids==["a"]


def test_null_or_wrong_planner_fields_have_safe_fallback(tmp_path):
    llm=FakeLLM(lambda n,p:{"intent":{},"aspects":[{"text":"capital","keywords":None}],"documents":None})
    result=plan_query(llm,"capital",[],settings(tmp_path))
    assert result.intent=="analytical" and result.aspects[0].keywords==["capital"]


def test_other_years_in_a_question_are_dates_inside_the_matched_source(tmp_path):
    # B30: the 2017 framework's timetable "from 1 January 2025" is not a missing 2025 report.
    card=Card("bcbs","bcbs.pdf",issuer="Basel Committee",period_year=2017)
    store=MemoryStore({"bcbs":["output floor 65% from 1 January 2025"]},[card])
    plan=QueryPlan("factoid",[Aspect("a1","output floor calibration",["floor"],"Basel Committee","December 2017 / 1 January 2025")],["bcbs"])
    guarded,_=guard_routing(plan,"Under the Basel Committee's December 2017 timetable, what was the output floor from 1 January 2025?",[card],store,settings(tmp_path))
    assert not guarded.limitations
    # A comparison still needs every year it names.
    guarded,_=guard_routing(plan,"Compare the Basel Committee 2017 and 2025 output floor",[card],store,settings(tmp_path))
    assert guarded.limitations==["Requested period 2025 not confirmed in routed source metadata"]


def test_a_prose_period_containing_the_year_needs_no_extra_obligation(tmp_path):
    card=Card("bcbs","bcbs.pdf",issuer="Basel Committee",period_year=2017)
    reply={"intent":"factoid","aspects":[{"text":"output floor calibration","keywords":["floor"],"entity":"Basel Committee",
           "period":"December 2017 / 1 January 2025"}],"documents":[{"doc_id":"bcbs"}]}
    plan=plan_query(FakeLLM(lambda n,p:reply),"Basel Committee December 2017 output floor from 1 January 2025?",[card],settings(tmp_path))
    assert len(plan.aspects)==1


def test_requested_version_is_added_when_the_planner_only_picked_another(tmp_path):
    cards=[Card("old","old.pdf",period_year=2024,sibling_group="guide"),Card("new","new.pdf",period_year=2025,sibling_group="guide")]
    store=MemoryStore({c.doc_id:["installation steps"] for c in cards},cards)
    plan=QueryPlan("analytical",[Aspect("a1","installation",["install"])],["old"])
    guarded,report=guard_routing(plan,"Guide 2025 installation steps",cards,store,settings(tmp_path))
    assert guarded.doc_ids==["new"] and report["excluded"][0]["doc_id"]=="old" and report["added_by_entity"]==["new"]


def test_a_year_about_events_does_not_rule_out_an_unrelated_document(tmp_path):
    # A 2023 history of the 2020 flood is still a valid source for a question about 2020.
    cards=[Card("history","history.pdf",period_year=2023),Card("other","other.pdf",period_year=2021)]
    store=MemoryStore({c.doc_id:["flood response"] for c in cards},cards)
    plan=QueryPlan("analytical",[Aspect("a1","flood",["flood"])],["history"])
    guarded,report=guard_routing(plan,"What happened in the 2020 flood?",cards,store,settings(tmp_path))
    assert guarded.doc_ids==["history"] and report["excluded"]==[]


def test_a_guessed_year_never_rules_out_a_document(tmp_path):
    cards=[Card("old","old.pdf",period_year=2024,sibling_group="guide",metadata_provenance={}),Card("new","new.pdf",period_year=2025,sibling_group="guide")]
    store=MemoryStore({c.doc_id:["steps"] for c in cards},cards)
    plan=QueryPlan("analytical",[Aspect("a1","steps",["steps"])],["old","new"])
    guarded,_=guard_routing(plan,"Guide 2025 steps",cards,store,settings(tmp_path))
    assert guarded.doc_ids==["old","new"]


def test_routing_guard_works_on_real_document_cards(tmp_path):
    from kb.models import DocCard
    def real(doc_id,year):
        return DocCard(doc_id,doc_id+".pdf",doc_id,"manual","Acme",[],str(year),year,None,"",[],"",10,[],"acme",{},{"period_year":"source","identifiers":"source"})
    cards=[real("v1",2024),real("v2",2025)]
    store=MemoryStore({c.doc_id:["pump settings"] for c in cards},cards)
    plan=QueryPlan("analytical",[Aspect("a1","pump",["pump"])],["v1","v2"])
    guarded,report=guard_routing(plan,"Pump settings in 2025",cards,store,settings(tmp_path))
    assert guarded.doc_ids==["v2"] and report["excluded"][0]["doc_id"]=="v1"


def test_identifiers_from_any_field_are_recognised(tmp_path):
    cards=[Card("a","a.pdf",identifiers=["RFC 9110"]),Card("b","b.pdf",identifiers=["RFC 9112"])]
    store=MemoryStore({c.doc_id:["http semantics"] for c in cards},cards)
    plan=QueryPlan("analytical",[Aspect("a1","http",["http"])],["a","b"])
    guarded,_=guard_routing(plan,"What does RFC 9110 say about status codes?",cards,store,settings(tmp_path))
    assert guarded.doc_ids==["a"]
