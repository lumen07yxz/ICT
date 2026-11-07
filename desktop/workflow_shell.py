"""Windows shell that serves the packaged React workbench and local runtime."""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


APP_MUTEX_NAME = "Local\\ICT.WorkflowWorkbench"
DEFAULT_PORT = 8767
PORT_SCAN_END = 8780


def resource_path(relative_path: str) -> Path:
    """Resolve bundled files from PyInstaller or the source checkout."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if isinstance(bundle_root, str):
        return Path(bundle_root) / relative_path
    return Path(__file__).resolve().parents[1] / relative_path


def app_data_root() -> Path:
    """Keep workflow databases, artifacts, logs, and browser cache out of install folders."""
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local_app_data) if local_app_data else Path.home() / "AppData" / "Local"
    return base / "ICT" / "WorkflowWorkbench"


def configure_logging(log_dir: Path) -> Path:
    """Persist runtime diagnostics without logging request bodies or credentials."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "workflow-runtime.log"
    handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)
    for logger_name in ("uvicorn", "uvicorn.error", "ict.local_runtime.api"):
        scoped_logger = logging.getLogger(logger_name)
        scoped_logger.handlers.clear()
        scoped_logger.addHandler(handler)
        scoped_logger.setLevel(logging.INFO)
        scoped_logger.propagate = False
    return log_path


def show_message(message: str, *, error: bool = True) -> None:
    """Show startup failures in the windowed build where no console is available."""
    if os.name == "nt":
        icon = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(None, message, "ICT 工作流桌面端", icon)


def acquire_single_instance_mutex() -> tuple[Any | None, bool]:
    """Prevent two launchers from racing for the local port and browser profile."""
    if os.name != "nt":
        return None, True
    kernel = ctypes.windll.kernel32
    handle = kernel.CreateMutexW(None, False, APP_MUTEX_NAME)
    if not handle:
        raise OSError("无法创建 ICT 工作流桌面端单实例锁。")
    already_running = kernel.GetLastError() == 183
    return handle, not already_running


def release_single_instance_mutex(handle: Any | None) -> None:
    if handle and os.name == "nt":
        ctypes.windll.kernel32.CloseHandle(handle)


