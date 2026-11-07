"""Bounded public Crossref DOI lookup for the local network execution target."""

from __future__ import annotations

import asyncio
import hashlib
import importlib.metadata
import json
import logging
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from typing import Any

from app.services.local_artifacts import ArtifactHandle, LocalArtifactStore
from app.services.workflow_scheduler import ExternalWait, WorkflowNodeFailure


logger = logging.getLogger("ict.network.crossref")
CROSSREF_API_BASE = "https://api.crossref.org/works/"
CROSSREF_EXECUTOR_BINDING = "ict.network.crossref_metadata"
CROSSREF_EXECUTOR_VERSION = "1.0.0"
CROSSREF_DEPENDENCY_REQUIREMENT = "httpx@0.28.1"
CROSSREF_PERMISSION_CAPABILITIES = {
    CROSSREF_EXECUTOR_BINDING: frozenset({"network:crossref:metadata:read"}),
}
MAX_CROSSREF_RESPONSE_BYTES = 2 * 1024 * 1024
CROSSREF_TIMEOUT_SECONDS = 20
DOI_PATTERN = re.compile(r"^10\.\d{4,9}/\S+$", re.IGNORECASE)


def resolve_network_dependency_versions() -> dict[str, str]:
    """Report only the pinned HTTP client version required by the network node."""
    try:
        return {"httpx": importlib.metadata.version("httpx")}
    except importlib.metadata.PackageNotFoundError:
        return {}


