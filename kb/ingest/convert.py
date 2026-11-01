"""Bring every supported file into the one page-accurate pipeline.

Office and text files keep their exact text in a sidecar (`<target>.text.json`, {page: markdown}): drawing Hindi, Tamil
or Arabic into a PDF and reading it back corrupts it. The PDF beside it only carries each page's pictures, for OCR.
"""
import csv
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

import pymupdf

IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
OFFICE_TYPES = {".docx", ".pptx", ".xlsx"}
LEGACY_TYPES = {".doc", ".ppt", ".xls", ".odt", ".odp", ".ods", ".rtf"}
TEXT_TYPES = {".txt", ".md", ".csv"}
SUPPORTED = {".pdf"} | IMAGE_TYPES | OFFICE_TYPES | LEGACY_TYPES | TEXT_TYPES
MAX_PAGES = 5000
MAX_UNPACKED_BYTES = 1 << 30
LEGACY_TIMEOUT_S = 180
_MAX_IMAGE_SIDE = 4000
_CHARS_PER_PAGE = 3000
_PAGE = pymupdf.paper_rect("a4")
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_EXTRA_PARTS = re.compile(r"/word/(?:header|footer|footnotes|endnotes|comments)\d*\.xml$")


def sidecar_for(pdf: Path) -> Path:
    return Path(str(pdf) + ".text.json")


def _table(rows: list[list[str]]) -> list[str]:
    """A Markdown table, with blank cells kept so columns stay aligned."""
    if not rows:
        return []
    width = max(len(r) for r in rows)
    line = lambda r: "|" + "|".join(" ".join(str(c).split()).replace("|", "/") for c in list(r) + [""] * (width - len(r))) + "|"
    return [line(rows[0]), "|" + "---|" * width] + [line(r) for r in rows[1:]]


def _pages_of(items: list[str]) -> list[str]:
    """Group text items into pages of readable length; no item is cut."""
    pages, batch, size = [], [], 0
    for item in items:
        if batch and size + len(item) > _CHARS_PER_PAGE:
            pages.append("\n\n".join(batch))
            batch, size = [], 0
        batch.append(item)
        size += len(item)
    return pages + (["\n\n".join(batch)] if batch else [])


def _unpacked_size_check(src: Path) -> None:
    """Office files are zips: refuse one that would unpack to an unreasonable size before any parser loads it."""
    with zipfile.ZipFile(src) as z:
        if sum(i.file_size for i in z.infolist()) > MAX_UNPACKED_BYTES:
            raise ValueError("file unpacks to more than the size limit")


def _element_text(element) -> str:
    """All text inside an XML element, paragraph by paragraph: includes text boxes and nested content."""
    paragraphs = []
    for p in element.iter(_W + "p"):
        text = "".join(t.text or "" for t in p.iter(_W + "t") if _owning_paragraph(t) is p)
        if text.strip():
            paragraphs.append(text.strip())
    return " ".join(paragraphs) or "".join(t.text or "" for t in element.iter(_W + "t")).strip()


def _owning_paragraph(node):
    parent = node.getparent()
    while parent is not None and parent.tag != _W + "p":
        parent = parent.getparent()
    return parent


def _docx_blocks(parent) -> list[str]:
    out = []
    for child in parent:
        if child.tag == _W + "tbl":
            rows = [[_element_text(c) for c in row.iter(_W + "tc") if c.getparent() is row] for row in child.iter(_W + "tr")]
            out.append("\n".join(_table([r for r in rows if r])))
        elif child.tag == _W + "sdt":
            for content in child.iter(_W + "sdtContent"):
                out.extend(_docx_blocks(content))
                break
        elif child.tag == _W + "p":
            for p in [child] + [x for x in child.iter(_W + "p") if x is not child]:  # the paragraph, then its text boxes
                text = "".join(t.text or "" for t in p.iter(_W + "t") if _owning_paragraph(t) is p).strip()
                if text:
                    out.append(text)
    return out


def _docx(src: Path) -> tuple[list[str], list[list[bytes]]]:
    from docx import Document
    from lxml import etree
    source = Document(str(src))
    items = _docx_blocks(source.element.body)
    pictures, extras = [], []
    for part in source.part.package.iter_parts():
        name = str(part.partname)
        if _EXTRA_PARTS.search(name):
            lines = [_element_text(p) for p in etree.fromstring(part.blob).iter(_W + "p")]
            extras.extend(line for line in lines if line)
        elif name.startswith("/word/media/"):
            pictures.append(part.blob)
    pages = _pages_of(items + list(dict.fromkeys(extras)))
    # Each picture gets a page of its own, after the text.
    return pages + [""] * len(pictures), [[] for _ in pages] + [[p] for p in pictures]


def _pptx(src: Path) -> tuple[list[str], list[list[bytes]]]:
    """One page per slide, so a citation's page number is the slide number."""
    from pptx import Presentation

    def walk(shapes):
        for shape in shapes:
            yield shape
            if hasattr(shape, "shapes"):
                yield from walk(shape.shapes)
    pages, pictures = [], []
    for slide in Presentation(str(src)).slides:
        items, images = [], []
        for shape in walk(slide.shapes):
            if getattr(shape, "has_text_frame", False) and shape.text_frame.text.strip():
                items.append(shape.text_frame.text.strip())
            if getattr(shape, "has_table", False) and shape.has_table:
                items.append("\n".join(_table([[c.text for c in row.cells] for row in shape.table.rows])))
            try:
                images.append(shape.image.blob)
            except (AttributeError, ValueError, KeyError):  # not a picture, or a linked picture with no stored bytes
                pass
        notes = slide.notes_slide.notes_text_frame if slide.has_notes_slide else None
        if notes is not None and notes.text.strip():
            items.append("Speaker notes: " + notes.text.strip())
        pages.append("\n\n".join(items))
        pictures.append(images)
    return pages, pictures


