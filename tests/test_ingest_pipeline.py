import re
import zipfile
from dataclasses import replace

import pytest

from kb.errors import KBError
from kb.ingest.pipeline import index_collection, safe_extract
from kb.llm import FakeLLM
from kb.registry import Registry
from kb.store import Store
from kb.testing import HashEmbedder, make_pdf


def card_responder(name, system, user):
    if name == "doc_card":
        return {"title": "Alpha Bank Annual Report", "doc_type": "annual_report", "issuer": "Alpha Bank",
                "entities": ["Alpha Bank"], "period_label": "FY2025", "period_year": 2025, "publication_date": None,
                "jurisdiction": "India", "topics": ["capital"], "summary": "Annual report."}
    pages = [int(n) for n in re.findall(r"=== page (\d+)", user)]
    return {"pages": [{"page_no": n, "summary": f"card for page {n}", "topics": ["capital"], "entities": [],
                       "figures": []} for n in pages]}


def _zip(tmp_path, files: dict[str, bytes], name="in.zip"):
    z = tmp_path / name
    with zipfile.ZipFile(z, "w") as f:
        for member, data in files.items():
            f.writestr(member, data)
    return z


def _pdf_bytes(tmp_path, pages, name="a.pdf"):
    return make_pdf(tmp_path / "src" / name, pages).read_bytes()


@pytest.fixture
def s1(settings):
    return replace(settings, parse_workers=1, page_cards_mode="llm")


def test_safe_extract_rejects_traversal(tmp_path, s1):
    z = _zip(tmp_path, {"../evil.pdf": b"%PDF", "ok.pdf": b"%PDF"})
    with pytest.raises(KBError) as e:
        safe_extract(z, tmp_path / "out", s1)
    assert e.value.code == "INVALID_ARCHIVE"
    assert not (tmp_path / "evil.pdf").exists()


def test_safe_extract_skips_junk_and_keeps_dup_basenames(tmp_path, s1):
    z = _zip(tmp_path, {"a/x.pdf": b"%PDF-1", "b/x.pdf": b"%PDF-2", "c/y.PDF": b"%PDF-3",
                        "__MACOSX/a/._x.pdf": b"junk", "notes.xyz": b"hi", ".DS_Store": b""})
    files, warnings = safe_extract(z, tmp_path / "out", s1)
    assert sorted(d for _, d in files) == ["a/x.pdf", "b/x.pdf", "y.PDF"]
    assert warnings == ["skipped unsupported file: notes.xyz"]
    assert all(p.is_file() for p, _ in files)


def test_safe_extract_errors(tmp_path, s1):
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(KBError) as e:
        safe_extract(bad, tmp_path / "o1", s1)
    assert e.value.code == "INVALID_ARCHIVE"
    with pytest.raises(KBError) as e:
        safe_extract(_zip(tmp_path, {"a.xyz": b"x"}, "n.zip"), tmp_path / "o2", s1)
    assert e.value.code == "NO_DOCUMENTS"
    with pytest.raises(KBError) as e:
        safe_extract(_zip(tmp_path, {"a.pdf": b"x" * 100}, "big.zip"), tmp_path / "o3", replace(s1, max_archive_bytes=10))
    assert e.value.code == "ARCHIVE_TOO_LARGE"


def test_index_end_to_end(tmp_path, s1):
    pdf = _pdf_bytes(tmp_path, ["Alpha bank capital ratio was 14.2 percent in FY2025 under the framework.",
                                "Liquidity coverage ratio stayed above the regulatory minimum all year."])
    z = _zip(tmp_path, {"docs/a.pdf": pdf, "docs/copy_of_a.pdf": pdf})
    out = index_collection(z, "c1", settings=s1, llm=FakeLLM(card_responder), embedder=HashEmbedder(), use_ocr=False)
    assert out["status"] == "ready" and out["documents"] == 1 and out["pages"] == 2 and out["elements"] >= 2
    assert any("duplicate of" in w for w in out["warnings"])
    assert out["llm_usage"]["calls"] == 2  # one doc card + one page-card batch
    gen_id, gen_dir = Registry(s1).active_dir("c1")
    assert gen_id == out["generation_id"] and not (gen_dir / "src").exists()
    store = Store.open(gen_dir)
    try:
        card = store.docs()[0]
        assert card.file_name in ("a.pdf", "copy_of_a.pdf") and card.period_year == 2025
        assert store.search_pages(["liquidity"], None, 1)[0][1] == 2
        assert store.dense_pages(HashEmbedder().embed(["card for page 2"]), None, 1)[0][1] == 2
        assert store.dense_elements(HashEmbedder().embed(["capital"]), None, 1) == []  # embed_elements off
        assert any("14.2" in e.text for e in store.elements_for_pages(card.doc_id, [1]))
    finally:
        store.close()


