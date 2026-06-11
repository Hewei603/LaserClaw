from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    executable = shutil.which(command[0]) or command[0]
    command = [executable, *command[1:]]
    printable = " ".join(command)
    print(f"\n==> {printable}", flush=True)
    completed = subprocess.run(command, cwd=cwd, env={**os.environ, **(env or {})})
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local LaserClaw acceptance checks.")
    parser.add_argument("--skip-frontend", action="store_true")
    parser.add_argument("--skip-lint", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()

    if not args.skip_lint:
        run([sys.executable, "-m", "ruff", "check", "backend"], cwd=ROOT)

    if not args.skip_tests:
        run([sys.executable, "-m", "pytest", "tests", "-q"], cwd=BACKEND)

    tmp_db = BACKEND / "_tmp_migration_check.db"
    if tmp_db.exists():
        tmp_db.unlink()
    try:
        run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND,
            env={"DATABASE_URL": "sqlite:///./_tmp_migration_check.db"},
        )
    finally:
        if tmp_db.exists():
            tmp_db.unlink()

    run(
        [
            sys.executable,
            "-m",
            "py_compile",
            "scripts/index_authorized_docs.py",
            "scripts/eval_authorized_rag.py",
            "scripts/tune_retrieval_thresholds.py",
            "scripts/final_acceptance_audit.py",
            "scripts/audit_endpoint_acl.py",
            "scripts/benchmark_retrieval_backends.py",
            "scripts/benchmark_generation_latency.py",
        ],
        cwd=BACKEND,
    )

    run(
        [
            sys.executable,
            "scripts/audit_endpoint_acl.py",
            "--fail-on-findings",
        ],
        cwd=BACKEND,
    )

    run(
        [
            sys.executable,
            "-c",
            (
                "from app.evals.datasets import load_jsonl_dataset; "
                "rows = load_jsonl_dataset('../docs/evals/examples/rag_eval_synthetic.jsonl'); "
                "assert len(rows) == 3"
            ),
        ],
        cwd=BACKEND,
    )

    if not args.skip_frontend:
        if not args.skip_lint:
            run(["npm", "run", "lint"], cwd=FRONTEND)
        run(["npm", "run", "build"], cwd=FRONTEND)

    print("\nLocal acceptance checks passed.")


if __name__ == "__main__":
    main()
