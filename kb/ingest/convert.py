"""Turn images and Office or text files into PDFs, so one page-accurate pipeline (including OCR) handles every format."""
import html
from pathlib import Path

import pymupdf

IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
OFFICE_TYPES = {".docx", ".pptx", ".xlsx"}
TEXT_TYPES = {".txt", ".md"}
SUPPORTED = {".pdf"} | IMAGE_TYPES | OFFICE_TYPES | TEXT_TYPES
_PAGE = pymupdf.paper_rect("a4")
_CHARS_PER_PAGE = 3000


def _body(page, rows: list[str], rect=None) -> None:
    box = rect or _PAGE + (40, 40, -40, -40)
    page.insert_htmlbox(box, "".join(f"<p>{html.escape(r)}</p>" for r in rows), css="p{font-size:10px;margin:0 0 4px 0}")


def _paged(doc, rows: list[str]) -> None:
    """Flow rows onto as many pages as they need; no row is cut."""
    batch, size = [], 0
    for row in rows:
        if batch and size + len(row) > _CHARS_PER_PAGE:
            _body(doc.new_page(width=_PAGE.width, height=_PAGE.height), batch)
            batch, size = [], 0
        batch.append(row)
        size += len(row)
    if batch:
        _body(doc.new_page(width=_PAGE.width, height=_PAGE.height), batch)


def _picture_pages(doc, pictures: list[bytes]) -> None:
    """Each picture becomes its own page, where the scanned-page path reads any text in it."""
    for blob in pictures:
        try:
            page = doc.new_page(width=_PAGE.width, height=_PAGE.height)
            page.insert_image(_PAGE + (40, 40, -40, -40), stream=blob)
        except Exception:  # noqa: BLE001 - a picture format MuPDF cannot draw (WMF, EMF) must not lose the document
            doc.delete_page(-1)


def _row(cells) -> str:
    return " | ".join(str(c).strip() for c in cells if c not in (None, "") and str(c).strip())


def _docx(src: Path, doc) -> None:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    source = Document(str(src))
    rows = []
    for item in source.iter_inner_content():  # paragraphs and tables in document order
        if isinstance(item, Paragraph) and item.text.strip():
            rows.append(item.text.strip())
        elif isinstance(item, Table):
            rows.extend(r for r in (_row(c.text for c in line.cells) for line in item.rows) if r)
    _paged(doc, rows)
    _picture_pages(doc, [rel.target_part.blob for rel in source.part.rels.values() if "image" in rel.reltype and not rel.is_external])


def _pptx(src: Path, doc) -> None:
    """One PDF page per slide, so a citation's page number is the slide number."""
    from pptx import Presentation
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    def walk(shapes):
        for shape in shapes:
            yield shape
            if shape.shape_type == MSO_SHAPE_TYPE.GROUP:
                yield from walk(shape.shapes)
    for slide in Presentation(str(src)).slides:
        rows, pictures = [], []
        for shape in walk(slide.shapes):
            if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                rows.append(" ".join(shape.text_frame.text.split()))
            if getattr(shape, "has_table", False) and shape.has_table:
                rows.extend(r for r in (_row(c.text for c in line.cells) for line in shape.table.rows) if r)
            if shape.shape_type == MSO_SHAPE_TYPE.PICTURE:
                pictures.append(shape.image.blob)
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None and slide.notes_slide.notes_text_frame.text.strip():
            rows.append("Speaker notes: " + " ".join(slide.notes_slide.notes_text_frame.text.split()))
        page = doc.new_page(width=_PAGE.width, height=_PAGE.height)
        middle = _PAGE.height / 2 if pictures else _PAGE.height - 40
        if rows:
            _body(page, rows, pymupdf.Rect(40, 40, _PAGE.width - 40, middle))
        for i, blob in enumerate(pictures):
            width = (_PAGE.width - 80) / len(pictures)
            try:
                page.insert_image(pymupdf.Rect(40 + i * width, middle, 40 + (i + 1) * width, _PAGE.height - 40), stream=blob)
            except Exception:  # noqa: BLE001 - see _picture_pages
                pass


def _xlsx(src: Path, doc) -> None:
    from openpyxl import load_workbook
    book = load_workbook(src, read_only=True, data_only=True)
    try:
        for sheet in book.worksheets:
            rows = [r for r in (_row(line) for line in sheet.iter_rows(values_only=True)) if r]
            if rows:
                _paged(doc, [f"Sheet: {sheet.title}"] + rows)
    finally:
        book.close()


def to_pdf(src: Path, target: Path) -> bool:
    """Write src as a PDF at target. False if it holds nothing to index."""
    kind = src.suffix.lower()
    if kind in IMAGE_TYPES:
        with pymupdf.open(src) as image:
            target.write_bytes(image.convert_to_pdf())
        return True
    with pymupdf.open() as doc:
        if kind == ".docx":
            _docx(src, doc)
        elif kind == ".pptx":
            _pptx(src, doc)
        elif kind == ".xlsx":
            _xlsx(src, doc)
        else:
            _paged(doc, [line for line in src.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()])
        if not doc.page_count:
            return False
        doc.save(target)
    return True
