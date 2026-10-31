"""Shared text helpers: one tokenizer for FTS queries, fakes and lexical scoring."""
import hashlib
import re

STOP_TOKENS = {"and", "or", "not", "near"}
_NOISE_LINE = re.compile(r"^[\W\d_]*$")
IDENTIFIER_PATTERNS = [   # document identifiers from any field; matched in source text and in queries
  r"FR Doc\.?\s*\d{4}\s*[–-]\s*\d{3,6}", r"Docket (?:ID |No\. ?)?[A-Z]{2,6}[–-]\d{4}[–-]\d{2,6}", r"Docket No\. ?R?-?\d{3,5}",
  r"RIN\s*\d{4}[–-][A-Z]{2}\d{2}", r"(?:ASU|Accounting Standards Update)(?: No\.)?\s*\d{4}[–-]\d{2}",
  r"\b[LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b", r"arXiv:\s?\d{4}\.\d{4,5}(?:v\d+)?", r"\b10\.\d{4,9}/[^\s\"<>]+",
  r"\bISBN(?:-1[03])?:?\s*[\dX-]{10,17}\b", r"\bISSN:?\s*\d{4}-\d{3}[\dX]\b", r"\bRFC\s?\d{3,5}\b",
  r"\bISO(?:/IEC)?\s?\d{3,5}(?:-\d+)?(?::\d{4})?\b", r"\b(?:US|EP|WO)\s?\d{4,}\s?[AB]\d\b"]


def tokens(text: str) -> list[str]:
    seen, out = set(), []
    for tok in re.findall(r"\w+", text.lower(), re.UNICODE):
        if (len(tok) == 1 and not tok.isdigit()) or tok in STOP_TOKENS or tok in seen:
            continue
        seen.add(tok)
        out.append(tok)
    return out


def norm_for_hash(text: str) -> str:
    lines = [ln for ln in text.lower().splitlines() if not _NOISE_LINE.match(ln.strip())]
    return " ".join(" ".join(lines).split())


def text_hash(text: str) -> str:
    return hashlib.sha1(norm_for_hash(text).encode("utf-8")).hexdigest()
