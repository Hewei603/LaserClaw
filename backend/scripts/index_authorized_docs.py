from __future__ import annotations

import mimetypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import SessionLocal
from app.knowledge.ingestion import content_hash, create_global_file_source, extract_text_from_file
from app.models import KnowledgeSource


DOC_DIR = BACKEND / "uploads" / "authorized_lab_docs"


def main() -> None:
    DOC_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    try:
        for path in sorted(DOC_DIR.glob("*")):
            if not path.is_file():
                continue
            content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            text = extract_text_from_file(str(path), content_type)
            digest = content_hash(text)
            existing = db.query(KnowledgeSource).filter(KnowledgeSource.content_hash == digest).first()
            if existing:
                print(f"skip existing {path.name}: source_id={existing.id}")
                continue
            source = create_global_file_source(
                db,
                title=path.name,
                filepath=str(path),
                content_type=content_type,
            )
            source.governance_status = "approved"
            source.metadata_json = {
                **(source.metadata_json or {}),
                "authorized_eval": True,
                "do_not_commit": True,
            }
            print(f"indexed {source.id}: {path.name}")
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
