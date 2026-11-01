"""ZIP -> validated generation: extract, parse (page-parallel), segment, cards, embed, store, promote.

Content-hash cache (settings.use_cache): parsed pages, LLM cards and page vectors are stored per document under
data/cache, keyed by the file's sha1 plus a fingerprint of every setting/prompt/model that affects them, so
re-indexing unchanged documents skips parsing, LLM calls and embedding.
"""
import hashlib
import json
import logging
import os
import re
import shutil
import stat
import threading
import time
import zipfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
from pathlib import Path, PurePosixPath

import numpy as np

from kb.config import Settings
from kb.errors import KBError
from kb.ingest import cards as cards_mod
from kb.ingest.cards import (assign_sibling_groups, augment_topics, build_doc_card, build_page_cards,
                             element_embedding_text, page_embedding_text)
from kb.ingest.convert import SUPPORTED, to_pdf
from kb.ingest.parse import parse_pages, read_pdf_info, page_source_metadata
from kb.ingest.progress import no_progress
from kb.ingest.segment import extraction_report, mark_boilerplate, segment_document
from kb.llm import LLM, parallel_map
from kb.models import BLANK_PAGE_SUMMARY, DocCard, Embedder, PageCard, PageText, ParsedDoc
from kb.registry import Registry
from kb.store import Store

CACHE_VERSION = 7

log = logging.getLogger("kb.ingest")
COLLECTION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
EMBED_CHUNK = 512
PARSE_STEP = "1/7 Reading pages"
VISION_STEP = "2/7 Summarising charts"
SEGMENT_STEP = "3/7 Checking every word"
DOC_CARD_STEP = "4/7 Document summaries"
PAGE_CARD_STEP = "5/7 Page summaries"
EMBED_STEP = "6/7 Search vectors"
SAVE_STEP = "7/7 Saving the index"


def _unsafe(name: str) -> bool:
    if "\x00" in name or name.startswith(("/", "\\")) or re.match(r"^[A-Za-z]:", name):
        return True
    return ".." in PurePosixPath(name.replace("\\", "/")).parts


def safe_extract(zip_path: Path, dest: Path, settings: Settings) -> tuple[list[tuple[Path, str]], list[str]]:
    """Extract every supported file as a PDF. Returns ([(path, display_name)], warnings). Unsafe archives are rejected whole."""
    try:
        zf = zipfile.ZipFile(zip_path)
    except (zipfile.BadZipFile, OSError) as e:
        raise KBError("INVALID_ARCHIVE", f"Not a readable zip file: {e}", 400)
    with zf:
        infos = zf.infolist()
        for info in infos:
            is_link = stat.S_ISLNK(info.external_attr >> 16)
            if _unsafe(info.filename) or is_link or info.flag_bits & 0x1:
                raise KBError("INVALID_ARCHIVE", "Archive contains an unsafe, linked or encrypted member.", 400,
                              details={"member": info.filename[:200]})
        if sum(i.file_size for i in infos) > settings.max_archive_bytes:
            raise KBError("ARCHIVE_TOO_LARGE", "Archive exceeds the uncompressed size limit.", 413,
                          details={"limit_bytes": settings.max_archive_bytes})
        warnings, pdfs = [], []
        for info in infos:
            name = info.filename.replace("\\", "/")
            parts = PurePosixPath(name).parts
            if info.is_dir() or not parts:
                continue
            if parts[0] == "__MACOSX" or parts[-1].startswith("."):
                continue
            if PurePosixPath(name).suffix.lower() not in SUPPORTED:
                warnings.append(f"skipped unsupported file: {name}")
                continue
            pdfs.append((info, name))
        if not pdfs:
            raise KBError("NO_DOCUMENTS", "The archive contains no supported documents.", 400)
        basenames = [PurePosixPath(n).name for _, n in pdfs]
        out = []
        dest.mkdir(parents=True, exist_ok=True)
        for i, (info, name) in enumerate(sorted(pdfs, key=lambda x: x[1])):
            base = PurePosixPath(name).name
            display = base if basenames.count(base) == 1 else name
            target = dest / f"{i:05d}.pdf"
            suffix = PurePosixPath(name).suffix.lower()
            raw = target if suffix == ".pdf" else dest / f"{i:05d}{suffix}"
            with zf.open(info) as src, open(raw, "wb") as dst:
                shutil.copyfileobj(src, dst, 1 << 20)
            if raw != target:
                try:
                    if not to_pdf(raw, target):
                        warnings.append(f"no content found in: {name}")
                        continue
                except Exception as e:  # noqa: BLE001 - one unreadable file must not fail the collection
                    warnings.append(f"could not read {name}: {str(e)[:120]}")
                    continue
                finally:
                    raw.unlink(missing_ok=True)
            out.append((target, display))
        return out, warnings


