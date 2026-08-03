"""One-time copy of experiment data out of the code tree.

Versions before 2.1 stored everything inside the repository — the database at
``backend/laserclaw.db``, attachments in ``<repo>/uploads``, the RAG index in
``<repo>/backend/vector_store``. A user whose idea of "updating" is re-downloading
the folder (the realistic path for a user with no software background) would
silently lose all of it. The launcher now points ``DATABASE_URL`` / ``UPLOAD_DIR``
/ ``VECTOR_STORE_DIR`` at ``%USERPROFILE%\\LaserClaw-Data``; this module copies the
legacy data there the first time the new location is empty.

Copy, never move: the legacy files stay behind as a de-facto backup, and because
each item is guarded by its own "target already has data" check, a half-finished
copy is simply resumed on the next start instead of corrupting anything.
"""
from __future__ import annotations

import shutil
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SQLITE_PREFIX = "sqlite:///"


def _sqlite_path(database_url: str) -> Path | None:
    """Filesystem path of a file-backed sqlite URL, else None."""
    if not database_url.startswith(_SQLITE_PREFIX):
        return None
    raw = database_url[len(_SQLITE_PREFIX):]
    if not raw or raw == ":memory:":
        return None
    return Path(raw)


def _dir_has_content(path: Path) -> bool:
    return path.is_dir() and any(path.iterdir())


def _copy_dir(legacy: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for entry in legacy.iterdir():
        dest = target / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, dest)


def migrate_legacy_data(settings, repo_root: Path | None = None) -> list[str]:
    """Copy pre-2.1 in-tree data to the configured locations. Returns log notes.

    Only ever fills an *empty* target: once the new location has data it is the
    single source of truth and the in-tree leftovers are ignored forever — the
    reverse (re-copying) would resurrect stale data after every update.
    """
    root = repo_root or _REPO_ROOT
    notes: list[str] = []

    # Database ---------------------------------------------------------------
    target_db = _sqlite_path(settings.database_url)
    legacy_db = root / "backend" / "laserclaw.db"
    if (
        target_db is not None
        and not target_db.exists()
        and legacy_db.is_file()
        and target_db.resolve() != legacy_db.resolve()
    ):
        target_db.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_db, target_db)
        notes.append(f"已把旧数据库 {legacy_db} 复制到新的数据目录 {target_db}(旧文件保留作为备份)")

    # Uploaded attachments ---------------------------------------------------
    target_uploads = Path(settings.upload_dir)
    for legacy_uploads in (root / "uploads", root / "backend" / "uploads"):
        if (
            _dir_has_content(legacy_uploads)
            and not _dir_has_content(target_uploads)
            and target_uploads.resolve() != legacy_uploads.resolve()
        ):
            _copy_dir(legacy_uploads, target_uploads)
            notes.append(f"已把旧附件目录 {legacy_uploads} 复制到 {target_uploads}")
            break

    # RAG vector store -------------------------------------------------------
    target_vs = Path(settings.vector_store_dir)
    for legacy_vs in (root / "backend" / "vector_store", root / "vector_store"):
        if (
            _dir_has_content(legacy_vs)
            and not _dir_has_content(target_vs)
            and target_vs.resolve() != legacy_vs.resolve()
        ):
            _copy_dir(legacy_vs, target_vs)
            notes.append(f"已把旧检索索引 {legacy_vs} 复制到 {target_vs}")
            break

    return notes
