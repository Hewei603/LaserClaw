"""Text chunking utilities."""
from __future__ import annotations

import re


SECTION_RE = re.compile(r"(===\s*[^=]+?\s*===)")


def _section_chunks(text: str) -> list[str]:
    parts = SECTION_RE.split(text)
    if len(parts) < 3:
        return []

    chunks: list[str] = []
    prefix = parts[0].strip()
    for index in range(1, len(parts), 2):
        heading = parts[index].strip()
        body = parts[index + 1].strip() if index + 1 < len(parts) else ""
        section = f"{prefix}\n{heading}\n{body}".strip() if prefix else f"{heading}\n{body}".strip()
        if section:
            chunks.append(section)
    return chunks


def _word_chunks(text: str, *, max_words: int, overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    if len(words) <= max_words:
        return [" ".join(words)]

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start = max(0, end - overlap)
    return chunks


def chunk_text(text: str, *, max_words: int = 180, overlap: int = 30) -> list[str]:
    """Split text into stable section-aware overlapping word chunks."""
    section_chunks = _section_chunks(text)
    if section_chunks:
        chunks: list[str] = []
        for section in section_chunks:
            chunks.extend(_word_chunks(section, max_words=max_words, overlap=overlap))
        return chunks
    return _word_chunks(text, max_words=max_words, overlap=overlap)