def _read_local_health(origin: str) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(f"{origin}/health", timeout=0.4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", port))
        except OSError:
            return False
        return True


def select_runtime_port(state_dir: Path) -> tuple[int, bool]:
    """Reuse a compatible local UI server or select a stable available loopback port."""
    configured_port = os.environ.get("ICT_LOCAL_RUNTIME_PORT", "").strip()
    saved_port_path = state_dir / "desktop-port.txt"
    saved_port = None
    try:
        saved_port = int(saved_port_path.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        pass

    if configured_port:
        try:
            candidates = [int(configured_port)]
        except ValueError as error:
            raise ValueError("ICT_LOCAL_RUNTIME_PORT 必须是有效端口号。") from error
    else:
        candidates = [port for port in (saved_port, DEFAULT_PORT) if port is not None]
        candidates.extend(range(DEFAULT_PORT + 1, PORT_SCAN_END + 1))

    seen: set[int] = set()
    for port in candidates:
        if port in seen or not 1024 <= port <= 65535:
            continue
        seen.add(port)
        origin = f"http://127.0.0.1:{port}"
        health = _read_local_health(origin)
        if health and health.get("status") == "ok" and health.get("mode") == "local" and health.get("frontend_served") is True:
            return port, False
        if _port_is_free(port):
            if not configured_port:
                state_dir.mkdir(parents=True, exist_ok=True)
                saved_port_path.write_text(str(port), encoding="ascii")
            return port, True
    raise RuntimeError("没有可用的本机工作流端口；请关闭占用端口的程序后重试。")


def find_edge_executable() -> Path | None:
    """Find the Windows Edge installation used for the standalone app window."""
    via_path = shutil.which("msedge.exe") or shutil.which("msedge")
    if via_path:
        return Path(via_path)
    program_files = [
        os.environ.get("ProgramFiles(x86)", ""),
        os.environ.get("ProgramFiles", ""),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    for base in (Path(value) for value in program_files if value):
        candidate = base / "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if candidate.is_file():
            return candidate
    return None


def start_runtime(app_root: Path, log_path: Path, port: int):
    """Start FastAPI on loopback and wait until both UI and API routes are ready."""
    backend_root = resource_path("backend")
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    import uvicorn

    from app.local_runtime import create_local_runtime_app

    frontend_root = resource_path("frontend/dist")
    if not (frontend_root / "index.html").is_file():
        raise FileNotFoundError(f"前端资源包缺少 index.html：{frontend_root}")

    origin = f"http://127.0.0.1:{port}"
    runtime_app = create_local_runtime_app(
        root=app_root / "runtime",
        allowed_origins={origin},
        static_dir=frontend_root,
    )
    config = uvicorn.Config(
        runtime_app,
        host="127.0.0.1",
        port=port,
        log_config=None,
        access_log=False,
        log_level="info",
    )
    server = uvicorn.Server(config)
    startup_errors: list[BaseException] = []

    def run_server() -> None:
        try:
            server.run()
        except BaseException as error:
            startup_errors.append(error)
            logging.getLogger("ict.desktop.shell").exception("local_runtime_thread_failed")

    thread = threading.Thread(target=run_server, name="ict-local-runtime", daemon=True)
    thread.start()
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if startup_errors:
            raise RuntimeError("本机运行时启动失败，请查看运行日志。") from startup_errors[0]
        if not thread.is_alive():
            raise RuntimeError("本机运行时提前退出，请查看运行日志。")
        if server.started:
            health = _read_local_health(origin)
            if health and health.get("frontend_served") is True:
                logging.getLogger("ict.desktop.shell").info(
                    "desktop_runtime_ready host=127.0.0.1 port=%s log_path=%s", port, log_path
                )
                return server, thread, origin
        time.sleep(0.1)
    server.should_exit = True
    thread.join(timeout=3)
    raise TimeoutError("本机运行时未在 20 秒内完成启动。")


def _serve_until_stopped(thread: threading.Thread) -> None:
    """Support diagnostics without opening an Edge window."""
    try:
        while thread.is_alive():
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="ICT 本机工作流桌面端")
    parser.add_argument("--serve-only", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    app_root = app_data_root()
    log_path = configure_logging(app_root / "logs")
    logger = logging.getLogger("ict.desktop.shell")
    mutex_handle = None
    server = None
    server_thread = None
    edge_process = None

    try:
        mutex_handle, is_primary = acquire_single_instance_mutex()
        if not is_primary:
            show_message("ICT 工作流桌面端已经运行，请切换到已打开的工作流窗口。", error=False)
            return 0

        port, should_start = select_runtime_port(app_root)
        origin = f"http://127.0.0.1:{port}"
        if should_start:
            server, server_thread, origin = start_runtime(app_root, log_path, port)
        else:
            logger.info("reusing_desktop_runtime port=%s", port)

        if args.serve_only:
            if server_thread is not None:
                _serve_until_stopped(server_thread)
            return 0

        edge = find_edge_executable()
        if edge is None:
            raise FileNotFoundError("未找到 Microsoft Edge；ICT 桌面端需要 Edge 打开本机工作台。")

        profile_dir = app_root / "browser-profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        edge_process = subprocess.Popen(
            [
                str(edge),
                f"--app={origin}/",
                f"--user-data-dir={profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-mode",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.info("desktop_window_opened port=%s browser_pid=%s", port, edge_process.pid)
        return_code = edge_process.wait()
        logger.info("desktop_window_closed browser_exit_code=%s", return_code)
        return 0
    except Exception as error:
        logger.exception("desktop_shell_failed error_type=%s", type(error).__name__)
        show_message(f"ICT 工作流桌面端启动失败。\n\n{error}\n\n诊断日志：{log_path}")
        return 1
    finally:
        if edge_process is not None and edge_process.poll() is None:
            edge_process.terminate()
        if server is not None and server_thread is not None and server_thread.is_alive():
            server.should_exit = True
            server_thread.join(timeout=10)
            if server_thread.is_alive():
                server.force_exit = True
                server_thread.join(timeout=2)
        release_single_instance_mutex(mutex_handle)


if __name__ == "__main__":
    raise SystemExit(main())