def test_failed_reindex_keeps_old_generation(tmp_path, s1):
    z = _zip(tmp_path, {"a.pdf": _pdf_bytes(tmp_path, ["Alpha bank capital ratio was 14.2 percent in FY2025."])})
    first = index_collection(z, "c1", settings=s1, llm=FakeLLM(card_responder), embedder=HashEmbedder(), use_ocr=False)

    class Boom:
        def embed(self, texts):
            raise RuntimeError("embedder down")

    with pytest.raises(RuntimeError):  # cache off, otherwise cached vectors would skip the embedder entirely
        index_collection(z, "c1", settings=replace(s1, use_cache=False), llm=FakeLLM(card_responder),
                         embedder=Boom(), use_ocr=False)
    gen_id, gen_dir = Registry(s1).active_dir("c1")
    assert gen_id == first["generation_id"]
    assert [d.name for d in (gen_dir.parent).iterdir()] == [gen_id]  # failed staging was discarded


def test_reindex_hits_cache_and_skips_parse_llm_embed(tmp_path, s1, monkeypatch):
    import kb.ingest.pipeline as pl

    z = _zip(tmp_path, {"a.pdf": _pdf_bytes(tmp_path, ["Alpha bank capital ratio was 14.2 percent in FY2025.",
                                                       "Liquidity coverage ratio stayed above the minimum."])})
    first = index_collection(z, "c1", settings=s1, llm=FakeLLM(card_responder), embedder=HashEmbedder(), use_ocr=False)
    assert first["cache_hits"] == {"parse": 0, "cards": 0, "embeddings": 0}

    def no_parse(*a, **k):
        raise AssertionError("parse_pages must not run on a cache hit")

    class NoEmbed:
        def embed(self, texts):
            raise AssertionError("embedder must not run on a cache hit")

    monkeypatch.setattr(pl, "parse_pages", no_parse)
    llm = FakeLLM(card_responder)
    second = index_collection(z, "c2", settings=s1, llm=llm, embedder=NoEmbed(), use_ocr=False)
    assert second["cache_hits"] == {"parse": 1, "cards": 1, "embeddings": 1}
    assert llm.calls == [] and second["elements"] == first["elements"]
    store = Store.open(Registry(s1).active_dir("c2")[1])
    try:
        assert store.search_pages(["liquidity"], None, 1)[0][1] == 2
        assert store.docs()[0].period_year == 2025
    finally:
        store.close()


def test_failed_llm_cards_are_not_cached(tmp_path, s1):
    from kb.llm import LLMError

    z = _zip(tmp_path, {"a.pdf": _pdf_bytes(tmp_path, ["Alpha bank capital ratio was 14.2 percent in FY2025."])})

    def failing(name, system, user):
        raise LLMError("no key")

    index_collection(z, "c1", settings=s1, llm=FakeLLM(failing), embedder=HashEmbedder(), use_ocr=False)
    llm = FakeLLM(card_responder)
    out = index_collection(z, "c2", settings=s1, llm=llm, embedder=HashEmbedder(), use_ocr=False)
    assert out["cache_hits"]["parse"] == 1 and out["cache_hits"]["cards"] == 0 and out["cache_hits"]["embeddings"] == 0
    assert any(c[0] == "doc_card" for c in llm.calls)  # cards rebuilt with the working LLM


def test_bad_name(tmp_path, s1):
    with pytest.raises(KBError) as e:
        index_collection(tmp_path / "z.zip", "bad name!", settings=s1, llm=FakeLLM(card_responder),
                         embedder=HashEmbedder(), use_ocr=False)
    assert e.value.code == "INVALID_COLLECTION_NAME" and e.value.http_status == 422


@pytest.mark.slow
def test_process_pool_parse(tmp_path, settings):
    """Real spawn-based worker pool on this OS (page_job_size=2 forces several jobs)."""
    pages = [f"Page {i} discusses capital buffers and leverage in detail for testing purposes." for i in range(1, 6)]
    z = _zip(tmp_path, {"a.pdf": _pdf_bytes(tmp_path, pages)})
    s = replace(settings, parse_workers=2, page_job_size=2)
    out = index_collection(z, "pool", settings=s, llm=FakeLLM(card_responder), embedder=HashEmbedder(), use_ocr=False)
    assert out["pages"] == 5
    store = Store.open(Registry(s).active_dir("pool")[1])
    try:
        assert [pc.page_no for pc in store.page_cards(store.docs()[0].doc_id)] == [1, 2, 3, 4, 5]
    finally:
        store.close()


