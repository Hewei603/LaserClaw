"""Legacy in-tree data must be copied to the external data directory exactly once.

The dangerous failure modes are silent: overwriting real data with stale in-tree
leftovers after an update, or re-copying on every start and resurrecting deleted
records. Every test here pins the "only fill an empty target, never touch a
populated one" contract.
"""
from types import SimpleNamespace

from app.data_migration import migrate_legacy_data


def make_settings(tmp_path, data_dir):
    return SimpleNamespace(
        database_url=f"sqlite:///{(data_dir / 'laserclaw.db').as_posix()}",
        upload_dir=str(data_dir / "uploads"),
        vector_store_dir=str(data_dir / "vector_store"),
    )


def make_legacy_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    (repo / "backend" / "laserclaw.db").write_bytes(b"legacy-db")
    (repo / "uploads").mkdir()
    (repo / "uploads" / "a.png").write_bytes(b"img")
    (repo / "backend" / "vector_store").mkdir()
    (repo / "backend" / "vector_store" / "index.bin").write_bytes(b"idx")
    return repo


def test_copies_all_three_when_target_empty(tmp_path):
    repo = make_legacy_repo(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    settings = make_settings(tmp_path, data_dir)

    notes = migrate_legacy_data(settings, repo_root=repo)

    assert (data_dir / "laserclaw.db").read_bytes() == b"legacy-db"
    assert (data_dir / "uploads" / "a.png").read_bytes() == b"img"
    assert (data_dir / "vector_store" / "index.bin").read_bytes() == b"idx"
    assert len(notes) == 3
    # Copy, not move: legacy files stay behind as a backup.
    assert (repo / "backend" / "laserclaw.db").exists()


def test_never_overwrites_populated_target(tmp_path):
    repo = make_legacy_repo(tmp_path)
    data_dir = tmp_path / "data"
    (data_dir / "uploads").mkdir(parents=True)
    (data_dir / "laserclaw.db").write_bytes(b"current-db")
    (data_dir / "uploads" / "b.png").write_bytes(b"current-img")
    settings = make_settings(tmp_path, data_dir)

    migrate_legacy_data(settings, repo_root=repo)

    # The populated target is the source of truth; stale in-tree data must not
    # resurrect over it after an update.
    assert (data_dir / "laserclaw.db").read_bytes() == b"current-db"
    assert not (data_dir / "uploads" / "a.png").exists()


def test_second_run_is_a_no_op(tmp_path):
    repo = make_legacy_repo(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    settings = make_settings(tmp_path, data_dir)

    first = migrate_legacy_data(settings, repo_root=repo)
    second = migrate_legacy_data(settings, repo_root=repo)

    assert len(first) == 3
    assert second == []


def test_no_legacy_data_is_a_no_op(tmp_path):
    repo = tmp_path / "repo"
    (repo / "backend").mkdir(parents=True)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    settings = make_settings(tmp_path, data_dir)

    assert migrate_legacy_data(settings, repo_root=repo) == []
    assert not (data_dir / "laserclaw.db").exists()


def test_memory_and_postgres_urls_skip_db_copy(tmp_path):
    repo = make_legacy_repo(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for url in ("sqlite://", "sqlite:///:memory:", "postgresql://u:p@host/db"):
        settings = SimpleNamespace(
            database_url=url,
            upload_dir=str(data_dir / "uploads"),
            vector_store_dir=str(data_dir / "vector_store"),
        )
        notes = migrate_legacy_data(settings, repo_root=repo)
        assert all("数据库" not in n for n in notes)


def test_interrupted_copy_leaves_no_wedge(tmp_path):
    """Staging debris from a killed copy must be cleaned and re-copied.

    The dangerous wedge: a half-written file under the FINAL name would make
    the "target exists" guard treat garbage as the source of truth forever.
    With staging + atomic rename, an interruption leaves only *.copying files,
    which the next start deletes and redoes.
    """
    repo = make_legacy_repo(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # simulate a copy killed halfway: staging debris, target absent
    (data_dir / "laserclaw.db.copying").write_bytes(b"half")
    (data_dir / "uploads.copying").mkdir()
    (data_dir / "uploads.copying" / "partial.png").write_bytes(b"x")
    settings = make_settings(tmp_path, data_dir)

    migrate_legacy_data(settings, repo_root=repo)

    assert (data_dir / "laserclaw.db").read_bytes() == b"legacy-db"
    assert (data_dir / "uploads" / "a.png").read_bytes() == b"img"
    assert not (data_dir / "laserclaw.db.copying").exists()
    assert not (data_dir / "uploads.copying").exists()


def test_both_upload_candidates_merge(tmp_path):
    repo = make_legacy_repo(tmp_path)
    (repo / "backend" / "uploads").mkdir()
    (repo / "backend" / "uploads" / "b.png").write_bytes(b"img2")
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    settings = make_settings(tmp_path, data_dir)

    migrate_legacy_data(settings, repo_root=repo)

    # Neither historical location is silently dropped.
    assert (data_dir / "uploads" / "a.png").read_bytes() == b"img"
    assert (data_dir / "uploads" / "b.png").read_bytes() == b"img2"


def test_target_equal_to_legacy_is_untouched(tmp_path):
    """Manual runs (uvicorn from backend/) still point at the in-tree db."""
    repo = make_legacy_repo(tmp_path)
    settings = SimpleNamespace(
        database_url=f"sqlite:///{(repo / 'backend' / 'laserclaw.db').as_posix()}",
        upload_dir=str(repo / "uploads"),
        vector_store_dir=str(repo / "backend" / "vector_store"),
    )
    assert migrate_legacy_data(settings, repo_root=repo) == []
