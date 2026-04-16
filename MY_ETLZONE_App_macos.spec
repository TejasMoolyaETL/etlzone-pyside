# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations

import os

from PyInstaller.utils.hooks import collect_all


project_root = os.path.abspath(SPECPATH)

datas = [
    (os.path.join(project_root, "assets"), "assets"),
]
binaries = []
hiddenimports = []

login_image = os.path.join(project_root, "login_image.jpg")
if os.path.exists(login_image):
    datas.append((login_image, "."))

tmp_ret = collect_all("PySide6")
datas += tmp_ret[0]
binaries += tmp_ret[1]
hiddenimports += tmp_ret[2]


a = Analysis(
    ["main.py"],
    pathex=[project_root],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Etlzone",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Etlzone",
)

app = BUNDLE(
    coll,
    name="Etlzone.app",
    icon=None,
    bundle_identifier="com.etlzone.app",
)
