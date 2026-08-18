"""Deterministic literature search layer.

Query building, HTTP fetching, parsing, dedup and ranking all happen here,
in plain code. The LLM never produces a paper record — a fabricated citation
is the classic LLM failure mode and the whole point of this package is that
every entry shown to the user came from a real index (OpenAlex / arXiv) and
carries its own DOI or arXiv id.

What this layer knows is metadata plus abstracts. It has NOT read any paper's
full text, and every consumer (UI, docs, prompts) must say so.
"""
from .records import PaperRecord, dedup_records
from .service import run_literature_search

__all__ = ["PaperRecord", "dedup_records", "run_literature_search"]
