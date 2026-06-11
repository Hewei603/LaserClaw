from app.database import SessionLocal
from app.knowledge.ingestion import replace_source_chunks, extract_text_from_file, object_to_text, upsert_case_source
from app.models import KnowledgeSource


def reindex_source(db, source: KnowledgeSource):
    if source.source_type == "case" and source.case:
        upsert_case_source(db, source.case)
        return
    if source.attachment:
        text = extract_text_from_file(source.attachment.filepath, source.attachment.file_type)
        replace_source_chunks(db, source, text)
        return
    if source.generated_content:
        text = object_to_text(source.generated_content.content)
        replace_source_chunks(db, source, text)
        return
    if source.source_type == "global_attachment":
        filepath = (source.metadata_json or {}).get("filepath")
        file_type = (source.metadata_json or {}).get("file_type")
        text = extract_text_from_file(filepath, file_type)
        replace_source_chunks(db, source, text)


def main():
    db = SessionLocal()
    try:
        sources = db.query(KnowledgeSource).all()
        for source in sources:
            print(f"reindex source_id={source.id} title={source.title}")
            reindex_source(db, source)
            db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
