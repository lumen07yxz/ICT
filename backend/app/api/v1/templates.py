"""Authenticated, global read-only catalog for registered workflow templates."""

from fastapi import APIRouter, Depends

from app.api.v1.projects import PipelineTemplateRead
from app.auth import DemoIdentity, get_demo_identity
from app.errors import AppError
from app.services.template_registry import TemplateRegistryError, list_registered_template_manifests


router = APIRouter(tags=["templates"])


@router.get("/api/v1/templates", response_model=list[PipelineTemplateRead])
def read_template_catalog(
    _identity: DemoIdentity = Depends(get_demo_identity),
) -> list[PipelineTemplateRead]:
    """List globally registered templates independently of project membership."""
    try:
        manifests = list_registered_template_manifests()
    except TemplateRegistryError as exc:
        raise AppError(503, "TEMPLATE_REGISTRY_UNAVAILABLE") from exc

    return [
        PipelineTemplateRead(
            **loaded.manifest.model_dump(),
            manifest_sha256=loaded.sha256,
        )
        for loaded in manifests
    ]
