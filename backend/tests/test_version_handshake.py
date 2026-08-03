"""The stale-backend banner only works if three version strings never drift:

* ``backend/app/version.py::APP_VERSION`` — what the backend reports,
* ``frontend/src/expectedBackend.js`` — what the frontend expects,
* the FastAPI app object — what /docs displays.

A mismatch would either hide a genuinely stale backend or show the restart
banner forever; both silently break the one mechanism a non-technical user has
for noticing that their double-clicked launcher is serving old code.
"""
import re
from pathlib import Path

from app.main import app
from app.version import APP_VERSION

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_health_reports_app_version(client):
    data = client.get("/health").json()
    assert data["version"] == APP_VERSION
    assert data["status"] == "healthy"


def test_root_and_openapi_report_app_version(client):
    assert client.get("/").json()["version"] == APP_VERSION
    assert app.version == APP_VERSION


def test_frontend_expected_version_matches_backend():
    js = (REPO_ROOT / "frontend" / "src" / "expectedBackend.js").read_text(encoding="utf-8")
    match = re.search(r"EXPECTED_BACKEND_VERSION\s*=\s*'([^']+)'", js)
    assert match, "frontend/src/expectedBackend.js must define EXPECTED_BACKEND_VERSION"
    assert match.group(1) == APP_VERSION, (
        f"frontend expects backend {match.group(1)!r} but backend is {APP_VERSION!r}; "
        "update both files together"
    )
