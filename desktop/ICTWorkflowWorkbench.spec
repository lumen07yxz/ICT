# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import copy_metadata

PROJECT_ROOT = Path(SPECPATH).resolve().parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
DESKTOP_ROOT = PROJECT_ROOT / "desktop"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

if not (FRONTEND_DIST / "index.html").is_file():
    raise FileNotFoundError(f"Run the frontend build before packaging: {FRONTEND_DIST}")

datas = [
    (
        str(path),
        (
            f"frontend/dist/{path.parent.relative_to(FRONTEND_DIST).as_posix()}"
            if path.parent != FRONTEND_DIST
            else "frontend/dist"
        ),
    )
    for path in FRONTEND_DIST.rglob("*")
    if path.is_file()
]
datas += [
    (str(DESKTOP_ROOT / "ict_desktop" / "manifest_quality.py"), "desktop/ict_desktop"),
    (str(BACKEND_ROOT / "app" / "services" / "local_artifacts.py"), "app/services"),
    (str(BACKEND_ROOT / "app" / "services" / "local_csv_executor.py"), "app/services"),
    (str(BACKEND_ROOT / "app" / "services" / "network_crossref_executor.py"), "app/services"),
]
datas += copy_metadata("httpx")

a = Analysis(
    [str(DESKTOP_ROOT / "workflow_shell.py")],
    pathex=[str(BACKEND_ROOT), str(DESKTOP_ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "app.local_runtime",
        "app.services.local_csv_executor",
        "app.services.network_crossref_executor",
        "httpx",
        "ict_desktop.manifest_quality",
        "uvicorn.lifespan.on",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "unittest"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="ICTWorkflowWorkbench",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(DESKTOP_ROOT / "assets" / "ict-workbench.ico"),
    runtime_tmpdir=None,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