def _parse(tmp_path, monkeypatch, text, markdown, *, ocr=None, regions=None):
    from kb.config import get_settings
    from kb.ingest import parse
    from kb.testing import make_pdf
    path = make_pdf(tmp_path / "a.pdf", [text])
    monkeypatch.setattr(parse, "_markdown", lambda doc, idx, *a, **k: {i + 1: markdown for i in idx})
    if ocr is not None:
        class Engine:
            def image_to_text(self, png):
                return ocr
        monkeypatch.setattr(parse, "get_ocr_engine", lambda: Engine())
        monkeypatch.setattr(parse, "_picture_regions", lambda page: [page.rect] if regions else [])
    pages, _ = parse.parse_pages(path, 1, 1, get_settings(data_dir=tmp_path), ocr is not None)
    return pages[0]


SENTENCE = "The total income during the year under review increased to eleven crore rupees overall."


def test_text_the_markdown_converter_drops_is_recovered(tmp_path, monkeypatch):
    page = _parse(tmp_path, monkeypatch, SENTENCE, "")
    assert "eleven crore rupees" in page.markdown and page.metadata["recovered_words"] > 0


def test_a_word_already_kept_is_not_added_twice(tmp_path, monkeypatch):
    page = _parse(tmp_path, monkeypatch, SENTENCE, SENTENCE)
    assert page.markdown.count("eleven crore rupees") == 1 and page.metadata["recovered_words"] == 0


def test_even_a_single_lost_word_comes_back(tmp_path, monkeypatch):
    page = _parse(tmp_path, monkeypatch, "Net 42", "")
    assert "Net" in page.markdown and "42" in page.markdown


def test_a_repeated_word_lost_once_comes_back(tmp_path, monkeypatch):
    from kb.ingest.parse import _words
    page = _parse(tmp_path, monkeypatch, "Total 10 Total 10", "Total 10")
    assert _words(page.markdown).count("total") >= 2


def test_every_text_layer_word_reaches_the_page(tmp_path, monkeypatch):
    from kb.ingest.parse import _words
    page = _parse(tmp_path, monkeypatch, SENTENCE, "The total")
    assert set(_words(SENTENCE)) <= set(_words(page.markdown))


def test_text_inside_a_picture_on_a_text_page_is_read(tmp_path, monkeypatch):
    page = _parse(tmp_path, monkeypatch, SENTENCE, SENTENCE, ocr="Credit rating Baa1\nthe total income during the year\n42", regions=True)
    assert "Text in image or figure:" in page.markdown and "Credit rating Baa1" in page.markdown and "\n42" in page.markdown
    assert page.is_ocr and page.metadata["visual"] and page.markdown.count("total income") == 1


def test_a_page_with_no_picture_is_not_read_by_ocr(tmp_path, monkeypatch):
    page = _parse(tmp_path, monkeypatch, SENTENCE, SENTENCE, ocr="Should not appear", regions=False)
    assert "Should not appear" not in page.markdown and not page.is_ocr


def test_comments_and_form_values_are_kept(tmp_path, monkeypatch):
    import pymupdf
    from kb.config import get_settings
    from kb.ingest import parse
    path = tmp_path / "f.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.add_text_annot((50, 50), "Reviewer note about the rate")
    field = pymupdf.Widget()
    field.field_name, field.field_type, field.field_value = "amount", pymupdf.PDF_WIDGET_TYPE_TEXT, "1500"
    field.rect = pymupdf.Rect(100, 100, 300, 130)
    page.add_widget(field)
    doc.save(path)
    pages, _ = parse.parse_pages(path, 1, 1, get_settings(data_dir=tmp_path), False)
    assert "Reviewer note about the rate" in pages[0].markdown and "1500" in pages[0].markdown


def test_index_summary_reports_extraction_coverage(tmp_path):
    from kb.config import get_settings
    from kb.ingest.pipeline import index_collection
    from kb.llm import FakeLLM
    from kb.testing import HashEmbedder
    settings = get_settings(data_dir=tmp_path / "data")
    z = _zip(tmp_path, {"a.pdf": _pdf_bytes(tmp_path, ["Alpha bank capital ratio was 14.2 percent in FY2025."])})
    out = index_collection(z, "c1", settings=settings, llm=FakeLLM(lambda n, s, u: {}), embedder=HashEmbedder(), use_ocr=False)
    assert out["extraction"]["coverage"] == 1.0 and out["extraction"]["missing_words"] == 0 and out["extraction"]["source_words"] > 0
    assert out["extraction"]["visual_pages_pending"] == 0
