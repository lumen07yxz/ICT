"""Database engine construction from explicit environment configuration."""

import os

from sqlalchemy import Engine, create_engine, event


def build_engine(database_url: str | None = None) -> Engine:
    """Build a SQLAlchemy engine without logging or exposing database credentials."""
    resolved_url = database_url or os.environ.get("DATABASE_URL", "").strip()
    if not resolved_url:
        raise RuntimeError("DATABASE_URL is required to connect to the application database")

    options: dict[str, object] = {"pool_pre_ping": True}
    if resolved_url.startswith("sqlite:"):
        # SQLite is for isolated tests and local prototyping; deployment uses PostgreSQL.
        options["connect_args"] = {"check_same_thread": False}

    engine = create_engine(resolved_url, **options)
    if resolved_url.startswith("sqlite:"):
        @event.listens_for(engine, "connect")
        def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
            """Make SQLite honor the ownership and lifecycle constraints in the schema."""
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys = ON")
            finally:
                cursor.close()

    return engine
