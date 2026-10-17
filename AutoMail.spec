# PyInstaller : un seul AutoMail.exe, sans console, front compilé embarqué.
#
#   npm --prefix frontend ci && npm --prefix frontend run build
#   pyinstaller AutoMail.spec --noconfirm
#
# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

root = Path(SPECPATH)
dist = root / "frontend" / "dist"
if not (dist / "index.html").exists():
    raise SystemExit("frontend/dist est absent : lance d'abord « npm run build » dans frontend/.")

hidden = [
    # uvicorn charge ses protocoles par nom
    *collect_submodules("uvicorn"),
    # keyring choisit son backend à l'exécution (Gestionnaire d'identification Windows)
    *collect_submodules("keyring.backends"),
    "multipart",
    "python_multipart",
]
if sys.platform == "win32":
    hidden += [
        "win32ctypes.core",
        "win32ctypes.pywin32.win32cred",
        "webview.platforms.edgechromium",
        "webview.platforms.winforms",
        "clr",
    ]

a = Analysis(
    ["automail.py"],
    pathex=[str(root)],
    datas=[(str(dist), "frontend_dist")],
    hiddenimports=hidden,
    excludes=["tkinter", "pytest", "PyQt5", "PyQt6", "PySide2", "PySide6", "gi"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AutoMail",
    console=False,
    icon=str(root / "assets" / "icon.ico"),
    upx=False,
    runtime_tmpdir=None,
)
