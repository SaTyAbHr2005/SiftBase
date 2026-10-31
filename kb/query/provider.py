"""Query-side adapter over the shared kb.llm client."""
from .errors import QueryError


class SharedQueryClient:
    """Keep shared cache/spend accounting, with one deadline-bound pass over the provider chain per query call."""
    def __init__(self, llm):
        self.llm=llm
        self.model=llm.settings.effective_answer_model()

    def scoped(self):
        from dataclasses import replace
        clone=self.llm.scoped()
        clone.settings=replace(clone.settings,llm_max_retries=1)
        return SharedQueryClient(clone)

    @property
    def usage(self):
        from dataclasses import asdict
        return asdict(self.llm.usage)

    @property
    def last_usage(self):
        return getattr(self.llm,"last_usage",None)

    @last_usage.setter
    def last_usage(self,v):
        self.llm.last_usage=v

    @property
    def last_response(self):
        return getattr(self.llm,"last_response",None)

    @last_response.setter
    def last_response(self,v):
        self.llm.last_response=v

    def set_request_deadline(self,deadline):
        self.llm.deadline=deadline

    def complete_json(self,system,user,*,name,max_tokens):
        try:
            return self.llm.complete_json(system,user,name=name,model=self.model,max_tokens=max_tokens)
        except Exception as exc:
            from kb.llm import LLMError
            if isinstance(exc,LLMError) and self.last_response is not None:
                raise QueryError("MODEL_SCHEMA","Model returned invalid or truncated JSON",503) from exc
            raise
