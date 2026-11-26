import io
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

import kb.routes.collections as listing
from kb.testing import make_pdf
from tests.test_api_index import _client


def test_collections_lists_live_indexes_with_docs_and_pages(tmp_path, settings, monkeypatch):
    client = _client(monkeypatch, settings)  # patches the index route's settings, LLM and embedder
    monkeypatch.setattr(listing, "get_settings", lambda: settings)
    desktop = FastAPI()  # kb.api mounts the listing only for the desktop app (KB_DESKTOP=1)
    desktop.include_router(listing.router)
    listed = TestClient(desktop)
    assert listed.get("/collections").json() == {"collections": []}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.pdf", make_pdf(tmp_path / "a.pdf", ["Alpha page one.", "Alpha page two."]).read_bytes())
        z.writestr("b.pdf", make_pdf(tmp_path / "b.pdf", ["Beta page one."]).read_bytes())
    assert client.post("/index", files={"file": ("d.zip", buf.getvalue(), "application/zip")},
                       data={"collection_name": "c1"}).status_code == 200
    (settings.data_dir / "collections" / "half-built").mkdir()  # no active index yet: left out

    body = listed.get("/collections").json()
    [c] = body["collections"]
    assert c["name"] == "c1" and c["generation_id"].startswith("gen_") and c["indexed_at"]
    assert [(d["name"], d["pages"]) for d in c["docs"]] == [("a.pdf", 2), ("b.pdf", 1)]
    assert all(d["doc_id"] for d in c["docs"]) and c["elements"] >= 3
