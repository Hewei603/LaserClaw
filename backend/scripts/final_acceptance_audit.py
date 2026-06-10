from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.evals.acceptance import (
    fetch_latest_github_ci_run,
    load_eval_report,
    summarize_final_acceptance,
    validate_eval_report,
    validate_github_ci_run,
)


def _run_local_acceptance() -> bool:
    completed = subprocess.run([sys.executable, "scripts/acceptance_check.py"], cwd=BACKEND)
    return completed.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit LaserClaw final enterprise acceptance gates.")
    parser.add_argument("--skip-local", action="store_true", help="Do not run scripts/acceptance_check.py.")
    parser.add_argument("--github-repo", default="Hewei603/LaserClaw")
    parser.add_argument("--github-branch", default="main")
    parser.add_argument("--github-workflow", default="CI")
    parser.add_argument("--private-report", default=str(ROOT / "docs" / "evals" / "private" / "last_report.json"))
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    local_passed = True if args.skip_local else _run_local_acceptance()

    try:
        run = fetch_latest_github_ci_run(args.github_repo, branch=args.github_branch, workflow_name=args.github_workflow)
        ci = validate_github_ci_run(run)
    except Exception as exc:  # pragma: no cover - network/runtime diagnostic path
        ci = {"passed": False, "reason": f"Could not fetch GitHub Actions status: {exc}"}

    try:
        private_eval = validate_eval_report(load_eval_report(args.private_report))
    except Exception as exc:
        private_eval = {"passed": False, "reason": str(exc)}

    summary = summarize_final_acceptance(local_passed=local_passed, ci=ci, private_eval=private_eval)
    text = json.dumps(summary, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
    if not summary["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
