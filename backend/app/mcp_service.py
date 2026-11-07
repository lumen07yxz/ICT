"""Public, read-only Streamable HTTP MCP service for the synthetic demo."""

from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Annotated, Sequence
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

from app.services.demo_catalog import (
    DemoProjectNotAllowed,
    DemoProjectOverview,
    get_demo_project_overview,
)


logger = logging.getLogger("ict.mcp")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger.addHandler(handler)
logger.propagate = False

DEFAULT_ALLOWED_HOSTS = [
    "127.0.0.1",
    "127.0.0.1:*",
    "localhost",
    "localhost:*",
    "testserver",
    "testserver:*",
]
MCP_PATH = "/mcp"
MCP_KEY_HEADER = "x-agentarts-key"
INTERNAL_API_KEY_HEADER = "X-ICT-Internal-Key"
IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
DEFAULT_INTERNAL_API_URL = "http://127.0.0.1:8765/internal/v1/run-proposals"


class RunProposalToolResult(BaseModel):
    """MCP result contains only fixed proposal metadata and synthetic trace linkage."""

    model_config = ConfigDict(extra="forbid")

    id: str
    project_id: str
    dataset_version: str
    pipeline_template: str
    parameters: dict[str, int]
    config_sha256: str
    trace_id: str
    status: Literal["pending_approval", "expired", "approved"]
    approved_by: str | None
    approved_at: str | None
    run_id: str | None
    created_at: str
    expires_at: str


class SmokeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task: Literal["synthetic_smoke"]
    processed_count: int = Field(ge=1, le=100)
    synthetic_only: Literal[True]
    research_ready: Literal[False]
    message: Literal["集成冒烟任务完成。"]


class RunStatusToolResult(BaseModel):
    """Strict result DTO for a single fixed synthetic execution."""

    model_config = ConfigDict(extra="forbid")

    id: str
    proposal_id: str
    project_id: str
    dataset_version: Literal["dataset-synthetic-v1"]
    pipeline_template: Literal["research-smoke-v1"]
    parameters: dict[str, int]
    config_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    quality_status: Literal["success", "warning"] | None
    quality_rule_set_version: str | None
    quality_report_sha256: str | None
    trace_id: str
    status: Literal["queued", "running", "succeeded", "failed"]
    result: SmokeResult | None
    error_code: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


