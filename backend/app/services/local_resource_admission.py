"""Conservative request checks for the first local execution runtime."""

from __future__ import annotations

import json
import logging
from collections.abc import Collection, Iterator, Mapping
from typing import Any

from app.services.local_artifacts import LocalArtifactError, LocalArtifactStore
from app.services.local_runtime_store import LocalRuntimeStoreError


logger = logging.getLogger("ict.local_runtime.admission")

# This is an admission policy for the demo runtime, not an OS-level hard limit.
LOCAL_RESOURCE_BUDGET = {
    "timeout_seconds": 600,
    # Two runs may each schedule two nodes; these per-node ceilings keep their
    # aggregate request within the conservative 2-core / 2-GiB demo budget.
    "cpu_millicores": 500,
    "memory_mb": 512,
    "gpu_count": 0,
    "gpu_memory_mb": 0,
    "max_input_bytes": 100 * 1024 * 1024,
}

# The first network adapter performs one bounded metadata GET and never reads
# local files or requests GPU resources.
NETWORK_RESOURCE_BUDGET = {
    "timeout_seconds": 30,
    "cpu_millicores": 250,
    "memory_mb": 128,
    "gpu_count": 0,
    "gpu_memory_mb": 0,
    "max_input_bytes": 0,
}


def _artifact_ids(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        artifact_id = value.get("artifact_id")
        if isinstance(artifact_id, str) and artifact_id:
            yield artifact_id
        for key, nested in value.items():
            # Folder source selections are stored in a bounded JSON parameter so
            # each member still receives the same admission checks as one CSV.
            if key == "files_json" and isinstance(nested, str):
                try:
                    nested = json.loads(nested)
                except json.JSONDecodeError as error:
                    raise LocalRuntimeStoreError(
                        "CSV_FOLDER_MANIFEST_INVALID",
                        "CSV 文件夹清单格式无效，请重新选择目录。",
                        status_code=422,
                    ) from error
            yield from _artifact_ids(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _artifact_ids(nested)


def _dependency_requirement(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or "@" not in value:
        raise LocalRuntimeStoreError(
            "COMPONENT_DEPENDENCY_INVALID", "组件依赖声明格式无效。", status_code=422
        )
    dependency_id, version = value.rsplit("@", 1)
    if not dependency_id.strip() or not version.strip():
        raise LocalRuntimeStoreError(
            "COMPONENT_DEPENDENCY_INVALID", "组件依赖声明格式无效。", status_code=422
        )
    return dependency_id.strip(), version.strip()


def _validate_target_component_capabilities(
    node: dict[str, Any],
    *,
    expected_target: str,
    available_dependency_versions: Mapping[str, str],
    executor_permission_capabilities: Mapping[str, Collection[str]],
) -> None:
    """Check one execution target, audited executor scopes, and exact dependency versions."""
    node_id = str(node.get("id") or "unknown")
    target_label = "本机" if expected_target == "local" else "网络"
    if node.get("execution_target") != expected_target:
        raise LocalRuntimeStoreError(
            f"{expected_target.upper()}_EXECUTION_TARGET_UNAVAILABLE",
            f"此节点不属于{target_label}执行目标。",
            status_code=422,
        )

    binding = node.get("executor_binding")
    if not isinstance(binding, str) or not binding:
        raise LocalRuntimeStoreError(
            f"{expected_target.upper()}_EXECUTOR_UNAVAILABLE",
            f"此{target_label}组件没有已登记的执行器。", status_code=422
        )
    allowed_permissions = executor_permission_capabilities.get(binding)
    if allowed_permissions is None:
        logger.warning(
            "runtime_executor_capability_missing target=%s node_id=%s component_id=%s binding=%s",
            expected_target,
            node_id, node.get("component_id"), binding,
        )
        raise LocalRuntimeStoreError(
            f"{expected_target.upper()}_EXECUTOR_UNAVAILABLE",
            f"此{target_label}组件没有已登记的执行器能力。", status_code=422
        )

    permissions = node.get("permissions")
    if not isinstance(permissions, list) or any(not isinstance(item, str) or not item for item in permissions):
        raise LocalRuntimeStoreError(
            "COMPONENT_PERMISSION_INVALID", "组件权限声明格式无效。", status_code=422
        )
    denied_permissions = sorted(set(permissions) - set(allowed_permissions))
    if denied_permissions:
        logger.warning(
            "runtime_permission_rejected target=%s node_id=%s component_id=%s permission_count=%s",
            expected_target, node_id, node.get("component_id"), len(denied_permissions),
        )
        raise LocalRuntimeStoreError(
            f"{expected_target.upper()}_PERMISSION_UNAVAILABLE",
            f"{target_label}执行器未获准使用组件声明的权限。", status_code=403
        )

    dependencies = node.get("dependencies", [])
    if not isinstance(dependencies, list):
        raise LocalRuntimeStoreError(
            "COMPONENT_DEPENDENCY_INVALID", "组件依赖声明格式无效。", status_code=422
        )
    for requirement in dependencies:
        dependency_id, required_version = _dependency_requirement(requirement)
        installed_version = available_dependency_versions.get(dependency_id)
        if installed_version != required_version:
            logger.warning(
                "runtime_dependency_unavailable target=%s node_id=%s component_id=%s dependency_id=%s required_version=%s available=%s",
                expected_target, node_id, node.get("component_id"), dependency_id, required_version,
                installed_version is not None,
            )
            raise LocalRuntimeStoreError(
                "COMPONENT_DEPENDENCY_UNAVAILABLE",
                f"{target_label}组件依赖未安装、接口不兼容或版本不匹配。",
                status_code=424,
            )


def validate_local_component_capabilities(
    node: dict[str, Any],
    *,
    available_dependency_versions: Mapping[str, str],
    executor_permission_capabilities: Mapping[str, Collection[str]],
) -> None:
    """Check the local target, audited executor scopes, and exact dependency versions."""
    _validate_target_component_capabilities(
        node,
        expected_target="local",
        available_dependency_versions=available_dependency_versions,
        executor_permission_capabilities=executor_permission_capabilities,
    )


def validate_network_component_capabilities(
    node: dict[str, Any],
    *,
    available_dependency_versions: Mapping[str, str],
    executor_permission_capabilities: Mapping[str, Collection[str]],
) -> None:
    """Check the network target, fixed executor scopes, and exact dependency versions."""
    _validate_target_component_capabilities(
        node,
        expected_target="network",
        available_dependency_versions=available_dependency_versions,
        executor_permission_capabilities=executor_permission_capabilities,
    )


def local_component_capability_blockers(
    node: dict[str, Any],
    *,
    available_dependency_versions: Mapping[str, str],
    executor_permission_capabilities: Mapping[str, Collection[str]],
) -> list[str]:
    """Return stable blockers for the component picker without hiding the contract."""
    try:
        validate_local_component_capabilities(
            node,
            available_dependency_versions=available_dependency_versions,
            executor_permission_capabilities=executor_permission_capabilities,
        )
    except LocalRuntimeStoreError as error:
        return [error.code]
    return []


def network_component_capability_blockers(
    node: dict[str, Any],
    *,
    available_dependency_versions: Mapping[str, str],
    executor_permission_capabilities: Mapping[str, Collection[str]],
) -> list[str]:
    """Return stable blockers for a registered network component."""
    try:
        validate_network_component_capabilities(
            node,
            available_dependency_versions=available_dependency_versions,
            executor_permission_capabilities=executor_permission_capabilities,
        )
    except LocalRuntimeStoreError as error:
        return [error.code]
    return []


def validate_local_plan_admission(
    plan: dict[str, Any],
    artifact_store: LocalArtifactStore,
    *,
    available_dependency_versions: Mapping[str, str],
    executor_permission_capabilities: Mapping[str, Collection[str]],
    network_dependency_versions: Mapping[str, str] | None = None,
    network_executor_permission_capabilities: Mapping[str, Collection[str]] | None = None,
) -> None:
    """Reject local/network nodes lacking permission, dependency, or resource admission."""
    for node in plan.get("nodes", []):
        if not isinstance(node, dict):
            raise LocalRuntimeStoreError(
                "EXECUTION_PLAN_NODE_INVALID", "执行计划包含无效节点。", status_code=422
            )
        target = node.get("execution_target")
        # Platform nodes still travel through the plan and are blocked by the
        # scheduler when no platform worker is registered; independent branches continue.
        if target not in ("local", "network"):
            continue
        if target == "network":
            validate_network_component_capabilities(
                node,
                available_dependency_versions=network_dependency_versions or {},
                executor_permission_capabilities=network_executor_permission_capabilities or {},
            )
            resource_budget = NETWORK_RESOURCE_BUDGET
        else:
            validate_local_component_capabilities(
                node,
                available_dependency_versions=available_dependency_versions,
                executor_permission_capabilities=executor_permission_capabilities,
            )
            resource_budget = LOCAL_RESOURCE_BUDGET
        permissions = set(node.get("permissions", []))
        limits = node.get("resource_limits")
        if not isinstance(limits, dict):
            raise LocalRuntimeStoreError(
                "RESOURCE_REQUEST_MISSING", "可运行组件没有声明资源需求，无法安全准入。", status_code=422
            )
        for resource_name, budget in resource_budget.items():
            requested = limits.get(resource_name)
            if requested is None:
                if node.get("executor_binding") is not None:
                    raise LocalRuntimeStoreError(
                        "RESOURCE_REQUEST_MISSING", "可运行组件必须声明资源需求。", status_code=422
                    )
                continue
            if type(requested) is not int or requested < 0:
                raise LocalRuntimeStoreError(
                    "RESOURCE_REQUEST_INVALID", "本机组件资源需求格式无效。", status_code=422
                )
            if requested > budget:
                logger.warning(
                    "local_run_admission_rejected node_id=%s component_id=%s resource=%s requested=%s budget=%s",
                    node.get("id"), node.get("component_id"), resource_name, requested, budget,
                )
                raise LocalRuntimeStoreError(
                    "LOCAL_RESOURCE_BUDGET_EXCEEDED",
                    "组件资源需求超过此执行目标当前准入上限。",
                    status_code=422,
                )

        # Only local components can declare readable ArtifactHandles in this runtime.
        if target != "local":
            continue
        max_input_bytes = limits.get("max_input_bytes")
        parameters = node.get("parameters") if isinstance(node.get("parameters"), dict) else {}
        total_input_bytes = 0
        for artifact_id in _artifact_ids(parameters):
            try:
                artifact = artifact_store.resolve(artifact_id).handle
            except LocalArtifactError as error:
                logger.warning(
                    "local_run_admission_artifact_unavailable node_id=%s artifact_id=%s error_code=%s",
                    node.get("id"), artifact_id, error.code,
                )
                raise LocalRuntimeStoreError(
                    error.code, "本机输入产物不可用，请重新导入后再运行。", status_code=422
                ) from error
            if "local:artifact:read" in permissions and artifact.authorization_status not in {
                "confirmed", "derived_from_confirmed_input"
            }:
                logger.warning(
                    "local_run_artifact_permission_rejected node_id=%s artifact_id=%s authorization_status=%s",
                    node.get("id"), artifact_id, artifact.authorization_status,
                )
                raise LocalRuntimeStoreError(
                    "ARTIFACT_AUTHORIZATION_REQUIRED",
                    "本机输入产物没有有效授权记录，请重新确认并导入。",
                    status_code=403,
                )
            if max_input_bytes is not None and artifact.size_bytes > max_input_bytes:
                logger.warning(
                    "local_run_admission_input_too_large node_id=%s artifact_id=%s size_bytes=%s limit_bytes=%s",
                    node.get("id"), artifact_id, artifact.size_bytes, max_input_bytes,
                )
                raise LocalRuntimeStoreError(
                    "LOCAL_INPUT_SIZE_LIMIT_EXCEEDED",
                    "本机输入文件超过此组件声明的大小上限。",
                    status_code=422,
                )
            total_input_bytes += artifact.size_bytes
            if max_input_bytes is not None and total_input_bytes > max_input_bytes:
                logger.warning(
                    "local_run_admission_total_input_too_large node_id=%s total_size_bytes=%s limit_bytes=%s",
                    node.get("id"), total_input_bytes, max_input_bytes,
                )
                raise LocalRuntimeStoreError(
                    "LOCAL_INPUT_SIZE_LIMIT_EXCEEDED",
                    "本机输入文件集合超过此组件声明的总大小上限。",
                    status_code=422,
                )
