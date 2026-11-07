"""Load versioned, fixed template contracts without loading executable code."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


DEMO_PIPELINE_TEMPLATE = "research-smoke-v1"
DEMO_DATASET_VERSION = "dataset-synthetic-v1"
REGISTERED_TEMPLATE_IDS = (DEMO_PIPELINE_TEMPLATE,)
TEMPLATE_MANIFEST_DIR = Path(__file__).resolve().parents[1] / "data" / "templates"

_TEMPLATE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*-v[0-9]+$")
_EXPECTED_STATES = ["queued", "running", "succeeded", "failed"]
_EXPECTED_ERROR_CODES = [
    "DATA_QUALITY_BLOCKED",
    "PROPOSAL_CONFIG_MISMATCH",
    "QUEUE_UNAVAILABLE",
    "WORKER_EXECUTION_FAILED",
]
logger = logging.getLogger("ict.template_registry")


class TemplateRegistryError(ValueError):
    """A fixed template manifest is missing, invalid, or outside the code allowlist."""


class TemplateContractError(ValueError):
    """A value does not satisfy the declared fixed template contract."""


class TemplateFieldContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    type: Literal["string", "integer", "boolean"]
    required: bool = True
    minimum: int | None = None
    maximum: int | None = None
    const: str | int | bool | None = None

    @model_validator(mode="after")
    def validate_constraints(self) -> TemplateFieldContract:
        if self.type != "integer" and (self.minimum is not None or self.maximum is not None):
            raise ValueError("numeric bounds require an integer field")
        if (
            self.minimum is not None
            and self.maximum is not None
            and self.minimum > self.maximum
        ):
            raise ValueError("minimum cannot exceed maximum")
        if self.const is not None:
            expected_type = {"string": str, "integer": int, "boolean": bool}[self.type]
            if type(self.const) is not expected_type:
                raise ValueError("constant value must match the declared field type")
        return self


class TemplateResourceLimits(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    max_concurrent_runs: int = Field(ge=1, le=1)
    soft_timeout_seconds: int = Field(ge=1, le=25)
    hard_timeout_seconds: int = Field(ge=2, le=30)

    @model_validator(mode="after")
    def validate_timeouts(self) -> TemplateResourceLimits:
        if self.soft_timeout_seconds >= self.hard_timeout_seconds:
            raise ValueError("soft timeout must be less than hard timeout")
        return self


class TemplateManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    template_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*-v[0-9]+$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    executor: Literal["synthetic_smoke_v1"]
    dataset_version: str
    permission_scope: Literal["synthetic_dataset_manifest_read_only"]
    resource_limits: TemplateResourceLimits
    inputs: dict[str, TemplateFieldContract]
    parameters: dict[str, TemplateFieldContract]
    outputs: dict[str, TemplateFieldContract]
    states: list[Literal["queued", "running", "succeeded", "failed"]]
    error_codes: list[
        Literal[
            "DATA_QUALITY_BLOCKED",
            "PROPOSAL_CONFIG_MISMATCH",
            "QUEUE_UNAVAILABLE",
            "WORKER_EXECUTION_FAILED",
        ]
    ]


@dataclass(frozen=True)
class LoadedTemplateManifest:
    manifest: TemplateManifest
    sha256: str


def _field_matches(
    field: TemplateFieldContract | None,
    *,
    value_type: str,
    required: bool = True,
    minimum: int | None = None,
    maximum: int | None = None,
    const: str | int | bool | None = None,
) -> bool:
    """Keep editable metadata inside the behavior implemented by this executor."""
    return (
        field is not None
        and field.type == value_type
        and field.required is required
        and field.minimum == minimum
        and field.maximum == maximum
        and field.const == const
        and (const is None or type(field.const) is type(const))
    )


def _validate_fixed_contract(manifest: TemplateManifest) -> None:
    """Reject manifest changes that exceed the current compiled synthetic executor."""
    if (
        manifest.template_id != DEMO_PIPELINE_TEMPLATE
        or manifest.dataset_version != DEMO_DATASET_VERSION
        or manifest.permission_scope != "synthetic_dataset_manifest_read_only"
        or manifest.states != _EXPECTED_STATES
        or manifest.error_codes != _EXPECTED_ERROR_CODES
        or set(manifest.inputs) != {"dataset_version"}
        or set(manifest.parameters) != {"sample_limit"}
        or set(manifest.outputs)
        != {"task", "processed_count", "synthetic_only", "research_ready", "message"}
    ):
        raise TemplateRegistryError("template manifest exceeds the fixed executor contract")

    if not _field_matches(
        manifest.inputs.get("dataset_version"),
        value_type="string",
        const=DEMO_DATASET_VERSION,
    ):
        raise TemplateRegistryError("template input contract is unsupported")
    if not _field_matches(
        manifest.parameters.get("sample_limit"),
        value_type="integer",
        minimum=1,
        maximum=100,
    ):
        raise TemplateRegistryError("template parameter contract is unsupported")

    expected_outputs = {
        "task": ("string", "synthetic_smoke"),
        "processed_count": ("integer", None),
        "synthetic_only": ("boolean", True),
        "research_ready": ("boolean", False),
        "message": ("string", None),
    }
    for name, (value_type, const) in expected_outputs.items():
        minimum = 0 if name == "processed_count" else None
        if not _field_matches(
            manifest.outputs.get(name),
            value_type=value_type,
            minimum=minimum,
            const=const,
        ):
            raise TemplateRegistryError("template output contract is unsupported")


def load_template_manifest(template_id: str) -> LoadedTemplateManifest:
    """Load the one allowlisted manifest and pin its exact bytes for proposal hashing."""
    if template_id != DEMO_PIPELINE_TEMPLATE or not _TEMPLATE_ID_PATTERN.fullmatch(template_id):
        logger.error("template_manifest_rejected error_code=TEMPLATE_NOT_ALLOWLISTED")
        raise TemplateRegistryError("template is not allowlisted")

    manifest_path = TEMPLATE_MANIFEST_DIR / f"{template_id}.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = TemplateManifest.model_validate_json(manifest_bytes)
        _validate_fixed_contract(manifest)
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        logger.error(
            "template_manifest_unavailable error_type=%s",
            type(exc).__name__,
        )
        raise TemplateRegistryError("template manifest is unavailable or invalid") from exc
    except TemplateRegistryError as exc:
        logger.error(
            "template_manifest_contract_rejected error_type=%s",
            type(exc).__name__,
        )
        raise

    return LoadedTemplateManifest(
        manifest=manifest,
        sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )


def list_registered_template_manifests() -> list[LoadedTemplateManifest]:
    """List the explicitly registered global templates in stable order."""
    return [load_template_manifest(template_id) for template_id in REGISTERED_TEMPLATE_IDS]


def validate_template_values(
    contracts: Mapping[str, TemplateFieldContract],
    values: Mapping[str, object],
) -> None:
    """Validate a complete input, parameter, or result mapping with strict Python types."""
    if not isinstance(values, Mapping):
        raise TemplateContractError("template values must be an object")
    if any(not isinstance(name, str) for name in values) or set(values) - set(contracts):
        raise TemplateContractError("template values contain unsupported fields")

    for name, contract in contracts.items():
        if name not in values:
            if contract.required:
                raise TemplateContractError("template values are missing a required field")
            continue
        value = values[name]
        type_matches = {
            "string": lambda item: isinstance(item, str),
            "integer": lambda item: type(item) is int,
            "boolean": lambda item: type(item) is bool,
        }[contract.type](value)
        if not type_matches:
            raise TemplateContractError("template value has the wrong type")
        if contract.minimum is not None and value < contract.minimum:
            raise TemplateContractError("template value is below its minimum")
        if contract.maximum is not None and value > contract.maximum:
            raise TemplateContractError("template value exceeds its maximum")
        if contract.const is not None and (
            type(value) is not type(contract.const) or value != contract.const
        ):
            raise TemplateContractError("template value does not match its fixed value")
