import io
import zipfile

import pymupdf
import pytest

from kb.config import get_settings
from kb.ingest.convert import to_pdf
from kb.ingest.pipeline import safe_extract


def _text(path):
    with pymupdf.open(path) as doc:
        return [page.get_text() for page in doc]


def _png():
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    pix.clear_with(255)
    return pix.tobytes("png")


def test_docx_keeps_paragraphs_tables_and_pictures_in_order(tmp_path):
    from docx import Document
    d = Document()
    d.add_paragraph("Opening paragraph about pumps.")
    table = d.add_table(rows=1, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Pressure", "4 bar"
    d.add_paragraph("Closing paragraph.")
    d.add_picture(io.BytesIO(_png()))
    d.save(tmp_path / "a.docx")
    assert to_pdf(tmp_path / "a.docx", tmp_path / "a.pdf")
    pages = _text(tmp_path / "a.pdf")
    text = " ".join(pages[0].split())
    assert text.index("Opening") < text.index("Pressure | 4 bar") < text.index("Closing")
    with pymupdf.open(tmp_path / "a.pdf") as doc:
        assert doc[1].get_images()  # the picture has its own page, so OCR can read it


def test_long_docx_flows_onto_more_pages_without_losing_text(tmp_path):
    from docx import Document
    d = Document()
    for i in range(400):
        d.add_paragraph(f"Line number {i} of a long document with enough words to fill a page.")
    d.save(tmp_path / "a.docx")
    to_pdf(tmp_path / "a.docx", tmp_path / "a.pdf")
    pages = _text(tmp_path / "a.pdf")
    assert len(pages) > 1
    text = " ".join(" ".join(pages).split())
    assert all(f"Line number {i} of" in text for i in range(400))


def test_pptx_has_one_page_per_slide_with_tables_notes_and_pictures(tmp_path):
    from pptx import Presentation
    from pptx.util import Inches
    p = Presentation()
    s = p.slides.add_slide(p.slide_layouts[5])
    s.shapes.title.text = "First slide title"
    s.notes_slide.notes_text_frame.text = "Spoken detail"
    t = s.shapes.add_table(1, 2, Inches(1), Inches(2), Inches(4), Inches(1)).table
    t.cell(0, 0).text, t.cell(0, 1).text = "Revenue", "12"
    s.shapes.add_picture(io.BytesIO(_png()), Inches(1), Inches(4))
    second = p.slides.add_slide(p.slide_layouts[5])
    second.shapes.title.text = "Second slide title"
    p.save(tmp_path / "a.pptx")
    to_pdf(tmp_path / "a.pptx", tmp_path / "a.pdf")
    pages = _text(tmp_path / "a.pdf")
    assert len(pages) == 2 and "Second slide title" in pages[1]
    assert "Revenue | 12" in " ".join(pages[0].split()) and "Spoken detail" in pages[0]
    with pymupdf.open(tmp_path / "a.pdf") as doc:
        assert doc[0].get_images()


def test_xlsx_keeps_each_sheet_and_row(tmp_path):
    from openpyxl import Workbook
    book = Workbook()
    book.active.title = "Costs"
    book.active.append(["Item", "Amount"])
    book.active.append(["Rent", 120])
    book.save(tmp_path / "a.xlsx")
    to_pdf(tmp_path / "a.xlsx", tmp_path / "a.pdf")
    text = " ".join(_text(tmp_path / "a.pdf")[0].split())
    assert "Sheet: Costs" in text and "Rent | 120" in text


def test_image_and_text_files_convert_and_empty_ones_report_nothing(tmp_path):
    (tmp_path / "a.png").write_bytes(_png())
    assert to_pdf(tmp_path / "a.png", tmp_path / "a.pdf")
    assert pymupdf.open(tmp_path / "a.pdf").page_count == 1
    (tmp_path / "n.txt").write_text("A plain note about pumps.", encoding="utf-8")
    assert to_pdf(tmp_path / "n.txt", tmp_path / "n.pdf") and "plain note" in _text(tmp_path / "n.pdf")[0]
    (tmp_path / "e.txt").write_text("  \n", encoding="utf-8")
    assert not to_pdf(tmp_path / "e.txt", tmp_path / "e.pdf")


def test_archive_converts_other_formats_keeps_names_and_warns_on_failures(tmp_path):
    z = tmp_path / "in.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("deck/note.txt", "A plain note about pumps.")
        f.writestr("broken.docx", b"not really a document")
        f.writestr("old.ppt", b"legacy")
    files, warnings = safe_extract(z, tmp_path / "out", get_settings(data_dir=tmp_path))
    assert [d for _, d in files] == ["note.txt"] and "plain note" in _text(files[0][0])[0]
    assert any("broken.docx" in w for w in warnings) and any("old.ppt" in w for w in warnings)
    with zipfile.ZipFile(tmp_path / "bad.zip", "w") as f:
        f.writestr("only.xyz", b"x")
    with pytest.raises(Exception, match="no supported"):
        safe_extract(tmp_path / "bad.zip", tmp_path / "o2", get_settings(data_dir=tmp_path))
