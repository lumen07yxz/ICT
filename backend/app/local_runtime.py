"""Standalone loopback runtime for offline workflow execution."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import unquote, urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from app.services.local_artifacts import LocalArtifactError, LocalArtifactStore
from app.services.local_csv_executor import (
    LOCAL_EXECUTOR_PERMISSION_CAPABILITIES,
    build_local_executor_registry,
    resolve_local_dependency_versions,
)
from app.services.network_crossref_executor import (
    CROSSREF_PERMISSION_CAPABILITIES,
    build_network_executor_registry,
    resolve_network_dependency_versions,
)
from app.services.local_execution_cache import build_cached_executor_registry
from app.services.local_resource_admission import (
    local_component_capability_blockers,
    network_component_capability_blockers,
    validate_local_plan_admission,
)
from app.services.local_runtime_store import LocalRuntimeStore, LocalRuntimeStoreError
from app.services.local_workflow_templates import (
    instantiate_local_workflow_template,
    list_local_workflow_templates,
)
from app.services.workflow_catalog import validate_workflow_component_contracts, validate_workflow_graph
from app.services.workflow_components import list_workflow_components
from app.services.workflow_execution import WorkflowCompilationError
from app.services.workflow_scheduler import execute_execution_plan


logger = logging.getLogger("ict.local_runtime.api")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
logger.propagate = False


class LocalWorkflowDraftWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    graph: dict[str, Any]
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=4000)


class LocalWorkflowNodePosition(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    x: float = Field(ge=-1_000_000, le=1_000_000)
    y: float = Field(ge=-1_000_000, le=1_000_000)


class LocalWorkflowNodeDocument(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=128)
    type: str = Field(min_length=1, max_length=80)
    position: LocalWorkflowNodePosition
    data: dict[str, Any] = Field(default_factory=dict)


class LocalWorkflowEdgeDocument(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    source_handle: str | None = Field(default=None, alias="sourceHandle", max_length=128)
    target_handle: str | None = Field(default=None, alias="targetHandle", max_length=128)
    type: str | None = Field(default=None, max_length=80)


class LocalWorkflowGraphDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["ict.workflow.v1"] = "ict.workflow.v1"
    nodes: list[LocalWorkflowNodeDocument] = Field(max_length=500)
    edges: list[LocalWorkflowEdgeDocument] = Field(max_length=2_000)

    @model_validator(mode="after")
    def bound_serialized_size(self) -> "LocalWorkflowGraphDocument":
        if len(self.model_dump_json(by_alias=True).encode("utf-8")) > 2_000_000:
            raise ValueError("workflow graph exceeds the 2 MB limit")
        return self


class LocalWorkflowValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: int = Field(ge=1)
    graph: LocalWorkflowGraphDocument


class LocalProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    domain: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=4000)

    @field_validator("name", "domain")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class LocalWorkflowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=4000)

    @field_validator("name")
    @classmethod
    def trim_required_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized


class LocalWorkflowTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(min_length=1, max_length=120)
    version: str = Field(min_length=1, max_length=40)


class LocalReproductionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    kind: Literal["paper", "experiment"]
    source: str = Field(default="", max_length=20_000)
    claim: str = Field(default="", max_length=20_000)
    baseline: dict[str, Any] | None = None
    criteria_version: str | None = Field(default=None, max_length=64)
    linked_project_id: str | None = Field(default=None, max_length=128)

    @field_validator("title")
    @classmethod
    def trim_required_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @model_validator(mode="after")
    def bound_baseline_size(self) -> "LocalReproductionCreate":
        """Bound the task's JSON baseline before it reaches the local store."""
        if self.baseline is not None and len(
            json.dumps(self.baseline, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ) > 64_000:
            raise ValueError("baseline metadata exceeds the 64 KB limit")
        return self


class LocalProjectSyncStateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "partial", "synced", "failed", "conflict", "needs_review"]
    platform_project_id: str | None = Field(default=None, max_length=128)
    error_code: str | None = Field(default=None, max_length=80)


class LocalProjectSyncStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_pending_retry: bool = False


class LocalWorkflowSyncStateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["pending", "synced", "failed", "conflict", "needs_review"]
    platform_workflow_id: str | None = Field(default=None, max_length=128)
    synced_revision: int | None = Field(default=None, ge=1)
    source_revision: int | None = Field(default=None, ge=1)
    error_code: str | None = Field(default=None, max_length=80)


class LocalRunSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_node_ids: list[str] = Field(min_length=1, max_length=500)


def _verified_recovery_outputs(
    outputs: dict[str, Any], artifact_store: LocalArtifactStore
) -> dict[str, Any]:
    """Keep only persisted node outputs whose embedded local artifact handles still match disk."""
    verified_handles: dict[tuple[str, str], bool] = {}

    def output_artifacts_valid(value: Any) -> bool:
        if isinstance(value, list):
            return all(output_artifacts_valid(item) for item in value)
        if not isinstance(value, dict):
            return True
        artifact_id = value.get("artifact_id")
        if artifact_id is not None:
            expected_digest = value.get("sha256")
            if not isinstance(artifact_id, str) or not isinstance(expected_digest, str):
                return False
            key = (artifact_id, expected_digest.lower())
            valid = verified_handles.get(key)
            if valid is None:
                try:
                    resolved = artifact_store.resolve(artifact_id)
                    if resolved.handle.sha256.lower() != expected_digest.lower():
                        valid = False
                    else:
                        digest = hashlib.sha256()
                        with resolved.path.open("rb") as source:
                            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                                digest.update(chunk)
                        valid = digest.hexdigest() == expected_digest.lower()
                except (LocalArtifactError, OSError):
                    valid = False
                verified_handles[key] = valid
            if not valid:
                return False
        return all(output_artifacts_valid(child) for child in value.values())

    accepted: dict[str, Any] = {}
    for node_id, output in outputs.items():
        if output_artifacts_valid(output):
            accepted[node_id] = output
        else:
            logger.warning("local_workflow_recovery_output_rejected node_id=%s", node_id)
    return accepted


