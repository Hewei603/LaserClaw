from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi.routing import APIRoute


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
DEFAULT_OUTPUT = ROOT / "docs" / "benchmarks" / "latest_endpoint_acl_audit.json"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

AUTH_DEPENDENCIES = {"get_current_principal", "dependency"}
PUBLIC_ENDPOINTS = {
    ("GET", "/"),
    ("GET", "/health"),
    ("GET", "/docs"),
    ("GET", "/openapi.json"),
    ("GET", "/redoc"),
}


def dependency_names(route: APIRoute) -> set[str]:
    names: set[str] = set()

    def visit(dependant: Any) -> None:
        call = getattr(dependant, "call", None)
        if call is not None:
            names.add(getattr(call, "__name__", repr(call)))
        for child in getattr(dependant, "dependencies", []) or []:
            visit(child)

    visit(route.dependant)
    return names


def route_record(route: APIRoute) -> dict[str, Any]:
    methods = sorted(method for method in route.methods if method not in {"HEAD", "OPTIONS"})
    deps = sorted(dependency_names(route))
    requires_principal = "get_current_principal" in deps
    public_methods = [method for method in methods if (method, route.path) in PUBLIC_ENDPOINTS]
    should_be_protected = route.path.startswith("/api/")
    finding = None
    if should_be_protected and not requires_principal:
        finding = "api_endpoint_without_principal_dependency"
    return {
        "path": route.path,
        "methods": methods,
        "name": route.name,
        "dependencies": deps,
        "requires_principal": requires_principal,
        "public_methods": public_methods,
        "should_be_protected": should_be_protected,
        "finding": finding,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit FastAPI endpoints for v1.0 auth/ACL coverage.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--fail-on-findings", action="store_true")
    args = parser.parse_args()

    from app.main import app

    records = [
        route_record(route)
        for route in app.routes
        if isinstance(route, APIRoute)
    ]
    findings = [record for record in records if record["finding"]]
    protected = [record for record in records if record["requires_principal"]]
    api_routes = [record for record in records if record["path"].startswith("/api/")]
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_routes": len(records),
            "api_routes": len(api_routes),
            "protected_routes": len(protected),
            "findings": len(findings),
        },
        "findings": findings,
        "routes": records,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"REPORT_PATH={args.output}")
    if findings and args.fail_on_findings:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
