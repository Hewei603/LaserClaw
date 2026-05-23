"""Knowledge ingestion services."""
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from io import StringIO
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..models import Attachment, ExperimentCase, GeneratedContent, KnowledgeChunk, KnowledgeSource
from .chunking import chunk_text
from .embeddings import embed_text


def content_hash(content: bytes | str) -> str:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(data).hexdigest()


def object_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def extract_text_from_file(filepath: str, content_type: Optional[str] = None) -> str:
    """Extract text from supported local files."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in {".txt", ".md", ".csv", ".json", ".log"} or (content_type or "").startswith("text/"):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as handle:
            raw = handle.read()
        if ext == ".csv":
            rows = list(csv.reader(StringIO(raw)))
            preview = [" | ".join(row) for row in rows[:200]]
            return "\n".join(preview)
        return raw

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except Exception:
            return "PDF uploaded. Install pypdf to extract searchable text."
        reader = PdfReader(filepath)
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    return f"Unsupported attachment type {ext or content_type or 'unknown'}; filename retained for citation."


def replace_source_chunks(db: Session, source: KnowledgeSource, text: str) -> None:
    source.chunks.clear()
    chunks = chunk_text(text)
    if not chunks:
        chunks = [text[:2000] or source.title]
    for index, chunk in enumerate(chunks):
        section_match = re.search(r"\[(SAF-[A-Z0-9-]+|OPT-[A-Z0-9-]+)\]", chunk)
        source.chunks.append(
            KnowledgeChunk(
                chunk_index=index,
                text=chunk,
                token_count=len(chunk.split()),
                embedding=embed_text(chunk),
                metadata_json={
                    "preview": chunk[:240],
                    "section_id": section_match.group(1) if section_match else None,
                },
            )
        )


def upsert_case_source(db: Session, case: ExperimentCase) -> KnowledgeSource:
    text = "\n".join(
        [
            f"Title: {case.title}",
            f"Description: {case.description or ''}",
            f"Cavity type: {case.cavity_type}",
            f"Goal: {case.goal}",
            f"Parameters: {object_to_text(case.parameters)}",
            f"Symptoms: {object_to_text(case.symptoms)}",
        ]
    )
    digest = content_hash(text)
    source = (
        db.query(KnowledgeSource)
        .filter(KnowledgeSource.case_id == case.id, KnowledgeSource.source_type == "case")
        .first()
    )
    if source is None:
        source = KnowledgeSource(case_id=case.id, source_type="case", title=case.title, uri=f"case:{case.id}")
        db.add(source)
    source.title = case.title
    source.content_hash = digest
    source.metadata_json = {"cavity_type": case.cavity_type}
    replace_source_chunks(db, source, text)
    return source


def create_attachment_source(db: Session, attachment: Attachment) -> KnowledgeSource:
    text = extract_text_from_file(attachment.filepath, attachment.file_type)
    source = KnowledgeSource(
        case_id=attachment.case_id,
        attachment_id=attachment.id,
        source_type="attachment",
        title=attachment.filename,
        uri=f"attachment:{attachment.id}",
        content_hash=content_hash(text),
        metadata_json={"file_type": attachment.file_type},
    )
    db.add(source)
    replace_source_chunks(db, source, text)
    return source


def create_generated_content_source(db: Session, generated: GeneratedContent) -> KnowledgeSource:
    text = object_to_text(generated.content)
    source = KnowledgeSource(
        case_id=generated.case_id,
        generated_content_id=generated.id,
        source_type="generated_content",
        title=f"{generated.content_type} #{generated.id}",
        uri=f"generated_content:{generated.id}",
        content_hash=content_hash(text),
        metadata_json={"content_type": generated.content_type},
    )
    db.add(source)
    replace_source_chunks(db, source, text)
    return source


def create_global_file_source(db: Session, *, title: str, filepath: str, content_type: str | None = None) -> KnowledgeSource:
    """Create a global searchable source from a lab knowledge file."""
    text = extract_text_from_file(filepath, content_type)
    source = KnowledgeSource(
        case_id=None,
        source_type="global_attachment",
        title=title,
        uri=f"global:{os.path.basename(filepath)}",
        content_hash=content_hash(text),
        metadata_json={"file_type": content_type, "scope": "global"},
    )
    db.add(source)
    replace_source_chunks(db, source, text)
    return source
