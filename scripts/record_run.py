"""Record one local query in the API's response shape, for the site's recorded run.

python -m scripts.record_run --collection train --env-file .env --out web/data/recorded-run.json "question"
Never pass a benchmark question: the site shows this run in full.
"""
import argparse
import json
import sqlite3
import time
from pathlib import Path


def main():
    p=argparse.ArgumentParser();p.add_argument("query");p.add_argument("--collection",required=True)
    p.add_argument("--out",required=True);p.add_argument("--env-file")
    args=p.parse_args()
    if args.env_file:
        from scripts.check_langfuse import load_local_env
        load_local_env(args.env_file)
    from kb.routes.query import legacy_bind
    from kb.query.pipeline import answer_query
    s=legacy_bind(args.collection)
    try:
        result=answer_query(args.collection,args.query,store=s.store,generation_id=s.generation_id,settings=s.settings,
                            llm=s.llm,embedder=s.embedder,reranker=s.reranker,sink=s.sink)
    finally:
        if s.close_store:
            s.store.close()
    body=result if isinstance(result,dict) else result.model_dump() if hasattr(result,"model_dump") else vars(result)
    body=public(json.loads(json.dumps(body,default=str)),args.query,time.strftime("%Y-%m-%d"),doc_names(args.collection))
    Path(args.out).write_text(json.dumps(body,indent=1,ensure_ascii=False),encoding="utf-8")
    print(body["status"],body["funnel"])


def trim(v,n=8):
    """Shorten long lists inside trace outputs; the site shows a summary, not every score."""
    if isinstance(v,list):
        return [trim(x,n) for x in v[:n]]+([f"... {len(v)-n} more"] if len(v)>n else [])
    if isinstance(v,dict):
        return {k:trim(x,n) for k,x in v.items()}
    return v


def doc_names(collection):
    from kb.config import get_settings
    from kb.registry import Registry
    _,directory=Registry(get_settings()).active_dir(collection)
    with sqlite3.connect(Path(directory)/"kb.sqlite") as db:
        return dict(db.execute("select doc_id,file_name from docs"))


def pages_by_doc(pairs):
    out={}
    for doc,page in pairs:
        if page not in out.setdefault(doc,[]):
            out[doc].append(page)
    return out


def public(body,query,day,names):
    """Keep the fields the site's proxy passes through, plus the real count and pages at each step."""
    t={s["step_name"]:s.get("output") or {} for s in body.get("trace") or []}
    chunks=[{k:c.get(k) for k in ("document","page","text","cited_by_claim_ids")} for c in body.get("chunks") or []]
    docs=t.get("candidate_pages",{}).get("documents",{})
    # Element ids look like "<doc_id>:p0003:e017"; sorted by reranker score, best first.
    scores=sorted(t.get("element_triage",{}).get("scores",[]),key=lambda x:-x[1])
    gathered=[(names.get(i.split(":")[0],i.split(":")[0]),int(i.split(":")[1][1:])) for i,_ in scores]
    pages={"routed":[names.get(d,d) for d in t.get("routing_guard",{}).get("routed_doc_ids",[])],
           "gathered":pages_by_doc(gathered),
           "order":[[d,pg] for d,pg in dict.fromkeys(gathered)],
           "kept":pages_by_doc((c["document"],c["page"]) for c in chunks),
           "cited":pages_by_doc((c["document"],c["page"]) for c in chunks if c["cited_by_claim_ids"])}
    funnel={
        "documents_routed":len(t.get("routing_guard",{}).get("routed_doc_ids",[])),
        "candidate_pages":sum(d.get("available",0) for d in docs.values()),
        "pages_picked":t.get("page_survey",{}).get("picked_pages",0),
        "passages_gathered":t.get("element_retrieval",{}).get("total",0),
        "passages_checked":t.get("element_verification",{}).get("elements_seen",0),
        "passages_kept":t.get("element_verification",{}).get("elements_kept",0),
        "claims_drafted":t.get("answer_generation",{}).get("draft_claims",0),
        "claims_accepted":t.get("answer_verification",{}).get("accepted",0),
        "claims_withdrawn":t.get("answer_verification",{}).get("rejected",0),
        "pages_cited":len({(c["document"],c["page"]) for c in chunks if c["cited_by_claim_ids"]}),
    }
    return {"question":query,"recorded_at":day,"status":body.get("status"),"answer":body.get("answer"),
            "latency_ms":body.get("latency_ms"),"coverage":{"limitations":(body.get("coverage") or {}).get("limitations",[])},
            "chunks":chunks,"funnel":funnel,"pages":pages,
            "trace":[{"step_name":s["step_name"],"description":s.get("description",""),"output":trim(s.get("output"))}
                     for s in body.get("trace") or []]}


if __name__=="__main__":
    main()
