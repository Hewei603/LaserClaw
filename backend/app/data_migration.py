"""One-time copy of experiment data out of the code tree.

Versions before 2.1 stored everything inside the repository — the database at
``backend/laserclaw.db``, attachments in ``<repo>/uploads``, the RAG index in
``<repo>/backend/vector_store``. A user whose idea of "updating" is re-downloading
the folder (the realistic path for a user with no software background) would
silently lose all of it. The launcher now points ``DATABASE_URL`` / ``UPLOAD_DIR``
/ ``VECTOR_STORE_DIR`` at ``%USERPROFILE%\\LaserClaw-Data``; this module copies the
legacy data there the first time the new location is empty.

Copy, never move — and never through the final name: everything is copied to a
``*.copying`` staging name first and atomically renamed into place. A user
closing the console window mid-copy (the documented way to stop LaserClaw)
therefore leaves only staging debris, which is deleted and re-copied on the
next start; the "target exists → it is the source of truth" guard can never be
fooled by a half-written file.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

_SQLITE_PREFIX = "sqlite:///"
_STAGING_SUFFIX = ".copying"


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


def _clear_stale_staging(target: Path) -> None:
    stale = target.parent / (target.name + _STAGING_SUFFIX)
    if stale.is_dir():
        shutil.rmtree(stale, ignore_errors=True)
    elif stale.exists():
        stale.unlink(missing_ok=True)


def _copy_dir(legacy: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for entry in legacy.iterdir():
        dest = target / entry.name
        if entry.is_dir():
            shutil.copytree(entry, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(entry, dest)


def _atomic_dir_migrate(sources: list[Path], target: Path) -> None:
    """Copy source dirs into a staging dir, then rename it into place."""
    staging = target.parent / (target.name + _STAGING_SUFFIX)
    if staging.exists():
        shutil.rmtree(staging)
    for src in sources:
        _copy_dir(src, staging)
    # The guard upstream ensured the target has no content; an empty leftover
    # directory would still make os.replace fail on Windows, so drop it.
    if target.is_dir() and not any(target.iterdir()):
        target.rmdir()
    os.replace(staging, target)


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
    if target_db is not None:
        _clear_stale_staging(target_db)
        if (
            not target_db.exists()
            and legacy_db.is_file()
            and target_db.resolve() != legacy_db.resolve()
        ):
            target_db.parent.mkdir(parents=True, exist_ok=True)
            staging = target_db.parent / (target_db.name + _STAGING_SUFFIX)
            shutil.copy2(legacy_db, staging)
            os.replace(staging, target_db)
            notes.append(f"已把旧数据库 {legacy_db} 复制到新的数据目录 {target_db}(旧文件保留作为备份)")

    # Uploaded attachments — both historical locations merge into one target.
    target_uploads = Path(settings.upload_dir)
    _clear_stale_staging(target_uploads)
    upload_sources = [
        legacy for legacy in (root / "uploads", root / "backend" / "uploads")
        if _dir_has_content(legacy) and target_uploads.resolve() != legacy.resolve()
    ]
    if upload_sources and not _dir_has_content(target_uploads):
        _atomic_dir_migrate(upload_sources, target_uploads)
        for legacy in upload_sources:
            notes.append(f"已把旧附件目录 {legacy} 复制到 {target_uploads}")

    # RAG vector store — first existing candidate only: the two locations are
    # alternative homes of the SAME index, and merging two indexes would
    # corrupt rather than complete it.
    target_vs = Path(settings.vector_store_dir)
    _clear_stale_staging(target_vs)
    for legacy_vs in (root / "backend" / "vector_store", root / "vector_store"):
        if (
            _dir_has_content(legacy_vs)
            and not _dir_has_content(target_vs)
            and target_vs.resolve() != legacy_vs.resolve()
        ):
            _atomic_dir_migrate([legacy_vs], target_vs)
            notes.append(f"已把旧检索索引 {legacy_vs} 复制到 {target_vs}")
            break

    return notes
