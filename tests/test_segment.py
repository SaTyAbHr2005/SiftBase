import json
import statistics
from pathlib import Path

import pytest

from kb.ingest.segment import mark_boilerplate, segment_document
from kb.models import Element, ParsedDoc, PageText

PARA = ("The company maintains a conservative capital structure with low leverage, "
        "strong liquidity buffers and a disciplined approach to allocating free cash flow.")


def _doc(pages: list[str], outline=None, doc_id="d1") -> ParsedDoc:
    return ParsedDoc(doc_id=doc_id, file_name=f"{doc_id}.pdf", page_count=len(pages),
                     pages=[PageText(i + 1, md, False, []) for i, md in enumerate(pages)],
                     outline=outline or [], pdf_metadata={})


def test_heading_prefixed_and_section():
    els, sections = segment_document(_doc([f"# Risk Management\n\n{PARA}"]))
    assert len(els) == 1
    e = els[0]
    assert e.text.startswith("# Risk Management\n")
    assert e.section == "Risk Management" and sections[1] == "Risk Management"
    assert e.element_id == "d1:p0001:e000" and e.idx == 0 and e.kind == "text"


def test_short_line_becomes_table_caption():
    md = "(Rs in crore)\n\n| Item | FY26 | FY25 |\n|---|---|---|\n| Debt | 10 | 12 |"
    els, _ = segment_document(_doc([md]))
    assert len(els) == 1
    assert els[0].kind == "table"
    assert els[0].text.startswith("Caption: (Rs in crore)\n| Item")


def test_long_table_split_repeats_header():
    rows = "\n".join(f"| row {i} | {'value ' * 4}{i} | {i * 7} |" for i in range(200))
    md = f"| H1 | H2 | H3 |\n|---|---|---|\n{rows}"
    els, _ = segment_document(_doc([md]))
    assert len(els) > 1
    for e in els:
        assert e.kind == "table"
        assert e.text.startswith("| H1 | H2 | H3 |\n|---|---|---|\n")
        assert len(e.text) <= 4300
    assert [e.idx for e in els] == list(range(len(els)))


def test_long_paragraph_split_on_sentence():
    els, _ = segment_document(_doc([" ".join(["This is a sentence about capital ratios."] * 80)]))
    assert len(els) >= 2
    assert all(len(e.text) <= 1800 for e in els)
    assert all(e.text.endswith(".") for e in els[:-1])


def test_outline_sections_carry_across_pages():
    _, sections = segment_document(_doc([PARA, PARA], outline=[(1, "Notes", 1), (2, "Borrowings", 2)]))
    assert sections == {1: "Notes", 2: "Notes > Borrowings"}


def test_markdown_headings_refine_page_only_with_outline():
    doc = _doc([f"## Term loans\n\n{PARA}", PARA], outline=[(1, "Notes", 1)])
    els, sections = segment_document(doc)
    assert els[0].section == "Notes > Term loans"
    assert sections == {1: "Notes > Term loans", 2: "Notes"}


def test_symbol_only_lines_are_dropped_but_a_number_is_kept():
    els, _ = segment_document(_doc([f"12\n\n---\n\n{PARA}"]))
    assert len(els) == 1 and els[0].text.startswith("12") and PARA in els[0].text and "---" not in els[0].text


def test_short_blocks_merge_and_table_gets_heading_caption():
    table = "| Asset | Value |\n|---|---|\n| Cash | 2 |"
    md = f"Short intro.\n\n{PARA}\n\n## Debt\n\nAside.\n\n{PARA}\n\n{table}\n\nTail."
    els, _ = segment_document(_doc([md]))
    assert [e.kind for e in els] == ["text", "text", "table"]
    assert els[0].text == f"Short intro.\n\n{PARA}"
    assert els[1].text.startswith("## Debt\nAside.\n\n")
    assert els[2].text == f"Caption: Debt\n{table}\n\nTail."


def test_boilerplate_marked(settings):
    footer = "Integrated Annual Report 2025-26 | Infosys\n{}"   # page-number line differs; normalised away
    footers = [Element(f"d1:p{i:04d}:e001", "d1", i, 1, "text", "", footer.format(i)) for i in range(1, 11)]
    uniques = [Element(f"d1:p{i:04d}:e000", "d1", i, 0, "text", "", f"Unique paragraph {i}. {PARA}")
               for i in range(1, 11)]
    n = mark_boilerplate(footers + uniques, 10, settings)
    assert n == 10
    assert all(f.flags == ["boilerplate"] for f in footers)
    assert all(u.flags == [] for u in uniques)


