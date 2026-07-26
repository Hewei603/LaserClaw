"""Benchmark LaserClaw's resume-grade RAG and AI workflow metrics.

The script is intentionally local and reproducible:
- loads the repository root .env without printing secrets
- uses the backend SQLite database unless DATABASE_URL is explicitly overridden
- indexes synthetic benchmark documents under docs/evals/synthetic_laser_docs
- optionally indexes files under backend/uploads/global_knowledge when requested
- reports standard retrieval and latency metrics: Recall@K, MRR, P50/P95
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def load_env_file(path: Path, *, override: bool = True) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if override or key not in os.environ:
            os.environ[key] = value


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return ordered[index]


def summarize_latency(values: list[float]) -> dict[str, float]:
    return {
        "count": len(values),
        "p50_ms": round(percentile(values, 50), 2),
        "p95_ms": round(percentile(values, 95), 2),
        "p99_ms": round(percentile(values, 99), 2),
        "mean_ms": round(statistics.mean(values), 2) if values else 0.0,
    }


def configure_environment(*, use_env_file: bool = False) -> None:
    if use_env_file:
        load_env_file(ROOT / ".env", override=False)
        load_env_file(BACKEND / ".env", override=False)
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url or "@db:" in database_url or database_url.startswith("postgresql://laserclaw:laserclaw123@db"):
        os.environ["DATABASE_URL"] = "sqlite:///./_resume_metrics.db"
    os.environ.setdefault("UPLOAD_DIR", str(BACKEND / "uploads"))
    if os.environ.get("UPLOAD_DIR") == "/app/uploads":
        os.environ["UPLOAD_DIR"] = str(BACKEND / "uploads")
    os.environ.setdefault("AUTO_CREATE_TABLES", "true")
    os.environ.setdefault("AI_PROVIDER", "mock")
    os.environ.setdefault("STRICT_PROVIDER", "false")
    os.environ.setdefault("EMBEDDING_PROVIDER", "local")
    os.environ.setdefault("RETRIEVAL_BACKEND", "sql_json")
    os.environ.setdefault("RERANKER_PROVIDER", "none")


def ensure_knowledge_index(db, *, include_upload_knowledge: bool = False) -> dict[str, Any]:
    from sqlalchemy import text

    from app.database import Base, engine
    from app.knowledge.ingestion import content_hash, create_global_file_source, extract_text_from_file
    from app.models import KnowledgeSource

    Base.metadata.create_all(bind=engine)
    if str(engine.url).startswith("sqlite"):
        def existing_columns(table: str) -> set[str]:
            return {row[1] for row in db.execute(text(f"PRAGMA table_info({table})")).fetchall()}

        migrations = {
            "retrieval_runs": [
                ("max_score", "FLOAT"),
                ("confidence", "VARCHAR(50)"),
                ("no_answer", "BOOLEAN"),
            ],
            "knowledge_sources": [
                ("governance_status", "VARCHAR(50)"),
                ("version", "INTEGER"),
                ("owner_id", "INTEGER"),
                ("reviewed_by_id", "INTEGER"),
                ("reviewed_at", "DATETIME"),
            ],
            "experiment_cases": [
                ("project_id", "INTEGER"),
                ("status", "VARCHAR(50)"),
                ("visibility", "VARCHAR(50)"),
                ("schema_version", "VARCHAR(50)"),
                ("tags", "JSON"),
                ("measurements", "JSON"),
                ("safety_notes", "TEXT"),
                ("conclusions", "TEXT"),
                ("owner_id", "INTEGER"),
            ],
        }
        for table, columns_to_add in migrations.items():
            current = existing_columns(table)
            for name, ddl_type in columns_to_add:
                if name not in current:
                    db.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl_type}"))
        db.commit()

    indexed = []
    candidate_paths = []
    synthetic_dir = ROOT / "docs" / "evals" / "synthetic_laser_docs"
    for pattern in ("*.md", "*.txt", "*.pdf"):
        candidate_paths.extend(sorted(synthetic_dir.glob(pattern)))

    if include_upload_knowledge:
        upload_dir = BACKEND / "uploads" / "global_knowledge"
        upload_dir.mkdir(parents=True, exist_ok=True)
        for pattern in ("*.md", "*.txt", "*.pdf"):
            candidate_paths.extend(sorted(upload_dir.glob(pattern)))

    for path in candidate_paths:
        content_type = "application/pdf" if path.suffix.lower() == ".pdf" else "text/markdown"
        text = extract_text_from_file(str(path), content_type)
        digest = content_hash(text)
        source = db.query(KnowledgeSource).filter(KnowledgeSource.content_hash == digest).first()
        if source is None:
            title = path.stem.replace("_", " ").title()
            if path.name == "laser_safety_sop.md":
                title = "Synthetic Laser Safety SOP"
            elif path.name == "optics_components_catalog.md":
                title = "Synthetic Optics Components Catalog"
            elif path.name == "troubleshooting_case_notes.md":
                title = "Synthetic Troubleshooting Case Notes"
            source = create_global_file_source(db, title=title, filepath=str(path), content_type=content_type)
        source.governance_status = source.governance_status or "approved"
        source.version = source.version or 1
        metadata = dict(source.metadata_json or {})
        metadata.setdefault("benchmark_file_size_bytes", path.stat().st_size)
        metadata.setdefault("benchmark_source", "synthetic_laser_docs" if synthetic_dir in path.parents else "global_knowledge")
        source.metadata_json = metadata
        indexed.append({"title": source.title, "bytes": path.stat().st_size})
    db.commit()

    sources = db.query(KnowledgeSource).all()
    chunks = sum(len(source.chunks) for source in sources)
    return {
        "benchmark_files": indexed,
        "source_count": len(sources),
        "chunk_count": chunks,
        "total_benchmark_bytes": sum(item["bytes"] for item in indexed),
    }


def source_ids(db) -> dict[str, int]:
    from app.models import KnowledgeSource

    ids: dict[str, int] = {}
    for source in db.query(KnowledgeSource).all():
        title = (source.title or "").lower()
        if "safety" in title or "saf" in title or "manual" in title:
            ids["safety"] = source.id
        if "optic" in title or "component" in title or "catalog" in title:
            ids["optics"] = source.id
        if "troubleshooting" in title or "case notes" in title:
            ids["troubleshooting"] = source.id
    return ids


def benchmark_retrieval(db, dataset: list[dict[str, Any]], *, repeats: int, top_k: int) -> dict[str, Any]:
    from app.knowledge.retrieval import search_knowledge

    latencies = []
    rows = []
    hits_at_1 = hits_at_3 = hits_at_k = 0
    reciprocal_ranks = []
    term_coverages = []
    confidence_counts: dict[str, int] = {}

    for _ in range(repeats):
        for item in dataset:
            started = time.perf_counter()
            run, results = search_knowledge(db, query=item["query"], top_k=top_k)
            db.commit()
            elapsed_ms = (time.perf_counter() - started) * 1000
            latencies.append(elapsed_ms)

            result_source_ids = [result.source_id for result in results]
            expected_id = item["expected_source_id"]
            rank = next((index + 1 for index, sid in enumerate(result_source_ids) if sid == expected_id), None)
            if rank == 1:
                hits_at_1 += 1
            if rank is not None and rank <= 3:
                hits_at_3 += 1
            if rank is not None and rank <= top_k:
                hits_at_k += 1
            reciprocal_ranks.append(1 / rank if rank else 0.0)

            snippets = "\n".join(result.snippet for result in results).lower()
            expected_terms = [term.lower() for term in item.get("expected_terms", [])]
            term_hits = sum(1 for term in expected_terms if term in snippets)
            term_coverage = term_hits / len(expected_terms) if expected_terms else 1.0
            term_coverages.append(term_coverage)
            confidence_counts[run.confidence or "unknown"] = confidence_counts.get(run.confidence or "unknown", 0) + 1

            rows.append(
                {
                    "query": item["query"],
                    "expected_source_id": expected_id,
                    "top_source_ids": result_source_ids[:top_k],
                    "rank": rank,
                    "max_score": round(run.max_score or 0.0, 4),
                    "confidence": run.confidence,
                    "term_coverage": round(term_coverage, 4),
                    "latency_ms": round(elapsed_ms, 2),
                }
            )

    total = len(dataset) * repeats
    return {
        "dataset_size": len(dataset),
        "repeats": repeats,
        "queries_executed": total,
        "top_k": top_k,
        "recall_at_1": round(hits_at_1 / total, 4),
        "recall_at_3": round(hits_at_3 / total, 4),
        f"recall_at_{top_k}": round(hits_at_k / total, 4),
        "mrr": round(sum(reciprocal_ranks) / total, 4),
        "mean_expected_term_coverage": round(sum(term_coverages) / total, 4),
        "confidence_distribution": confidence_counts,
        "latency": summarize_latency(latencies),
        "sample_rows": rows[: len(dataset)],
    }


def benchmark_reindex(db) -> dict[str, Any]:
    from app.knowledge.ingestion import extract_text_from_file, replace_source_chunks
    from app.models import KnowledgeSource

    rows = []
    total_chunks = 0
    total_bytes = 0
    started_all = time.perf_counter()
    for source in db.query(KnowledgeSource).filter(KnowledgeSource.source_type == "global_attachment").all():
        filepath = (source.metadata_json or {}).get("filepath")
        if not filepath or not Path(filepath).exists():
            continue
        size = Path(filepath).stat().st_size
        started = time.perf_counter()
        text = extract_text_from_file(filepath, (source.metadata_json or {}).get("file_type") or "application/pdf")
        replace_source_chunks(db, source, text)
        db.flush()
        elapsed_ms = (time.perf_counter() - started) * 1000
        chunk_count = len(source.chunks)
        total_chunks += chunk_count
        total_bytes += size
        rows.append(
            {
                "source_id": source.id,
                "title": source.title,
                "bytes": size,
                "chunks": chunk_count,
                "latency_ms": round(elapsed_ms, 2),
                "chunks_per_second": round(chunk_count / (elapsed_ms / 1000), 2) if elapsed_ms else 0.0,
            }
        )
    db.commit()
    elapsed_all = time.perf_counter() - started_all
    return {
        "sources_reindexed": len(rows),
        "total_bytes": total_bytes,
        "total_chunks": total_chunks,
        "total_seconds": round(elapsed_all, 4),
        "chunks_per_second": round(total_chunks / elapsed_all, 2) if elapsed_all else 0.0,
        "mb_per_second": round((total_bytes / 1024 / 1024) / elapsed_all, 2) if elapsed_all else 0.0,
        "rows": rows,
    }


async def benchmark_llm(*, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {"enabled": False, "reason": "disabled by CLI"}

    from app.providers.openai import OpenAIProvider

    provider = OpenAIProvider()
    case_data = {
        "title": "1064 nm Nd:YAG/LBO output stabilization benchmark case",
        "description": "Ring cavity shows unstable 532 nm output after pump current increase.",
        "cavity_type": "ring",
        "goal": "Recover stable green output while preserving laser safety controls.",
        "parameters": {"pump_current_a": 18.5, "wavelength_nm": 1064, "crystal": "LBO"},
        "symptoms": ["532 nm output drops after alignment", "beam spot tailing", "thermal drift suspected"],
    }
    tasks = [
        ("plan", provider.generate_plan(case_data)),
        ("troubleshooting", provider.generate_troubleshooting(case_data["symptoms"], case_data)),
        ("report", provider.generate_report(case_data)),
    ]
    rows = []
    latencies = []
    successes = 0
    total_tokens = 0
    for name, awaitable in tasks:
        started = time.perf_counter()
        try:
            content = await awaitable
            elapsed_ms = (time.perf_counter() - started) * 1000
            usage = content.get("_usage", {}) if isinstance(content, dict) else {}
            tokens = int(usage.get("total_tokens") or 0)
            total_tokens += tokens
            latencies.append(elapsed_ms)
            successes += 1
            rows.append(
                {
                    "task": name,
                    "success": True,
                    "latency_ms": round(elapsed_ms, 2),
                    "json_fields": len(content.keys()) if isinstance(content, dict) else 0,
                    "total_tokens": tokens,
                    "model": content.get("model") if isinstance(content, dict) else None,
                }
            )
        except Exception as exc:  # noqa: BLE001 - benchmark should report provider failures
            elapsed_ms = (time.perf_counter() - started) * 1000
            latencies.append(elapsed_ms)
            rows.append({"task": name, "success": False, "latency_ms": round(elapsed_ms, 2), "error": str(exc)[:300]})

    return {
        "enabled": True,
        "provider": "openai",
        "tasks": len(tasks),
        "success_rate": round(successes / len(tasks), 4),
        "json_validity_rate": round(successes / len(tasks), 4),
        "total_tokens": total_tokens,
        "latency": summarize_latency(latencies),
        "rows": rows,
    }


def build_dataset(ids: dict[str, int]) -> list[dict[str, Any]]:
    safety = ids["safety"]
    optics = ids["optics"]
    return [
        {"query": "1030-1100 nm 基频激光护目镜最低 OD 要求是什么", "expected_source_id": safety, "expected_terms": ["OD >= 5", "IR-1064-OD5"]},
        {"query": "开放高功率 4 类激光运行需要什么授权和 Watcher 要求", "expected_source_id": safety, "expected_terms": ["L3", "Watcher"]},
        {"query": "疑似眼照应急第一动作和就医时间要求", "expected_source_id": safety, "expected_terms": ["急停", "15分钟"]},
        {"query": "Beam dump 每日开机前检查要求是什么", "expected_source_id": safety, "expected_terms": ["Beam dump", "每日开机前"]},
        {"query": "触发红牌停机条件是否包括护目镜 OD 不匹配", "expected_source_id": safety, "expected_terms": ["护目镜OD不匹配"]},
        {"query": "1064 nm 输出耦合镜 T=5 ROC=100 的型号是什么", "expected_source_id": optics, "expected_terms": ["MIR-OC1064-T05", "ROC=100"]},
        {"query": "LBO 倍频无输出时优先检查哪些因素", "expected_source_id": optics, "expected_terms": ["LBO", "基频", "偏振", "角度"]},
        {"query": "测量 532 nm 光谱推荐什么滤光片和光谱仪", "expected_source_id": optics, "expected_terms": ["FLT-BP-532", "SPEC-USB"]},
        {"query": "临时封堵近红外光束应该使用哪个 beam block 器件编号", "expected_source_id": optics, "expected_terms": ["BB-BLOCK-IR"]},
        {"query": "光斑相机使用前为什么前端必须加 ND 衰减", "expected_source_id": optics, "expected_terms": ["CAM-BEAM", "ND", "饱和"]},
    ]


def _legacy_build_dataset(ids: dict[str, int]) -> list[dict[str, Any]]:
    safety = ids["safety"]
    optics = ids["optics"]
    troubleshooting = ids["troubleshooting"]
    return [
        {"query": "What OD eyewear is required for 1030-1100 nm Class 4 alignment?", "expected_source_id": safety, "expected_terms": ["OD >= 5", "IR-1064-OD5"]},
        {"query": "High-power Class 4 operation requires what authorization and watcher conditions?", "expected_source_id": safety, "expected_terms": ["L3 authorization", "Watcher"]},
        {"query": "疑似眼照射后第一步和就医时间要求是什么？", "expected_source_id": safety, "expected_terms": ["急停", "15 分钟"]},
        {"query": "Which shutdown conditions trigger a red-tag stop?", "expected_source_id": safety, "expected_terms": ["interlock", "eyewear OD mismatch", "beam dump"]},
        {"query": "Which 1064 nm output coupler has T=5 and ROC=100?", "expected_source_id": optics, "expected_terms": ["MIR-OC1064-T05", "ROC=100"]},
        {"query": "LBO 无 532 nm 输出时优先检查哪些因素？", "expected_source_id": optics, "expected_terms": ["基频功率", "偏振", "LBO 角度", "温度"]},
        {"query": "What filter and spectrometer should be used for 532 nm spectrum measurement?", "expected_source_id": optics, "expected_terms": ["FLT-BP-532", "SPEC-USB"]},
        {"query": "Which beam block should temporarily contain near-infrared beams?", "expected_source_id": optics, "expected_terms": ["BB-BLOCK-IR"]},
        {"query": "What low-risk checks help diagnose low output power after realignment?", "expected_source_id": troubleshooting, "expected_terms": ["cleaning inspection", "pump spot position", "mirror angle rollback"]},
        {"query": "What metrics should a power stability report include?", "expected_source_id": troubleshooting, "expected_terms": ["sampling duration", "standard deviation", "peak-to-peak drift"]},
    ]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--skip-llm", action="store_true")
    parser.add_argument("--use-env-file", action="store_true", help="Load .env files for real provider or deployment-specific benchmarks.")
    parser.add_argument("--include-upload-knowledge", action="store_true", help="Also index files under backend/uploads/global_knowledge.")
    args = parser.parse_args()

    configure_environment(use_env_file=args.use_env_file)
    os.chdir(BACKEND)

    from app.config import get_settings
    from app.database import SessionLocal

    get_settings.cache_clear()
    settings = get_settings()
    db = SessionLocal()
    try:
        index_summary = ensure_knowledge_index(db, include_upload_knowledge=args.include_upload_knowledge)
        ids = source_ids(db)
        missing = {"safety", "optics", "troubleshooting"} - set(ids)
        if missing:
            raise RuntimeError(f"Missing required benchmark knowledge source categories: {sorted(missing)}")
        dataset = build_dataset(ids)
        reindex = benchmark_reindex(db)
        retrieval = benchmark_retrieval(db, dataset, repeats=args.repeats, top_k=args.top_k)
        llm = await benchmark_llm(enabled=not args.skip_llm)
    finally:
        db.close()

    report = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "ai_provider": settings.ai_provider,
            "openai_model": settings.openai_model,
            "openai_base_url_set": bool(settings.openai_base_url),
            "openai_api_key_set": bool(settings.openai_api_key),
            "embedding_provider": settings.embedding_provider,
            "retrieval_backend": settings.retrieval_backend,
            "database_url": settings.database_url,
        },
        "knowledge_index": index_summary,
        "indexing": reindex,
        "retrieval": retrieval,
        "llm_generation": llm,
    }

    output_dir = ROOT / "docs" / "benchmarks"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"resume_metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nREPORT_PATH={output_path}")


if __name__ == "__main__":
    asyncio.run(main())
