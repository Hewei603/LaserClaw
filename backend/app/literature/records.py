"""Normalized paper records, dedup, and BibTeX rendering.

One :class:`PaperRecord` per paper regardless of source. Unknown fields stay
None and are shown as unknown — never guessed (same rule as the inventory L0
layer).
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


@dataclass
class PaperRecord:
    title: str
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    venue: str | None = None
    doi: str | None = None
    arxiv_id: str | None = None
    url: str | None = None
    pdf_url: str | None = None
    abstract: str | None = None
    cited_by: int | None = None
    source: str = ""  # openalex | arxiv | mock

    def as_dict(self) -> dict:
        data = asdict(self)
        data["bibtex"] = to_bibtex(self)
        return data


def normalize_doi(doi: str | None) -> str | None:
    """DOIs are case-insensitive and appear with or without the resolver URL."""
    if not doi:
        return None
    cleaned = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi.org/", "doi:"):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    return cleaned or None


def _normalized_title(title: str) -> str:
    """Fold case, punctuation and whitespace so the same paper matches itself
    across sources that style titles differently."""
    return re.sub(r"[^0-9a-z一-鿿]+", "", title.lower())


def _richness(record: PaperRecord) -> int:
    """How many informative fields a record carries, for merge preference."""
    return sum(
        1 for value in (record.year, record.venue, record.doi, record.arxiv_id,
                        record.url, record.pdf_url, record.abstract, record.cited_by)
        if value not in (None, "", [])
    ) + len(record.authors)


def _merge(keep: PaperRecord, other: PaperRecord) -> PaperRecord:
    """Fill keep's missing fields from the duplicate instead of discarding it —
    arXiv knows the pdf, OpenAlex knows the citation count."""
    for name in ("year", "venue", "doi", "arxiv_id", "url", "pdf_url", "abstract", "cited_by"):
        if getattr(keep, name) in (None, "") and getattr(other, name) not in (None, ""):
            setattr(keep, name, getattr(other, name))
    if not keep.authors and other.authors:
        keep.authors = other.authors
    return keep


def dedup_records(records: list[PaperRecord]) -> list[PaperRecord]:
    """Collapse the same paper reported by several sources.

    Identity is the normalized DOI when both sides have one; otherwise the
    normalized title. The richer record wins as the base and absorbs the
    other's fields. Order of first appearance is preserved (providers return
    relevance order).
    """
    kept: list[PaperRecord] = []
    by_doi: dict[str, int] = {}
    by_title: dict[str, int] = {}

    for record in records:
        doi = normalize_doi(record.doi)
        title_key = _normalized_title(record.title) if record.title else ""
        index = by_doi.get(doi) if doi else None
        if index is None and title_key:
            index = by_title.get(title_key)

        if index is None:
            kept.append(record)
            index = len(kept) - 1
        else:
            base, other = kept[index], record
            if _richness(other) > _richness(base):
                base, other = other, base
            kept[index] = _merge(base, other)

        merged = kept[index]
        merged_doi = normalize_doi(merged.doi)
        if merged_doi:
            by_doi[merged_doi] = index
        merged_title = _normalized_title(merged.title) if merged.title else ""
        if merged_title:
            by_title[merged_title] = index
    return kept


def _bibtex_escape(value: str) -> str:
    return value.replace("{", "").replace("}", "").replace("\\", "")


def to_bibtex(record: PaperRecord) -> str:
    """A usable-if-plain BibTeX entry; the grad student pastes it into a .bib."""
    first_author = (record.authors[0].split()[-1] if record.authors else "unknown").lower()
    key = re.sub(r"[^0-9a-z]", "", f"{first_author}{record.year or ''}") or "paper"
    kind = "article" if record.venue else "misc"
    lines = [f"@{kind}{{{key},", f"  title = {{{_bibtex_escape(record.title)}}},"]
    if record.authors:
        lines.append(f"  author = {{{' and '.join(_bibtex_escape(a) for a in record.authors)}}},")
    if record.year:
        lines.append(f"  year = {{{record.year}}},")
    if record.venue:
        lines.append(f"  journal = {{{_bibtex_escape(record.venue)}}},")
    if record.doi:
        lines.append(f"  doi = {{{normalize_doi(record.doi)}}},")
    if record.arxiv_id:
        lines.append(f"  eprint = {{{record.arxiv_id}}},")
        lines.append("  archivePrefix = {arXiv},")
    if record.url:
        lines.append(f"  url = {{{record.url}}},")
    lines.append("}")
    return "\n".join(lines)


def bibliography_line(record: PaperRecord) -> str:
    """One contiguous human-readable citation line.

    Stored alongside the structured records so the RAG chunker gets readable
    sentences, not only JSON key/value fragments.
    """
    authors = ", ".join(record.authors[:3]) + (" et al." if len(record.authors) > 3 else "")
    parts = [record.title.rstrip(".") + "."]
    if authors:
        parts.append(authors + ".")
    if record.venue:
        parts.append(record.venue + (f" {record.year}." if record.year else "."))
    elif record.year:
        parts.append(f"{record.year}.")
    if record.doi:
        parts.append(f"doi:{normalize_doi(record.doi)}")
    elif record.arxiv_id:
        parts.append(f"arXiv:{record.arxiv_id}")
    return " ".join(parts)
