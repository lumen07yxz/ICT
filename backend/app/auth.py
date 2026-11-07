"""Fixed demo bearer identities; tokens are supplied only via server environment."""

from dataclasses import dataclass
import hmac
from typing import Mapping

from fastapi import Header, Request

from app.errors import AppError


@dataclass(frozen=True)
class DemoIdentity:
    user_id: str
    role: str


def get_demo_identity(
    request: Request,
    authorization: str | None = Header(default=None),
) -> DemoIdentity:
    """Resolve one of the two demo roles without logging credentials."""
    tokens: Mapping[str, str | None] = request.app.state.demo_tokens
    operator_token = tokens.get("operator")
    viewer_token = tokens.get("viewer")

    if (
        not operator_token
        or not viewer_token
        or hmac.compare_digest(operator_token.encode("utf-8"), viewer_token.encode("utf-8"))
    ):
        raise AppError(503, "AUTH_NOT_CONFIGURED")

    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(401, "UNAUTHORIZED")

    supplied_token = authorization.removeprefix("Bearer ").strip()
    if not supplied_token:
        raise AppError(401, "UNAUTHORIZED")

    supplied_bytes = supplied_token.encode("utf-8")
    if hmac.compare_digest(supplied_bytes, operator_token.encode("utf-8")):
        return DemoIdentity(user_id="demo-operator", role="operator")
    if hmac.compare_digest(supplied_bytes, viewer_token.encode("utf-8")):
        return DemoIdentity(user_id="demo-viewer", role="viewer")
    raise AppError(401, "UNAUTHORIZED")
