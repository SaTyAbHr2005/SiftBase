import io
import json
import zipfile

import pymupdf
import pytest

from kb.config import get_settings
from kb.ingest.convert import sidecar_for, to_pdf
from kb.ingest.pipeline import safe_extract


def _pages(pdf):
    return json.loads(sidecar_for(pdf).read_text(encoding="utf-8"))


def _png():
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    pix.clear_with(255)
    return pix.tobytes("png")


def test_docx_keeps_order_tables_text_boxes_headers_and_pictures(tmp_path):
    from docx import Document
    d = Document()
    d.sections[0].header.paragraphs[0].text = "Running header text"
    d.sections[0].footer.paragraphs[0].text = "Footer disclaimer text"
    d.add_paragraph("Opening paragraph about pumps.")
    table = d.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Item", "Value"
    table.cell(1, 0).text, table.cell(1, 1).text = "Pressure", "4 bar"
    d.add_paragraph("Closing paragraph.")
    d.add_picture(io.BytesIO(_png()))
    d.save(tmp_path / "a.docx")
    assert to_pdf(tmp_path / "a.docx", tmp_path / "a.pdf")
    pages = _pages(tmp_path / "a.pdf")
    text = pages["1"]
    assert text.index("Opening") < text.index("|Pressure|4 bar|") < text.index("Closing")
    assert "Running header text" in text and "Footer disclaimer text" in text
    with pymupdf.open(tmp_path / "a.pdf") as doc:
        assert doc.page_count == 2 and doc[1].get_images()  # the picture has its own page, so OCR can read it


def test_long_docx_loses_no_line(tmp_path):
    from docx import Document
    d = Document()
    for i in range(400):
        d.add_paragraph(f"Line number {i} of a long document with enough words to fill a page.")
    d.save(tmp_path / "a.docx")
    to_pdf(tmp_path / "a.docx", tmp_path / "a.pdf")
    pages = _pages(tmp_path / "a.pdf")
    assert len(pages) > 1 and all(f"Line number {i} of" in " ".join(pages.values()) for i in range(400))


@pytest.mark.parametrize("sample", ["कंपनी का राजस्व बढ़ा", "நிறுவனத்தின் வருவாய்", "ارتفعت إيرادات الشركة", "公司收入增长了"])
def test_non_latin_office_and_text_stays_exact(tmp_path, sample):
    from docx import Document
    d = Document()
    d.add_paragraph(sample)
    d.save(tmp_path / "a.docx")
    to_pdf(tmp_path / "a.docx", tmp_path / "a.pdf")
    assert sample in _pages(tmp_path / "a.pdf")["1"]
    (tmp_path / "b.txt").write_text(sample, encoding="utf-16")
    to_pdf(tmp_path / "b.txt", tmp_path / "b.pdf")
    assert sample in _pages(tmp_path / "b.pdf")["1"]


def test_pptx_has_one_page_per_slide_with_tables_notes_groups_and_pictures(tmp_path):
    from pptx import Presentation
    from pptx.util import Inches
    p = Presentation()
    s = p.slides.add_slide(p.slide_layouts[5])
    s.shapes.title.text = "First slide title"
    s.notes_slide.notes_text_frame.text = "Spoken detail"
    t = s.shapes.add_table(1, 2, Inches(1), Inches(2), Inches(4), Inches(1)).table
    t.cell(0, 0).text, t.cell(0, 1).text = "Revenue", "12"
    group = s.shapes.add_group_shape()
    box = group.shapes.add_textbox(Inches(1), Inches(3), Inches(2), Inches(1))
    box.text_frame.text = "Grouped label"
    s.shapes.add_picture(io.BytesIO(_png()), Inches(1), Inches(4))
    second = p.slides.add_slide(p.slide_layouts[5])
    second.shapes.title.text = "Second slide title"
    p.save(tmp_path / "a.pptx")
    to_pdf(tmp_path / "a.pptx", tmp_path / "a.pdf")
    pages = _pages(tmp_path / "a.pdf")
    assert len(pages) == 2 and "Second slide title" in pages["2"]
    for expected in ("|Revenue|12|", "Spoken detail", "Grouped label", "First slide title"):
        assert expected in pages["1"]
    with pymupdf.open(tmp_path / "a.pdf") as doc:
        assert doc.page_count == 2 and doc[0].get_images()


