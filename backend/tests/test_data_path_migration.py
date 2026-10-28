"""A migrated database must work after the original checkout is removed."""
import json
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.data_migration import migrate_legacy_data
from app.database import Base, get_db
from app.main import app
from app.models import Attachment, CaseModule, CaseModuleFile, ExperimentCase, KnowledgeSource


def _legacy(tmp_path):
    repo = tmp_path / "legacy-repo"
    (repo / "backend").mkdir(parents=True)
    uploads = repo / "uploads"
    (uploads / "case_modules" / "1").mkdir(parents=True)
    (uploads / "global_knowledge").mkdir()
    paths = [uploads / "attachment.txt", uploads / "case_modules" / "1" / "curve.csv",
             uploads / "global_knowledge" / "source.txt"]
    for path in paths:
        path.write_text("Migration test evidence", encoding="utf-8")
    engine = create_engine(f"sqlite:///{(repo / 'backend' / 'laserclaw.db').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        case = ExperimentCase(title="Migration case", goal="Test", cavity_type="linear")
        db.add(case)
        db.flush()
        module = CaseModule(case_id=case.id, module_type="power_curve", title="Curve")
        db.add(module)
        db.flush()
        db.add(Attachment(case_id=case.id, filename="attachment.txt", filepath=str(paths[0]), file_type="text/plain"))
        db.add(CaseModuleFile(module_id=module.id, filename="curve.csv", filepath=str(paths[1]),
                              metadata_json={"original": {"filepath": str(paths[1])}}))
        db.add(KnowledgeSource(title="Global source", source_type="global_attachment",
                               metadata_json={"filepath": str(paths[2]), "file_type": "text/plain", "note": "Keep me"}))
        db.commit()
    engine.dispose()
    data = tmp_path / "external-data"
    settings = SimpleNamespace(database_url=f"sqlite:///{(data / 'laserclaw.db').as_posix()}",
                               upload_dir=str(data / "uploads"), vector_store_dir=str(data / "vectors"))
    return repo, data, settings


@pytest.mark.parametrize("already_copied", [False, True])
def test_migrated_downloads_and_reindex_work_without_old_checkout(tmp_path, client, monkeypatch, already_copied):
    repo, data, settings = _legacy(tmp_path)
    if already_copied:
        # Simulate the previous release's file-only migration and then launch
        # from a different checkout. No current-root prefix is available.
        data.mkdir()
        shutil.copy2(repo / "backend" / "laserclaw.db", data / "laserclaw.db")
        shutil.copytree(repo / "uploads", data / "uploads")
        (data / "laserclaw.db.before-upload-paths.bak.copying").write_bytes(b"interrupted backup")
        current_repo = tmp_path / "new-checkout"
        current_repo.mkdir()
    else:
        current_repo = repo
    notes = migrate_legacy_data(settings, repo_root=current_repo)
    assert any("附件路径" in note for note in notes)
    (repo / "uploads").rename(repo / "retired-uploads")
    assert migrate_legacy_data(settings, repo_root=current_repo) == []

    backup = data / "laserclaw.db.before-upload-paths.bak"
    assert not backup.with_name(backup.name + ".copying").exists()
    connection = sqlite3.connect(backup)
    try:
        assert str(repo) in connection.execute("SELECT filepath FROM attachments").fetchone()[0]
    finally:
        connection.close()

    engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
    try:
        with Session(engine) as db:
            monkeypatch.setitem(app.dependency_overrides, get_db, lambda: db)
            attachment = db.query(Attachment).one()
            module_file = db.query(CaseModuleFile).one()
            source = db.query(KnowledgeSource).one()
            for path in (attachment.filepath, module_file.filepath, source.metadata_json["filepath"]):
                assert Path(path).is_file() and Path(path).is_relative_to(data)
            assert module_file.metadata_json["original"]["filepath"] == module_file.filepath
            assert source.metadata_json["note"] == "Keep me"
            assert client.get(f"/api/attachments/{attachment.id}").status_code == 200
            assert client.get(f"/api/cases/module-files/{module_file.id}").status_code == 200
            result = client.post(f"/api/knowledge/sources/{source.id}/reindex")
            assert result.status_code == 200, result.text
            assert source.chunks and "Migration test evidence" in source.chunks[0].text
    finally:
        engine.dispose()


def test_existing_target_does_not_redirect_to_missing_or_different_files(tmp_path):
    repo, data, settings = _legacy(tmp_path)
    (data / "uploads").mkdir(parents=True)
    (data / "uploads" / "attachment.txt").write_text("Different bytes", encoding="utf-8")
    shutil.copy2(repo / "backend" / "laserclaw.db", data / "laserclaw.db")
    migrate_legacy_data(settings, repo_root=repo)
    connection = sqlite3.connect(data / "laserclaw.db")
    try:
        assert str(repo) in connection.execute("SELECT filepath FROM attachments").fetchone()[0]
        metadata = json.loads(connection.execute("SELECT metadata_json FROM knowledge_sources").fetchone()[0])
        assert str(repo) in metadata["filepath"]
    finally:
        connection.close()
    assert not (data / "laserclaw.db.before-upload-paths.bak").exists()
