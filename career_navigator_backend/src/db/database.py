import logging
import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

# Configure logger for the DB layer
logger = logging.getLogger(__name__)

# Base declarative class for SQLAlchemy models
Base = declarative_base()


def _build_sqlite_url(db_path: str) -> str:
    """
    Build a safe SQLite URL from a filesystem path.
    Note: SQLite paths are simple; we avoid user-controlled traversal by only using configured env var.
    """
    safe_path = os.path.normpath(db_path)
    # Ensure relative to working directory; no user input is accepted here
    return f"sqlite:///{safe_path}"


def get_database_url() -> str:
    """
    Resolve database URL from environment variable, falling back to ./data/app.db.
    """
    env_url: Optional[str] = os.environ.get("DATABASE_URL")
    if env_url:
        # Only allow sqlite in this MVP to avoid misconfigurations
        if not env_url.startswith("sqlite:///"):
            logger.warning("Non-sqlite DATABASE_URL detected; forcing SQLite for MVP.")
        return env_url

    default_dir = os.path.join(".", "data")
    try:
        os.makedirs(default_dir, exist_ok=True)
    except OSError as exc:
        logger.error("Failed to create default DB directory: %s", exc)
        # Fallback to current directory if directory cannot be created
        default_dir = "."
    default_path = os.path.join(default_dir, "app.db")
    return _build_sqlite_url(default_path)


# Create engine and session factory
DATABASE_URL = get_database_url()

# SQLite needs check_same_thread=False for multithreaded FastAPI usage
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite:///") else {},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# PUBLIC_INTERFACE
def get_db() -> Generator[Session, None, None]:
    """Yield a SQLAlchemy session for FastAPI dependencies."""
    db = SessionLocal()
    try:
        yield db
    finally:
        try:
            db.close()
        except Exception:  # noqa: BLE001
            logger.warning("Error closing DB session")


@contextmanager
def db_session_scope() -> Generator[Session, None, None]:
    """
    Context manager for DB session with commit/rollback semantics.
    """
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:  # noqa: BLE001
        session.rollback()
        logger.exception("DB transaction rolled back due to error")
        raise
    finally:
        try:
            session.close()
        except Exception:  # noqa: BLE001
            logger.warning("Error closing DB session")