def _workers(settings: Settings) -> int:
    return settings.parse_workers or min(6, max(1, (os.cpu_count() or 2) // 2))


def _fp(obj) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:12]


def _fingerprints(settings: Settings, use_ocr: bool) -> dict[str, str]:
    import pymupdf4llm
    parse = _fp({"v": CACHE_VERSION, "layout": settings.parse_layout, "ocr": use_ocr, "dpi": settings.ocr_dpi,
                 "min_text": settings.min_text_chars, "p4llm": getattr(pymupdf4llm, "__version__", "?")})
    cards = _fp({"parse": parse, "model": settings.llm_model, "mode": settings.page_cards_mode,
                 "per_call": settings.page_card_pages_per_call,
                 "chars": settings.page_card_chars_per_page, "doc_chars": settings.doc_card_chars,
                 "prompts": [cards_mod.DOC_CARD_SYSTEM, cards_mod.DOC_CARD_USER_TEMPLATE,
                             cards_mod.PAGE_CARD_SYSTEM, cards_mod.PAGE_CARD_USER_TEMPLATE]})
    emb = _fp({"cards": cards, "model": settings.embed_model, "max_chars": settings.embed_max_chars})
    return {"vision": "1", "parse": parse, "cards": cards, "emb": emb}


class _Cache:
    """Per-document artifacts on disk; writes are atomic (temp file + os.replace). Disabled -> all misses."""

    def __init__(self, settings: Settings, fps: dict[str, str]):
        self.root = settings.cache_path() if settings.use_cache else None
        self.fps = fps

    def _path(self, kind: str, doc_id: str, ext: str) -> Path:
        return self.root / kind / f"{doc_id}-{self.fps[kind]}.{ext}"

    def load_json(self, kind: str, doc_id: str):
        if self.root is None:
            return None
        try:
            return json.loads(self._path(kind, doc_id, "json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save_json(self, kind: str, doc_id: str, obj) -> None:
        if self.root is not None:
            self._atomic(self._path(kind, doc_id, "json"), json.dumps(obj).encode("utf-8"))

    def load_vecs(self, doc_id: str, rows: int) -> np.ndarray | None:
        if self.root is None:
            return None
        try:
            v = np.load(self._path("emb", doc_id, "npy"))
            return v if len(v) == rows else None
        except (OSError, ValueError):
            return None

    def save_vecs(self, doc_id: str, vecs: np.ndarray) -> None:
        if self.root is not None:
            path = self._path("emb", doc_id, "npy")
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{os.getpid()}.tmp.npy")
            np.save(tmp, vecs)
            os.replace(tmp, path)

    @staticmethod
    def _atomic(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)


class _CountingLLM:
    """Counts LLM failures for one document so fallback cards are never cached."""

    def __init__(self, inner: LLM):
        self.inner = inner
        self.failures = 0
        self._lock = threading.Lock()

    def complete_json(self, *args, **kwargs):
        try:
            return self.inner.complete_json(*args, **kwargs)
        except Exception:
            with self._lock:
                self.failures += 1
            raise


def _counted(fn, step: str, total: int, progress):
    """Wrap fn so each finished item moves the progress bar, also when items run in parallel."""
    lock, done = threading.Lock(), [0]
    progress(step, 0, total)

    def run(item):
        try:
            return fn(item)
        finally:
            with lock:
                done[0] += 1
                progress(step, done[0], total)
    return run


def _parse_all(files: list[tuple[Path, str]], settings: Settings, use_ocr: bool, cache: _Cache,
               progress=no_progress) -> tuple[list[ParsedDoc], int]:
    """Returns (docs, parse_cache_hits). Cached documents skip parsing entirely."""
    infos = [(path, display, *read_pdf_info(path)) for path, display in files]
    docs = [ParsedDoc(doc_id, display, count, [], outline, meta) for _, display, doc_id, count, outline, meta in infos]
    hits, todo = 0, []
    for i, d in enumerate(docs):
        cached = cache.load_json("parse", d.doc_id)
        if cached and len(cached["pages"]) == d.page_count:
            d.pages = [PageText(**p) for p in cached["pages"]]
            d.ocr_unavailable_pages = cached["ocr_unavailable"]
            if any(not p.metadata for p in d.pages):
                import pymupdf
                with pymupdf.open(infos[i][0]) as pdf:
                    for p in d.pages:
                        if not p.metadata:p.metadata=page_source_metadata(pdf[p.page_no-1],d.page_count,p.markdown)
                cache.save_json("parse",d.doc_id,{"pages":[asdict(p) for p in d.pages],"ocr_unavailable":d.ocr_unavailable_pages})
            hits += 1
        else:
            todo.append(i)
    jobs = [(i, start, min(start + settings.page_job_size - 1, docs[i].page_count))
            for i in todo for start in range(1, docs[i].page_count + 1, settings.page_job_size)]
    total_pages = sum(docs[i].page_count for i in todo)
    jobs_left = Counter(i for i, _, _ in jobs)
    pages_done = 0
    progress(PARSE_STEP, 0, total_pages)

    def finish(job: tuple[int, int, int], result: tuple[list[PageText], int]) -> None:
        # A finished document is saved at once, so a stopped run resumes without reading it again.
        nonlocal pages_done
        i, start, end = job
        docs[i].pages.extend(result[0])
        docs[i].ocr_unavailable_pages += result[1]
        jobs_left[i] -= 1
        if not jobs_left[i]:
            docs[i].pages.sort(key=lambda p: p.page_no)
            cache.save_json("parse", docs[i].doc_id, {"pages": [asdict(p) for p in docs[i].pages],
                                                      "ocr_unavailable": docs[i].ocr_unavailable_pages})
        pages_done += end - start + 1
        progress(PARSE_STEP, pages_done, total_pages)

    workers = _workers(settings)
    if workers <= 1 or len(jobs) <= 1:
        for job in jobs:
            i, s, e = job
            finish(job, parse_pages(infos[i][0], s, e, settings, use_ocr))
    else:
        # ponytail: each worker's onnxruntime may use all cores during OCR; fine for <200 OCR pages, cap workers if CPU-bound
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(parse_pages, infos[job[0]][0], job[1], job[2], settings, use_ocr): job for job in jobs}
            for future in as_completed(futures):
                finish(futures[future], future.result())
    return docs, hits


def _embed(embedder: Embedder, texts: list[str]) -> np.ndarray:
    parts = [embedder.embed(texts[i:i + EMBED_CHUNK]) for i in range(0, len(texts), EMBED_CHUNK)]
    return np.vstack(parts) if parts else np.zeros((0, 1), dtype=np.float32)


def index_collection(zip_path: Path, collection_name: str, *, settings: Settings, llm: LLM, embedder: Embedder,
                     use_ocr: bool = True, registry: Registry | None = None, progress=no_progress) -> dict:
    if not COLLECTION_RE.fullmatch(collection_name or ""):
        raise KBError("INVALID_COLLECTION_NAME", "collection_name must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$", 422,
                      details={"collection_name": (collection_name or "")[:100]})
    registry = registry or Registry(settings)
    llm = llm.scoped()
    t0 = time.perf_counter()

    def stage(name: str, **counts) -> None:
        log.info("[%s] %s %s (%.1fs)", collection_name, name, counts, time.perf_counter() - t0)

    with registry.indexing_lock(collection_name):
        gen_id, staging = registry.new_staging(collection_name)
        try:
            files, warnings = safe_extract(Path(zip_path), staging / "src", settings)
            stage("extracted", pdfs=len(files))

            cache = _Cache(settings, _fingerprints(settings, use_ocr))
            parsed, parse_hits = _parse_all(files, settings, use_ocr, cache, progress)
            docs, seen = [], {}
            for d in parsed:
                if d.doc_id in seen:
                    warnings.append(f"{d.file_name}: duplicate of {seen[d.doc_id]}")
                    continue
                seen[d.doc_id] = d.file_name
                docs.append(d)
            warnings.extend(f"{d.file_name}: {d.ocr_unavailable_pages} scanned pages gave no readable text"
                            for d in docs if d.ocr_unavailable_pages)
            stage("parsed", documents=len(docs), pages=sum(d.page_count for d in docs), cache_hits=parse_hits)

            from kb.ingest.parse import doc_id_for
            from kb.ingest.vision import add_visual_descriptions
            visuals = add_visual_descriptions(docs, {doc_id_for(p): str(p) for p, _ in files}, cache, settings.vision_pages,
                                              lambda done, total: progress(VISION_STEP, done, total))
            stage("visuals", **visuals)

            segmented = []
            for n, d in enumerate(docs, 1):
                elements, sections = segment_document(d)
                mark_boilerplate(elements, d.page_count, settings)
                segmented.append((elements, sections))
                progress(SEGMENT_STEP, n, len(docs))
            extraction = {**extraction_report(docs, segmented), **visuals}
            stage("segmented", elements=sum(len(e) for e, _ in segmented), coverage=extraction["coverage"])

            # Cards: cached per document (raw doc card + page cards), only when every LLM call for it succeeded.
            cards: list[DocCard | None] = [None] * len(docs)
            page_cards: list[list[PageCard] | None] = [None] * len(docs)
            for i, d in enumerate(docs):
                cached = cache.load_json("cards", d.doc_id)
                if cached and len(cached["page_cards"]) == d.page_count:
                    cards[i] = replace(DocCard(**cached["doc_card"]), file_name=d.file_name, sibling_group=None)
                    page_cards[i] = [PageCard(**pc) for pc in cached["page_cards"]]
            misses = [i for i in range(len(docs)) if cards[i] is None]
            counters = {i: _CountingLLM(llm) for i in misses}
            built = parallel_map(_counted(lambda i: build_doc_card(counters[i], docs[i], settings), DOC_CARD_STEP, len(misses), progress),
                                 misses, settings.llm_concurrency)
            for i, c in zip(misses, built):
                if isinstance(c, Exception):  # build_doc_card never raises; keep the guard explicit
                    raise c
                cards[i] = c
            stage("doc_cards", cache_hits=len(docs) - len(misses))

            built = parallel_map(_counted(lambda i: build_page_cards(counters[i], docs[i], cards[i], segmented[i][1], settings),
                                          PAGE_CARD_STEP, len(misses), progress),
                                 misses, max(1, settings.llm_concurrency // 2))
            for i, pcs in zip(misses, built):
                if isinstance(pcs, Exception):  # build_page_cards never raises; keep the guard explicit
                    raise pcs
                page_cards[i] = pcs
                if counters[i].failures == 0:
                    cache.save_json("cards", docs[i].doc_id, {"doc_card": asdict(cards[i]),
                                                              "page_cards": [asdict(pc) for pc in pcs]})
            from kb.ingest.navigation import build_navigation
            cards=[replace(c,navigation=build_navigation(d,e,sections))
                   for c,d,(e,sections) in zip(cards,docs,segmented)]
            cards = assign_sibling_groups(cards)
            cards = [augment_topics(c, pcs) for c, pcs in zip(cards, page_cards)]
            stage("page_cards", llm_calls=llm.usage.calls, llm_failures=sum(c.failures for c in counters.values()))

            # Vectors are cached only for documents whose cards are cached (never on top of fallback cards).
            cards_cached = {docs[i].doc_id for i in range(len(docs)) if i not in counters or counters[i].failures == 0}
            page_keys, vec_parts, emb_hits = [], [], 0
            for n, (c, pcs) in enumerate(zip(cards, page_cards), 1):
                progress(EMBED_STEP, n - 1, len(cards))
                live = [pc for pc in pcs if pc.summary != BLANK_PAGE_SUMMARY]
                page_keys.extend((c.doc_id, pc.page_no) for pc in live)
                vecs = cache.load_vecs(c.doc_id, len(live)) if c.doc_id in cards_cached else None
                if vecs is None:
                    vecs = _embed(embedder, [page_embedding_text(c, pc, settings.embed_max_chars) for pc in live])
                    if len(live) and c.doc_id in cards_cached:
                        cache.save_vecs(c.doc_id, vecs)
                else:
                    emb_hits += 1
                if len(live):
                    vec_parts.append(vecs)
            progress(EMBED_STEP, len(cards), len(cards))
            page_vecs = np.vstack(vec_parts) if vec_parts else np.zeros((0, 1), dtype=np.float32)
            el_keys, el_vecs = [], None
            if settings.embed_elements:
                el_texts = []
                for c, (elements, _) in zip(cards, segmented):
                    for e in elements:
                        if "boilerplate" not in e.flags:
                            el_keys.append(e.element_id)
                            el_texts.append(element_embedding_text(c, e, settings.embed_max_chars))
                el_vecs = _embed(embedder, el_texts)
            stage("embedded", pages=len(page_keys), elements=len(el_keys), doc_cache_hits=emb_hits)

            store = Store.create(staging)
            try:
                for n, (d, c, pcs, (elements, _)) in enumerate(zip(docs, cards, page_cards, segmented), 1):
                    store.add_document(c, d.pages, pcs, elements)
                    progress(SAVE_STEP, n, len(docs))
                if page_keys:
                    store.set_vectors("page", page_keys, page_vecs)
                if el_keys:
                    store.set_vectors("element", el_keys, el_vecs)
            finally:
                store.close()

            summary = {
                "status": "ready", "collection_name": collection_name, "generation_id": gen_id,
                "documents": len(docs), "pages": sum(d.page_count for d in docs),
                "elements": sum(len(e) for e, _ in segmented),
                "extraction": extraction,
                "ocr_pages": sum(p.is_ocr for d in docs for p in d.pages),
                "ocr_unavailable_pages": sum(d.ocr_unavailable_pages for d in docs),
                "warnings": warnings, "llm_usage": asdict(llm.usage),
                "cache_hits": {"parse": parse_hits, "cards": len(docs) - len(misses), "embeddings": emb_hits},
                "ingestion_seconds": round(time.perf_counter() - t0, 2),
            }
            (staging / "manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            shutil.rmtree(staging / "src", ignore_errors=True)
            registry.promote(collection_name, gen_id, staging)
            stage("promoted", generation_id=gen_id)
            return summary
        except BaseException:
            registry.discard(staging)
            raise
