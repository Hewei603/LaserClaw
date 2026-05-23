"""FastAPI application entry point."""
from __future__ import annotations

import logging
import os
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, agent, attachments, cases, generation, knowledge
from .config import get_settings
from .database import Base, engine
from . import models  # noqa: F401 - register SQLAlchemy models

settings = get_settings()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("laserclaw")

if settings.auto_create_tables:
    Base.metadata.create_all(bind=engine)
os.makedirs(settings.upload_dir, exist_ok=True)

app = FastAPI(
    title="LaserClaw API",
    description="Retrieval-augmented laser experiment workflow and Agent system.",
    version="2.0.0",
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
    except Exception as exc:
        logger.exception("Unhandled API error", extra={"request_id": request_id})
        return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id})
    response.headers["x-request-id"] = request_id
    return response


app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")

app.include_router(cases.router, prefix="/api/cases", tags=["cases"])
app.include_router(attachments.router, prefix="/api", tags=["attachments"])
app.include_router(generation.router, prefix="/api/cases", tags=["generation"])
app.include_router(knowledge.router, prefix="/api/knowledge", tags=["knowledge"])
app.include_router(agent.router, prefix="/api/agent", tags=["agent"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])


@app.get("/")
async def root():
    return {"message": "LaserClaw API", "version": "2.0.0", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "healthy"}
