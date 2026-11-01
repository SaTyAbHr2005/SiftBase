"""PDF -> per-page markdown (pymupdf4llm layout mode), with every text-layer word checked and pictures read by OCR.

OCR variant (acceptance check on a fully scanned 92-page corpus PDF, pages 1 and 29, mean whitespace-token length):
pymupdf4llm's built-in RapidOCR loses word spaces (p29: 13.4 at 200 dpi, 12.7 at 300 dpi). Our RapidOCREngine
restores spaces from pixel gaps (p29: 5.25 at 200 and 300 dpi). So to_markdown always runs with use_ocr=False
and image-only pages are OCRed here with RapidOCREngine at settings.ocr_dpi.
"""
import hashlib
import json
import logging
import re
from collections import Counter
from pathlib import Path

import pymupdf
import pymupdf4llm

from kb.config import Settings
from kb.ingest.convert import sidecar_for
from kb.ingest.ocr import get_ocr_engine
from kb.models import PageText, ParsedDoc

log = logging.getLogger(__name__)

_IMAGE_LINK = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def doc_id_for(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:10]


def _outline(doc) -> list[tuple[int, str, int]]:
    return [(int(lvl), str(title), int(page)) for lvl, title, page, *_ in doc.get_toc(simple=True) if page >= 1]


def read_pdf_info(path: Path) -> tuple[str, int, list[tuple[int, str, int]], dict]:
    with pymupdf.open(path) as doc:
        meta=dict(doc.metadata or {})
        meta["page_label_rules"]=doc.get_page_labels()
        meta["file_size_bytes"]=Path(path).stat().st_size
        with open(path,"rb") as source:
            digest=hashlib.sha256()
            for block in iter(lambda:source.read(1<<20),b""):digest.update(block)
            meta["source_sha256"]=digest.hexdigest()
        return doc_id_for(path), doc.page_count, _outline(doc), meta


def _clean(md: str) -> str:
    return _IMAGE_LINK.sub("", md or "").strip()


def _markdown(doc, idx: list[int], settings: Settings, name: str, drop_margins: bool) -> dict[int, str]:
    """{1-based page: markdown} for 0-based page indexes idx; plain text if the markdown parser raises."""
    try:
        # Classic markdown by default: the layout AI renders + runs ONNX per page and measured ~3.8x slower
        # under 6 workers (65 vs 162-182 ms/page). header/footer/use_ocr kwargs are ignored by the classic path.
        pymupdf4llm.use_layout(settings.parse_layout)
        chunks = pymupdf4llm.to_markdown(
            doc, pages=idx, page_chunks=True, show_progress=False, write_images=False, embed_images=False,
            use_ocr=False, ocr_dpi=settings.ocr_dpi, header=not drop_margins, footer=not drop_margins)
        # layout mode names the 1-based page "page_number"; classic mode names it "page" (also 1-based, verified)
        return {int(c["metadata"].get("page_number") or c["metadata"]["page"]): c.get("text") or "" for c in chunks}
    except Exception as e:
        log.warning("to_markdown failed for %s (%d pages from p%d): %s; using plain text", name, len(idx), idx[0] + 1, e)
        return {i + 1: doc[i].get_text("text") for i in idx}



_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_MAX_RENDER_SIDE = 4000  # pixels: a hostile or huge page must not exhaust memory
_MAX_PICTURES_PER_PAGE = 8
_VECTOR_HEAVY = 150  # drawing operations on a page before it counts as a chart or diagram
_GARBLED = re.compile(r"\(cid:\d+\)|�")


def _words(text: str) -> list[str]:
    return _WORD.findall((text or "").lower())


