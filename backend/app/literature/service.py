"""The literature search workflow: query building → fan-out → merge → verdict.

Follows the case-module compute convention (status in needs_input | failed |
completed, Chinese message naming exactly what is missing) so the existing
chat confirmation, module page and agent trace all render it with zero new
plumbing.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from ..config import get_settings
from .providers import build_providers
from .records import PaperRecord, bibliography_line, dedup_records

DEFAULT_RESULTS = 20
HARD_CAP = 50
_SORTS = {"relevance", "citations", "year"}

# Intent/content words a chat sentence carries that are NOT the topic.
# "帮我找几篇LBO相位匹配的论文" must reduce to "LBO相位匹配".
_GOAL_STOPWORDS = [
    "请问", "帮我", "给我", "我想", "我要", "查一下", "查查", "查", "找一下", "找找", "找",
    "搜一下", "搜索", "搜", "检索", "看看", "几篇", "一些", "相关", "关于", "领域",
    "文献", "论文", "综述", "预印本", "资料", "paper", "papers", "literature",
    "preprint", "articles", "article", "search", "find", "look up", "about",
    "的", "了", "吧", "呢", "。", "，", "？", "！",
]


def _query_from_goal(goal: str | None) -> str | None:
    """Strip the asking words from a chat sentence; the remainder is the topic.

    Deterministic on purpose: asking an LLM to extract the topic would put a
    model between the user and the search box.
    """
    if not goal:
        return None
    text = goal
    for word in _GOAL_STOPWORDS:
        text = text.replace(word, " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _query_from_case(case_params: dict | None) -> str | None:
    """Build a query from the physics the case already declares."""
    if not case_params:
        return None
    params = case_params.get("parameters") or {}
    tokens: list[str] = []
    gain = params.get("gain_medium") or params.get("gain_crystal")
    if isinstance(gain, str):
        tokens.append(gain)
    wavelength = params.get("laser_wavelength_nm") or params.get("wavelength_nm")
    if wavelength:
        tokens.append(f"{wavelength} nm laser")
    nonlinear = params.get("nonlinear_crystal")
    if isinstance(nonlinear, str):
        tokens.append(nonlinear + " second harmonic")
    if not tokens and case_params.get("title"):
        tokens.append(str(case_params["title"]))
    return " ".join(tokens) or None


def run_literature_search(config: dict | None, case_params: dict | None = None,
                          goal: str | None = None) -> dict:
    """Search the configured sources and return a typed, honest verdict.

    Query precedence: explicit config.query > the chat sentence with asking
    words stripped > tokens from the case's physics parameters > needs_input.
    """
    config = dict(config or {})
    settings = get_settings()

    query = str(config.get("query") or "").strip()
    query_source = "config"
    if not query:
        query = _query_from_goal(goal) or ""
        query_source = "goal"
    if not query:
        query = _query_from_case(case_params) or ""
        query_source = "case"
    if not query:
        return {
            "status": "needs_input",
            "tool": "literature_search",
            "message": "请先填写检索关键词:在模块参数的「检索词」里输入主题"
                       "(建议英文,如 Nd:YAG passive Q-switching),或在案例物理参数里填好波长/晶体后重试。",
        }

    try:
        max_results = int(config.get("max_results") or DEFAULT_RESULTS)
    except (TypeError, ValueError):
        max_results = DEFAULT_RESULTS
    max_results = max(1, min(max_results, HARD_CAP))
    sort = str(config.get("sort") or "relevance")
    if sort not in _SORTS:
        sort = "relevance"
    year_from = None
    raw_year = config.get("year_from")
    if raw_year not in (None, ""):
        try:
            year_from = int(raw_year)
        except (TypeError, ValueError):
            year_from = None

    providers, source_errors = build_providers(config.get("sources"))
    per_source: dict[str, int] = {}
    records: list[PaperRecord] = []

    def _search_one(provider):
        return provider.name, provider.search(
            query, max_results=max_results, year_from=year_from,
            sort=sort, timeout_s=settings.literature_timeout_s,
        )

    if providers:
        # Concurrent fan-out so the worst case is ~one timeout, not the sum.
        # Each source fails alone: arXiv being slow must not hide OpenAlex.
        with ThreadPoolExecutor(max_workers=len(providers)) as pool:
            futures = [pool.submit(_search_one, p) for p in providers]
            for provider, future in zip(providers, futures):
                try:
                    name, found = future.result()
                    per_source[name] = len(found)
                    records.extend(found)
                except Exception as exc:  # noqa: BLE001 - per-source isolation
                    source_errors.append(
                        f"{provider.name} 检索失败:{type(exc).__name__}: {exc}")

    if not per_source:
        return {
            "status": "failed",
            "tool": "literature_search",
            "message": "所有文献源都检索失败,请检查网络后重试。" + "；".join(source_errors),
            "query": query,
        }

    merged = dedup_records(records)
    if sort == "citations":
        merged.sort(key=lambda r: (r.cited_by is None, -(r.cited_by or 0)))
    elif sort == "year":
        merged.sort(key=lambda r: (r.year is None, -(r.year or 0)))
    merged = merged[:max_results]

    source_note = ", ".join(f"{name}({count})" for name, count in per_source.items())
    return {
        "status": "completed",
        "tool": "literature_search",
        "query": query,
        "query_source": query_source,
        "sort": sort,
        "year_from": year_from,
        "papers": [record.as_dict() for record in merged],
        "bibliography": [bibliography_line(record) for record in merged],
        "source_errors": source_errors,
        "summary": f"共检索到 {len(merged)} 篇(去重后)。来源: {source_note}。检索词: {query}",
        "disclaimer": "以上为各文献库返回的元数据与摘要,系统未读取任何论文全文;"
                      "摘要仅供初筛,采信结论请阅读原文。",
    }
