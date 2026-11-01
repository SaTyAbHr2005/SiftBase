"""PDF -> per-page markdown (pymupdf4llm layout mode) with OCR for image-only pages.

OCR variant (acceptance check on a fully scanned 92-page corpus PDF, pages 1 and 29, mean whitespace-token length):
pymupdf4llm's built-in RapidOCR loses word spaces (p29: 13.4 at 200 dpi, 12.7 at 300 dpi). Our RapidOCREngine
restores spaces from pixel gaps (p29: 5.25 at 200 and 300 dpi). So to_markdown always runs with use_ocr=False
and image-only pages are OCRed here with RapidOCREngine at settings.ocr_dpi.
"""
import hashlib
import logging
import re
from pathlib import Path

import pymupdf
import pymupdf4llm

from kb.config import Settings
from kb.ingest.ocr import get_ocr_engine
from kb.models import PageText, ParsedDoc
from kb.textutil import tokens

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



def _recover_missing_text(page, md: str) -> str:
    """The Markdown converter can drop real text, often text laid over a page image: put back any block it lost."""
    have = set(tokens(md))
    lost = []
    for block in page.get_text("blocks", sort=True):
        if block[6] != 0:  # image block
            continue
        text = " ".join(block[4].split())
        words = tokens(text)
        if len(words) >= 6 and sum(w in have for w in words) < 0.6 * len(words):
            lost.append(text)
    return "\n\n".join(([md] if md else []) + lost)


OCR_IMAGE_COVERAGE = 0.25  # share of a page covered by pictures before a text page is also read by OCR


def _image_coverage(page) -> float:
    area = page.rect.get_area() or 1.0
    return sum(pymupdf.Rect(i["bbox"]).get_area() for i in page.get_image_info()) / area


def _add_new_lines(md: str, ocr_text: str) -> str:
    """OCR lines are short labels and figures, so keep each line with two or more words or any number not already on the page."""
    have = set(tokens(md))
    new = []
    for line in ocr_text.splitlines():
        words = tokens(line)
        unseen = [w for w in words if w not in have]
        if len(unseen) >= max(1, 0.6 * len(words)) and (len(words) >= 2 or any(c.isdigit() for c in line)):
            new.append(line.strip())
    return "\n\n".join(([md] if md else []) + (["\n".join(new)] if new else []))


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
        md_by_page = _markdown(doc, list(range(start - 1, end)), settings, path.name, drop_margins=True)
        # The layout model can classify a page's only text as running header/footer; never lose a text page.
        lost = [p - 1 for p, md in md_by_page.items()
                if not _clean(md) and len(doc[p - 1].get_text().strip()) >= settings.min_text_chars]
        if lost:
            md_by_page.update(_markdown(doc, lost, settings, path.name, drop_margins=False))

        for page_no in range(start, end + 1):
            page = doc[page_no - 1]
            md = _recover_missing_text(page, _clean(md_by_page.get(page_no, "")))
            is_ocr = False
            if use_ocr and len(page.get_text().strip()) >= settings.min_text_chars and _image_coverage(page) >= OCR_IMAGE_COVERAGE:
                # Text inside a large picture (infographic, pasted table) has no text layer: read it and keep what is new.
                engine = get_ocr_engine()
                try:
                    merged = _add_new_lines(md, _clean(engine.image_to_text(page.get_pixmap(dpi=settings.ocr_dpi).tobytes("png")))) if engine else md
                except Exception as e:
                    log.warning("OCR failed on %s p%d: %s", path.name, page_no, e)
                    merged = md
                is_ocr = merged != md
                md = merged
            elif use_ocr and len(page.get_text().strip()) < settings.min_text_chars and page.get_image_info():
                engine = get_ocr_engine()
                text = ""
                if engine is not None:
                    try:
                        text = _clean(engine.image_to_text(page.get_pixmap(dpi=settings.ocr_dpi).tobytes("png")))
                    except Exception as e:
                        log.warning("OCR failed on %s p%d: %s", path.name, page_no, e)
                if len(text) > len(md):
                    md, is_ocr = text, True
                if not md:
                    unavailable += 1
            metadata=page_source_metadata(page,doc.page_count,md)
            pages.append(PageText(page_no=page_no, markdown=md, is_ocr=is_ocr,
                                  toc_titles=titles.get(page_no, []),metadata=metadata))
    return pages, unavailable


def parse_pdf(path: Path, settings: Settings, use_ocr: bool = True) -> ParsedDoc:
    path = Path(path)
    doc_id, page_count, outline, metadata = read_pdf_info(path)
    pages, unavailable = parse_pages(path, 1, page_count, settings, use_ocr)
    return ParsedDoc(doc_id=doc_id, file_name=path.name, page_count=page_count, pages=pages, outline=outline,
                     pdf_metadata=metadata, ocr_unavailable_pages=unavailable)
