"""Local preferences for the desktop client; credentials are never stored here."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .api import DemoProjectApiClient, DesktopApiError


DEFAULT_API_BASE_URL = "http://127.0.0.1:8765"
SETTINGS_FILENAME = "settings.json"


def default_settings_path() -> Path:
    """Return the per-user settings location without relying on the working directory."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "ICTResearchWorkbench" / SETTINGS_FILENAME


def _validate_api_base_url(value: Any) -> str:
    if not isinstance(value, str):
        raise DesktopApiError("服务地址无效；远程服务必须使用 HTTPS。")
    # Reuse the API client's fail-closed URL rules for both settings and startup overrides.
    DemoProjectApiClient(value)
    return value


def load_api_base_url(path: str | Path | None = None) -> str:
    settings_path = Path(path) if path is not None else default_settings_path()
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(settings, dict):
            return DEFAULT_API_BASE_URL
        return _validate_api_base_url(settings.get("api_base_url"))
    except (OSError, json.JSONDecodeError, DesktopApiError, TypeError, ValueError):
        # Corrupt or inaccessible preferences must not prevent launching the desktop app.
        return DEFAULT_API_BASE_URL


def save_api_base_url(value: str, path: str | Path | None = None) -> None:
    safe_value = _validate_api_base_url(value)
    settings_path = Path(path) if path is not None else default_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # Write beside the destination and replace atomically, so interruption cannot leave
    # a partially written settings file that prevents the next launch.
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f"{settings_path.name}.",
            suffix=".tmp",
            dir=settings_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            json.dump({"api_base_url": safe_value}, temporary_file, ensure_ascii=False)
            temporary_file.write("\n")
        os.replace(temporary_path, settings_path)
    finally:
        if temporary_path and os.path.exists(temporary_path):
            os.unlink(temporary_path)


def resolve_api_base_url(
    cli_value: str | None = None,
    env_value: str | None = None,
    path: str | Path | None = None,
) -> str:
    """Resolve startup URL by CLI, environment, saved preference, then local default."""
    if cli_value is not None:
        return _validate_api_base_url(cli_value)
    if env_value is not None:
        return _validate_api_base_url(env_value)
    return load_api_base_url(path=path)
