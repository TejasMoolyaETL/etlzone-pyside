"""Bundled branding: app logo path and window icon (dev tree + PyInstaller)."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QWidget

# Stable Win32 App User Model ID — call before QApplication() so the taskbar shows our icon
# instead of a generic Python/host icon (SetCurrentProcessExplicitAppUserModelID).
_WIN_APP_ID = "Etlzone.Etlzone.Desktop.1"


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", ""))
    return _project_root()


def app_logo_path() -> Path | None:
    """Return ``app_logo.png`` path if the file exists."""
    p = _bundle_root() / "assets" / "app_logo.png"
    return p if p.is_file() else None


def app_icon_ico_path() -> Path | None:
    """Return ``app_icon.ico`` path if present (multi-size; best for Windows taskbar)."""
    p = _bundle_root() / "assets" / "app_icon.ico"
    return p if p.is_file() else None


def apply_windows_taskbar_app_id() -> None:
    """Windows only: set process AppUserModelID before any UI so the taskbar uses our window icon."""
    if sys.platform != "win32":
        return
    try:
        from ctypes import windll  # type: ignore[attr-defined]

        windll.shell32.SetCurrentProcessExplicitAppUserModelID(_WIN_APP_ID)
    except Exception:
        pass


def app_window_icon() -> QIcon:
    """Taskbar / window icon: prefer ``.ico``, then ``app_logo.png``."""
    for path in (app_icon_ico_path(), app_logo_path()):
        if path is not None:
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
    return QIcon()


def apply_window_icon(widget: QWidget) -> None:
    """Set ``setWindowIcon`` when a logo file is available."""
    icon = app_window_icon()
    if not icon.isNull():
        widget.setWindowIcon(icon)
