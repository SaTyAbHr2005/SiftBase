"""Summarize charts and pictures as text once, at indexing, so queries only ever send that text to a model.

A daily free quota cannot cover a large collection in one run, so summaries are saved per page: every later index
reuses them and continues with the pages still pending. KB_VISION_PAGES=0 turns this off (for private documents too).
"""
import base64
import logging
import os
import time

import pymupdf
import requests

from kb.model_api import build_providers

log = logging.getLogger(__name__)

PROMPT = ("Describe this document page's charts, diagrams and pictures for a search index. For each one say what it shows, "
          "its axes or labels, the main values and the pattern. Only state what is visible. Do not repeat body text. "
          "If the page has no meaningful chart, diagram or picture, reply exactly NONE.")
MAX_OUTPUT_TOKENS = 400
PACE_S = 15  # the free tier allows about 8,000 tokens a minute and each page uses about 2,000


def _provider():
    found = build_providers({**os.environ, "KB_LLM_PROVIDERS": os.getenv("KB_VISION_PROVIDER", "groq:qwen/qwen3.8-27b")})
    return found[0] if found else None


def _describe(provider, png: bytes) -> str:
    image = "data:image/png;base64," + base64.b64encode(png).decode()
    resp = requests.post(provider.url, headers={"Authorization": f"Bearer {provider.key}"}, timeout=60, json={
        "model": provider.model, "temperature": 0, "max_tokens": MAX_OUTPUT_TOKENS,
        "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT},
                                                  {"type": "image_url", "image_url": {"url": image}}]}]})
    resp.raise_for_status()
    return (resp.json()["choices"][0]["message"].get("content") or "").strip()


def add_visual_descriptions(docs, paths: dict[str, str], cache, limit: int, progress=lambda done, total: None) -> dict:
    """Append saved or new summaries to pages flagged as visual; returns counts for the extraction report."""
    provider = _provider() if limit else None
    used = described = pending = 0
    stopped = False
    for doc in docs:
        pages = [p for p in doc.pages if p.metadata.get("visual")]
        saved = (cache.load_json("vision", doc.doc_id) or {}) if cache else {}
        changed = False
        source = None
        for page in pages:
            key = str(page.page_no)
            if key not in saved:
                if stopped or not provider or used >= limit:
                    pending += 1
                    continue
                try:
                    source = source or pymupdf.open(paths[doc.doc_id])
                    target = source[page.page_no - 1]
                    dpi = max(1, min(110, int(1600 * 72 / max(target.rect.width, target.rect.height, 1))))
                    if used:
                        time.sleep(PACE_S)
                    saved[key] = _describe(provider, target.get_pixmap(dpi=dpi).tobytes("png"))
                    used += 1
                    changed = True
                    progress(used, limit)
                except (requests.RequestException, KeyError, IndexError, ValueError) as e:
                    log.warning("Vision stopped at %s p%d: %s", doc.file_name, page.page_no, type(e).__name__)
                    stopped = True
                    pending += 1
                    continue
            text = saved[key]
            if text and text.upper().rstrip(".") != "NONE":
                page.markdown = f"{page.markdown}\n\nFigure description (generated from the page image): {' '.join(text.split())}".strip()
                described += 1
        if source:
            source.close()
        if changed and cache:
            cache.save_json("vision", doc.doc_id, saved)
    return {"visual_pages_described": described, "visual_pages_pending": pending}