def _proposal_idempotency_key(
    request_id: str,
    payload: dict[str, object],
    session_id: str = "",
) -> str:
    """Make retries stable while separating different sessions and parameter sets."""
    material = json.dumps(
        {
            "session_id": session_id,
            "request_id": request_id,
            "arguments": payload,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def create_mcp_server(
    *,
    internal_api_key: str | None = None,
    backend_api_url: str = DEFAULT_INTERNAL_API_URL,
    backend_timeout_seconds: float = 5.0,
) -> MCPServer:
    """Build a narrow MCP server with read access and one pending-only write."""
    server = MCPServer(
        name="ict_research_mcp",
        title="ICT Synthetic Research Tools",
        version="0.2.0",
        instructions=(
            "Use only the fixed synthetic demo project. The proposal tool creates a pending "
            "approval request and never starts a run. Read run status only by run ID. "
            "The data is a software-test fixture, "
            "not real research data or a research result."
        ),
    )

    @server.tool(
        name="get_demo_project_overview",
        title="Read synthetic demo project overview",
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
    )
    def get_project_overview(
        project_id: Annotated[
            str,
            Field(
                min_length=1,
                max_length=64,
                description="Allowed synthetic demo project ID; currently demo-research.",
            ),
        ],
    ) -> DemoProjectOverview:
        """Read one allow-listed synthetic project overview without changing data."""
        try:
            return get_demo_project_overview(project_id)
        except DemoProjectNotAllowed as exc:
            # Keep private or unknown identifiers out of the model-visible error.
            raise ToolError(
                "项目不可用。当前只开放 demo-research 合成演示项目。"
            ) from exc

    @server.tool(
        name="create_run_proposal",
        title="Create a pending synthetic run proposal",
        description=(
            "Create a 15-minute pending approval proposal for the fixed synthetic dataset and "
            "research-smoke-v1 template. This tool never approves or starts a run."
        ),
        annotations=ToolAnnotations(
            read_only_hint=False,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    async def create_proposal(
        project_id: Annotated[
            Literal["demo-research"],
            Field(description="The only allowed project: demo-research."),
        ],
        dataset_version: Annotated[
            Literal["dataset-synthetic-v1"],
            Field(description="The only allowed synthetic dataset version."),
        ],
        pipeline_template: Annotated[
            Literal["research-smoke-v1"],
            Field(description="The only allowed short synthetic pipeline template."),
        ],
        sample_limit: Annotated[
            int,
            Field(ge=1, le=100, description="Synthetic sample count, from 1 through 100."),
        ],
        ctx: Context,
    ) -> RunProposalToolResult:
        """Forward a fixed request to the private API; never start a worker or run."""
        if not internal_api_key:
            raise ToolError("提案服务尚未配置，当前无法创建提案。")
        request_id = ctx.request_id
        if not request_id:
            raise ToolError("提案请求标识不可用，请重新发起。")

        payload = {
            "project_id": project_id,
            "dataset_version": dataset_version,
            "pipeline_template": pipeline_template,
            "sample_limit": sample_limit,
        }
        headers = {key.lower(): value for key, value in (ctx.headers or {}).items()}
        session_id = headers.get("mcp-session-id", "")
        idempotency_key = _proposal_idempotency_key(request_id, payload, session_id)
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=backend_timeout_seconds) as client:
                response = await client.post(
                    backend_api_url,
                    headers={
                        INTERNAL_API_KEY_HEADER: internal_api_key,
                        IDEMPOTENCY_KEY_HEADER: idempotency_key,
                    },
                    json=payload,
                )
        except httpx.TimeoutException as exc:
            logger.warning(
                "proposal_forward_failed request_id=%s error_code=INTERNAL_API_TIMEOUT",
                uuid4().hex,
            )
            raise ToolError("提案服务响应超时，请稍后重试。") from exc
        except httpx.HTTPError as exc:
            logger.error(
                "proposal_forward_failed request_id=%s error_code=INTERNAL_API_UNAVAILABLE error_type=%s",
                uuid4().hex,
                type(exc).__name__,
            )
            raise ToolError("提案服务暂时不可用，请稍后重试。") from exc

        if response.status_code not in {200, 201}:
            error_code = "INTERNAL_API_REJECTED"
            try:
                body = response.json()
                if isinstance(body, dict) and isinstance(body.get("error"), dict):
                    candidate = body["error"].get("code")
                    if isinstance(candidate, str) and candidate.isascii() and candidate.isupper():
                        error_code = candidate[:64]
            except (ValueError, TypeError):
                pass
            logger.warning(
                "proposal_forward_failed request_id=%s error_code=%s status=%s",
                uuid4().hex,
                error_code,
                response.status_code,
            )
            messages = {
                "IDEMPOTENCY_CONFLICT": "提案请求与已有请求冲突，请重新发起。",
                "INVALID_REQUEST": "提案不符合当前固定模板。",
                "INTERNAL_UNAUTHORIZED": "提案服务鉴权失败，请联系管理员。",
                "INTERNAL_AUTH_NOT_CONFIGURED": "提案服务尚未配置，当前无法创建提案。",
                "DATABASE_NOT_CONFIGURED": "提案服务暂不可用，请联系管理员。",
                "DEMO_DATASET_NOT_CONFIGURED": "合成演示数据暂不可用，请联系管理员。",
            }
            raise ToolError(messages.get(error_code, "提案暂时无法创建，请稍后重试。"))

        try:
            result = RunProposalToolResult.model_validate(response.json())
        except (ValueError, TypeError) as exc:
            logger.error(
                "proposal_forward_failed request_id=%s error_code=INVALID_INTERNAL_RESPONSE",
                uuid4().hex,
            )
            raise ToolError("提案服务返回的数据格式不正确，请联系管理员。") from exc

        logger.info(
            "proposal_forward_complete request_id=%s status=%s duration_ms=%s",
            uuid4().hex,
            response.status_code,
            round((time.monotonic() - started) * 1000),
        )
        return result

    # MCP 2.3 generates argument models that ignore unknown fields by default.
    # Pin the input contract to forbid extras both in JSON Schema and at call time.
    proposal_tool = server._tool_manager.get_tool("create_run_proposal")
    if proposal_tool is not None:
        argument_model = proposal_tool.fn_metadata.arg_model
        argument_model.model_config["extra"] = "forbid"
        argument_model.model_rebuild(force=True)
        proposal_tool.parameters = argument_model.model_json_schema(by_alias=True)

    run_status_url = backend_api_url.rsplit("/", 1)[0] + "/runs"

    @server.tool(
        name="get_run_status",
        title="Read synthetic run status",
        description="Read the status and fixed synthetic smoke result for one run ID.",
        annotations=ToolAnnotations(
            read_only_hint=True,
            destructive_hint=False,
            idempotent_hint=True,
            open_world_hint=False,
        ),
        structured_output=True,
    )
    async def read_run_status(
        run_id: Annotated[
            str,
            Field(min_length=36, max_length=36, description="Run UUID returned after operator approval."),
        ],
    ) -> RunStatusToolResult:
        """Forward a UUID-only status read using the separate internal service key."""
        if not internal_api_key:
            raise ToolError("运行状态服务尚未配置，请联系管理员。")
        try:
            safe_run_id = str(UUID(run_id))
        except (ValueError, TypeError, AttributeError) as exc:
            raise ToolError("运行标识无效，请检查运行记录中的 ID。") from exc
        if safe_run_id != run_id.lower():
            raise ToolError("运行标识无效，请检查运行记录中的 ID。")
        started = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=backend_timeout_seconds) as client:
                response = await client.get(
                    f"{run_status_url}/{safe_run_id}",
                    headers={INTERNAL_API_KEY_HEADER: internal_api_key},
                )
        except httpx.TimeoutException as exc:
            logger.warning("run_status_forward_failed error_code=INTERNAL_API_TIMEOUT")
            raise ToolError("运行状态查询超时，请稍后重试。") from exc
        except httpx.HTTPError as exc:
            logger.error(
                "run_status_forward_failed error_code=INTERNAL_API_UNAVAILABLE error_type=%s",
                type(exc).__name__,
            )
            raise ToolError("运行状态服务暂时不可用，请稍后重试。") from exc
        if response.status_code != 200:
            logger.warning(
                "run_status_forward_failed error_code=RUN_NOT_FOUND status=%s",
                response.status_code,
            )
            raise ToolError("运行记录不存在或暂时不可用。")
        try:
            result = RunStatusToolResult.model_validate(response.json())
        except (ValueError, TypeError) as exc:
            logger.error("run_status_forward_failed error_code=INVALID_INTERNAL_RESPONSE")
            raise ToolError("运行状态服务返回的数据格式不正确。") from exc
        logger.info(
            "run_status_forward_complete run_id=%s trace_id=%s status=%s duration_ms=%s",
            result.id,
            result.trace_id,
            result.status,
            round((time.monotonic() - started) * 1000),
        )
        return result

    run_status_tool = server._tool_manager.get_tool("get_run_status")
    if run_status_tool is not None:
        argument_model = run_status_tool.fn_metadata.arg_model
        argument_model.model_config["extra"] = "forbid"
        argument_model.model_rebuild(force=True)
        run_status_tool.parameters = argument_model.model_json_schema(by_alias=True)

    return server


def _allowed_hosts(configured: Sequence[str] | None) -> list[str]:
    """Use an explicit hostname allowlist so the deployed route rejects rebinding."""
    if configured is not None:
        hosts = [host.strip() for host in configured if host.strip()]
    else:
        raw_hosts = os.environ.get("MCP_ALLOWED_HOSTS", "").strip()
        hosts = [host.strip() for host in raw_hosts.split(",") if host.strip()]
        if not hosts:
            hosts = DEFAULT_ALLOWED_HOSTS.copy()
    if not hosts:
        raise ValueError("MCP_ALLOWED_HOSTS must contain at least one hostname")
    return hosts


def create_mcp_app(
    *,
    api_key: str | None = None,
    internal_api_key: str | None = None,
    backend_api_url: str | None = None,
    backend_timeout_seconds: float | None = None,
    allowed_hosts: Sequence[str] | None = None,
) -> FastAPI:
    """Create the isolated MCP web app; missing credentials fail closed."""
    configured_key = api_key if api_key is not None else os.environ.get("AGENTARTS_MCP_API_KEY")
    expected_key = configured_key.strip() if configured_key and configured_key.strip() else None
    configured_internal_key = (
        internal_api_key
        if internal_api_key is not None
        else os.environ.get("ICT_INTERNAL_API_KEY")
    )
    expected_internal_key = (
        configured_internal_key.strip()
        if configured_internal_key and configured_internal_key.strip()
        else None
    )
    configured_backend_url = (
        backend_api_url
        if backend_api_url is not None
        else os.environ.get("ICT_INTERNAL_API_URL", DEFAULT_INTERNAL_API_URL)
    )
    backend_url = configured_backend_url.strip()
    parsed_backend_url = urlsplit(backend_url)
    if (
        parsed_backend_url.scheme not in {"http", "https"}
        or not parsed_backend_url.hostname
        or parsed_backend_url.username is not None
        or parsed_backend_url.password is not None
        or parsed_backend_url.query
        or parsed_backend_url.fragment
    ):
        raise ValueError("ICT_INTERNAL_API_URL must be a valid HTTP or HTTPS URL")
    timeout_value = (
        backend_timeout_seconds
        if backend_timeout_seconds is not None
        else float(os.environ.get("ICT_INTERNAL_API_TIMEOUT_SECONDS", "5"))
    )
    if timeout_value <= 0 or timeout_value > 30:
        raise ValueError("ICT_INTERNAL_API_TIMEOUT_SECONDS must be between 0 and 30")
    server = create_mcp_server(
        internal_api_key=expected_internal_key,
        backend_api_url=backend_url,
        backend_timeout_seconds=timeout_value,
    )
    server_app = server.streamable_http_app(
        streamable_http_path="/",
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(allowed_hosts=_allowed_hosts(allowed_hosts)),
    )

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Mounted MCP sub-apps do not start their own session manager lifespan.
        async with server.session_manager.run():
            yield

    app = FastAPI(title="ICT Synthetic Research MCP", version="0.3.0", lifespan=lifespan)
    app.state.mcp_server = server
    app.state.mcp_api_key_configured = expected_key is not None
    app.state.internal_api_key_configured = expected_internal_key is not None
    app.mount(MCP_PATH, server_app)

    @app.middleware("http")
    async def audit_and_authenticate(request: Request, call_next):
        """Authenticate only MCP paths and log request metadata without credentials."""
        request_id = uuid4().hex
        request.state.request_id = request_id
        started = time.monotonic()
        path = request.url.path
        is_mcp_request = path == MCP_PATH or path.startswith(f"{MCP_PATH}/")

        if is_mcp_request:
            if expected_key is None:
                logger.warning(
                    "request_rejected request_id=%s error_code=MCP_AUTH_NOT_CONFIGURED",
                    request_id,
                )
                response = JSONResponse(
                    status_code=503,
                    content={"error": {"code": "MCP_AUTH_NOT_CONFIGURED", "request_id": request_id}},
                )
            else:
                supplied_key = request.headers.get(MCP_KEY_HEADER, "")
                if not supplied_key or not hmac.compare_digest(
                    supplied_key.encode("utf-8"), expected_key.encode("utf-8")
                ):
                    logger.warning(
                        "request_rejected request_id=%s error_code=MCP_UNAUTHORIZED",
                        request_id,
                    )
                    response = JSONResponse(
                        status_code=401,
                        content={"error": {"code": "MCP_UNAUTHORIZED", "request_id": request_id}},
                    )
                else:
                    response = await call_next(request)
        else:
            response = await call_next(request)

        elapsed_ms = round((time.monotonic() - started) * 1000)
        logger.info(
            "request_complete request_id=%s method=%s route=%s status=%s duration_ms=%s",
            request_id,
            request.method,
            MCP_PATH if is_mcp_request else path,
            response.status_code,
            elapsed_ms,
        )
        response.headers["x-request-id"] = request_id
        return response

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        """Report MCP process liveness without exposing private service details."""
        return {"status": "ok", "mode": "read_only_synthetic_mcp"}

    return app


app = create_mcp_app()
