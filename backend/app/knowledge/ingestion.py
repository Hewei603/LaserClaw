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
from .vector_store import index_source_chunks


def content_hash(content: bytes | str) -> str:
    data = content.encode("utf-8") if isinstance(content, str) else content
    return hashlib.sha256(data).hexdigest()


def object_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)


def _extract_table_text(raw: str, *, delimiter: str = ",", max_rows: int = 5000) -> str:
    rows = list(csv.reader(StringIO(raw), delimiter=delimiter))
    if not rows:
        return ""
    header = rows[0]
    lines = [f"Table columns: {' | '.join(header)}"]
    for index, row in enumerate(rows[1:max_rows], start=1):
        pairs = []
        for col_index, value in enumerate(row):
            column = header[col_index] if col_index < len(header) and header[col_index] else f"column_{col_index + 1}"
            pairs.append(f"{column}={value}")
        lines.append(f"row {index}: " + "; ".join(pairs))
    if len(rows) > max_rows:
        lines.append(f"Table truncated after {max_rows} rows out of {len(rows)} rows.")
    return "\n".join(lines)


def extract_text_from_file(filepath: str, content_type: Optional[str] = None) -> str:
    """Extract text from supported local files."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in {".txt", ".md", ".json", ".log"} or (content_type or "").startswith("text/"):
        with open(filepath, "r", encoding="utf-8", errors="ignore") as handle:
            raw = handle.read()
        return raw

    if ext in {".csv", ".tsv"}:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as handle:
            raw = handle.read()
        return _extract_table_text(raw, delimiter="\t" if ext == ".tsv" else ",")

    if ext == ".pdf":
        try:
            from unstructured.partition.pdf import partition_pdf

            elements = partition_pdf(filename=filepath)
            extracted = "\n\n".join(str(element) for element in elements if str(element).strip())
            if extracted.strip():
                return extracted
        except Exception:
            pass
        try:
            from pypdf import PdfReader
        except Exception:
            return "PDF uploaded. Install pypdf to extract searchable text."
        reader = PdfReader(filepath)
        pages = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                pages.append(f"[page {index}]\n{text}")
        return "\n\n".join(pages)

    return f"Unsupported attachment type {ext or content_type or 'unknown'}; filename retained for citation."


def replace_source_chunks(db: Session, source: KnowledgeSource, text: str) -> None:
    source.chunks.clear()
    chunks = chunk_text(text)
    if not chunks:
        chunks = [text[:2000] or source.title]
    for index, chunk in enumerate(chunks):
        section_match = re.search(r"\[(SAF-[A-Z0-9-]+|OPT-[A-Z0-9-]+)\]", chunk)
        embedding = embed_text(chunk)
        source.chunks.append(
            KnowledgeChunk(
                chunk_index=index,
                text=chunk,
                token_count=len(chunk.split()),
                embedding=embedding,
                metadata_json={
                    "preview": chunk[:240],
                    "section_id": section_match.group(1) if section_match else None,
                    "embedding_provider": embedding.get("provider", "local"),
                    "embedding_model": embedding.get("model"),
                },
            )
        )
    index_source_chunks(db, source)


def upsert_case_source(db: Session, case: ExperimentCase) -> KnowledgeSource:
    text = "\n".join(
        [
            f"Title: {case.title}",
            f"Description: {case.description or ''}",
            f"Cavity type: {case.cavity_type}",
            f"Goal: {case.goal}",
            f"Status: {case.status}",
            f"Tags: {object_to_text(case.tags)}",
            f"Parameters: {object_to_text(case.parameters)}",
            f"Symptoms: {object_to_text(case.symptoms)}",
            f"Measurements: {object_to_text(case.measurements)}",
            f"Safety notes: {case.safety_notes or ''}",
            f"Conclusions: {case.conclusions or ''}",
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
    source.metadata_json = {"cavity_type": case.cavity_type, "schema_version": case.schema_version, "tags": case.tags or []}
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
        metadata_json={"file_type": attachment.file_type, "filepath": attachment.filepath},
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
        metadata_json={"file_type": content_type, "scope": "global", "filepath": filepath},
    )
    db.add(source)
    replace_source_chunks(db, source, text)
    return source
