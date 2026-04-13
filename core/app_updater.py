"""Background download and detached launch for in-app auto-updates.

Uses :mod:`urllib` (no extra dependencies). Supported payloads:

* **Inno Setup ``MY_ETLZONE_Setup_*.exe``** (recommended) → launch that file; with
  ``inno_silent=True``, passes ``/VERYSILENT`` / ``/CLOSEAPPLICATIONS`` so the install
  upgrades in place and the ``.iss`` ``[Run]`` entry can restart the app.
* **``.zip``** of the PyInstaller ``onedir`` folder (legacy) → extract to a temp folder,
  find the main ``.exe``, launch it detached, then quit.

1. Version API → ``downloadUrl`` (+ optional ``checksum`` / ``sha256`` for the **downloaded** file).
2. :class:`DownloadUpdateWorker` streams to a temp ``.exe`` or ``.zip``.
3. Verify SHA-256 (optional), then :func:`resolve_launch_path` → :func:`launch_installer_and_quit`.

Set ``ETL_UPDATE_MAIN_EXE`` (e.g. ``MY_ETLZONE_App.exe``) if your zip uses a different name.

For the Inno installer, restart is handled by the installer; for a zip bundle the new
process is started and the old app exits.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, QCoreApplication, Signal, Slot
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

# Chunk size for streaming download (bytes).
_READ_CHUNK = 256 * 1024

# Executable name inside an extracted zip (PyInstaller onedir: MY_ETLZONE_App.exe next to _internal).
def _default_main_exe_name() -> str:
    n = (os.getenv("ETL_UPDATE_MAIN_EXE") or "MY_ETLZONE_App.exe").strip()
    return n if n.lower().endswith(".exe") else f"{n}.exe"


def verify_file_sha256(path: str, expected_hex: str) -> bool:
    """Return True if file SHA-256 (hex, any case) matches ``expected_hex``."""
    want = (expected_hex or "").strip().lower()
    if not want:
        return False
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest() == want


class DownloadUpdateWorker(QObject):
    """Runs on a ``QThread``; streams ``download_url`` to ``dest_path``.

    Emits byte progress for UI; supports cooperative cancel via ``cancel_event``.
    """

    # Bytes received, total from Content-Length or -1 if unknown
    progress = Signal(int, int)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        download_url: str,
        dest_path: str,
        *,
        cancel_event: threading.Event | None = None,
        timeout_s: float = 300.0,
    ) -> None:
        super().__init__()
        self._url = (download_url or "").strip()
        self._dest = dest_path
        self._cancel_event = cancel_event or threading.Event()
        self._timeout_s = timeout_s

    def request_cancel(self) -> None:
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        if not self._url:
            self.failed.emit("Download URL is empty.")
            return
        tmp_dir = os.path.dirname(self._dest)
        os.makedirs(tmp_dir, exist_ok=True)
        partial = f"{self._dest}.part"
        try:
            if os.path.isfile(partial):
                os.remove(partial)
        except OSError as exc:
            logger.warning("Could not remove stale partial download: %s", exc)

        headers = {"User-Agent": "MY-ETLZONE-App/1.0"}
        req = Request(self._url, headers=headers, method="GET")
        logger.info("Starting update download: %s", self._url)
        try:
            with urlopen(req, timeout=self._timeout_s) as resp:
                total = -1
                cl = resp.headers.get("Content-Length")
                if cl is not None:
                    try:
                        total = int(cl)
                    except (TypeError, ValueError):
                        total = -1
                done = 0
                with open(partial, "wb") as out:
                    while True:
                        if self._cancel_event.is_set():
                            out.flush()
                            os.fsync(out.fileno())
                            try:
                                os.remove(partial)
                            except OSError:
                                pass
                            self.failed.emit("Download cancelled.")
                            return
                        chunk = resp.read(_READ_CHUNK)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        self.progress.emit(done, total)
        except HTTPError as exc:
            logger.exception("Update download HTTP error: %s", exc)
            try:
                os.remove(partial)
            except OSError:
                pass
            self.failed.emit(f"Download failed (HTTP {getattr(exc, 'code', 'error')}).")
            return
        except (URLError, TimeoutError, OSError, ValueError) as exc:
            logger.exception("Update download failed: %s", exc)
            try:
                os.remove(partial)
            except OSError:
                pass
            self.failed.emit(f"Download failed: {exc}")
            return

        try:
            os.replace(partial, self._dest)
        except OSError as exc:
            logger.exception("Could not finalize download file: %s", exc)
            self.failed.emit(f"Could not save installer: {exc}")
            return

        logger.info("Update download complete: %s (%s bytes)", self._dest, os.path.getsize(self._dest))
        self.finished_ok.emit(self._dest)


def make_temp_download_path(suggested_name: str = "update.bin") -> str:
    """Temp path for a downloaded update; preserves ``.zip`` or ``.exe`` from ``suggested_name``."""
    base = tempfile.gettempdir()
    safe = "".join(c for c in suggested_name if c.isalnum() or c in "._- ") or "update"
    low = safe.lower()
    # CDN / mistaken names like ``App.zip.exe`` — save as ``.zip`` so we never try to execute a zip.
    if low.endswith(".zip.exe"):
        safe = safe[:-4]
        low = safe.lower()
    if not (low.endswith(".exe") or low.endswith(".zip")):
        safe = f"{safe}.exe"
    unique = uuid.uuid4().hex[:12]
    return os.path.join(base, f"etlzone_update_{unique}_{safe}")


def make_temp_installer_path(suggested_name: str = "MY_ETLZONE_update.exe") -> str:
    """Backward-compatible alias for :func:`make_temp_download_path`."""
    return make_temp_download_path(suggested_name)


def _is_zip_archive(path: str) -> bool:
    return os.path.isfile(path) and zipfile.is_zipfile(path)


def extract_zip_safely(zip_path: str, dest_dir: str) -> None:
    """Extract ``zip_path`` into ``dest_dir`` with zip-slip protection."""
    dest_dir = os.path.abspath(dest_dir)
    os.makedirs(dest_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            rel = info.filename.replace("\\", "/").strip()
            if not rel or rel.startswith("/"):
                raise ValueError(f"Unsafe path in zip: {info.filename!r}")
            parts = rel.split("/")
            if ".." in parts:
                raise ValueError(f"Unsafe path in zip: {info.filename!r}")
            target = os.path.join(dest_dir, *parts)
            abs_target = os.path.abspath(target)
            if abs_target != dest_dir and not abs_target.startswith(dest_dir + os.sep):
                raise ValueError(f"Zip slip blocked: {info.filename!r}")
            parent = os.path.dirname(abs_target)
            os.makedirs(parent, exist_ok=True)
            with zf.open(info, "r") as src, open(abs_target, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)


def find_main_executable_in_extract(root: str, exe_name: str) -> str | None:
    """Locate ``exe_name`` under ``root`` (top level, one subfolder, or shallow walk)."""
    root = os.path.abspath(root)
    direct = os.path.join(root, exe_name)
    if os.path.isfile(direct):
        return direct
    try:
        for entry in sorted(os.listdir(root)):
            sub = os.path.join(root, entry)
            if os.path.isdir(sub):
                p = os.path.join(sub, exe_name)
                if os.path.isfile(p):
                    return p
    except OSError:
        pass
    for dirpath, dirnames, filenames in os.walk(root):
        rel = os.path.relpath(dirpath, root)
        depth = 0 if rel == "." else rel.count(os.sep) + 1
        if depth >= 5:
            dirnames.clear()
            continue
        if exe_name in filenames:
            return os.path.join(dirpath, exe_name)
    return None


def resolve_launch_path(
    downloaded_path: str,
    *,
    main_exe_name: str | None = None,
) -> str:
    """Return absolute path to the ``.exe`` to start.

    If ``downloaded_path`` is a ``.zip`` (or zip by magic), extracts to a new temp directory
    and returns the path to ``main_exe_name`` inside it.

    Raises:
        ValueError: missing file, bad zip, or executable not found.
    """
    path = os.path.abspath(downloaded_path)
    if not os.path.isfile(path):
        raise ValueError("Downloaded update file is missing.")

    exe_name = (main_exe_name or _default_main_exe_name()).strip()
    if not exe_name.lower().endswith(".exe"):
        exe_name = f"{exe_name}.exe"

    # Prefer zip-by-content before trusting the extension (fixes ``*.zip.exe`` or wrong suffix).
    looks_zip_name = path.lower().endswith(".zip") or path.lower().endswith(".zip.exe")
    if _is_zip_archive(path) or looks_zip_name:
        extract_root = os.path.join(
            tempfile.gettempdir(),
            f"etlzone_update_extract_{uuid.uuid4().hex[:12]}",
        )
        logger.info("Extracting update zip to %s", extract_root)
        try:
            os.makedirs(extract_root, exist_ok=True)
            extract_zip_safely(path, extract_root)
        except (OSError, ValueError, zipfile.BadZipFile) as exc:
            logger.exception("Zip extract failed: %s", exc)
            try:
                shutil.rmtree(extract_root, ignore_errors=True)
            except OSError:
                pass
            raise ValueError(f"Could not extract update archive: {exc}") from exc

        exe_path = find_main_executable_in_extract(extract_root, exe_name)
        if not exe_path:
            raise ValueError(
                f"Could not find {exe_name} inside the update zip. "
                f"Include the full app folder (exe + _internal) and set ETL_UPDATE_MAIN_EXE if the name differs."
            )
        logger.info("Resolved update launch target: %s", exe_path)
        return exe_path

    low = path.lower()
    if not low.endswith(".exe"):
        raise ValueError("Update must be a .exe file or a .zip containing the application.")
    if _is_zip_archive(path):
        raise ValueError(
            "Downloaded file is a zip archive but was saved with a .exe name. "
            "Use a .zip URL/filename or fix the server Content-Disposition name."
        )
    return path


# Inno Setup 6 — silent in-place upgrade (no extra prompts; app relaunch via [Run] in .iss).
_INNO_SILENT_ARGS = (
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",  # suppress “restart Windows” prompt only
    "/CLOSEAPPLICATIONS",
)


def launch_installer_and_quit(
    installer_path: str,
    *,
    qapp: QApplication | None = None,
    inno_silent: bool = False,
) -> None:
    """Start ``installer_path`` fully detached, then quit the Qt application.

    If ``inno_silent`` is True (Windows only), passes Inno Setup silent switches so the
    downloaded ``MY_ETLZONE_Setup_*.exe`` upgrades without UI; the .iss ``[Run]`` entry
    starts the app after install.

    On Windows uses ``DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`` so the child
    survives parent exit. Non-Windows uses ``start_new_session=True``.
    """
    path = os.path.normpath(os.path.abspath(installer_path))
    if not os.path.isfile(path):
        logger.error("Installer not found: %s", path)
        return

    cmd: list[str] = [path]
    if inno_silent and sys.platform == "win32":
        cmd.extend(_INNO_SILENT_ARGS)
        logger.info("Launching Inno installer (silent): %s", " ".join(cmd))

    app = qapp or QApplication.instance()
    if not inno_silent or sys.platform != "win32":
        logger.info("Launching installer and exiting app: %s", path)

    try:
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
            subprocess.Popen(
                cmd,
                close_fds=True,
                creationflags=creationflags,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(
                cmd,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except OSError as exc:
        logger.exception("Failed to start installer: %s", exc)
        return

    if app is not None:
        app.quit()
    else:
        QCoreApplication.exit(0)
