"""Best-effort field extraction from SDS PDFs.

This is advisory only: extracted values are meant to pre-fill the Add/Edit
dialog for the user to review, never to be saved without a human looking at
them. Extraction failures (corrupt/encrypted/unusual PDFs) must never block
manually entering an SDS, so failures here are swallowed and logged rather
than raised.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pypdf

logger = logging.getLogger(__name__)

_CAS_RE = re.compile(r"\b(\d{2,7}-\d{2}-\d)\b")

_PRODUCT_NAME_LABELS = [r"product\s*(?:name|identifier)", r"trade\s*name"]
_MANUFACTURER_LABELS = [r"manufacturer", r"supplier", r"company\s*name"]
_REVISION_DATE_LABELS = [
    r"revision\s*date",
    r"date\s*of\s*(?:issue|revision|preparation)",
    r"issue\s*date",
    r"preparation\s*date",
]
_SIGNAL_WORD_LABELS = [r"signal\s*word"]


def _iso_from_ymd(m: re.Match) -> str:
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _iso_from_mdy(m: re.Match) -> str:
    return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"


_DATE_FORMATS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), _iso_from_ymd),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), _iso_from_mdy),
]

_MONTHS = {
    name.lower(): i
    for i, name in enumerate(
        [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ],
        start=1,
    )
}
_MONTH_DATE_RE = re.compile(
    r"\b([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})\b"
)

_MAX_LEADING_PAGES = 4


def extract_fields(pdf_path: Path | str) -> dict:
    """Read a PDF and return best-guess SDS fields. Never raises; returns {} on any failure."""
    try:
        reader = pypdf.PdfReader(str(pdf_path))
    except (OSError, pypdf.errors.PdfReadError, ValueError) as exc:
        logger.warning("Could not open %s as a PDF: %s", pdf_path, exc)
        return {}

    page_count = len(reader.pages)
    page_indices = list(range(min(_MAX_LEADING_PAGES, page_count)))
    if page_count > _MAX_LEADING_PAGES:
        page_indices.append(page_count - 1)

    text_parts = []
    for i in page_indices:
        try:
            text_parts.append(reader.pages[i].extract_text() or "")
        except Exception as exc:
            # pypdf's per-page parser can raise a wide variety of errors on
            # malformed pages; a bad page must not abort the whole extraction.
            logger.warning("Could not extract text from page %s of %s: %s", i, pdf_path, exc)

    return extract_fields_from_text("\n".join(text_parts))


def extract_fields_from_text(text: str) -> dict:
    """Pure-text version of extract_fields, kept separate so it's easy to unit test."""
    lines = text.splitlines()

    return {
        "product_name": _find_label_value(lines, _PRODUCT_NAME_LABELS),
        "manufacturer": _find_label_value(lines, _MANUFACTURER_LABELS),
        "cas_number": _find_cas_numbers(text),
        "revision_date": _find_revision_date(lines),
        "signal_word": _find_signal_word(lines, text),
    }


def _find_label_value(lines: list[str], label_patterns: list[str]) -> str | None:
    for i, line in enumerate(lines):
        for pattern in label_patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if not match:
                continue
            after = line[match.end():].strip(" :\t-")
            if after:
                return after
            for candidate in lines[i + 1:i + 3]:
                candidate = candidate.strip()
                if candidate:
                    return candidate
    return None


def _find_cas_numbers(text: str, limit: int = 8) -> str | None:
    seen: list[str] = []
    for match in _CAS_RE.finditer(text):
        cas = match.group(1)
        if cas not in seen:
            seen.append(cas)
        if len(seen) >= limit:
            break
    return ", ".join(seen) if seen else None


def _find_revision_date(lines: list[str]) -> str | None:
    candidate = _find_label_value(lines, _REVISION_DATE_LABELS)
    if not candidate:
        return None
    return _parse_date(candidate)


def _parse_date(text: str) -> str | None:
    for pattern, formatter in _DATE_FORMATS:
        match = pattern.search(text)
        if match:
            return formatter(match)

    month_match = _MONTH_DATE_RE.search(text)
    if month_match:
        month_name, day, year = month_match.groups()
        month = _MONTHS.get(month_name.lower())
        if month:
            return f"{year}-{month:02d}-{int(day):02d}"

    return None


def _find_signal_word(lines: list[str], full_text: str) -> str | None:
    labeled = _find_label_value(lines, _SIGNAL_WORD_LABELS)
    if labeled:
        lowered = labeled.lower()
        if "danger" in lowered:
            return "Danger"
        if "warning" in lowered:
            return "Warning"

    danger_match = re.search(r"\bDANGER\b", full_text)
    warning_match = re.search(r"\bWARNING\b", full_text)
    if danger_match and (not warning_match or danger_match.start() < warning_match.start()):
        return "Danger"
    if warning_match:
        return "Warning"
    return None