def _row_pages(title: str, rows: list[list[str]]) -> list[str]:
    """Rows as Markdown tables, repeating the sheet name and header row on every page."""
    if not rows:
        return []
    pages, batch, size = [], [], 0
    for row in rows[1:] or [[]]:
        batch.append(row)
        size += sum(len(c) for c in row)
        if size > _CHARS_PER_PAGE:
            pages.append(f"{title}\n\n" + "\n".join(_table([rows[0]] + batch)))
            batch, size = [], 0
    if batch:
        pages.append(f"{title}\n\n" + "\n".join(_table([rows[0]] + batch)))
    return pages


def _xlsx(src: Path) -> tuple[list[str], list[list[bytes]]]:
    from openpyxl import load_workbook
    values = load_workbook(src, read_only=True, data_only=True)
    formulas = load_workbook(src, read_only=True, data_only=False)  # a formula with no stored result still has its text
    try:
        pages = []
        for sheet in values.worksheets:
            rows = []
            for row, source in zip(sheet.iter_rows(values_only=True), formulas[sheet.title].iter_rows(values_only=True)):
                cells = ["" if (v if v is not None else f) is None else str(v if v is not None else f) for v, f in zip(row, source)]
                if any(c.strip() for c in cells):
                    rows.append(cells)
            pages.extend(_row_pages(f"Sheet: {sheet.title}", rows))
    finally:
        values.close()
        formulas.close()
    return pages, [[] for _ in pages]


def _read_text(src: Path) -> str:
    raw = src.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8-sig", errors="replace")


def _plain(src: Path) -> tuple[list[str], list[list[bytes]]]:
    text = _read_text(src)
    if src.suffix.lower() == ".csv":
        rows = [r for r in csv.reader(text.splitlines()) if any(c.strip() for c in r)]
        pages = _row_pages(f"File: {src.name}", rows)
    else:
        pages = _pages_of([p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()])
    return pages, [[] for _ in pages]


def _image_pages(src: Path) -> list[bytes]:
    """Every frame as a PNG, scaled down if huge, so OCR memory stays bounded."""
    blobs = []
    with pymupdf.open(src) as image:
        if image.page_count > MAX_PAGES:
            raise ValueError("too many frames")
        for frame in image:
            scale = min(1.0, _MAX_IMAGE_SIDE / max(frame.rect.width, frame.rect.height, 1))
            blobs.append(frame.get_pixmap(matrix=pymupdf.Matrix(scale, scale)).tobytes("png"))
    return blobs


def _legacy_tool() -> str | None:
    known = [r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
             "/usr/bin/soffice", "/Applications/LibreOffice.app/Contents/MacOS/soffice"]
    return shutil.which("soffice") or shutil.which("libreoffice") or next((p for p in known if Path(p).exists()), None)


def _legacy(src: Path, target: Path) -> bool:
    tool = _legacy_tool()
    if not tool:
        raise ValueError("this older format needs LibreOffice, which is not installed")
    with tempfile.TemporaryDirectory() as work:
        subprocess.run([tool, "--headless", f"-env:UserInstallation=file:///{work.replace(chr(92), '/')}/profile",
                        "--convert-to", "pdf", "--outdir", work, str(src)],
                       check=True, timeout=LEGACY_TIMEOUT_S, capture_output=True)
        made = Path(work) / (src.stem + ".pdf")
        if not made.exists():
            raise ValueError("LibreOffice produced no output")
        shutil.move(str(made), target)
    return True


def to_pdf(src: Path, target: Path) -> bool:
    """Write src as a PDF at target, plus its text sidecar. False if it holds nothing to index."""
    kind = src.suffix.lower()
    if kind in LEGACY_TYPES:
        return _legacy(src, target)
    texts: list[str] = []
    if kind in IMAGE_TYPES:
        pictures = [[b] for b in _image_pages(src)]
    else:
        if kind in OFFICE_TYPES:
            _unpacked_size_check(src)
        texts, pictures = {".docx": _docx, ".pptx": _pptx, ".xlsx": _xlsx}.get(kind, _plain)(src)
        if not any(t.strip() for t in texts) and not any(pictures):
            return False
    if len(pictures) > MAX_PAGES:
        raise ValueError(f"more than {MAX_PAGES} pages")
    with pymupdf.open() as doc:
        for images in pictures:
            page = doc.new_page(width=_PAGE.width, height=_PAGE.height)
            area = _PAGE + (40, 40, -40, -40)
            step = area.height / max(1, len(images))
            for i, blob in enumerate(images):
                try:
                    page.insert_image(pymupdf.Rect(area.x0, area.y0 + i * step, area.x1, area.y0 + (i + 1) * step), stream=blob)
                except Exception:  # noqa: BLE001 - a picture format MuPDF cannot draw (WMF, EMF) must not lose the text
                    pass
        # Identical blank pages must not make different files look like duplicates: identity comes from the content.
        digest = hashlib.sha256(json.dumps(texts).encode() + b"".join(b for images in pictures for b in images)).hexdigest()
        doc.set_metadata({"keywords": digest})
        doc.save(target)
    if texts:
        sidecar_for(target).write_text(json.dumps({str(i + 1): t for i, t in enumerate(texts)}, ensure_ascii=False), encoding="utf-8")
    return True