def test_xlsx_keeps_blank_cells_every_sheet_and_formulas(tmp_path):
    from openpyxl import Workbook
    book = Workbook()
    book.active.title = "Costs"
    book.active.append(["Item", "Note", "Amount"])
    book.active.append(["Rent", None, 120])
    book.active.append(["Total", None, "=SUM(C2:C2)"])
    book.create_sheet("Other").append(["Second sheet value"])
    book.save(tmp_path / "a.xlsx")
    to_pdf(tmp_path / "a.xlsx", tmp_path / "a.pdf")
    text = " ".join(_pages(tmp_path / "a.pdf").values())
    assert "Sheet: Costs" in text and "|Rent||120|" in text and "=SUM(C2:C2)" in text and "Second sheet value" in text


def test_every_page_of_a_long_sheet_repeats_its_column_names(tmp_path):
    from openpyxl import Workbook
    book = Workbook()
    book.active.append(["Item", "Amount"])
    for i in range(2000):
        book.active.append([f"Row {i}", i])
    book.save(tmp_path / "a.xlsx")
    to_pdf(tmp_path / "a.xlsx", tmp_path / "a.pdf")
    pages = _pages(tmp_path / "a.pdf")
    assert len(pages) > 1 and all("|Item|Amount|" in p for p in pages.values())
    assert all(f"|Row {i}|{i}|" in " ".join(pages.values()) for i in range(2000))


def test_images_become_pages_and_huge_ones_are_scaled_down(tmp_path):
    (tmp_path / "a.png").write_bytes(_png())
    assert to_pdf(tmp_path / "a.png", tmp_path / "a.pdf")
    with pymupdf.open(tmp_path / "a.pdf") as doc:
        assert doc.page_count == 1 and doc[0].get_images() and doc[0].rect.width < 700
    assert not sidecar_for(tmp_path / "a.pdf").exists()


def test_empty_file_is_reported_and_different_files_stay_distinct(tmp_path):
    (tmp_path / "e.txt").write_text("  \n", encoding="utf-8")
    assert not to_pdf(tmp_path / "e.txt", tmp_path / "e.pdf")
    from kb.ingest.parse import doc_id_for
    for name, text in (("a", "First note."), ("b", "Second note.")):
        (tmp_path / f"{name}.txt").write_text(text, encoding="utf-8")
        to_pdf(tmp_path / f"{name}.txt", tmp_path / f"{name}.pdf")
    assert doc_id_for(tmp_path / "a.pdf") != doc_id_for(tmp_path / "b.pdf")


def test_csv_becomes_a_table(tmp_path):
    (tmp_path / "c.csv").write_text('Item,Amount\n"Rent, office",120\n', encoding="utf-8")
    to_pdf(tmp_path / "c.csv", tmp_path / "c.pdf")
    assert "|Rent, office|120|" in _pages(tmp_path / "c.pdf")["1"]


def test_office_zip_bomb_is_refused_before_parsing(tmp_path, monkeypatch):
    from kb.ingest import convert
    monkeypatch.setattr(convert, "MAX_UNPACKED_BYTES", 10)
    with zipfile.ZipFile(tmp_path / "a.docx", "w") as z:
        z.writestr("word/document.xml", "x" * 100)
    with pytest.raises(ValueError, match="size limit"):
        to_pdf(tmp_path / "a.docx", tmp_path / "a.pdf")


def test_legacy_format_without_libreoffice_gives_a_clear_reason(tmp_path, monkeypatch):
    from kb.ingest import convert
    monkeypatch.setattr(convert, "_legacy_tool", lambda: None)
    (tmp_path / "a.doc").write_bytes(b"old")
    with pytest.raises(ValueError, match="LibreOffice"):
        to_pdf(tmp_path / "a.doc", tmp_path / "a.pdf")


