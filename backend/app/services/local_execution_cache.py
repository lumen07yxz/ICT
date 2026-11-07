"""Input-signature cache wrappers for deterministic local executors."""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import platform
import sys
from typing import Any

from app.services.local_artifacts import LocalArtifactError, LocalArtifactStore
from app.services.local_runtime_store import LocalRuntimeStore, LocalRuntimeStoreError
from app.services.workflow_scheduler import CachedNodeOutput, Executor, ExternalWait


logger = logging.getLogger("ict.local_runtime.cache")


def _normalize_for_signature(value: Any, artifact_store: LocalArtifactStore) -> tuple[Any, bool]:
    """Replace artifact IDs with content hashes; unknown references disable caching."""
    if isinstance(value, dict):
        artifact_id = value.get("artifact_id")
        if isinstance(artifact_id, str) and artifact_id:
            try:
                resolved = artifact_store.resolve(artifact_id)
                handle = resolved.handle
                digest = hashlib.sha256()
                with resolved.path.open("rb") as source:
                    for chunk in iter(lambda: source.read(1024 * 1024), b""):
                        digest.update(chunk)
                if digest.hexdigest() != handle.sha256:
                    logger.warning("local_node_cache_input_hash_mismatch artifact_id=%s", artifact_id)
                    return {"unverified_artifact_id": artifact_id}, False
            except (LocalArtifactError, OSError):
                logger.exception("local_node_cache_input_unavailable artifact_id=%s", artifact_id)
                return {"unresolved_artifact_id": artifact_id}, False
            return {
                # Preserve the exact source handle so a cached report remains tied to
                # the same imported artifact identity as its provenance record.
                "artifact_id": artifact_id,
                "sha256": handle.sha256,
                "media_type": handle.media_type,
                "size_bytes": handle.size_bytes,
                # Folder collections add relative paths to handles; path changes
                # must invalidate a cached collection result even when bytes match.
                **(
                    {"relative_path": value["relative_path"]}
                    if isinstance(value.get("relative_path"), str)
                    else {}
                ),
            }, True
        normalized: dict[str, Any] = {}
        cacheable = True
        for key, nested in value.items():
            if key == "files_json" and isinstance(nested, str):
                try:
                    nested = json.loads(nested)
                except json.JSONDecodeError:
                    logger.warning("local_node_cache_folder_manifest_invalid")
                    manifest_hash = hashlib.sha256(nested.encode("utf-8")).hexdigest()
                    return {"invalid_folder_manifest_sha256": manifest_hash}, False
            normalized_value, nested_cacheable = _normalize_for_signature(nested, artifact_store)
            normalized[key] = normalized_value
            cacheable = cacheable and nested_cacheable
        return normalized, cacheable
    if isinstance(value, list):
        normalized_values = []
        cacheable = True
        for nested in value:
            normalized_value, nested_cacheable = _normalize_for_signature(nested, artifact_store)
            normalized_values.append(normalized_value)
            cacheable = cacheable and nested_cacheable
        return normalized_values, cacheable
    return value, True


def _signature(node: dict[str, Any], inputs: dict[str, Any], artifact_store: LocalArtifactStore) -> str | None:
    if not node.get("implementation_digest"):
        return None
    normalized_parameters, parameters_cacheable = _normalize_for_signature(
        node.get("parameters", {}), artifact_store
    )
    normalized_inputs, inputs_cacheable = _normalize_for_signature(inputs, artifact_store)
    if not parameters_cacheable or not inputs_cacheable:
        return None
    signature_document = {
        "schema": "ict.input-signature.v1",
        "component_id": node.get("component_id"),
        "component_version": node.get("component_version"),
        "component_contract_hash": node.get("component_contract_hash"),
        "executor_version": node.get("executor_version"),
        "implementation_digest": node.get("implementation_digest"),
        "dependencies": node.get("dependencies", []),
        "parameters": normalized_parameters,
        "upstream_inputs": normalized_inputs,
        "runtime_environment": {
            "python": sys.version,
            "platform": platform.system(),
        },
    }
    try:
        encoded = json.dumps(
            signature_document, ensure_ascii=False, allow_nan=False,
            sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        logger.exception("local_node_cache_signature_unserializable node_id=%s", node.get("id"))
        return None
    return hashlib.sha256(encoded).hexdigest()


def build_cached_executor_registry(
    executors: dict[str, Executor],
    *,
    run_store: LocalRuntimeStore,
    artifact_store: LocalArtifactStore,
    run_id: str,
) -> dict[str, Executor]:
    """Cache deterministic executor outputs while retaining per-run node records."""
    wrapped: dict[str, Executor] = {}
    for binding, executor in executors.items():
        def invoke_with_cache(
            node: dict[str, Any],
            inputs: dict[str, Any],
            *,
            _executor: Executor = executor,
            _binding: str = binding,
        ) -> Any:
            executor_node = {**node, "_runtime_run_id": run_id}
            if node.get("cache_policy") != "input_signature":
                return _executor(executor_node, inputs)

            signature_hash = _signature(node, inputs, artifact_store)
            if signature_hash is not None:
                cached = run_store.get_cached_node_output(signature_hash)
                if cached is not None:
                    logger.info(
                        "local_node_cache_hit node_id=%s component_id=%s signature_hash=%s",
                        node.get("id"), node.get("component_id"), signature_hash,
                    )
                    return CachedNodeOutput(cached)
                logger.info(
                    "local_node_cache_miss node_id=%s component_id=%s signature_hash=%s",
                    node.get("id"), node.get("component_id"), signature_hash,
                )

            def cache_output(output: Any) -> None:
                if signature_hash is None:
                    return
                try:
                    run_store.store_cached_node_output(signature_hash, output)
                except LocalRuntimeStoreError:
                    # Cache persistence is an optimization; a successful node remains successful.
                    logger.exception(
                        "local_node_cache_write_skipped node_id=%s binding=%s",
                        node.get("id"), _binding,
                    )

            async def finish_and_cache(awaitable: Any) -> Any:
                output = await awaitable
                cache_output(output)
                return output

            result = _executor(executor_node, inputs)
            if isinstance(result, ExternalWait):
                return ExternalWait(finish_and_cache(result.awaitable), operation_code=result.operation_code)
            if inspect.isawaitable(result):
                return finish_and_cache(result)
            cache_output(result)
            return result

        wrapped[binding] = invoke_with_cache
    return wrapped
