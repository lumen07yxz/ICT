"""Launch the native desktop client."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import tempfile
import tkinter as tk
from logging.handlers import RotatingFileHandler
from pathlib import Path
from tkinter import messagebox

from .api import DemoProjectApiClient, DesktopApiError
from .main_window import MainWindow
from .settings import resolve_api_base_url, save_api_base_url


def _configure_logging() -> None:
    """Write rotated local diagnostics without recording request credentials."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    roots = [Path(local_app_data)] if local_app_data else []
    roots.append(Path(tempfile.gettempdir()))

    for root in roots:
        try:
            log_dir = root / "ICTResearchWorkbench" / "logs"
            log_dir.mkdir(parents=True, exist_ok=True)
            handler = RotatingFileHandler(
                log_dir / "desktop.log",
                maxBytes=1_000_000,
                backupCount=3,
                encoding="utf-8",
            )
        except OSError:
            continue

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
            handlers=[handler],
            force=True,
        )
        return

    logging.basicConfig(level=logging.CRITICAL, handlers=[logging.NullHandler()], force=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ICT Windows research desktop client")
    parser.add_argument(
        "--api-base-url",
        default=None,
        help="本机 HTTP 或远程 HTTPS 后端地址；不会保存访问凭据",
    )
    args = parser.parse_args(argv)
    _configure_logging()

    try:
        api_base_url = resolve_api_base_url(
            cli_value=args.api_base_url,
            env_value=os.environ.get("ICT_API_BASE_URL"),
        )
        client = DemoProjectApiClient(api_base_url)
    except DesktopApiError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("服务地址无效", str(exc), parent=root)
        root.destroy()
        return 2

    root = tk.Tk()
    MainWindow(root, client=client, service_url=api_base_url, settings_saver=save_api_base_url)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
