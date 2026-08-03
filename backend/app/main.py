"""FastAPI application entry point."""
from __future__ import annotations

import logging
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, agent, attachments, case_modules, cases, collaboration, evals, generation, inventory, knowledge, versioning
from .config import get_settings
from .database import Base, engine, sync_additive_schema
from .version import APP_VERSION
from . import models  # noqa: F401 - register SQLAlchemy models

settings = get_settings()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("laserclaw")

# Must run before create_all: create_all would materialize an empty database at
# the new location, and the legacy-data copy only ever fills an empty target.
from .data_migration import migrate_legacy_data  # noqa: E402

for _note in migrate_legacy_data(settings):
    logger.info(_note)

if settings.auto_create_tables:
    Base.metadata.create_all(bind=engine)
    # create_all only creates missing tables; a database made by an earlier
    # release also needs the columns added since. See sync_additive_schema.
    sync_additive_schema()
os.makedirs(settings.upload_dir, exist_ok=True)

app = FastAPI(
    title="LaserClaw API",
    description="Retrieval-augmented laser experiment workflow and Agent system.",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled API error", extra={"request_id": request_id})
        return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id})
    response.headers["x-request-id"] = request_id
    return response


app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

app.include_router(cases.router, prefix="/api/cases", tags=["cases"])
app.include_router(case_modules.router, prefix="/api/cases", tags=["case-modules"])
app.include_router(attachments.router, prefix="/api", tags=["attachments"])
app.include_router(generation.router, prefix="/api/cases", tags=["generation"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(collaboration.router, prefix="/api/collaboration", tags=["collaboration"])
app.include_router(versioning.router, prefix="/api/versioning", tags=["versioning"])
app.include_router(evals.router, prefix="/api/evals", tags=["evals"])
app.include_router(inventory.router, prefix="/api/inventory", tags=["inventory"])


@app.get("/")
async def root():
    return {"message": "LaserClaw API", "version": APP_VERSION, "docs": "/docs"}


@app.get("/health")
async def health():
    # The provider block lets the frontend show a "demo mode" banner: mock
    # output reads like real output, so the user must be told which is running.
    # The version lets it show a "stale backend, restart the launcher" banner:
    # the launcher-started process keeps serving old code until its window is
    # closed, and the user has no other way to notice.
    from .providers import provider_status

    return {"status": "healthy", "version": APP_VERSION, "provider": provider_status()}
