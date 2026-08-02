"""Database engine and session management."""
import logging

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.schema import CreateIndex

from .config import get_settings

logger = logging.getLogger("laserclaw.database")

settings = get_settings()

engine_kwargs = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs.update({"pool_size": 10, "max_overflow": 20})

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def _add_column_ddl(bind, table, column) -> str | None:
    """Emit ADD COLUMN for one column, exactly as ``create_all`` would spell it.

    The one exception is the DEFAULT clause: SQLite refuses a non-constant
    default (``CURRENT_TIMESTAMP``, any parenthesised expression) in ADD COLUMN,
    even though it accepts the same default in CREATE TABLE. Rather than encode
    each dialect's rules, the statement is offered as written and retried
    without the default if the database rejects it — and the fact that existing
    and future rows will see NULL there is logged, not hidden.
    """
    compiler = bind.dialect.ddl_compiler(bind.dialect, None)
    spec = compiler.get_column_specification(column)
    ddl = f"ALTER TABLE {table.name} ADD COLUMN {spec}"
    try:
        with bind.begin() as conn:
            conn.execute(text(ddl))
        return ddl
    except (OperationalError, ProgrammingError):
        if " DEFAULT " not in spec.upper():
            raise
        bare = spec[:spec.upper().index(" DEFAULT ")]
        ddl = f"ALTER TABLE {table.name} ADD COLUMN {bare}"
        with bind.begin() as conn:
            conn.execute(text(ddl))
        # No "run alembic" advice here: a create_all-managed database has no
        # alembic_version stamp, so `alembic upgrade head` would replay 0001
        # and die on the first existing table — a dead end for the launcher
        # user this path serves.
        logger.warning(
            "%s.%s was added without its default (this database does not allow "
            "one in ALTER TABLE); existing and new rows read NULL there. "
            "Harmless for optional columns; if values are needed, back up and "
            "recreate the database, or manage it with Alembic from the start.",
            table.name, column.name,
        )
        return ddl


def sync_additive_schema(bind=None) -> list[str]:
    """Add columns/indexes that models declare but an existing database lacks.

    ``Base.metadata.create_all`` creates missing *tables* and nothing else, so a
    release that adds a column to a table the user already has leaves their
    database one column short and every query against it raises
    ``no such column``. The one-click launcher runs on ``create_all``
    (``AUTO_CREATE_TABLES=true``, no Alembic), so without this the first upgrade
    would brick an install that already holds the lab's imported inventory.

    Deliberately additive only — new nullable/defaulted columns and new indexes.
    Type changes, drops, renames and data backfills are Alembic's job and are
    reported here rather than attempted. Alembic stays authoritative for the
    Docker/production path, where ``AUTO_CREATE_TABLES`` is false.

    ``bind`` defaults to the application engine; tests pass their own.
    Returns the DDL statements applied, for logging and tests.
    """
    bind = bind if bind is not None else engine
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())
    applied: list[str] = []

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all just made it, or will
        have = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in have:
                continue
            if not column.nullable and column.default is None and column.server_default is None:
                # SQLite cannot add a NOT NULL column without a default, and
                # guessing a value would fabricate data. Say so instead — and
                # do NOT say "run alembic": a create_all database has no
                # alembic_version stamp, so upgrading from 0001 would fail on
                # the first already-existing table.
                logger.warning(
                    "%s.%s is NOT NULL with no default and cannot be added "
                    "automatically. Back up the database file and let the app "
                    "recreate it, or restore from an Alembic-managed copy.",
                    table.name, column.name,
                )
                continue
            ddl = _add_column_ddl(bind, table, column)
            if ddl:
                applied.append(ddl)

        have_indexes = {idx["name"] for idx in inspector.get_indexes(table.name)}
        for index in table.indexes:
            if index.name in have_indexes:
                continue
            # An index on a column that was just added; without it the new
            # filters work but scan the whole table.
            with bind.begin() as conn:
                conn.execute(CreateIndex(index))
            applied.append(f"CREATE INDEX {index.name}")

    if applied:
        logger.info("Schema reconciled with %d additive change(s): %s",
                    len(applied), "; ".join(applied))
    return applied


def get_db():
    """Yield a database session for FastAPI dependencies."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Discard any partial, uncommitted writes so the connection is not
        # returned to the pool mid-transaction with a poisoned state.
        db.rollback()
        raise
    finally:
        db.close()