def create_local_runtime_app(
    *,
    root: Path | None = None,
    max_artifact_bytes: int = 100 * 1024 * 1024,
    allowed_origins: set[str] | None = None,
    static_dir: Path | None = None,
) -> FastAPI:
    """Build a loopback-only runtime, optionally serving its packaged desktop UI."""
    configured_root = root if root is not None else os.environ.get(
        "ICT_LOCAL_RUNTIME_DIR", Path.home() / ".ict" / "runtime"
    )
    runtime_root = Path(configured_root).expanduser().resolve()
    artifact_store = LocalArtifactStore(runtime_root, max_artifact_bytes=max_artifact_bytes)
    run_store = LocalRuntimeStore(runtime_root)
    frontend_root = Path(static_dir).expanduser().resolve() if static_dir is not None else None
    if frontend_root is not None and not (frontend_root / "index.html").is_file():
        raise FileNotFoundError(f"Frontend bundle is missing index.html: {frontend_root}")
    origins = allowed_origins or {
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    }

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        run_store.mark_incomplete_runs_failed()
        yield
        tasks: dict[str, asyncio.Task[None]] = _app.state.active_runs
        if tasks:
            for task in tasks.values():
                task.cancel()
            await asyncio.gather(*tasks.values(), return_exceptions=True)

    app = FastAPI(title="ICT Local Workflow Runtime", version="0.1.0", lifespan=lifespan)
    app.state.artifact_store = artifact_store
    app.state.run_store = run_store
    app.state.active_runs = {}
    app.state.max_active_runs = 2
    app.state.max_node_concurrency = 2
    app.state.network_request_semaphore = asyncio.Semaphore(1)
    app.state.local_sessions = {}
    app.state.frontend_served = frontend_root is not None
    app.add_middleware(
        CORSMiddleware,
        allow_origins=sorted(origins),
        # Local preview/dev ports may vary; browser access still requires a loopback
        # origin and the middleware below independently enforces a loopback Host.
        allow_origin_regex=r"^http://(?:127\.0\.0\.1|localhost):[0-9]{1,5}$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-ICT-Local-Token",
            "X-Artifact-File-Name",
            "X-ICT-Local-Consent",
        ],
        max_age=300,
    )

    @app.middleware("http")
    async def enforce_loopback_boundary(request: Request, call_next):
        hostname = (request.url.hostname or "").lower()
        if hostname not in {"127.0.0.1", "localhost", "::1"}:
            return JSONResponse(status_code=403, content={"error": {"code": "LOOPBACK_HOST_REQUIRED"}})
        origin = request.headers.get("origin")
        is_configured_origin = origin in origins if origin is not None else True
        is_loopback_origin = False
        if origin is not None and not is_configured_origin:
            try:
                # Dev servers and desktop shells may choose another port; trust only HTTP loopback origins.
                parsed_origin = urlsplit(origin)
                origin_port = parsed_origin.port
                is_loopback_origin = (
                    parsed_origin.scheme == "http"
                    and parsed_origin.hostname in {"127.0.0.1", "localhost"}
                    and origin_port is not None
                    and 1 <= origin_port <= 65535
                    and parsed_origin.username is None
                    and parsed_origin.password is None
                    and not parsed_origin.path
                    and not parsed_origin.query
                    and not parsed_origin.fragment
                )
            except ValueError:
                is_loopback_origin = False
        if origin is not None and not (is_configured_origin or is_loopback_origin):
            return JSONResponse(status_code=403, content={"error": {"code": "LOCAL_ORIGIN_REJECTED"}})
        return await call_next(request)

    async def require_local_auth(request: Request) -> None:
        supplied = request.headers.get("X-ICT-Local-Token", "")
        session = request.app.state.local_sessions.get(supplied)
        if session is None or session["expires_at"] <= time.monotonic():
            logger.warning(
                "local_runtime_auth_rejected reason=session_missing_or_expired method=%s path=%s",
                request.method,
                request.url.path,
            )
            raise LocalRuntimeStoreError("LOCAL_RUNTIME_UNAUTHORIZED", "本机运行凭据无效。", status_code=401)
        session_origin = session["origin"]
        request_origin = request.headers.get("origin")
        if session_origin is None:
            return
        if request_origin is None:
            # Same-origin GETs omit Origin; accept only browser-marked requests whose URL matches the session origin.
            request_url_origin = f"{request.url.scheme}://{request.url.netloc}"
            is_same_origin_fetch = request.headers.get("sec-fetch-site") == "same-origin"
            if is_same_origin_fetch and request_url_origin == session_origin:
                return
            logger.warning(
                "local_runtime_auth_rejected reason=origin_missing_or_unverified method=%s path=%s fetch_site=%s",
                request.method,
                request.url.path,
                request.headers.get("sec-fetch-site", "missing"),
            )
            raise LocalRuntimeStoreError("LOCAL_RUNTIME_UNAUTHORIZED", "本机运行凭据无效。", status_code=401)
        if session_origin != request_origin:
            logger.warning(
                "local_runtime_auth_rejected reason=origin_mismatch method=%s path=%s session_origin=%s request_origin=%s",
                request.method,
                request.url.path,
                session_origin,
                request_origin,
            )
            raise LocalRuntimeStoreError("LOCAL_RUNTIME_UNAUTHORIZED", "本机运行凭据无效。", status_code=401)

    @app.exception_handler(LocalRuntimeStoreError)
    @app.exception_handler(LocalArtifactError)
    async def local_runtime_error(_request: Request, error: Exception):
        code = getattr(error, "code", "LOCAL_RUNTIME_ERROR")
        status_code = getattr(error, "status_code", 400)
        if isinstance(error, LocalArtifactError):
            status_code = 400
        return JSONResponse(status_code=status_code, content={"error": {"code": code}})

    @app.exception_handler(RequestValidationError)
    async def invalid_local_request(_request: Request, _error: RequestValidationError):
        return JSONResponse(status_code=422, content={"error": {"code": "INVALID_LOCAL_REQUEST"}})

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "mode": "local",
            "platform_required": False,
            "frontend_served": app.state.frontend_served,
        }

    @app.post("/api/v1/local/session")
    async def create_local_session(request: Request) -> dict[str, Any]:
        now = time.monotonic()
        sessions = request.app.state.local_sessions
        for token, session in list(sessions.items()):
            if session["expires_at"] <= now:
                sessions.pop(token, None)
        if len(sessions) >= 100:
            raise LocalRuntimeStoreError(
                "LOCAL_SESSION_LIMIT_REACHED",
                "本机活动会话已达到上限。",
                status_code=429,
            )
        session_token = secrets.token_urlsafe(32)
        ttl_seconds = 15 * 60
        sessions[session_token] = {
            "origin": request.headers.get("origin"),
            "expires_at": now + ttl_seconds,
        }
        return {"token": session_token, "expires_in_seconds": ttl_seconds}

    @app.delete("/api/v1/local/session")
    async def revoke_local_session(request: Request) -> dict[str, str]:
        await require_local_auth(request)
        request.app.state.local_sessions.pop(request.headers.get("X-ICT-Local-Token", ""), None)
        return {"status": "revoked"}

    @app.get("/api/v1/local/workflow-components")
    async def local_components(request: Request) -> list[dict[str, Any]]:
        await require_local_auth(request)
        local_dependencies = resolve_local_dependency_versions()
        network_dependencies = resolve_network_dependency_versions()
        components = list_workflow_components(available_execution_targets={"local", "network"})
        for component in components:
            if component.get("execution_target") == "network":
                blockers = network_component_capability_blockers(
                    component,
                    available_dependency_versions=network_dependencies,
                    executor_permission_capabilities=CROSSREF_PERMISSION_CAPABILITIES,
                )
            elif component.get("execution_target") == "local":
                blockers = local_component_capability_blockers(
                    component,
                    available_dependency_versions=local_dependencies,
                    executor_permission_capabilities=LOCAL_EXECUTOR_PERMISSION_CAPABILITIES,
                )
            else:
                blockers = ["PLATFORM_EXECUTION_TARGET_UNAVAILABLE"]
            if blockers:
                component["execution_available"] = False
                component["execution_blockers"] = blockers
        return components

    @app.get("/api/v1/local/workflow-templates")
    async def local_workflow_templates(request: Request) -> list[dict[str, object]]:
        await require_local_auth(request)
        return list_local_workflow_templates()

    @app.get("/api/v1/local/projects")
    async def list_local_projects(request: Request) -> list[dict[str, Any]]:
        await require_local_auth(request)
        return request.app.state.run_store.list_local_projects()

    @app.post("/api/v1/local/projects", status_code=201)
    async def create_local_project(payload: LocalProjectCreate, request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.create_local_project(
            name=payload.name,
            domain=payload.domain,
            description=payload.description,
        )

    @app.get("/api/v1/local/projects/{project_id}")
    async def read_local_project(project_id: str, request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.get_local_project(project_id)

    @app.get("/api/v1/local/reproductions")
    async def list_local_reproductions(request: Request) -> list[dict[str, Any]]:
        await require_local_auth(request)
        return request.app.state.run_store.list_local_reproduction_tasks()

    @app.post("/api/v1/local/reproductions", status_code=201)
    async def create_local_reproduction(
        payload: LocalReproductionCreate,
        request: Request,
    ) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.create_local_reproduction_task(
            title=payload.title,
            kind=payload.kind,
            source=payload.source,
            claim=payload.claim,
            baseline=payload.baseline,
            criteria_version=payload.criteria_version,
            linked_project_id=payload.linked_project_id,
        )

    @app.get("/api/v1/local/reproductions/{task_id}")
    async def read_local_reproduction(task_id: str, request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.get_local_reproduction_task(task_id)

    @app.get("/api/v1/local/reproductions/{task_id}/workflows")
    async def list_local_reproduction_workflows(task_id: str, request: Request) -> list[dict[str, Any]]:
        await require_local_auth(request)
        return request.app.state.run_store.list_local_reproduction_workflows(task_id)

    @app.post("/api/v1/local/reproductions/{task_id}/workflows", status_code=201)
    async def create_local_reproduction_workflow(
        task_id: str,
        payload: LocalWorkflowCreate,
        request: Request,
    ) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.create_local_reproduction_workflow(
            task_id,
            name=payload.name,
            description=payload.description,
        )

    @app.get("/api/v1/local/projects/{project_id}/sync-state")
    async def read_local_project_sync_state(project_id: str, request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.get_local_project_sync_state(project_id)

    @app.post("/api/v1/local/projects/{project_id}/sync-state/start")
    async def start_local_project_sync(
        project_id: str,
        payload: LocalProjectSyncStart,
        request: Request,
    ) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.begin_local_project_sync(
            project_id,
            allow_pending_retry=payload.allow_pending_retry,
        )

    @app.put("/api/v1/local/projects/{project_id}/sync-state")
    async def save_local_project_sync_state(
        project_id: str,
        payload: LocalProjectSyncStateWrite,
        request: Request,
    ) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.save_local_project_sync_state(
            project_id,
            status=payload.status,
            platform_project_id=payload.platform_project_id,
            error_code=payload.error_code,
        )

    @app.get("/api/v1/local/projects/{project_id}/workflows")
    async def list_local_project_workflows(project_id: str, request: Request) -> list[dict[str, Any]]:
        await require_local_auth(request)
        return request.app.state.run_store.list_local_workflows(project_id)

    @app.post("/api/v1/local/projects/{project_id}/workflows", status_code=201)
    async def create_local_project_workflow(
        project_id: str,
        payload: LocalWorkflowCreate,
        request: Request,
    ) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.create_local_workflow(
            project_id,
            name=payload.name,
            description=payload.description,
        )

    @app.post("/api/v1/local/projects/{project_id}/workflows/from-template", status_code=201)
    async def create_local_project_workflow_from_template(
        project_id: str,
        payload: LocalWorkflowTemplateCreate,
        request: Request,
    ) -> dict[str, Any]:
        await require_local_auth(request)
        graph = instantiate_local_workflow_template(payload.template_id, payload.version)
        if graph is None:
            raise LocalRuntimeStoreError(
                "LOCAL_WORKFLOW_TEMPLATE_NOT_FOUND",
                "本机没有此模板版本；请刷新模板目录后重试。",
                status_code=404,
            )
        template = next(
            item for item in list_local_workflow_templates()
            if item["template_id"] == payload.template_id and item["version"] == payload.version
        )
        return request.app.state.run_store.create_local_workflow(
            project_id,
            name=str(template["name"]),
            description=str(template["description"]),
            graph=graph,
        )

    @app.put("/api/v1/local/projects/{project_id}/workflows/{workflow_id}/sync-state")
    async def save_local_workflow_sync_state(
        project_id: str,
        workflow_id: str,
        payload: LocalWorkflowSyncStateWrite,
        request: Request,
    ) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.save_local_workflow_sync_state(
            project_id,
            workflow_id,
            status=payload.status,
            platform_workflow_id=payload.platform_workflow_id,
            synced_revision=payload.synced_revision,
            source_revision=payload.source_revision,
            error_code=payload.error_code,
        )

    @app.get("/api/v1/local/workflows/{workflow_id}")
    async def read_local_workflow(workflow_id: str, request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.get_local_workflow(workflow_id)

    @app.post("/api/v1/local/artifacts", status_code=201)
    async def import_local_artifact(request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        if request.headers.get("X-ICT-Local-Consent") != "confirmed":
            raise LocalArtifactError(
                "ARTIFACT_AUTHORIZATION_REQUIRED",
                "导入前请确认你有权在本机处理此文件。",
            )
        file_name = unquote(request.headers.get("X-Artifact-File-Name", ""))
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > max_artifact_bytes:
                    raise LocalArtifactError("ARTIFACT_TOO_LARGE", "文件超过本机导入大小限制。")
            except ValueError as error:
                if isinstance(error, LocalArtifactError):
                    raise
                raise LocalArtifactError("ARTIFACT_LENGTH_INVALID", "文件长度信息无效。") from error

        artifact_store = request.app.state.artifact_store
        staged = tempfile.SpooledTemporaryFile(max_size=4 * 1024 * 1024, mode="w+b", dir=artifact_store.temp_dir)
        byte_count = 0
        try:
            async for chunk in request.stream():
                byte_count += len(chunk)
                if byte_count > max_artifact_bytes:
                    raise LocalArtifactError("ARTIFACT_TOO_LARGE", "文件超过本机导入大小限制。")
                await asyncio.to_thread(staged.write, chunk)
            if byte_count == 0:
                raise LocalArtifactError("ARTIFACT_EMPTY", "CSV 文件为空。")
            await asyncio.to_thread(staged.seek, 0)
            handle = await asyncio.to_thread(
                artifact_store.import_csv,
                staged,
                file_name=file_name,
                authorization_confirmed=True,
            )
            return handle.to_dict()
        finally:
            await asyncio.to_thread(staged.close)

    @app.get("/api/v1/local/artifacts/{artifact_id}/csv-preflight-report")
    async def read_csv_preflight_report(artifact_id: str, request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        return await asyncio.to_thread(
            request.app.state.artifact_store.read_csv_preflight_report,
            artifact_id,
        )

    @app.get("/api/v1/local/artifacts/{artifact_id}/csv-descriptive-summary")
    async def read_csv_descriptive_summary(artifact_id: str, request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        return await asyncio.to_thread(
            request.app.state.artifact_store.read_csv_descriptive_summary_report,
            artifact_id,
        )

    @app.get("/api/v1/local/artifacts/{artifact_id}/csv-folder-quality-report")
    async def read_csv_folder_quality_report(artifact_id: str, request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        return await asyncio.to_thread(
            request.app.state.artifact_store.read_csv_folder_quality_report,
            artifact_id,
        )

    @app.get("/api/v1/local/artifacts/{artifact_id}/crossref-metadata")
    async def read_crossref_metadata_report(artifact_id: str, request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        return await asyncio.to_thread(
            request.app.state.artifact_store.read_crossref_metadata_report,
            artifact_id,
        )

    @app.put("/api/v1/local/workflows/{workflow_id}/draft")
    async def save_local_draft(
        workflow_id: str,
        payload: LocalWorkflowDraftWrite,
        request: Request,
    ) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.save_workflow_draft(
            workflow_id,
            revision=payload.revision,
            graph=payload.graph,
            name=payload.name,
            description=payload.description,
        )

    @app.get("/api/v1/local/workflows/{workflow_id}/draft")
    async def read_local_draft(workflow_id: str, request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.get_workflow_draft(workflow_id)

    @app.post("/api/v1/local/workflows/{workflow_id}/validations")
    async def validate_local_workflow(
        workflow_id: str,
        payload: LocalWorkflowValidationRequest,
        request: Request,
    ) -> dict[str, Any]:
        await require_local_auth(request)
        if not workflow_id or len(workflow_id) > 128:
            raise LocalRuntimeStoreError("LOCAL_WORKFLOW_INVALID", "本机工作流标识无效。")

        # Reuse the same registered graph and component contract checks as the platform API.
        graph = payload.graph.model_dump(mode="json", by_alias=True)
        structural_issues = validate_workflow_graph(graph)
        contract_issues = validate_workflow_component_contracts(graph)

        def format_issue(scope: str, issue: dict[str, Any]) -> dict[str, Any]:
            code = str(issue["code"])
            message = str(issue.get("message") or "工作流校验未通过。")
            title = {
                "EMPTY_GRAPH": "工作流为空",
                "CYCLE_UNSUPPORTED": "存在循环依赖",
                "COMPONENT_NOT_REGISTERED": "组件未登记",
                "PARAMETER_REQUIRED": "必需参数缺失",
                "REQUIRED_INPUT_UNCONNECTED": "必需输入未连接",
                "PORT_TYPE_MISMATCH": "端口数据类型不兼容",
            }.get(code, "工作流校验未通过")
            return {
                "scope": scope,
                **issue,
                "severity": "blocker",
                "title": title,
                "reason": message,
                "impact": "该问题会阻止工作流通过结构或组件契约校验。",
                "guidance": "按问题提示修正关联节点或连线后重新校验。",
            }

        issues = [
            *(format_issue("structure", item) for item in structural_issues),
            *(format_issue("component", item) for item in contract_issues),
        ]
        structural_status = "invalid" if structural_issues else "valid"
        contract_status = "invalid" if contract_issues else "valid"
        logger.info(
            "local_workflow_validated workflow_id=%s revision=%s structural_status=%s contract_status=%s issue_count=%s",
            workflow_id,
            payload.revision,
            structural_status,
            contract_status,
            len(issues),
        )
        return {
            "workflow_id": workflow_id,
            "revision": payload.revision,
            "structural_status": structural_status,
            "contract_status": contract_status,
            "executable": False,
            "execution_blockers": [],
            "issues": issues,
        }

    def schedule_local_run(
        runtime_app: FastAPI,
        run_id: str,
        *,
        restored_outputs: dict[str, Any] | None = None,
    ) -> None:
        """Use the same supervised in-process worker path for new and recovered runs."""
        task = asyncio.create_task(
            execute_local_run(runtime_app, run_id, restored_outputs=restored_outputs),
            name=f"local-workflow-{run_id}",
        )
        runtime_app.state.active_runs[run_id] = task

        def remove_finished(completed: asyncio.Task[None]) -> None:
            runtime_app.state.active_runs.pop(run_id, None)
            if completed.cancelled():
                return
            error = completed.exception()
            if error is None:
                return
            logger.error(
                "local_workflow_background_task_failed run_id=%s error_type=%s",
                run_id,
                type(error).__name__,
                exc_info=(type(error), error, error.__traceback__),
            )
            try:
                runtime_app.state.run_store.set_run_status(run_id, "failed", error_code="LOCAL_WORKER_TASK_CRASHED")
            except LocalRuntimeStoreError:
                logger.exception("local_workflow_supervisor_persist_failed run_id=%s", run_id)

        task.add_done_callback(remove_finished)

    @app.post("/api/v1/local/workflows/{workflow_id}/runs", status_code=202)
    async def submit_local_run(
        workflow_id: str,
        payload: LocalRunSubmit,
        request: Request,
    ) -> dict[str, Any]:
        await require_local_auth(request)
        if len(request.app.state.active_runs) >= request.app.state.max_active_runs:
            raise LocalRuntimeStoreError(
                "LOCAL_RUN_CAPACITY_REACHED",
                "本机运行队列已达到首版并发上限，请等待当前运行结束。",
                status_code=429,
            )
        try:
            created = request.app.state.run_store.create_run(
                workflow_id,
                target_node_ids=payload.target_node_ids,
                validate_plan=lambda plan: validate_local_plan_admission(
                    plan,
                    request.app.state.artifact_store,
                    available_dependency_versions=resolve_local_dependency_versions(),
                    executor_permission_capabilities=LOCAL_EXECUTOR_PERMISSION_CAPABILITIES,
                    network_dependency_versions=resolve_network_dependency_versions(),
                    network_executor_permission_capabilities=CROSSREF_PERMISSION_CAPABILITIES,
                ),
            )
        except WorkflowCompilationError as error:
            raise LocalRuntimeStoreError(error.code, str(error), status_code=422) from error
        run_id = created["run_id"]
        schedule_local_run(request.app, run_id)
        return {
            "run_id": run_id,
            "workflow_id": workflow_id,
            "status": "queued",
            "plan_hash": created["plan"]["plan_hash"],
            "target_node_ids": created["plan"]["target_node_ids"],
        }

    @app.post("/api/v1/local/runs/{run_id}/recover", status_code=202)
    async def recover_local_run(run_id: str, request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        if len(request.app.state.active_runs) >= request.app.state.max_active_runs:
            raise LocalRuntimeStoreError(
                "LOCAL_RUN_CAPACITY_REACHED",
                "本机运行队列已达到首版并发上限，请等待当前运行结束。",
                status_code=429,
            )
        try:
            snapshot = request.app.state.run_store.get_recovery_snapshot(run_id)
            restored_outputs = _verified_recovery_outputs(
                snapshot["outputs"], request.app.state.artifact_store
            )

            def validate_plan(plan: dict[str, Any]) -> None:
                validate_local_plan_admission(
                    plan,
                    request.app.state.artifact_store,
                    available_dependency_versions=resolve_local_dependency_versions(),
                    executor_permission_capabilities=LOCAL_EXECUTOR_PERMISSION_CAPABILITIES,
                    network_dependency_versions=resolve_network_dependency_versions(),
                    network_executor_permission_capabilities=CROSSREF_PERMISSION_CAPABILITIES,
                )

            created = request.app.state.run_store.create_recovery_run(
                run_id,
                restored_outputs=restored_outputs,
                validate_plan=validate_plan,
            )
        except WorkflowCompilationError as error:
            raise LocalRuntimeStoreError(error.code, str(error), status_code=422) from error
        schedule_local_run(
            request.app,
            created["run_id"],
            restored_outputs=restored_outputs,
        )
        restored_node_ids = created["restored_node_ids"]
        return {
            "run_id": created["run_id"],
            "workflow_id": created["workflow_id"],
            "status": "queued",
            "plan_hash": created["plan"]["plan_hash"],
            "target_node_ids": created["plan"]["target_node_ids"],
            "recovered_from_run_id": run_id,
            "restored_node_ids": restored_node_ids,
            "rerun_node_ids": [
                node_id for node_id in created["plan"]["node_order"] if node_id not in restored_node_ids
            ],
        }

    @app.get("/api/v1/local/runs/{run_id}")
    async def read_local_run(run_id: str, request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        return request.app.state.run_store.get_run(run_id)

    @app.get("/api/v1/local/workflows/{workflow_id}/runs")
    async def list_local_runs(workflow_id: str, request: Request) -> list[dict[str, Any]]:
        await require_local_auth(request)
        return request.app.state.run_store.list_runs(workflow_id)

    @app.post("/api/v1/local/runs/{run_id}/cancel", status_code=202)
    async def cancel_local_run(run_id: str, request: Request) -> dict[str, Any]:
        await require_local_auth(request)
        run = request.app.state.run_store.get_run(run_id)
        if run["status"] in {"succeeded", "partially_succeeded", "failed", "cancelled"}:
            return {"run_id": run_id, "status": run["status"]}
        task = request.app.state.active_runs.get(run_id)
        if task is None:
            raise LocalRuntimeStoreError(
                "LOCAL_RUN_NOT_ACTIVE",
                "本机运行当前不在活动队列中。",
                status_code=409,
            )
        task.cancel()
        return {"run_id": run_id, "status": "cancelling"}

    async def execute_local_run(
        runtime_app: FastAPI,
        run_id: str,
        *,
        restored_outputs: dict[str, Any] | None = None,
    ) -> None:
        run_store = runtime_app.state.run_store
        artifact_store = runtime_app.state.artifact_store
        executor_registry = build_local_executor_registry(artifact_store)
        executor_registry.update(build_network_executor_registry(
            artifact_store,
            request_semaphore=runtime_app.state.network_request_semaphore,
        ))
        executors = build_cached_executor_registry(
            executor_registry,
            run_store=run_store,
            artifact_store=artifact_store,
            run_id=run_id,
        )
        try:
            run_store.set_run_status(run_id, "running")
            plan = run_store.get_plan(run_id)
            result = await execute_execution_plan(
                plan,
                executors=executors,
                max_concurrency=runtime_app.state.max_node_concurrency,
                on_event=lambda event: run_store.record_node_event(run_id, event),
                restored_outputs=restored_outputs,
                on_node_result=lambda event: run_store.record_node_result(run_id, event),
            )
            run_store.finish_run(run_id, result)
            logger.info(
                "local_workflow_run_completed run_id=%s status=%s plan_hash=%s",
                run_id,
                result["status"],
                plan["plan_hash"],
            )
        except asyncio.CancelledError:
            try:
                run_store.set_run_status(run_id, "cancelled", error_code="RUN_CANCELLED")
            except LocalRuntimeStoreError:
                logger.exception("local_workflow_cancel_persist_failed run_id=%s", run_id)
            raise
        except Exception:
            logger.exception("local_workflow_run_failed run_id=%s", run_id)
            try:
                run_store.set_run_status(run_id, "failed", error_code="LOCAL_RUNTIME_EXECUTION_FAILED")
            except LocalRuntimeStoreError:
                logger.exception("local_workflow_failure_persist_failed run_id=%s", run_id)

    if frontend_root is not None:
        # API routes are registered first; this mount serves only the packaged React assets.
        app.mount("/", StaticFiles(directory=frontend_root, html=True), name="frontend")

    return app


def main() -> None:
    """Start the standalone runtime on loopback for an approved local UI origin."""
    import uvicorn

    root = Path(os.environ.get("ICT_LOCAL_RUNTIME_DIR", Path.home() / ".ict" / "runtime"))
    configured_frontend = os.environ.get("ICT_WEB_DIST", "").strip()
    frontend_root = Path(configured_frontend) if configured_frontend else Path(__file__).resolve().parents[2] / "frontend" / "dist"
    app = create_local_runtime_app(
        root=root,
        static_dir=frontend_root if frontend_root.is_dir() else None,
    )
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("ICT_LOCAL_RUNTIME_PORT", "8767")))


if __name__ == "__main__":
    main()