def crossref_implementation_digest() -> str | None:
    """Fingerprint this adapter in both source and PyInstaller one-file layouts."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    source_path = (
        Path(frozen_root) / "app" / "services" / "network_crossref_executor.py"
        if isinstance(frozen_root, str)
        else Path(__file__)
    )
    try:
        return hashlib.sha256(source_path.resolve().read_bytes()).hexdigest()
    except OSError:
        logger.exception("crossref_executor_digest_unavailable")
        return None


def _normalize_doi(value: Any) -> str:
    """Accept a DOI or doi.org URL while preventing path traversal in the fixed endpoint."""
    if not isinstance(value, str):
        raise WorkflowNodeFailure("CROSSREF_DOI_REQUIRED", "请填写有效 DOI。")
    doi = value.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if doi.lower().startswith(prefix):
            doi = doi[len(prefix):].strip()
            break
    if (
        not doi
        or len(doi) > 300
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in doi)
        or not DOI_PATTERN.fullmatch(doi)
        or any(part in {".", ".."} for part in doi.split("/"))
    ):
        raise WorkflowNodeFailure("CROSSREF_DOI_INVALID", "DOI 格式无效，请检查 DOI 前缀和字符。")
    return doi


def _field_text(value: Any, *, limit: int = 1000) -> str | None:
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return cleaned[:limit] or None
    return None


def _first_text(value: Any) -> str | None:
    if isinstance(value, list):
        for item in value:
            cleaned = _field_text(item)
            if cleaned:
                return cleaned
    return _field_text(value)


def _published_date(message: dict[str, Any]) -> str | None:
    """Extract only a deposited calendar date; do not infer missing precision."""
    for field in ("published-print", "published-online", "published", "issued"):
        candidate = message.get(field)
        parts = candidate.get("date-parts") if isinstance(candidate, dict) else None
        first = parts[0] if isinstance(parts, list) and parts else None
        if not isinstance(first, list) or not first:
            continue
        if any(type(part) is not int for part in first[:3]):
            continue
        try:
            return datetime(*first[:3]).date().isoformat() if len(first) >= 3 else (
                f"{first[0]:04d}-{first[1]:02d}" if len(first) == 2 else f"{first[0]:04d}"
            )
        except ValueError:
            continue
    return None


def _authors(message: dict[str, Any]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    raw_authors = message.get("author")
    if not isinstance(raw_authors, list):
        return result
    for author in raw_authors[:100]:
        if not isinstance(author, dict):
            continue
        name = _field_text(author.get("name")) or " ".join(
            part for part in (_field_text(author.get("given"), limit=200), _field_text(author.get("family"), limit=200))
            if part
        )
        if not name:
            continue
        item = {"name": name[:300]}
        orcid = _field_text(author.get("ORCID"), limit=100)
        if orcid:
            item["orcid"] = orcid
        result.append(item)
    return result


def _crossref_report(doi: str, source_url: str, message: dict[str, Any]) -> dict[str, object]:
    """Keep only bibliographic fields; abstracts and full deposited payloads are excluded."""
    return {
        "report_type": "crossref_doi_metadata",
        "label": "Crossref 公开文献元数据，非科研结果",
        "research_result": False,
        "source_name": "Crossref REST API",
        "source_url": source_url,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "doi": _field_text(message.get("DOI"), limit=300) or doi,
        "title": _first_text(message.get("title")),
        "authors": _authors(message),
        "container_title": _first_text(message.get("container-title")),
        "publisher": _field_text(message.get("publisher")),
        "published_date": _published_date(message),
        "work_type": _field_text(message.get("type"), limit=100),
        "landing_page": _field_text(message.get("URL"), limit=2000),
        "verification_note": "元数据来自 Crossref 的登记记录，可能缺失或有误；请与出版方页面和论文原文核对。",
    }


async def _fetch_crossref_message(doi: str, source_url: str, node_id: str) -> dict[str, Any]:
    """Make one bounded HTTPS request without redirects, credentials, or retries."""
    try:
        import httpx
    except ImportError as error:
        logger.exception("crossref_http_client_unavailable node_id=%s", node_id)
        raise WorkflowNodeFailure("NETWORK_DEPENDENCY_UNAVAILABLE", "本机缺少网络组件依赖。") from error

    try:
        timeout = httpx.Timeout(CROSSREF_TIMEOUT_SECONDS, connect=5.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                "User-Agent": "ICTResearchWorkbench/0.1.0",
            },
        ) as client:
            async with client.stream("GET", source_url) as response:
                if response.status_code == 404:
                    raise WorkflowNodeFailure("CROSSREF_DOI_NOT_FOUND", "Crossref 中没有找到此 DOI。")
                if response.status_code == 429:
                    raise WorkflowNodeFailure("NETWORK_RATE_LIMITED", "Crossref 请求达到公开服务限流，请稍后再运行。")
                if 300 <= response.status_code < 400:
                    raise WorkflowNodeFailure("NETWORK_REDIRECT_REJECTED", "Crossref 返回重定向，本次请求已拒绝。")
                if response.status_code in {401, 403}:
                    raise WorkflowNodeFailure("NETWORK_ACCESS_DENIED", "Crossref 暂时拒绝此请求。")
                if response.status_code >= 500:
                    raise WorkflowNodeFailure("NETWORK_UPSTREAM_ERROR", "Crossref 服务暂时不可用。")
                if response.status_code != 200:
                    raise WorkflowNodeFailure("NETWORK_HTTP_ERROR", "Crossref 返回了无法处理的状态码。")
                content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                if content_type != "application/json":
                    raise WorkflowNodeFailure("NETWORK_RESPONSE_INVALID", "Crossref 返回的内容不是 JSON。")

                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_CROSSREF_RESPONSE_BYTES:
                        raise WorkflowNodeFailure("NETWORK_RESPONSE_TOO_LARGE", "Crossref 响应超过本机读取上限。")
    except WorkflowNodeFailure:
        raise
    except httpx.TimeoutException as error:
        logger.exception("crossref_request_timeout node_id=%s error_type=%s", node_id, type(error).__name__)
        raise WorkflowNodeFailure("NETWORK_TIMEOUT", "Crossref 请求超时，请检查网络后重试。") from error
    except httpx.NetworkError as error:
        logger.exception("crossref_network_unavailable node_id=%s error_type=%s", node_id, type(error).__name__)
        raise WorkflowNodeFailure("NETWORK_UNAVAILABLE", "无法连接 Crossref；本机节点失败，其依赖下游将被阻断。") from error
    except httpx.HTTPError as error:
        logger.exception("crossref_http_error node_id=%s error_type=%s", node_id, type(error).__name__)
        raise WorkflowNodeFailure("NETWORK_UPSTREAM_ERROR", "Crossref 响应读取失败。") from error

    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WorkflowNodeFailure("NETWORK_RESPONSE_INVALID", "Crossref 返回的 JSON 无法解析。") from error
    message = payload.get("message") if isinstance(payload, dict) else None
    if not isinstance(message, dict):
        raise WorkflowNodeFailure("NETWORK_RESPONSE_INVALID", "Crossref JSON 缺少文献元数据。")
    return message


def build_network_executor_registry(
    artifact_store: LocalArtifactStore,
    *,
    request_semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Register one fixed-host network node; graph data cannot select another endpoint."""
    async def lookup(node: dict[str, Any], inputs: dict[str, Any]) -> dict[str, dict[str, str | int]]:
        parameters = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
        doi = _normalize_doi(parameters.get("doi") or inputs.get("doi"))
        source_url = CROSSREF_API_BASE + quote(doi, safe="/")
        async with request_semaphore:
            message = await _fetch_crossref_message(doi, source_url, str(node.get("id") or "unknown"))

        report = _crossref_report(doi, source_url, message)
        try:
            artifact: ArtifactHandle = artifact_store.store_json_report(
                report,
                producer_node_id=str(node.get("id") or "unknown"),
                producer_run_id=node.get("_runtime_run_id"),
                file_name="crossref-doi-metadata.json",
                authorization_status="public_metadata",
            )
        except Exception as error:
            logger.exception("crossref_report_persist_failed node_id=%s", node.get("id"))
            raise WorkflowNodeFailure("NETWORK_RESULT_PERSIST_FAILED", "文献元数据已读取，但本机产物保存失败。") from error
        return {"paper_metadata": artifact.to_dict()}

    def dispatch(node: dict[str, Any], inputs: dict[str, Any]) -> ExternalWait:
        # The scheduler records WAITING_EXTERNAL while network I/O is outstanding.
        return ExternalWait(lookup(node, inputs), operation_code="CROSSREF_DOI_METADATA")

    return {CROSSREF_EXECUTOR_BINDING: dispatch}
