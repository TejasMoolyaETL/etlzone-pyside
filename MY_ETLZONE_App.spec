# -*- mode: python ; coding: utf-8 -*-
import os
import re

from PyInstaller.utils.hooks import collect_all


def _write_version_info_for_exe() -> str:
    """Version resource so Task Manager / Properties show Product name \"Etlzone\" (not just the .exe name)."""
    root = os.path.dirname(os.path.abspath(SPEC))
    with open(os.path.join(root, 'core', 'app_version.py'), encoding='utf-8') as f:
        m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', f.read())
    ver = m.group(1) if m else '1.0.0'
    parts: list[int] = []
    for seg in ver.split('.'):
        try:
            parts.append(int(seg))
        except ValueError:
            parts.append(0)
    while len(parts) < 4:
        parts.append(0)
    tup = tuple(parts[:4])
    ver_dot = '.'.join(str(x) for x in tup)
    bdir = os.path.join(root, 'build')
    os.makedirs(bdir, exist_ok=True)
    out = os.path.join(bdir, 'etlzone_version_info.txt')
    content = f"""# utf-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={tup},
    prodvers={tup},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
    ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u'Etlzone'),
        StringStruct(u'FileDescription', u'Etlzone'),
        StringStruct(u'FileVersion', u'{ver_dot}'),
        StringStruct(u'InternalName', u'Etlzone-windows'),
        StringStruct(u'LegalCopyright', u'Etlzone'),
        StringStruct(u'OriginalFilename', u'Etlzone-windows.exe'),
        StringStruct(u'ProductName', u'Etlzone'),
        StringStruct(u'ProductVersion', u'{ver}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
"""
    with open(out, 'w', encoding='utf-8') as f:
        f.write(content)
    return out


_VERSION_INFO = _write_version_info_for_exe()

_root_dir = os.path.dirname(os.path.abspath(SPEC))
_app_icon = os.path.join(_root_dir, "assets", "app_icon.ico")

datas = [
    ("assets/app_logo.png", "assets"),
    ("assets/app_icon.ico", "assets"),
]
binaries = []
hiddenimports = []
tmp_ret = collect_all('PySide6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
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
    name='Etlzone-windows',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=_VERSION_INFO,
    icon=_app_icon if os.path.isfile(_app_icon) else None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Etlzone',
)
