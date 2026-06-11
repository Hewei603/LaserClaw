from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
DEFAULT_OUTPUT = ROOT / "docs" / "benchmarks" / "latest_generation_latency.json"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


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


def has_expected_shape(mode: str, content: dict[str, Any]) -> bool:
    if not isinstance(content, dict):
        return False
    if mode == "plan":
        return bool(content.get("steps") or content.get("plan"))
    if mode == "troubleshooting":
        return bool(content.get("suggestions") or content.get("diagnosis") or content.get("checks") or content.get("likely_causes"))
    if mode == "report":
        return bool(content.get("summary") or content.get("sections"))
    if mode == "rezonator":
        return bool(content.get("elements") or content.get("cavity_type") or content.get("parameters") or content.get("rezonator") or content.get("cavity"))
    return True


async def run_benchmark(modes: list[str], repeats: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="laserclaw-generation-") as tmp:
        tmp_path = Path(tmp)
        os.environ["DATABASE_URL"] = f"sqlite:///{tmp_path / 'bench.db'}"
        os.environ["UPLOAD_DIR"] = str(tmp_path / "uploads")
        os.environ["VECTOR_STORE_DIR"] = str(tmp_path / "vector_store")
        os.environ["AI_PROVIDER"] = os.environ.get("AI_PROVIDER", "mock")
        os.environ["EMBEDDING_PROVIDER"] = os.environ.get("EMBEDDING_PROVIDER", "local")
        os.environ["RETRIEVAL_BACKEND"] = os.environ.get("RETRIEVAL_BACKEND", "sql_json")
        os.environ["RERANKER_PROVIDER"] = os.environ.get("RERANKER_PROVIDER", "none")
        os.environ["AUTO_CREATE_TABLES"] = "true"

        from app.agent.orchestrator import create_and_run_task
        from app.database import Base, SessionLocal, engine
        from app.knowledge.ingestion import create_global_file_source, upsert_case_source
        from app.models import ExperimentCase, GeneratedContent

        Base.metadata.create_all(bind=engine)
        upload_dir = Path(os.environ["UPLOAD_DIR"])
        upload_dir.mkdir(parents=True, exist_ok=True)
        safety_doc = upload_dir / "laser_safety.md"
        safety_doc.write_text(
            "Class 4 laser experiments require OD-rated eyewear, interlocks, beam blocks, emergency stop checks, and human review.",
            encoding="utf-8",
        )
        db = SessionLocal()
        try:
            case = ExperimentCase(
                title="Synthetic 1064 nm alignment case",
                description="Low output power after cavity realignment.",
                cavity_type="linear",
                goal="Recover stable 1064 nm output while following lab safety rules.",
                parameters={"wavelength_nm": 1064, "pump_current_a": 18},
                symptoms=["low power", "unstable output"],
                safety_notes="Class 4 laser. Verify interlocks and PPE before alignment.",
            )
            db.add(case)
            db.flush()
            upsert_case_source(db, case)
            create_global_file_source(db, title="Laser Safety SOP", filepath=str(safety_doc), content_type="text/markdown")
            db.commit()

            results = []
            for mode in modes:
                latencies: list[float] = []
                schema_pass = 0
                failures = 0
                for index in range(repeats):
                    start = time.perf_counter()
                    try:
                        task = await create_and_run_task(
                            db,
                            case_id=case.id,
                            goal=f"Create a {mode} artifact for the synthetic laser case run {index + 1}.",
                            mode=mode,
                        )
                        elapsed_ms = (time.perf_counter() - start) * 1000
                        latencies.append(elapsed_ms)
                        generated = db.query(GeneratedContent).filter(GeneratedContent.id == task.final_content_id).first()
                        if generated and has_expected_shape(mode, generated.content or {}):
                            schema_pass += 1
                    except Exception:
                        db.rollback()
                        failures += 1
                total = repeats
                results.append(
                    {
                        "mode": mode,
                        "runs": total,
                        "failures": failures,
                        "schema_pass_rate": round(schema_pass / total, 4) if total else 0,
                        "latency": summarize(latencies),
                    }
                )
            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "provider": os.environ.get("AI_PROVIDER", "mock"),
                "dataset": "synthetic",
                "results": results,
            }
        finally:
            db.close()
            engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark structured generation latency and output shape.")
    parser.add_argument("--modes", default="plan,troubleshooting,report,rezonator")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    report = asyncio.run(run_benchmark([mode.strip() for mode in args.modes.split(",") if mode.strip()], args.repeats))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\nREPORT_PATH={args.output}")


if __name__ == "__main__":
    main()
