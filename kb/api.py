"""FastAPI app. Routes live in kb/routes/index.py (Track A) and kb/routes/query.py (Track B)."""
import importlib
import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from kb.errors import KBError

log = logging.getLogger("kb.api")
# No slash redirects: a redirect is answered before the key check and could send the key again over plain http.
app = FastAPI(title="Smart Knowledge Base", docs_url=None, redoc_url=None, openapi_url=None, redirect_slashes=False)


def new_request_id() -> str:
    return "req_" + uuid.uuid4().hex[:12]


@app.middleware("http")
async def _access(request: Request, call_next):
    # API key and rate limit; errors raised here would skip the handlers below, so the response is built directly.
    from starlette.routing import get_route_path
    from kb.access import check
    # The routed path, so a root_path prefix cannot make this check and the router see different paths.
    denied = check(request.method, get_route_path(request.scope), request.headers,
                   request.client.host if request.client else "")
    if denied:
        err, headers = denied
        return JSONResponse(status_code=err.http_status, content=err.to_body(new_request_id()), headers=headers)
    return await call_next(request)


@app.exception_handler(KBError)
async def _kb_error(request: Request, exc: KBError):
    return JSONResponse(status_code=exc.http_status, content=exc.to_body(new_request_id()))


@app.exception_handler(RequestValidationError)
async def _validation_error(request: Request, exc: RequestValidationError):
    err = KBError("INVALID_REQUEST", "Request fields are missing or malformed.", 422,
                  details={"errors": [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in exc.errors()]})
    return JSONResponse(status_code=422, content=err.to_body(new_request_id()))


@app.exception_handler(Exception)
async def _unexpected(request: Request, exc: Exception):
    log.exception("unhandled error")
    err = KBError("INTERNAL_ERROR", "Internal error.", 500, retryable=True)
    return JSONResponse(status_code=500, content=err.to_body(new_request_id()))


for _module in ("kb.routes.index", "kb.routes.query"):
    app.include_router(importlib.import_module(_module).router)