def test_parse_uses_the_exact_office_text_and_reads_pictures(tmp_path, monkeypatch):
    from docx import Document
    from kb.config import get_settings
    from kb.ingest import parse
    d = Document()
    d.add_paragraph("कंपनी का राजस्व बढ़ा")
    d.add_picture(io.BytesIO(_png()))
    d.save(tmp_path / "a.docx")
    to_pdf(tmp_path / "a.docx", tmp_path / "a.pdf")
    class Engine:
        def image_to_text(self, png):
            return "Label inside picture"
    monkeypatch.setattr(parse, "get_ocr_engine", lambda: Engine())
    pages, _ = parse.parse_pages(tmp_path / "a.pdf", 1, 2, get_settings(data_dir=tmp_path), True)
    assert "कंपनी का राजस्व बढ़ा" in pages[0].markdown and "Label inside picture" in pages[1].markdown


def test_archive_converts_other_formats_keeps_names_and_warns_on_failures(tmp_path):
    z = tmp_path / "in.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("deck/note.txt", "A plain note about pumps.")
        f.writestr("broken.docx", b"not really a document")
        f.writestr("old.xyz", b"unknown")
    files, warnings = safe_extract(z, tmp_path / "out", get_settings(data_dir=tmp_path))
    assert [d for _, d in files] == ["note.txt"] and "plain note" in _pages(files[0][0])["1"]
    assert any("broken.docx" in w for w in warnings) and any("old.xyz" in w for w in warnings)
    with zipfile.ZipFile(tmp_path / "bad.zip", "w") as f:
        f.writestr("only.xyz", b"x")
    with pytest.raises(Exception, match="no supported"):
        safe_extract(tmp_path / "bad.zip", tmp_path / "o2", get_settings(data_dir=tmp_path))


class _Reply:
    status_code = 200
    def __init__(self, text): self.text = text
    def raise_for_status(self): pass
    def json(self): return {"choices": [{"message": {"content": self.text}}]}


def test_chart_descriptions_are_saved_and_resume_within_the_daily_limit(tmp_path, monkeypatch):
    import requests
    from kb.ingest import vision
    from kb.models import PageText, ParsedDoc
    from kb.testing import make_pdf
    monkeypatch.setenv("GROQ_API_KEY", "k")
    monkeypatch.setattr(vision, "PACE_S", 0)
    calls = []
    monkeypatch.setattr(vision.requests, "post", lambda *a, **k: (calls.append(1), _Reply("Bar chart of revenue."))[1])
    path = make_pdf(tmp_path / "a.pdf", ["one", "two"])
    class Cache:
        store = {}
        def load_json(self, kind, key): return self.store.get(key)
        def save_json(self, kind, key, value): self.store[key] = dict(value)
    def doc():
        pages = [PageText(i, "body", False, [], {"visual": True}) for i in (1, 2)]
        return ParsedDoc("d", "a.pdf", 2, pages, [], {})
    first = doc()
    assert vision.add_visual_descriptions([first], {"d": str(path)}, Cache(), 1) == {"visual_pages_described": 1, "visual_pages_pending": 1}
    assert "Bar chart" in first.pages[0].markdown and "Bar chart" not in first.pages[1].markdown
    second = doc()
    assert vision.add_visual_descriptions([second], {"d": str(path)}, Cache(), 1)["visual_pages_described"] == 2
    assert len(calls) == 2  # the saved page was not paid for twice
    monkeypatch.setattr(vision.requests, "post", lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError()))
    Cache.store = {}
    third = doc()
    assert vision.add_visual_descriptions([third], {"d": str(path)}, Cache(), 5) == {"visual_pages_described": 0, "visual_pages_pending": 2}
    assert third.pages[0].markdown == "body"  # a failed description never harms indexing
