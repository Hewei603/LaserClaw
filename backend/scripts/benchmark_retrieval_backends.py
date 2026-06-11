from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
DEFAULT_OUTPUT = ROOT / "docs" / "benchmarks" / "latest_retrieval_backends.json"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DOCUMENTS = {
    "Laser Safety SOP": "Class 4 laser work requires OD-rated safety glasses, interlocks, warning signs, and emergency stop verification before alignment.",
    "Optics Catalog": "The 1064 nm resonator uses high-reflectivity mirrors, Nd:YAG crystal, beam splitter, lens mounts, and an output coupler.",
    "Troubleshooting Notes": "Low power can be caused by dirty optics, crystal temperature drift, pump current instability, or poor cavity alignment.",
    "中文安全规程": "四类激光调光前必须检查防护眼镜、急停按钮、门禁联锁和光路遮挡，禁止未授权人员进入。",
}

QUERIES = [
    {"query": "What PPE is required for Class 4 laser alignment?", "expected": "Laser Safety SOP"},
    {"query": "Which components are used in a 1064 nm resonator?", "expected": "Optics Catalog"},
    {"query": "Why is laser output power low?", "expected": "Troubleshooting Notes"},
    {"query": "调光前需要检查哪些安全措施？", "expected": "中文安全规程"},
]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "count": len(values),
        "p50_ms": round(percentile(values, 50), 2),
        "p95_ms": round(percentile(values, 95), 2),
        "mean_ms": round(statistics.mean(values), 2) if values else 0.0,
    }


def run_one_backend(backend: str, repeats: int, top_k: int) -> dict[str, Any]:
    if backend == "pgvector":
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url.startswith("postgresql"):
            return {"backend": backend, "status": "skipped", "reason": "DATABASE_URL is not PostgreSQL"}

    with tempfile.TemporaryDirectory(prefix=f"laserclaw-{backend}-") as tmp:
        tmp_path = Path(tmp)
        os.environ["DATABASE_URL"] = os.environ.get("DATABASE_URL") if backend == "pgvector" else f"sqlite:///{tmp_path / 'bench.db'}"
        os.environ["UPLOAD_DIR"] = str(tmp_path / "uploads")
        os.environ["VECTOR_STORE_DIR"] = str(tmp_path / "vector_store")
        os.environ["RETRIEVAL_BACKEND"] = backend
        os.environ.setdefault("EMBEDDING_PROVIDER", "local")
        os.environ.setdefault("RERANKER_PROVIDER", "none")
        os.environ["AUTO_CREATE_TABLES"] = "true"

        from app.database import Base, SessionLocal, engine
        from app.knowledge.ingestion import create_global_file_source
        from app.knowledge.retrieval import search_knowledge

        Base.metadata.create_all(bind=engine)
        upload_dir = Path(os.environ["UPLOAD_DIR"])
        upload_dir.mkdir(parents=True, exist_ok=True)
        db = SessionLocal()
        try:
            for title, text in DOCUMENTS.items():
                path = upload_dir / f"{title.replace(' ', '_')}.md"
                path.write_text(text, encoding="utf-8")
                create_global_file_source(db, title=title, filepath=str(path), content_type="text/markdown")
            db.commit()

            latencies: list[float] = []
            hits_at_1 = 0
            hits_at_k = 0
            result_count = 0
            for _ in range(repeats):
                for item in QUERIES:
                    start = time.perf_counter()
                    _, results = search_knowledge(db, query=item["query"], top_k=top_k)
                    db.rollback()
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    latencies.append(elapsed_ms)
                    titles = [result.title for result in results]
                    result_count += len(results)
                    if titles and titles[0] == item["expected"]:
                        hits_at_1 += 1
                    if item["expected"] in titles:
                        hits_at_k += 1
            total = repeats * len(QUERIES)
            return {
                "backend": backend,
                "status": "passed",
                "queries": total,
                "top_k": top_k,
                "avg_result_count": round(result_count / total, 2) if total else 0,
                "hit_at_1": round(hits_at_1 / total, 4) if total else 0,
                f"hit_at_{top_k}": round(hits_at_k / total, 4) if total else 0,
                "latency": summarize(latencies),
            }
        finally:
            db.close()
            engine.dispose()


def run_child(backend: str, repeats: int, top_k: int) -> dict[str, Any]:
    env = {**os.environ, "LASERCLAW_BENCHMARK_CHILD": "1"}
    completed = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).resolve()),
            "--backend",
            backend,
            "--repeats",
            str(repeats),
            "--top-k",
            str(top_k),
        ],
        cwd=BACKEND,
        env=env,
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        return {"backend": backend, "status": "failed", "stderr": completed.stderr[-4000:], "stdout": completed.stdout[-2000:]}
    return json.loads(completed.stdout)


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark LaserClaw retrieval backends on a reproducible synthetic corpus.")
    parser.add_argument("--backends", default="sql_json,chroma,pgvector")
    parser.add_argument("--backend")
    parser.add_argument("--repeats", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if os.environ.get("LASERCLAW_BENCHMARK_CHILD") == "1":
        print(json.dumps(run_one_backend(args.backend or "sql_json", args.repeats, args.top_k), ensure_ascii=False))
        return

    reports = [run_child(backend.strip(), args.repeats, args.top_k) for backend in args.backends.split(",") if backend.strip()]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": "synthetic",
        "repeats": args.repeats,
        "top_k": args.top_k,
        "results": reports,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nREPORT_PATH={args.output}")


if __name__ == "__main__":
    main()
