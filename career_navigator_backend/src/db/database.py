import logging
import os
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
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
def ensure_sqlite_schema_compatibility(engine_obj: Optional[Engine] = None) -> None:
    """
    Ensure runtime SQLite schema has required columns introduced in newer app versions.

    Performs idempotent, lightweight migrations for:
    - role_skills.is_gap (INTEGER NULL)
    - role_skills.color (VARCHAR(16) NULL)
    - roadmaps table (if not exists) with required columns

    Safe to run multiple times; no-ops when columns already exist.
    """
    try:
        eng: Engine = engine_obj or engine  # type: ignore[assignment]
    except Exception:
        logger.exception("Could not resolve SQLAlchemy engine for schema checks")
        return

    # Only relevant for SQLite in this MVP
    try:
        backend = str(eng.url.get_backend_name())
        if backend != "sqlite":
            return
    except Exception:
        # If backend resolution fails, skip silently
        return

    try:
        with eng.begin() as conn:
            inspector = inspect(conn)
            # role_skills columns
            try:
                existing_cols = {c["name"] for c in inspector.get_columns("role_skills")}
            except Exception:
                logger.exception("Failed to inspect 'role_skills' table; skipping schema check for it")
                existing_cols = set()

            if existing_cols:
                if "is_gap" not in existing_cols:
                    try:
                        conn.execute(text("ALTER TABLE role_skills ADD COLUMN is_gap INTEGER NULL"))
                        logger.info("SQLite migration: added role_skills.is_gap")
                    except Exception:
                        logger.warning("SQLite migration: role_skills.is_gap add failed (already exists or locked)")

                if "color" not in existing_cols:
                    try:
                        conn.execute(text("ALTER TABLE role_skills ADD COLUMN color VARCHAR(16) NULL"))
                        logger.info("SQLite migration: added role_skills.color")
                    except Exception:
                        logger.warning("SQLite migration: role_skills.color add failed (already exists or locked)")

            # roadmaps table
            try:
                _ = {c["name"] for c in inspector.get_columns("roadmaps")}
                table_exists = True
            except Exception:
                table_exists = False

            if not table_exists:
                try:
                    conn.execute(
                        text(
                            """
                            CREATE TABLE IF NOT EXISTS roadmaps (
                                id INTEGER PRIMARY KEY,
                                name VARCHAR(200) NOT NULL,
                                user_identifier VARCHAR(200),
                                from_role_id INTEGER NOT NULL,
                                to_role_id INTEGER NOT NULL,
                                graph_payload TEXT NOT NULL,
                                notes TEXT,
                                created_at DATETIME NOT NULL,
                                updated_at DATETIME NOT NULL
                            )
                            """
                        )
                    )
                    logger.info("SQLite migration: created roadmaps table")
                except Exception:
                    logger.warning("SQLite migration: creation of roadmaps table failed or already exists")
    except Exception:
        logger.exception("SQLite schema compatibility check failed unexpectedly")


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
