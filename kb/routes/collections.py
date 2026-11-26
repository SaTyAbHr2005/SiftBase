"""GET /collections: every collection with a live index, its documents and page counts (for the desktop app)."""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from fastapi import APIRouter

from kb.config import get_settings
from kb.errors import KBError
from kb.registry import Registry
from kb.store import DB_NAME

router = APIRouter()


@router.get("/collections")
def list_collections():
    settings = get_settings()
    root = Path(settings.data_dir) / "collections"
    registry = Registry(settings)
    out = []
    for folder in sorted(root.iterdir()) if root.is_dir() else []:
        try:
            generation, directory = registry.active_dir(folder.name)
        except KBError:  # still indexing for the first time, or not a collection
            continue
        # Read-only, so listing never blocks or changes an index another process is using.
        try:
            with closing(sqlite3.connect(f"{(directory / DB_NAME).resolve().as_uri()}?mode=ro", uri=True)) as db:
                docs = [{"doc_id": i, "name": n, "pages": p or 0}
                        for i, n, p in db.execute("SELECT doc_id, file_name, page_count FROM docs ORDER BY file_name")]
                elements = db.execute("SELECT count(*) FROM elements").fetchone()[0]
        except sqlite3.Error:  # one damaged index must not hide the others
            continue
        try:
            indexed_at = json.loads((folder / "active.json").read_text(encoding="utf-8")).get("promoted_at")
        except (OSError, ValueError):
            indexed_at = None
        out.append({"name": folder.name, "generation_id": generation, "indexed_at": indexed_at,
                    "docs": docs, "elements": elements})
    return {"collections": out}
