"""Literature source adapters: OpenAlex and arXiv, plus a mock for tests.

Both real sources are keyless and free — chosen deliberately so the feature
works on a lab machine with nothing configured. All HTTP goes through the two
module-level seams below; tests monkeypatch them and never touch the network.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Any

import httpx

from ..config import get_settings
from ..version import APP_VERSION
from .records import PaperRecord

# NOTE: no `proxies=` kwarg anywhere — removed in httpx 0.28, which our
# version range allows. trust_env stays default so a system proxy still works.
_USER_AGENT = f"LaserClaw/{APP_VERSION}"


def _http_get_json(url: str, params: dict[str, Any], timeout_s: float) -> dict:
    """Single JSON GET. Tests monkeypatch THIS function, not httpx."""
    response = httpx.get(url, params=params, timeout=timeout_s,
                         headers={"User-Agent": _USER_AGENT})
    response.raise_for_status()
    return response.json()


def _http_get_text(url: str, params: dict[str, Any], timeout_s: float) -> str:
    """Single text GET (arXiv Atom). Tests monkeypatch THIS function."""
    response = httpx.get(url, params=params, timeout=timeout_s,
                         headers={"User-Agent": _USER_AGENT})
    response.raise_for_status()
    return response.text


def reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    """OpenAlex ships abstracts as {word: [positions]}; rebuild the text."""
    if not inverted_index:
        return None
    positions: list[tuple[int, str]] = []
    for word, indexes in inverted_index.items():
        for index in indexes:
            positions.append((index, word))
    if not positions:
        return None
    return " ".join(word for _, word in sorted(positions))


class OpenAlexProvider:
    """Journal metadata + abstracts + citation counts. No key needed."""

    name = "openalex"
    _URL = "https://api.openalex.org/works"

    def search(self, query: str, *, max_results: int, year_from: int | None,
               sort: str, timeout_s: float) -> list[PaperRecord]:
        params: dict[str, Any] = {"search": query, "per-page": min(max_results, 50)}
        filters = ["type:article|preprint|review"]
        if year_from:
            filters.append(f"from_publication_date:{year_from}-01-01")
        params["filter"] = ",".join(filters)
        if sort == "citations":
            params["sort"] = "cited_by_count:desc"
        elif sort == "year":
            params["sort"] = "publication_date:desc"
        mailto = get_settings().literature_mailto
        if mailto:
            # Opt into OpenAlex's "polite pool" (faster, more reliable).
            params["mailto"] = mailto
        payload = _http_get_json(self._URL, params, timeout_s)
        return [self._parse(work) for work in payload.get("results", [])]

    @staticmethod
    def _parse(work: dict) -> PaperRecord:
        location = work.get("primary_location") or {}
        venue = (location.get("source") or {}).get("display_name")
        oa = work.get("best_oa_location") or {}
        return PaperRecord(
            title=work.get("display_name") or "(无标题)",
            authors=[(a.get("author") or {}).get("display_name")
                     for a in work.get("authorships", [])
                     if (a.get("author") or {}).get("display_name")][:20],
            year=work.get("publication_year"),
            venue=venue,
            doi=work.get("doi"),
            url=work.get("doi") or (work.get("ids") or {}).get("openalex"),
            pdf_url=oa.get("pdf_url"),
            abstract=reconstruct_abstract(work.get("abstract_inverted_index")),
            cited_by=work.get("cited_by_count"),
            source="openalex",
        )


class ArxivProvider:
    """Physics preprints with full abstracts and PDFs. No key needed."""

    name = "arxiv"
    _URL = "https://export.arxiv.org/api/query"
    _NS = {"atom": "http://www.w3.org/2005/Atom"}

    def search(self, query: str, *, max_results: int, year_from: int | None,
               sort: str, timeout_s: float) -> list[PaperRecord]:
        params: dict[str, Any] = {
            "search_query": f"all:{query}",
            "max_results": min(max_results, 50),
            # arXiv has no citation counts; "citations" falls back to relevance.
            "sortBy": "submittedDate" if sort == "year" else "relevance",
            "sortOrder": "descending",
        }
        text = _http_get_text(self._URL, params, timeout_s)
        root = ET.fromstring(text)
        records = [self._parse(entry) for entry in root.findall("atom:entry", self._NS)]
        if year_from:
            # The API cannot filter by date on an `all:` query; filter here so
            # the knob behaves identically across sources.
            records = [r for r in records if r.year is None or r.year >= year_from]
        return records

    def _parse(self, entry: ET.Element) -> PaperRecord:
        def text_of(tag: str) -> str | None:
            node = entry.find(f"atom:{tag}", self._NS)
            return node.text.strip() if node is not None and node.text else None

        entry_id = text_of("id") or ""
        arxiv_id = entry_id.rsplit("/abs/", 1)[-1] if "/abs/" in entry_id else None
        published = text_of("published") or ""
        pdf_url = None
        for link in entry.findall("atom:link", self._NS):
            if link.get("title") == "pdf":
                pdf_url = link.get("href")
        return PaperRecord(
            title=" ".join((text_of("title") or "(无标题)").split()),
            authors=[node.text.strip()
                     for node in entry.findall("atom:author/atom:name", self._NS)
                     if node.text][:20],
            year=int(published[:4]) if published[:4].isdigit() else None,
            venue=None,  # preprint — a journal name here would be a lie
            arxiv_id=arxiv_id,
            url=entry_id or None,
            pdf_url=pdf_url,
            abstract=" ".join((text_of("summary") or "").split()) or None,
            source="arxiv",
        )


class MockProvider:
    """Deterministic canned records: tests and demo runs, zero network.

    Includes a DOI duplicate of the first record (as arXiv would report it) so
    the dedup path is exercised by any end-to-end test.
    """

    name = "mock"

    def search(self, query: str, *, max_results: int, year_from: int | None,
               sort: str, timeout_s: float) -> list[PaperRecord]:
        records = [
            PaperRecord(
                title=f"Passive Q-switching and mode locking review: {query}"[:120],
                authors=["A. Author", "B. Builder", "C. Checker", "D. Fourth"],
                year=2019, venue="Journal of Deterministic Optics",
                doi="10.1000/mock.1", url="https://doi.org/10.1000/mock.1",
                abstract="A canned abstract for offline runs. 该条目来自演示数据源。",
                cited_by=123, source="mock",
            ),
            PaperRecord(
                title=f"Passive Q-switching and mode locking review: {query}"[:120],
                authors=["A. Author"],
                year=2019, doi="HTTPS://DOI.ORG/10.1000/MOCK.1",
                arxiv_id="1901.00001", pdf_url="https://arxiv.org/pdf/1901.00001",
                abstract="Preprint duplicate of the same paper.", source="mock",
            ),
            PaperRecord(
                title=f"Thermal lensing measurement methods for {query}"[:120],
                authors=["E. Example"], year=2021,
                venue="Applied Mock Photonics", doi="10.1000/mock.2",
                url="https://doi.org/10.1000/mock.2",
                abstract="Second canned abstract.", cited_by=7, source="mock",
            ),
        ]
        if year_from:
            records = [r for r in records if r.year is None or r.year >= year_from]
        return records[:max_results]


_PROVIDERS = {p.name: p for p in (OpenAlexProvider(), ArxivProvider(), MockProvider())}


def build_providers(names_csv: str | None = None) -> tuple[list, list[str]]:
    """Resolve provider names → instances.

    Reads settings LAZILY (never at import) so tests that clear the settings
    cache see their env. Unknown names come back as error notes, not a crash —
    a typo in .env must degrade loudly but keep the working sources.
    """
    csv = names_csv if names_csv is not None else get_settings().literature_providers
    providers, errors = [], []
    for raw in csv.split(","):
        name = raw.strip().lower()
        if not name:
            continue
        if name in _PROVIDERS:
            providers.append(_PROVIDERS[name])
        else:
            errors.append(f"未知文献源 '{name}'(可用:openalex, arxiv)")
    return providers, errors
