"""Load unchanged official definition cells; sample invocation never executes."""
import ast
import hashlib
import json
from pathlib import Path

EXPECTED_EVALUATOR_SHA256="f75493648896a79fc28499f04bb4909baea9bf717c1b040d0c3fb3974aa5f583"
METRICS=("answer_precision","answer_recall","context_precision","context_recall")


def load_notebook_namespace(ipynb,expected_hash=EXPECTED_EVALUATOR_SHA256,config=None):
    path=Path(ipynb);original=path.read_bytes()
    if hashlib.sha256(original).hexdigest()!=expected_hash:
        raise ValueError("official evaluator hash differs; inspect and explicitly pin the provided original")
    notebook=json.loads(original)
    # The notebook's definition cells expect these names; its own client is replaced by the judge transport below.
    cfg={"OPENCODE_API_KEY":"","OPENCODE_MODEL":"free-chain","OPENCODE_BASE_URL":""}
    if config:
        cfg.update(config)
    ns={"__name__":"official_evaluator_isolated",**cfg};executed=[]
    wanted={"OpenCodeClient","RAGMetricsEvaluator","evaluate_dataset"}
    for index,cell in enumerate(notebook["cells"]):
        if cell["cell_type"]!="code":
            continue
        source="".join(cell.get("source",[]))
        tree=ast.parse(source)
        definitions={n.name for n in tree.body if isinstance(n,(ast.ClassDef,ast.FunctionDef))}
        only_imports=bool(tree.body) and all(isinstance(n,(ast.Import,ast.ImportFrom)) for n in tree.body)
        if only_imports or definitions & wanted:
            # Entire source cell is executed verbatim; unexpected top-level calls fail review.
            if any(not isinstance(n,(ast.ClassDef,ast.FunctionDef,ast.Import,ast.ImportFrom)) for n in tree.body):
                raise ValueError("definition cell has unexpected top-level side effects")
            exec(compile(source,f"{path.name}:cell{index}","exec"),ns)
            executed.append(index)
    if not wanted.issubset(ns):
        raise ValueError("missing official evaluator definitions")
    if path.read_bytes()!=original:
        raise RuntimeError("protected evaluator changed during load")
    ns["_executed_cells"]=executed
    return ns


def evaluate_file(run_path,notebook=None,expected_hash=EXPECTED_EVALUATOR_SHA256):
    if notebook is None:
        raise ValueError("pass the provided official notebook path")
    ns=load_notebook_namespace(notebook,expected_hash)
    # Keep official metric definitions unchanged; adapt only the provider transport.
    client=OfficialJudgeTransport()
    evaluator=ns["RAGMetricsEvaluator"](client)
    rows=[json.loads(s) for s in Path(run_path).read_text(encoding="utf-8").splitlines() if s.strip()]
    scored=[];errors=[]
    for row in rows:
        if row.get("error"):
            errors.append({"id":row["id"],"stage":"query","error":row["error"]});continue
        try:
            client.log=[]
            metrics=evaluator.evaluate_single(query=row["query"],ai_answer=row["ai_answer"],benchmark_answer=row["benchmark_answer"],
                                               retrieved_chunks=row["retrieved_chunks"],benchmark_chunks=row["benchmark_chunks"])
            # Official metrics untouched; alongside them, every judge request/response this score came from
            # (data/judge_cache/<request_sha256>.json) and zero-call consistency flags. Flagged rows are never re-judged.
            from evaluation.audit import judge_consistency, checklist
            scored.append({"id":row["id"],**metrics,"judge_calls":client.log,
                           "consistency":judge_consistency(metrics,row["ai_answer"],client.log),
                           "dev_checklist":checklist(row["id"],row["ai_answer"])})
        except Exception as exc:
            errors.append({"id":row["id"],"stage":"judge","error":f"{type(exc).__name__}: {exc}"[:300]})
    n=len(rows)
    summary={"total_rows":n,"scored_rows":len(scored),"failed_rows":len(errors),
             "scored_row_means":{m:sum(r[m] for r in scored)/len(scored) if scored else None for m in METRICS},
             "failure_as_zero_means_diagnostic":{m:sum(r[m] for r in scored)/n if n else None for m in METRICS},
             "warning":"Failure-as-zero aggregate is separately labeled; official formulas are unchanged.",
             "evaluator_sha256":expected_hash,"executed_definition_cells":ns["_executed_cells"],
             "judge_models":sorted(client.models),
             "rows_with_consistency_flags":[r["id"] for r in scored if r["consistency"]["flags"]]}
    result={"summary":summary,"per_question":scored,"errors":errors}
    Path(str(run_path)+".scores.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return result


class OfficialJudgeTransport:
    """Send official judge prompts to one free model without changing official metric logic.

    One model only (KB_JUDGE_PROVIDERS, default Gemini): scores from different judges are not comparable, so a rate
    limit waits and a judge that stays down leaves the row unscored rather than switching model."""
    def __init__(self,attempts=6,wait_s=65):
        import os
        from dataclasses import replace
        from kb.config import get_settings
        from kb.llm import ChainLLM
        from kb.model_api import build_providers
        settings=get_settings()
        providers=build_providers({**os.environ,"KB_LLM_PROVIDERS":os.getenv("KB_JUDGE_PROVIDERS","gemini")})[:1] or settings.providers[-1:]
        self.log=[];self.models=set();self.attempts,self.wait_s=attempts,wait_s
        self.cache=settings.ledger_path().parent/"judge_cache"
        self.client=ChainLLM(replace(settings,providers=providers,llm_cache=False,llm_max_retries=1))

    def call_structured(self,system_prompt,user_prompt,max_tokens=10000,temperature=0,max_retries=3):
        import time
        from kb.llm import LLMError
        # Temperature 0: the same judge call gives the same verdict, so a rerun reads it from disk for free.
        key=hashlib.sha256(json.dumps([system_prompt,user_prompt,max_tokens]).encode()).hexdigest()
        cached=self.cache/(key+".json")
        if cached.is_file():
            self.log.append({"request_sha256":key,"cached":True,"max_tokens":max_tokens})
            return json.loads(cached.read_text(encoding="utf-8"))
        for attempt in range(self.attempts):
            try:
                result=self.client.complete_json(system_prompt,user_prompt,name="official_judge",max_tokens=max_tokens)
                break
            except LLMError:
                if attempt==self.attempts-1:
                    raise
                time.sleep(self.wait_s)
        response=self.client.last_response or {}
        self.models.add(response.get("model"))
        cached.parent.mkdir(parents=True,exist_ok=True)
        cached.write_text(json.dumps(result,ensure_ascii=False),encoding="utf-8")
        self.log.append({"request_sha256":key,"model":response.get("model"),"finish_reason":response.get("finish_reason"),"max_tokens":max_tokens})
        return result
