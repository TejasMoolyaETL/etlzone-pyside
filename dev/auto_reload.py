from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer
from PySide6.QtWidgets import QApplication

# Directories to skip when watching
_SKIP_DIRS = {"__pycache__", ".git", ".venv", "venv", "node_modules"}

# Poll interval (ms). Shorter = faster reload; 800ms works well on Windows.
_POLL_INTERVAL_MS = 800

_DEBUG = os.getenv("ETL_AUTORELOAD_DEBUG", "").strip().lower() in ("1", "true", "yes")


def _collect_py_files(watch_dir: str) -> list[str]:
    watch_dir = os.path.normpath(os.path.abspath(watch_dir))
    py_files: list[str] = []
    for root, dirs, files in os.walk(watch_dir):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for file_name in files:
            if file_name.endswith(".py"):
                py_files.append(os.path.normpath(os.path.abspath(os.path.join(root, file_name))))
    return py_files


class DevAutoReloader(QObject):
    def __init__(self, app: QApplication, watch_dir: str) -> None:
        super().__init__()
        self.app = app
        self.watch_dir = os.path.normpath(os.path.abspath(watch_dir))
        self.restart_timer = QTimer(self)
        self.restart_timer.setSingleShot(True)
        self.restart_timer.setInterval(250)
        self.restart_timer.timeout.connect(self._restart_app)

        # File watcher (works on Linux/macOS; often misses saves on Windows)
        self.watcher = QFileSystemWatcher(self)
        py_files = _collect_py_files(self.watch_dir)
        if py_files:
            try:
                self.watcher.addPaths(py_files)
            except Exception:
                pass
        self.watcher.fileChanged.connect(self._on_file_changed)

        # Polling: reliable on Windows when editor saves
        self._py_files = py_files
        self._mtimes: dict[str, float] = {}
        for p in self._py_files:
            try:
                self._mtimes[p] = os.path.getmtime(p)
            except OSError:
                pass
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(_POLL_INTERVAL_MS)
        self.poll_timer.timeout.connect(self._poll_files)
        self.poll_timer.start()

        print(f"[auto-reload] enabled, watching {len(self._py_files)} .py files", flush=True)

    def _on_file_changed(self, path: str) -> None:
        if os.path.exists(path) and path not in self.watcher.files():
            try:
                self.watcher.addPath(path)
            except Exception:
                pass
        self._schedule_restart()

    def _schedule_restart(self) -> None:
        if _DEBUG:
            print("[auto-reload] change detected, restarting...", flush=True)
        self.restart_timer.start()

    def _poll_files(self) -> None:
        for path in list(self._py_files):
            try:
                if not os.path.exists(path):
                    continue
                mtime = os.path.getmtime(path)
                if self._mtimes.get(path) != mtime:
                    self._mtimes[path] = mtime
                    self._schedule_restart()
                    return
            except OSError:
                pass
        # Re-scan for new .py files
        new_list = _collect_py_files(self.watch_dir)
        for p in new_list:
            if p not in self._mtimes:
                try:
                    self._mtimes[p] = os.path.getmtime(p)
                    self._schedule_restart()
                    return
                except OSError:
                    pass
        self._py_files = new_list

    def _restart_app(self) -> None:
        cmd = [sys.executable] + sys.argv
        if _DEBUG:
            print(f"[auto-reload] exec: {cmd}", flush=True)
        # Use subprocess so restart works reliably on Windows (execv can be flaky there)
        try:
            subprocess.Popen(cmd, cwd=os.getcwd())
        except Exception:
            try:
                os.execv(sys.executable, cmd)
            except Exception:
                pass
        self.app.quit()


def enable_auto_reload(app: QApplication) -> DevAutoReloader | None:
    """Enable auto-reload during development unless ETL_DISABLE_AUTORELOAD is set."""
    if os.getenv("ETL_DISABLE_AUTORELOAD") == "1":
        return None

    watch_dir = os.path.normpath(os.path.abspath(str(Path(__file__).resolve().parents[1])))
    return DevAutoReloader(app=app, watch_dir=watch_dir)
