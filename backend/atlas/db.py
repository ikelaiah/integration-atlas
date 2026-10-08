"""Engine and session management.

Sync SQLAlchemy keeps the mental model simple. FastAPI runs these in a normal
threadpool dependency; the CLI uses them directly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event, inspect
from sqlalchemy.orm import Session, sessionmaker

from atlas.config import get_settings
from atlas.models import Base

#: Idempotent column additions for databases created before a schema change.
#: ``(table, column, DDL)``. Existing rows receive the column default, so data
#: (including manual knowledge) is preserved.
_SCHEMA_ADDITIONS: tuple[tuple[str, str, str], ...] = (
    (
        "entities",
        "is_active",
        "ALTER TABLE entities ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1",
    ),
    (
        "entities",
        "manual_fields_json",
        "ALTER TABLE entities ADD COLUMN manual_fields_json JSON DEFAULT '[]'",
    ),
    (
        "relationships",
        "is_active",
        "ALTER TABLE relationships ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT 1",
    ),
)


def migrate_schema(engine: Engine) -> list[str]:
    """Add columns introduced after a database was first created.

    ``Base.metadata.create_all`` only creates *missing tables*; it never alters
    an existing one. This walks the known additions and applies the ones a
    database is missing, preserving all existing rows. It is safe to run on a
    fresh database (everything is already present) and on a database that has
    been migrated before (nothing to do).
    """
    if engine.dialect.name != "sqlite":
        return []
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    applied: list[str] = []
    for table, column, ddl in _SCHEMA_ADDITIONS:
        if table not in tables:
            continue
        columns = {c["name"] for c in inspector.get_columns(table)}
        if column in columns:
            continue
        with engine.begin() as conn:
            conn.exec_driver_sql(ddl)
        applied.append(f"{table}.{column}")
    return applied

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _configure_sqlite(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return

    @event.listens_for(engine, "connect")
    def _set_pragmas(dbapi_connection, _connection_record):  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


def get_engine(url: str | None = None) -> Engine:
    global _engine, _session_factory
    if _engine is None or url is not None:
        resolved = url or get_settings().resolved_database_url()
        _engine = create_engine(
            resolved,
            future=True,
            echo=False,
            connect_args={"check_same_thread": False} if resolved.startswith("sqlite") else {},
        )
        _configure_sqlite(_engine)
        _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        get_engine()
    assert _session_factory is not None
    return _session_factory


def _migrate_fingerprints(engine: Engine) -> None:
    """Re-key legacy server-scoped fingerprints in place.

    Called from :func:`init_db` so an existing database is upgraded before any
    scan reconciles against it. Idempotent and data-preserving: manual fields,
    evidence and relationships are untouched.
    """
    from atlas.demo.seeder import upgrade_legacy_fingerprints

    session = get_session_factory()()
    try:
        upgrade_legacy_fingerprints(session)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db(url: str | None = None) -> Engine:
    engine = get_engine(url)
    Base.metadata.create_all(engine)
    migrate_schema(engine)
    _migrate_fingerprints(engine)
    return engine


def reset_engine() -> None:
    """Drop cached engine/session factory (used by tests)."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


@contextmanager
def session_scope() -> Iterator[Session]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
