"""FastAPI entry point for the synthetic demo and project access API."""

from contextlib import asynccontextmanager
import logging
import os
import time
from collections.abc import Callable, Mapping
from uuid import UUID, uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.demo import router as demo_router
from app.api.v1.projects import router as projects_router
from app.api.v1.reproductions import router as reproductions_router
from app.api.v1.run_proposals import router as run_proposals_router
from app.api.v1.runs import router as runs_router
from app.api.v1.templates import router as templates_router
from app.api.v1.workflows import router as workflows_router
from app.db.session import build_engine
from app.errors import AppError
from app.services.demo_catalog import DemoProjectNotAllowed


logger = logging.getLogger("ict.api")
# Keep structured request and exception logs visible in normal service processes.
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
logger.propagate = False


SessionFactory = Callable[[], Session]


def _dispatch_run(run_id: UUID) -> None:
    """Load Celery only when an operator actually approves a task."""
    from app.worker import enqueue_run

    enqueue_run(run_id)


def create_app(
    *,
    session_factory: SessionFactory | sessionmaker[Session] | None = None,
    auth_tokens: Mapping[str, str | None] | None = None,
    internal_api_key: str | None = None,
    run_dispatcher: Callable[[UUID], None] | None = None,
) -> FastAPI:
    """Build an app with optional test dependencies and environment configuration."""
    database_engine = None
    if session_factory is None:
        database_url = os.environ.get("DATABASE_URL", "").strip()
        if database_url:
            database_engine = build_engine(database_url)
            session_factory = sessionmaker(
                bind=database_engine,
                autoflush=False,
                expire_on_commit=False,
            )

    if auth_tokens is None:
        auth_tokens = {
            "operator": os.environ.get("DEMO_OPERATOR_TOKEN"),
            "viewer": os.environ.get("DEMO_VIEWER_TOKEN"),
        }
    if internal_api_key is None:
        internal_api_key = os.environ.get("ICT_INTERNAL_API_KEY")
    normalized_internal_key = (
        internal_api_key.strip() if internal_api_key and internal_api_key.strip() else None
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        try:
            yield
        finally:
            if database_engine is not None:
                database_engine.dispose()

    app = FastAPI(title="ICT Research API", version="0.10.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.database_engine = database_engine
    app.state.demo_tokens = auth_tokens
    app.state.internal_api_key = normalized_internal_key
    app.state.run_dispatcher = run_dispatcher or _dispatch_run
    app.include_router(demo_router)
    app.include_router(projects_router)
    app.include_router(reproductions_router)
    app.include_router(templates_router)
    app.include_router(workflows_router)
    app.include_router(run_proposals_router)
    app.include_router(runs_router)

    @app.middleware("http")
    async def audit_request(request: Request, call_next):
        """Log request ID, route template, status, and duration without headers/body."""
        request_id = uuid4().hex
        request.state.request_id = request_id
        started = time.monotonic()

        try:
            response = await call_next(request)
        except Exception:
            route = request.scope.get("route")
            route_name = route.path if route is not None else "<unmatched>"
            logger.exception(
                "request_failed request_id=%s method=%s route=%s status=500",
                request_id,
                request.method,
                route_name,
            )
            response = JSONResponse(
                status_code=500,
                content={"error": {"code": "INTERNAL_ERROR", "request_id": request_id}},
            )

        route = request.scope.get("route")
        route_name = route.path if route is not None else "<unmatched>"
        elapsed_ms = round((time.monotonic() - started) * 1000)
        logger.info(
            "request_complete request_id=%s method=%s route=%s status=%s duration_ms=%s",
            request_id,
            request.method,
            route_name,
            response.status_code,
            elapsed_ms,
        )
        response.headers["x-request-id"] = request_id
        return response

    @app.exception_handler(AppError)
    async def app_error(request: Request, exc: AppError):
        """Expose stable errors without revealing tokens, SQL, or object existence."""
        request_id = getattr(request.state, "request_id", "")
        logger.warning(
            "request_rejected request_id=%s error_code=%s status=%s",
            request_id,
            exc.code,
            exc.status_code,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "request_id": request_id}},
        )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, _exc: RequestValidationError):
        """Return a stable validation code without echoing submitted values."""
        request_id = getattr(request.state, "request_id", "")
        logger.warning(
            "request_rejected request_id=%s error_code=INVALID_REQUEST status=422",
            request_id,
        )
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "INVALID_REQUEST", "request_id": request_id}},
        )

    @app.exception_handler(DemoProjectNotAllowed)
    async def project_not_allowed(request: Request, _exc: DemoProjectNotAllowed):
        """Reject unknown demo projects without echoing their identifiers."""
        request_id = getattr(request.state, "request_id", "")
        logger.warning("request_rejected request_id=%s error_code=PROJECT_NOT_ALLOWED", request_id)
        return JSONResponse(
            status_code=404,
            content={"error": {"code": "PROJECT_NOT_ALLOWED", "request_id": request_id}},
        )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Report process liveness without claiming database or research readiness."""
        return {"status": "ok", "mode": "synthetic_demo"}

    return app


app = create_app()
