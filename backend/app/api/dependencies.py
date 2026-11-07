"""Shared request-scoped API dependencies."""

from collections.abc import Generator

from fastapi import Request
from sqlalchemy.orm import Session

from app.errors import AppError


def get_database_session(request: Request) -> Generator[Session, None, None]:
    """Yield a request-scoped database session or a safe not-configured error."""
    session_factory = request.app.state.session_factory
    if session_factory is None:
        raise AppError(503, "DATABASE_NOT_CONFIGURED")

    with session_factory() as session:
        yield session
