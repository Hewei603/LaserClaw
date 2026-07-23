"""Database engine and session management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import get_settings

settings = get_settings()

engine_kwargs = {"pool_pre_ping": True}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs.update({"pool_size": 10, "max_overflow": 20})

engine = create_engine(settings.database_url, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


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