INFOSYS = Path(__file__).resolve().parents[1] / "Train" / "Train" / "Documents" / "infosys-ar-26.pdf"


@pytest.mark.slow
@pytest.mark.skipif(not INFOSYS.exists(), reason="training corpus not present")
def test_real_infosys_segmentation(settings):
    import pymupdf
    import pymupdf4llm

    pdf = pymupdf.open(INFOSYS)
    chunks = pymupdf4llm.to_markdown(pdf, page_chunks=True, show_progress=False, use_ocr=False,
                                     header=False, footer=False)
    doc = ParsedDoc("infosys", INFOSYS.name, pdf.page_count,
                    [PageText(c["metadata"]["page_number"], c["text"], False, []) for c in chunks],
                    [tuple(t) for t in pdf.get_toc(simple=True) if t[2] >= 1], {})
    els, _ = segment_document(doc)
    mark_boilerplate(els, doc.page_count, settings)
    median = statistics.median(len(e.text) for e in els)
    print(json.dumps({"elements": len(els), "median_chars": median,
                      "boilerplate": sum("boilerplate" in e.flags for e in els)}))
    assert 250 <= median <= 900
    assert any("Sundaram" in e.text for e in els if e.page_no == 108)


def _pages(*markdowns):
    from kb.models import PageText, ParsedDoc
    return ParsedDoc(doc_id="d", file_name="d.pdf", page_count=len(markdowns), outline=[], pdf_metadata={},
                     pages=[PageText(page_no=i + 1, markdown=m, is_ocr=False, toc_titles=[]) for i, m in enumerate(markdowns)])


FIRST = "|Year|Revenue|Profit|\n|---|---|---|\n|2023|10|1|"
NEXT = "|2024|12|2|\n|---|---|---|\n|2025|14|3|"


def test_table_continuing_on_the_next_page_keeps_its_column_names():
    elements, _ = segment_document(_pages(FIRST, NEXT, NEXT))
    assert "Table continued from page 1; columns: Year | Revenue | Profit" in elements[1].text
    # A third page still gets the headings from the first page, and pages stay exact.
    assert "Table continued from page 2; columns: Year | Revenue | Profit" in elements[2].text
    assert [e.page_no for e in elements] == [1, 2, 3] and "|2025|14|3|" in elements[2].text
    assert "continued" not in elements[0].text


def test_unrelated_tables_are_not_treated_as_continuations():
    other = "|A|B|\n|---|---|\n|1|2|"
    text = "A full sentence of ordinary text that sits between the two tables on this page here, long enough to stand alone as a block."
    for pages in ((FIRST, other), (FIRST, "# Next heading\n" + NEXT), (FIRST + "\n\n" + text, NEXT), (FIRST, text, NEXT)):
        elements, _ = segment_document(_pages(*pages))
        assert not any("continued" in e.text for e in elements)


def test_repeated_header_row_is_noted_without_repeating_columns():
    elements, _ = segment_document(_pages(FIRST, FIRST))
    assert "Table continued from page 1" in elements[1].text and "columns:" not in elements[1].text


def test_figures_trailing_headings_and_short_lines_all_survive_segmentation():
    from kb.ingest.segment import extraction_report
    doc = _pages("|12|40|\n|---|---|\n|13|55|", "Some text here\n\n7", "# Final heading of the page", "45\n60\n75")
    elements, sections = segment_document(doc)
    text = " ".join(e.text for e in elements)
    assert "|13|55|" in text and "Final heading" in text and "60" in text
    report = extraction_report([doc], [(elements, sections)])
    assert report["missing_words"] == 0 and report["coverage"] == 1.0


def test_extraction_report_names_pages_that_lost_words():
    from kb.ingest.segment import extraction_report
    doc = _pages("Alpha beta gamma.")
    report = extraction_report([doc], [([], {})])
    assert report["missing_words"] == 3 and report["pages_with_missing_words"] == [{"document": "d.pdf", "page": 1, "missing_words": 3}]


def test_running_header_does_not_break_table_continuation():
    elements, _ = segment_document(_pages(FIRST + "\n\nCompany Report", "Company Report\n\n" + NEXT))
    assert any("Table continued from page 1; columns: Year | Revenue | Profit" in e.text for e in elements)


def test_two_column_tables_on_adjacent_pages_are_only_a_suggestion():
    elements, _ = segment_document(_pages("|Name|Value|\n|---|---|\n|a|1|", "|b|2|\n|---|---|\n|c|3|"))
    assert "Table may continue from page 1" in elements[1].text