def _text_lines(page) -> list[tuple[int, str]]:
    """The text layer as (block, line), rebuilt from words. Words on one baseline stay in one row, wide gaps marked."""
    rows: dict[tuple[int, int], list] = {}
    for x0, y0, x1, y1, word, block, *_ in page.get_text("words"):
        rows.setdefault((int(block), round(y1 / 3)), []).append((x0, x1, word))
    lines = []
    for (block, _), parts in sorted(rows.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        parts.sort()
        text = parts[0][2]
        for (_, end, _), (start, _, word) in zip(parts, parts[1:]):
            text += (" | " if start - end > 18 else " ") + word
        lines.append((block, text))
    return lines


def _recover_missing_text(page, md: str) -> tuple[str, int, int]:
    """Every word of the text layer must reach the page: add back any line holding a word the converter lost.
    Words are counted, not just matched, so a repeated row is kept too. Returns (markdown, words, recovered)."""
    have = Counter(_words(md))
    joined = "".join(_words(md))  # "inter-national" arrives as "international"
    lost, block_of, total, recovered = [], None, 0, 0
    for block, line in _text_lines(page):
        missing = 0
        for word in _words(line):
            total += 1
            if have[word] > 0:
                have[word] -= 1
            elif not (len(word) >= 4 and word in joined):
                missing += 1
        if missing:
            recovered += missing
            lost.append(("\n\n" if lost and block != block_of else "\n" if lost else "") + line)
            block_of = block
    return "\n\n".join(x for x in (md, "".join(lost)) if x), total, recovered


def _non_page_text(page) -> list[str]:
    """Comments and form values live outside the page content, so neither converter nor OCR sees them."""
    out = []
    for annot in page.annots() or []:
        content = (annot.info or {}).get("content", "").strip()
        if content:
            out.append(f"Annotation: {content}")
    for widget in page.widgets() or []:
        value = str(widget.field_value or "").strip()
        if value and value.lower() != "off":
            out.append(f"Form field {widget.field_name or ''}: {value}".replace("  ", " "))
    return out


def _picture_regions(page) -> list:
    """Each picture big enough to hold text, largest first."""
    area = page.rect.get_area() or 1.0
    rects = []
    for info in page.get_image_info():
        rect = pymupdf.Rect(info["bbox"]) & page.rect
        if not rect.is_empty and rect.get_area() >= 0.02 * area and rect.width >= 30 and rect.height >= 30 and rect not in rects:
            rects.append(rect)
    return sorted(rects, key=lambda r: -r.get_area())[:_MAX_PICTURES_PER_PAGE]


def _read_region(engine, page, rect, dpi: int) -> str:
    dpi = max(1, min(dpi, int(_MAX_RENDER_SIDE * 72 / max(rect.width, rect.height, 1))))  # PyMuPDF needs a whole number
    return _clean(engine.image_to_text(page.get_pixmap(dpi=dpi, clip=rect).tobytes("png")))


def _add_new_lines(md: str, ocr_text: str) -> str:
    """Keep OCR lines that add something: a line mostly already on the page is the text layer read a second time."""
    have = set(_words(md))
    new = []
    for line in ocr_text.splitlines():
        words = _words(line)
        unseen = [w for w in words if w not in have]
        if unseen and (len(words) <= 2 or len(unseen) >= 0.6 * len(words)):
            new.append(line.strip())
            have.update(unseen)
    return "\n\n".join(([md] if md else []) + (["Text in image or figure:\n" + "\n".join(new)] if new else []))


def page_source_metadata(page,page_count,markdown):
    links=[int(link["page"])+1 for link in page.get_links()
           if link.get("kind")==pymupdf.LINK_GOTO and isinstance(link.get("page"),int) and 0<=link["page"]<page_count]
    return {"page_label":page.get_label(),"rotation":page.rotation,
            "width_points":round(page.rect.width,2),"height_points":round(page.rect.height,2),
            "internal_link_pages":list(dict.fromkeys(links))[:40],"image_count":len(page.get_image_info()),
            "text_chars":len(markdown),"origin":"pdf_page"}

def parse_pages(path: Path, start: int, end: int, settings: Settings, use_ocr: bool) -> tuple[list[PageText], int]:
    """Pages start..end inclusive (1-based). Returns (pages, ocr_unavailable_count). Top-level for process pools."""
    path = Path(path)
    pages: list[PageText] = []
    unavailable = 0
    with pymupdf.open(path) as doc:
        end = min(end, doc.page_count)
        if start > end:
            return [], 0
        titles: dict[int, list[str]] = {}
        for _, title, page in _outline(doc):
            titles.setdefault(page, []).append(title)
        # The converter changes the document it reads (it removes comments and form fields), so it gets its own copy.
        with pymupdf.open(path) as scratch:
            md_by_page = _markdown(scratch, list(range(start - 1, end)), settings, path.name, drop_margins=True)
        # The layout model can classify a page's only text as running header/footer; never lose a text page.
        lost = [p - 1 for p, md in md_by_page.items()
                if not _clean(md) and len(doc[p - 1].get_text().strip()) >= settings.min_text_chars]
        if lost:
            with pymupdf.open(path) as scratch:
                md_by_page.update(_markdown(scratch, lost, settings, path.name, drop_margins=False))

        sidecar = sidecar_for(path)
        exact = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.exists() else None
        for page_no in range(start, end + 1):
            page = doc[page_no - 1]
            is_ocr = False
            if exact is not None:  # Office or text file: its own text is exact, and this PDF page only holds its pictures
                md, text_words, recovered = exact.get(str(page_no), ""), len(_words(exact.get(str(page_no), ""))), 0
            else:
                md, text_words, recovered = _recover_missing_text(page, _clean(md_by_page.get(page_no, "")))
            extras = _non_page_text(page)
            if extras:
                md = "\n\n".join(([md] if md else []) + extras)
            layer = page.get_text()
            scanned = exact is None and len(layer.strip()) < settings.min_text_chars and bool(page.get_image_info())
            pictures = _picture_regions(page)
            vector_heavy = exact is None and len(page.get_drawings()) > _VECTOR_HEAVY
            garbled = len(_GARBLED.findall(layer)) > 5
            ocr_words = 0
            if use_ocr and (scanned or pictures or vector_heavy or garbled):
                engine = get_ocr_engine()
                try:
                    if engine is None:
                        unavailable += scanned
                    elif scanned:
                        text = _read_region(engine, page, page.rect, settings.ocr_dpi)
                        if len(text) > len(md):
                            md, is_ocr = text, True
                            ocr_words = len(_words(text))
                        elif not md:
                            unavailable += 1
                    else:
                        before = md
                        for rect in [page.rect] if vector_heavy or garbled else pictures:
                            md = _add_new_lines(md, _read_region(engine, page, rect, settings.ocr_dpi))
                        is_ocr = md != before
                        ocr_words = len(_words(md)) - len(_words(before))
                except Exception as e:  # noqa: BLE001 - one unreadable picture must not lose the rest of the page
                    log.warning("OCR failed on %s p%d: %s", path.name, page_no, e)
                    unavailable += scanned
            metadata=page_source_metadata(page,doc.page_count,md)
            metadata.update(text_layer_words=text_words, recovered_words=recovered, ocr_words=ocr_words,
                            visual=bool(pictures or vector_heavy))
            pages.append(PageText(page_no=page_no, markdown=md, is_ocr=is_ocr,
                                  toc_titles=titles.get(page_no, []),metadata=metadata))
    return pages, unavailable


def parse_pdf(path: Path, settings: Settings, use_ocr: bool = True) -> ParsedDoc:
    path = Path(path)
    doc_id, page_count, outline, metadata = read_pdf_info(path)
    pages, unavailable = parse_pages(path, 1, page_count, settings, use_ocr)
    return ParsedDoc(doc_id=doc_id, file_name=path.name, page_count=page_count, pages=pages, outline=outline,
                     pdf_metadata=metadata, ocr_unavailable_pages=unavailable)
