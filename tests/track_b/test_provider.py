import json
import pytest
from kb.query.runtime import QueryRuntime
from kb.query.observability import LocalSink
from kb.query.errors import QueryError
from .helpers import settings


class Reply:
    status_code=200
    headers={}
    def __init__(self,body): self.body=body
    def json(self): return self.body


def shared_client(tmp_path,monkeypatch,body):
    from kb.config import get_settings
    from kb.llm import ChainLLM
    from kb.query.provider import SharedQueryClient
    calls=[]
    monkeypatch.setattr('kb.llm.requests.post',lambda url,**kw:(calls.append(kw),Reply(body))[1])
    shared=get_settings(data_dir=tmp_path/'data',llm_cache=False,llm_max_retries=3)
    return SharedQueryClient(ChainLLM(shared)).scoped(),calls,shared


def test_failed_json_still_accounts_used_tokens(tmp_path,monkeypatch):
    body={"usage":{"prompt_tokens":123,"completion_tokens":17},"choices":[{"message":{"content":"no json here"}}]}
    client,calls,_=shared_client(tmp_path,monkeypatch,body)
    runtime=QueryRuntime(settings(tmp_path),client,LocalSink())
    with pytest.raises(QueryError,match="invalid or truncated"):
        runtime.call("plan","system",{},100)
    assert runtime.usage()["input_tokens"]==123
    assert runtime.usage()["output_tokens"]==17
    assert runtime.events[0]["status"]=="failed"


def test_raw_failure_diagnostics_and_reservation_release(tmp_path,monkeypatch):
    body={"usage":{"prompt_tokens":31,"completion_tokens":23},
          "choices":[{"finish_reason":"length","message":{"content":None}}]}
    client,calls,_=shared_client(tmp_path,monkeypatch,body)
    runtime=QueryRuntime(settings(tmp_path),client,LocalSink())
    with pytest.raises(QueryError):
        runtime.call("verify","system",{},500)
    raw=json.loads((runtime.path/'call_1_raw_response.json').read_text(encoding='utf-8'))
    assert raw["content"] is None and raw["finish_reason"]=="length" and raw["output_limit"]==500
    assert runtime.reserved_verify==23 and runtime.reserved_output==0
    assert runtime.usage()['output_tokens']==23


def test_query_call_makes_one_pass_over_the_chain_and_records_the_model(tmp_path,monkeypatch):
    body={"usage":{"prompt_tokens":31,"completion_tokens":23},"choices":[{"finish_reason":"length","message":{"content":None}}]}
    client,calls,_=shared_client(tmp_path,monkeypatch,body)
    runtime=QueryRuntime(settings(tmp_path),client,LocalSink())
    with pytest.raises(QueryError,match='invalid or truncated'):
        runtime.call('verify','system',{},500)
    assert len(calls)==1
    assert runtime.usage()['input_tokens']==31
    assert runtime.usage()['models']==['groq:openai/gpt-oss-120b']
    assert runtime.events[0]['response_artifact']=='call_1_raw_response'


def test_shared_dryrun_understands_compact_spans(tmp_path):
    from kb.config import get_settings
    from kb.llm import get_llm
    from kb.query.provider import SharedQueryClient
    client=SharedQueryClient(get_llm(get_settings(data_dir=tmp_path,llm_mode='dryrun'))).scoped()
    out=client.complete_json('system',json.dumps({'query':'capital ratio','aspects':'a1: capital ratio',
        'elements':[{'id':'E1','source_spans':{'S1':'The capital ratio is 15 percent.'}}]}),name='verify',max_tokens=500)
    assert out['keep'][0]['support_span_ids']==['S1']


def test_answer_stage_has_its_own_pool(tmp_path):
    # Early stages using their whole output pool cannot starve the writers or claim checks, and the answer pool
    # still has a hard bound.
    from .helpers import FakeLLM
    from kb.query.errors import BudgetExceeded
    runtime=QueryRuntime(settings(tmp_path,max_output_tokens=24000,answer_pool_output_tokens=10000),FakeLLM(lambda n,p:{'ok':1}),LocalSink())
    runtime.reserved_output=24000
    runtime.call('answer','system',{},4000)
    runtime.call('answer_verify','system',{'claims':[]},2000)
    runtime.reserved_final=8001
    with pytest.raises(BudgetExceeded,match='Answer output'):
        runtime.call('answer','system',{},2000)
    assert runtime.calls==2


def test_reasoning_floor_included_in_all_future_reserves(tmp_path):
    from .helpers import FakeLLM
    from kb.query.errors import BudgetExceeded
    llm=FakeLLM()
    runtime=QueryRuntime(settings(tmp_path,max_output_tokens=24000),llm,LocalSink())
    runtime.llm.model='deepseek-v4.1-flash'
    runtime.reserved_output=20000  # 512 becomes the 4,096 reasoning floor: 24,096 > 24,000
    with pytest.raises(BudgetExceeded,match='Output reservation'):
        runtime.call('survey','system',{},512)
    assert runtime.calls==0


def test_verification_has_its_own_output_pool(tmp_path):
    # A concurrent verify round must not be cut by the answer's reserve: 20 batches of 2,000 fit the verify pool.
    from .helpers import FakeLLM
    runtime=QueryRuntime(settings(tmp_path,max_llm_calls=40),FakeLLM(lambda n,p:{"keep":[]}),LocalSink())
    out=runtime.call_many('verify','system',[{"i":i} for i in range(20)],2000)
    assert not any(isinstance(r,Exception) for r in out) and runtime.reserved_output==0
