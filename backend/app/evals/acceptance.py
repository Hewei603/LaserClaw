"""Final acceptance helpers for release gates."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


def load_eval_report(path: str | Path) -> dict[str, Any]:
    report_path = Path(path)
    if not report_path.is_file():
        raise FileNotFoundError(f"Eval report does not exist: {report_path}")
    return json.loads(report_path.read_text(encoding="utf-8"))


def validate_eval_report(report: dict[str, Any]) -> dict[str, Any]:
    acceptance = report.get("acceptance")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return {"passed": False, "reason": "Eval report is missing summary"}
    if not isinstance(acceptance, dict):
        return {"passed": False, "reason": "Eval report is missing acceptance"}
    if not acceptance.get("passed"):
        return {
            "passed": False,
            "reason": "Eval report did not meet acceptance thresholds",
            "failures": acceptance.get("failures") or [],
            "summary": summary,
        }
    return {
        "passed": True,
        "summary": summary,
        "thresholds": acceptance.get("thresholds") or {},
    }


def fetch_latest_github_ci_run(repo: str, *, branch: str = "main", workflow_name: str = "CI") -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repo}/actions/runs?branch={branch}&per_page=20"
    request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "LaserClaw-acceptance-audit"})
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    for run in payload.get("workflow_runs", []):
        if run.get("name") == workflow_name:
            return run
    return {}


def validate_github_ci_run(run: dict[str, Any]) -> dict[str, Any]:
    if not run:
        return {"passed": False, "reason": "No matching GitHub Actions run found"}
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        return {
            "passed": False,
            "reason": "Latest matching GitHub Actions run is not successful",
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "html_url": run.get("html_url"),
        }
    return {
        "passed": True,
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "html_url": run.get("html_url"),
    }


def summarize_final_acceptance(*, local_passed: bool, ci: dict[str, Any], private_eval: dict[str, Any]) -> dict[str, Any]:
    gates = {
        "local": {"passed": local_passed},
        "remote_ci": ci,
        "private_eval": private_eval,
    }
    return {
        "passed": all(gate.get("passed") for gate in gates.values()),
        "gates": gates,
    }
