# -*- coding: utf-8 -*-
"""The one-click launcher runs on ``create_all``, never Alembic.

``create_all`` creates missing tables and stops there, so every release that
adds a column to an existing table would otherwise leave an already-installed
lab with a database one column short — and `no such column` on every query
against it. The upgrade path for that user is therefore
``sync_additive_schema``, and these tests are what keep it honest.
"""
import sqlalchemy as sa

from app import models  # noqa: F401 - register every model with Base.metadata
from app.database import Base, sync_additive_schema


def _old_release_database(bind):
    """Build a database, then remove recently-added columns to age it.

    Two columns per table where possible — the last nullable one and the last
    *indexed* nullable one — because an index is dropped with its column and a
    fixture that never removes one would let a broken index path pass.

    Returns ``(removed_columns, removed_indexes)``.
    """
    Base.metadata.create_all(bind=bind)
    removed_columns, removed_indexes = [], []
    inspector = sa.inspect(bind)
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            droppable = [c for c in table.columns
                         if c.nullable and not c.primary_key and not c.foreign_keys]
            if not droppable:
                continue
            indexed = [c for c in droppable if c.index]
            # Stand-ins for "whatever the newest release added to this table".
            targets = {droppable[-1].name: droppable[-1]}
            if indexed:
                targets[indexed[-1].name] = indexed[-1]
            for column in targets.values():
                for index in inspector.get_indexes(table.name):
                    if column.name in index["column_names"]:
                        conn.execute(sa.text(f'DROP INDEX "{index["name"]}"'))
                        removed_indexes.append((table.name, index["name"]))
                conn.execute(sa.text(f'ALTER TABLE {table.name} DROP COLUMN "{column.name}"'))
                removed_columns.append((table.name, column.name))
    return removed_columns, removed_indexes


def test_every_model_column_exists_after_the_upgrade(tmp_path):
    """Asserted over all tables rather than the one column of the day.

    A per-column test only protects the column someone remembered to write it
    for; this one fails for any future model change the upgrade path misses.
    """
    bind = sa.create_engine(f"sqlite:///{tmp_path / 'aged.db'}")
    removed, _ = _old_release_database(bind)
    assert removed, "the fixture must actually age the database"

    aged = sa.inspect(bind)
    for table_name, column_name in removed:
        have = {c["name"] for c in aged.get_columns(table_name)}
        assert column_name not in have, "fixture failed to remove the column"

    sync_additive_schema(bind=bind)

    upgraded = sa.inspect(bind)
    for table in Base.metadata.sorted_tables:
        have = {c["name"] for c in upgraded.get_columns(table.name)}
        missing = {c.name for c in table.columns} - have
        assert not missing, f"{table.name} still missing {sorted(missing)} after upgrade"


def test_indexes_come_back_too(tmp_path):
    """A restored column without its index reads as fixed but scans the table."""
    bind = sa.create_engine(f"sqlite:///{tmp_path / 'aged.db'}")
    _, dropped_indexes = _old_release_database(bind)
    assert dropped_indexes, "vacuous otherwise: the fixture must drop an index"

    sync_additive_schema(bind=bind)

    upgraded = sa.inspect(bind)
    for table in Base.metadata.sorted_tables:
        have = {idx["name"] for idx in upgraded.get_indexes(table.name)}
        missing = {idx.name for idx in table.indexes} - have
        assert not missing, f"{table.name} still missing indexes {sorted(missing)}"


def test_the_aged_database_is_usable_afterwards(tmp_path):
    """The column has to be queryable, not merely present in the catalogue."""
    bind = sa.create_engine(f"sqlite:///{tmp_path / 'aged.db'}")
    Base.metadata.create_all(bind=bind)
    with bind.begin() as conn:
        conn.execute(sa.text('DROP INDEX "ix_inventory_items_condition_manual"'))
        conn.execute(sa.text('ALTER TABLE inventory_items DROP COLUMN "condition_manual"'))
        conn.execute(sa.text(
            "INSERT INTO inventory_items (category, name, quantity) VALUES ('mirror', '腔镜', 1)"
        ))

    sync_additive_schema(bind=bind)

    from sqlalchemy.orm import sessionmaker
    session = sessionmaker(bind=bind)()
    try:
        item = session.query(models.InventoryItem).first()
        assert item.condition_manual is None, "pre-existing rows get NULL, not a guess"
        assert item.effective_condition == "ok"
        assert item.name == "腔镜", "the lab's existing data must survive the upgrade"
    finally:
        session.close()


def test_a_not_null_column_is_reported_rather_than_faked(tmp_path, caplog):
    """Adding a NOT NULL column needs a real backfill decision, so it must not
    be invented here — SQLite would reject it and a fabricated default would be
    wrong data. The user gets told to run Alembic instead."""
    metadata = sa.MetaData()
    sa.Table("widgets", metadata,
             sa.Column("id", sa.Integer, primary_key=True),
             sa.Column("label", sa.String(50)))
    bind = sa.create_engine(f"sqlite:///{tmp_path / 'nn.db'}")
    metadata.create_all(bind=bind)

    grown = sa.MetaData()
    sa.Table("widgets", grown,
             sa.Column("id", sa.Integer, primary_key=True),
             sa.Column("label", sa.String(50)),
             sa.Column("owner", sa.String(50), nullable=False))

    applied = _sync_with_metadata(grown, bind, caplog)

    assert applied == [], "must not invent a value for a NOT NULL column"
    assert any("alembic" in record.message.lower() for record in caplog.records)


def _sync_with_metadata(metadata, bind, caplog):
    """Run the reconciliation against a stand-in metadata, not the app's."""
    import logging

    from app import database

    caplog.set_level(logging.WARNING, logger="laserclaw.database")
    real = database.Base.metadata
    try:
        database.Base.metadata = metadata
        return database.sync_additive_schema(bind=bind)
    finally:
        database.Base.metadata = real
