"""Background download and detached launch for in-app auto-updates.

Uses :mod:`urllib` (no extra dependencies). Supported payloads:

* **Inno Setup ``Etlzone-windows.exe``** (Windows) → launch that file; with
  ``inno_silent=True``, passes ``/VERYSILENT`` / ``/CLOSEAPPLICATIONS`` so the install
  upgrades in place and the ``.iss`` ``[Run]`` entry can restart the app.
* **``.dmg``** (macOS) → after download, ``open`` the disk image so the user can drag the
  ``.app`` to **Applications** (no silent replace like Inno; Apple-style install).
* **``.zip``** of the PyInstaller ``onedir`` folder (legacy, Windows) → extract to a temp folder,
  find the main ``.exe``, launch it detached, then quit.

1. Version API → ``downloadUrl`` (+ optional ``checksum`` / ``sha256`` for the **downloaded** file).
2. :class:`DownloadUpdateWorker` streams to a temp ``.exe`` or ``.zip``.
3. Verify SHA-256 (optional), then :func:`resolve_launch_path` → :func:`launch_installer_and_quit`.

Set ``ETL_UPDATE_MAIN_EXE`` (e.g. ``Etlzone-windows.exe``) if your zip uses a different name.

For the Inno installer, restart is handled by the installer; for a zip bundle the new
process is started and the old app exits.

**Diagnostics (Windows silent Inno + relaunch):**

* ``%TEMP%\\etlzone_relaunch_python.log`` — Python / UI stages (``[py_stage]``, ``[ui]``, spawn PID).
* ``%TEMP%\\etlzone_relaunch.log`` — helper script stages (``[1_…]`` resolved ``.ps1``, ``[enc…]`` encoded fallback, ``[p…]`` parametric, ``[vbs…]`` VBScript).
* ``%TEMP%\\etlzone_relaunch_ps_stderr.log`` — PowerShell stderr for ``-File`` attempts.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
from datetime import datetime
from typing import TextIO
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid
import zipfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, QCoreApplication, QTimer, Signal, Slot
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)

# Let the detached post-update helper fully start before Qt exits (avoids killing the child tree).
_POST_UPDATE_QUIT_DELAY_MS = 900


def _quit_qt_after_helper_spawn(app: QApplication | None) -> None:
    """Quit the UI after a short delay so the detached PowerShell/VBS child is not torn down."""
    if app is not None:
        try:
            app.processEvents()
        except Exception:
            pass
        QTimer.singleShot(_POST_UPDATE_QUIT_DELAY_MS, app.quit)
        return
    QCoreApplication.exit(0)


def _relaunch_debug_log_path() -> str:
    return os.path.join(tempfile.gettempdir(), "etlzone_relaunch_python.log")


def _relaunch_debug_append(line: str) -> None:
    """Always from Python — if this file never appears, the relaunch branch never ran."""
    try:
        p = _relaunch_debug_log_path()
        with open(p, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{datetime.now().isoformat()} {line}\n")
            f.flush()
    except OSError:
        pass


def log_relaunch_stage(line: str) -> None:
    """Public hook for UI / callers: same file as :func:`_relaunch_debug_append`."""
    _relaunch_debug_append(line)


def _ps_escape_single_quoted(path: str) -> str:
    """Escape for use inside PowerShell single-quoted string literals."""
    return path.replace("'", "''")


# Chunk size for streaming download (bytes).
_READ_CHUNK = 256 * 1024

# Executable name inside an extracted zip (PyInstaller onedir: Etlzone-windows.exe next to _internal).
def _default_main_exe_name() -> str:
    n = (os.getenv("ETL_UPDATE_MAIN_EXE") or "Etlzone-windows.exe").strip()
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
    if not (low.endswith(".exe") or low.endswith(".zip") or low.endswith(".dmg")):
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
    """Return absolute path to the file to run or open.

    On macOS, a ``.dmg`` is returned as-is for :func:`launch_installer_and_quit` (``open``).

    If ``downloaded_path`` is a ``.zip`` (or zip by magic), extracts to a new temp directory
    and returns the path to ``main_exe_name`` inside it (Windows onedir).

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
    if sys.platform == "darwin" and low.endswith(".dmg"):
        return path

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
)


def _popen_win_detached_hidden(
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    win32_full_isolation: bool = True,
    stderr: int | TextIO | None = None,
) -> subprocess.Popen:
    """Windows: spawn ``args`` detached. If ``win32_full_isolation`` is False, omits NO_WINDOW/BREAKAWAY (some PCs fail)."""
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = subprocess.SW_HIDE
    flags = (
        getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )
    if win32_full_isolation:
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0
        )
    proc_env = {str(k): str(v) for k, v in os.environ.items() if isinstance(v, str)}
    if env:
        proc_env.update({str(k): str(v) for k, v in env.items()})
    err = subprocess.DEVNULL if stderr is None else stderr
    return subprocess.Popen(
        args,
        close_fds=True,
        creationflags=flags,
        startupinfo=si,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=err,
        env=proc_env,
    )


def _wscript_exe() -> str:
    found = shutil.which("wscript.exe")
    if found:
        return found
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(system_root, "System32", "wscript.exe")


def _powershell_exe() -> str:
    found = shutil.which("powershell.exe")
    if found:
        return found
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    return os.path.join(
        system_root,
        "System32",
        "WindowsPowerShell",
        "v1.0",
        "powershell.exe",
    )


# Paths via env (ETLZONE_POSTUPDATE_*) so we can use -EncodedCommand (no .ps1 / policy issues).
_POSTUPDATE_ENV_INSTALLER = "ETLZONE_POSTUPDATE_INSTALLER"
_POSTUPDATE_ENV_APP = "ETLZONE_POSTUPDATE_APP"

# Log: %TEMP%\etlzone_relaunch.log — stages prefixed [encN_…] / [N_…] for support.
# App launch matches typical Inno [Run]: WorkingDir = install dir, normal window, no wait (nowait).
_PS_INNO_RELAUNCH_ONELINER = (
    "$log=Join-Path $env:TEMP 'etlzone_relaunch.log';"
    "function __Z($m){Add-Content -LiteralPath $log -Encoding UTF8 -Value $m};"
    "__Z('[enc1_begin] '+$(Get-Date -Format o));"
    "$i=$env:ETLZONE_POSTUPDATE_INSTALLER;$r=$env:ETLZONE_POSTUPDATE_APP;"
    "if(-not $i -or -not $r){__Z('[enc_err_missing_env]');exit 1};"
    "__Z('[enc2_paths] inst='+$i+' rel='+$r);"
    "if(-not (Test-Path -LiteralPath $i)){__Z('[enc_err_installer_missing]');exit 1};"
    "$id=Split-Path -LiteralPath $i -Parent;"
    "__Z('[enc3_start_installer] wd='+$id);"
    "$p=Start-Process -LiteralPath $i -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS' "
    "-WorkingDirectory $id -PassThru -Wait -WindowStyle Hidden;"
    "__Z('[enc4_installer_exit] '+$p.ExitCode+' '+$(Get-Date -Format o));"
    "__Z('[enc5_sleep_3s]');Start-Sleep -Seconds 3;__Z('[enc6_sleep_done]');"
    "if(Test-Path -LiteralPath $r){"
    "$rd=Split-Path -LiteralPath $r -Parent;"
    "__Z('[enc7_start_app] wd='+$rd);"
    "$a=Start-Process -LiteralPath $r -WorkingDirectory $rd -WindowStyle Normal -PassThru;"
    "__Z('[enc8_app_pid] '+$a.Id+' '+$(Get-Date -Format o))"
    "}else{__Z('[enc_err_app_missing] '+$r)}"
)

_PS_INNO_RELAUNCH_B64 = base64.b64encode(
    _PS_INNO_RELAUNCH_ONELINER.encode("utf-16-le")
).decode("ascii")

# Primary: paths baked in (no env vars — child may not inherit custom env reliably).
# Relaunch matches Inno [Run]: WorkingDir = folder containing the exe, Normal window, async (no -Wait on app).
_PS_RELAUNCH_INLINE_TEMPLATE = """$ErrorActionPreference = 'Continue'
$log = Join-Path $env:TEMP 'etlzone_relaunch.log'
function __EtlW($m) { Add-Content -LiteralPath $log -Encoding UTF8 -Value $m }
__EtlW ("[1_begin] " + (Get-Date -Format o))
$i = '__INST__'
$r = '__REL__'
__EtlW ("[2_paths] inst=$i rel=$r")
try {
  if (-not (Test-Path -LiteralPath $i)) { __EtlW "[3_err_installer_missing]"; exit 1 }
  $sz = (Get-Item -LiteralPath $i).Length
  __EtlW ("[3_installer_ok] bytes=$sz")
  $id = Split-Path -LiteralPath $i -Parent
  __EtlW ("[4_start_installer] wd=$id " + (Get-Date -Format o))
  $p = Start-Process -LiteralPath $i -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS' -WorkingDirectory $id -PassThru -Wait -WindowStyle Hidden
  __EtlW ("[5_installer_exit] code=$($p.ExitCode) " + (Get-Date -Format o))
  __EtlW "[6_sleep_3s]"
  Start-Sleep -Seconds 3
  __EtlW "[7_sleep_done]"
  if (Test-Path -LiteralPath $r) {
    $rd = Split-Path -LiteralPath $r -Parent
    __EtlW ("[8_relaunch_ok] starting app wd=$rd")
    $a = Start-Process -LiteralPath $r -WorkingDirectory $rd -WindowStyle Normal -PassThru
    __EtlW ("[9_app_started] pid=$($a.Id) path=$r " + (Get-Date -Format o))
  } else {
    __EtlW ("[8_err_app_missing] $r")
  }
} catch {
  __EtlW ("[ERR] " + $_.Exception.Message)
  exit 1
}
"""

# Fallback: parametric .ps1 (arguments after -File).
_INNO_RELAUNCH_PS1_PARAM = """param(
    [Parameter(Mandatory = $true)][string] $Inst,
    [Parameter(Mandatory = $true)][string] $Rel
)
$log = Join-Path $env:TEMP 'etlzone_relaunch.log'
function __E($m) { Add-Content -LiteralPath $log -Encoding UTF8 -Value $m }
__E ("[p1_begin] " + (Get-Date -Format o))
__E ("[p2_paths] inst=$Inst rel=$Rel")
if (-not (Test-Path -LiteralPath $Inst)) { __E '[p_err_installer_missing]'; exit 1 }
$instDir = Split-Path -LiteralPath $Inst -Parent
__E "[p3_start_installer]"
$p = Start-Process -LiteralPath $Inst -ArgumentList '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS' -WorkingDirectory $instDir -PassThru -Wait -WindowStyle Hidden
__E ("[p4_installer_exit] $($p.ExitCode)")
Start-Sleep -Seconds 3
if (-not (Test-Path -LiteralPath $Rel)) { __E '[p_err_app_missing]'; exit 1 }
$relDir = Split-Path -LiteralPath $Rel -Parent
__E "[p5_start_app]"
$a = Start-Process -LiteralPath $Rel -WorkingDirectory $relDir -WindowStyle Normal -PassThru
__E ("[p6_app_pid] $($a.Id)")
exit 0
"""


def _write_inno_relaunch_ps1_resolved(installer_path: str, relaunch_exe: str) -> str:
    inst = _ps_escape_single_quoted(
        os.path.normpath(os.path.abspath(installer_path))
    )
    rel = _ps_escape_single_quoted(os.path.normpath(os.path.abspath(relaunch_exe)))
    body = _PS_RELAUNCH_INLINE_TEMPLATE.replace("__INST__", inst).replace("__REL__", rel)
    path = os.path.join(
        tempfile.gettempdir(),
        f"etlzone_post_update_{uuid.uuid4().hex[:12]}.ps1",
    )
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(body)
    return path


def _write_inno_relaunch_ps1_parametric() -> str:
    path = os.path.join(
        tempfile.gettempdir(),
        f"etlzone_post_update_{uuid.uuid4().hex[:12]}.ps1",
    )
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as f:
        f.write(_INNO_RELAUNCH_PS1_PARAM)
    return path


def _vbs_string_literal(path: str) -> str:
    """Escape for embedding inside a VBScript double-quoted string."""
    return path.replace('"', '""')


def _write_inno_relaunch_vbs(installer_path: str, relaunch_exe: str) -> str:
    """Fallback: WshShell waits on Inno (hidden), then starts the GUI app visibly (style 1) with correct cwd."""
    inst = _vbs_string_literal(os.path.normpath(os.path.abspath(installer_path)))
    rel = _vbs_string_literal(os.path.normpath(os.path.abspath(relaunch_exe)))
    vbs_path = os.path.join(
        tempfile.gettempdir(),
        f"etlzone_post_update_{uuid.uuid4().hex[:12]}.vbs",
    )
    # Installer: style 0 = hidden, wait. App: style 1 = normal window (Inno [Run]-like). Cwd = exe folder (onedir).
    content = "\r\n".join(
        [
            "Option Explicit",
            "Sub EtlRelaunchLog(msg)",
            '  Dim fso, f, p',
            '  Set fso = CreateObject("Scripting.FileSystemObject")',
            '  p = fso.GetSpecialFolder(2) & "\\etlzone_relaunch.log"',
            '  Set f = fso.OpenTextFile(p, 8, True)',
            '  f.WriteLine CStr(Now) & " " & msg',
            '  f.Close',
            "End Sub",
            "Dim sh, fso, inst, rel, relDir",
            'Set sh = CreateObject("WScript.Shell")',
            'Set fso = CreateObject("Scripting.FileSystemObject")',
            f'inst = "{inst}"',
            f'rel = "{rel}"',
            "relDir = fso.GetParentFolderName(rel)",
            'EtlRelaunchLog "[vbs1_begin]"',
            'EtlRelaunchLog "[vbs2_start_installer]"',
            'sh.Run Chr(34) & inst & Chr(34) & " /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS", 0, True',
            'EtlRelaunchLog "[vbs3_installer_finished]"',
            "WScript.Sleep 3000",
            'EtlRelaunchLog "[vbs4_after_sleep]"',
            "If fso.FileExists(rel) Then",
            '  EtlRelaunchLog "[vbs5_start_app] " & rel',
            "  sh.CurrentDirectory = relDir",
            "  sh.Run Chr(34) & rel & Chr(34), 1, False",
            '  EtlRelaunchLog "[vbs6_app_run_queued]"',
            "Else",
            '  EtlRelaunchLog "[vbs_err_missing_app] " & rel',
            "End If",
            "",
        ]
    )
    with open(vbs_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(content)
    return vbs_path


def _windows_relaunch_exe_candidate() -> str | None:
    """Best path to start after an in-place Inno upgrade (PyInstaller / frozen exe)."""
    ex = (sys.executable or "").strip()
    if not ex or not os.path.isfile(ex):
        return None
    low = ex.lower()
    if not low.endswith(".exe"):
        return None
    if os.path.basename(low) in ("python.exe", "pythonw.exe"):
        return None
    return os.path.normpath(os.path.abspath(ex))


def _spawn_inno_relaunch_helper(installer_path: str, relaunch_exe: str) -> bool:
    """Start hidden helper: resolved ``.ps1`` → EncodedCommand+env → parametric ``.ps1`` → VBScript."""
    inst = os.path.normpath(os.path.abspath(installer_path))
    rel = os.path.normpath(os.path.abspath(relaunch_exe))
    ps_stderr_path = os.path.join(tempfile.gettempdir(), "etlzone_relaunch_ps_stderr.log")
    _relaunch_debug_append(f"helper enter installer={inst} relaunch={rel}")

    ps = _powershell_exe()
    if os.path.isfile(ps):
        # 1) Resolved .ps1 — paths embedded (no custom env in child).
        ps1_res = ""
        try:
            ps1_res = _write_inno_relaunch_ps1_resolved(inst, rel)
            _relaunch_debug_append(f"wrote resolved ps1 {ps1_res}")
        except OSError as exc:
            _relaunch_debug_append(f"write resolved ps1 failed: {exc}")
            logger.warning("Could not write resolved relaunch .ps1: %s", exc)

        if ps1_res and os.path.isfile(ps1_res):
            args = [
                ps,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                ps1_res,
            ]
            try:
                with open(ps_stderr_path, "a", encoding="utf-8") as errf:
                    errf.write(f"\n--- {datetime.now().isoformat()} resolved_ps1 ---\n")
                    errf.flush()
                    for full_iso in (True, False):
                        try:
                            p = _popen_win_detached_hidden(
                                args,
                                win32_full_isolation=full_iso,
                                stderr=errf,
                            )
                            _relaunch_debug_append(
                                f"resolved_ps1 ok pid={p.pid} full_iso={full_iso}"
                            )
                            logger.info(
                                "Post-install relaunch helper: PowerShell -File %s (resolved)",
                                ps1_res,
                            )
                            return True
                        except OSError as exc:
                            _relaunch_debug_append(
                                f"resolved_ps1 OSError full_iso={full_iso}: {exc}"
                            )
                            logger.warning(
                                "PowerShell -File resolved relaunch failed (full_iso=%s): %s",
                                full_iso,
                                exc,
                            )
            except OSError as exc:
                _relaunch_debug_append(f"ps stderr log open failed: {exc}")

        _relaunch_debug_append("[helper] stage=EncodedCommand+env")

        # 2) EncodedCommand + env (policy / path edge cases).
        for full_iso in (True, False):
            try:
                p = _popen_win_detached_hidden(
                    [
                        ps,
                        "-NoProfile",
                        "-ExecutionPolicy",
                        "Bypass",
                        "-WindowStyle",
                        "Hidden",
                        "-EncodedCommand",
                        _PS_INNO_RELAUNCH_B64,
                    ],
                    env={
                        _POSTUPDATE_ENV_INSTALLER: inst,
                        _POSTUPDATE_ENV_APP: rel,
                    },
                    win32_full_isolation=full_iso,
                )
                _relaunch_debug_append(f"encoded ok pid={p.pid} full_iso={full_iso}")
                logger.info(
                    "Post-install relaunch helper: EncodedCommand (installer=%s app=%s)",
                    inst,
                    rel,
                )
                return True
            except OSError as exc:
                _relaunch_debug_append(
                    f"encoded OSError full_iso={full_iso}: {exc}"
                )
                logger.warning(
                    "PowerShell EncodedCommand relaunch failed (full_iso=%s): %s",
                    full_iso,
                    exc,
                )

        _relaunch_debug_append("[helper] stage=parametric_ps1")

        # 3) Parametric -File + args
        ps1p = ""
        try:
            ps1p = _write_inno_relaunch_ps1_parametric()
            _relaunch_debug_append(f"wrote param ps1 {ps1p}")
        except OSError as exc:
            _relaunch_debug_append(f"write param ps1 failed: {exc}")
            logger.warning("Could not write parametric relaunch .ps1: %s", exc)
        if ps1p and os.path.isfile(ps1p):
            args = [
                ps,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-WindowStyle",
                "Hidden",
                "-File",
                ps1p,
                "-Inst",
                inst,
                "-Rel",
                rel,
            ]
            try:
                with open(ps_stderr_path, "a", encoding="utf-8") as errf:
                    errf.write(f"\n--- {datetime.now().isoformat()} param_ps1 ---\n")
                    errf.flush()
                    for full_iso in (True, False):
                        try:
                            p = _popen_win_detached_hidden(
                                args,
                                win32_full_isolation=full_iso,
                                stderr=errf,
                            )
                            _relaunch_debug_append(
                                f"param_ps1 ok pid={p.pid} full_iso={full_iso}"
                            )
                            logger.info(
                                "Post-install relaunch helper: PowerShell -File %s (param)",
                                ps1p,
                            )
                            return True
                        except OSError as exc:
                            _relaunch_debug_append(
                                f"param_ps1 OSError full_iso={full_iso}: {exc}"
                            )
                            logger.warning(
                                "PowerShell -File param relaunch failed (full_iso=%s): %s",
                                full_iso,
                                exc,
                            )
            except OSError as exc:
                _relaunch_debug_append(f"ps stderr log open failed (param): {exc}")
    else:
        _relaunch_debug_append(f"powershell.exe not found: {ps}")
        logger.warning("powershell.exe not found at %s", ps)

    _relaunch_debug_append("[helper] stage=VBScript")

    try:
        vbs = _write_inno_relaunch_vbs(inst, rel)
        _relaunch_debug_append(f"wrote vbs {vbs}")
    except OSError as exc:
        _relaunch_debug_append(f"write vbs failed: {exc}")
        logger.exception("Could not write VBScript relaunch script: %s", exc)
        return False
    ws = _wscript_exe()
    if not os.path.isfile(ws):
        _relaunch_debug_append(f"wscript missing: {ws}")
        logger.warning("wscript.exe not found.")
        return False
    for full_iso in (True, False):
        try:
            p = _popen_win_detached_hidden(
                [ws, "//nologo", vbs],
                win32_full_isolation=full_iso,
            )
            _relaunch_debug_append(f"vbs ok pid={p.pid} full_iso={full_iso}")
            logger.info("Post-install relaunch helper: VBScript %s", vbs)
            return True
        except OSError as exc:
            _relaunch_debug_append(f"vbs OSError full_iso={full_iso}: {exc}")
            logger.exception("VBScript relaunch helper failed: %s", exc)
    return False


def launch_installer_and_quit(
    installer_path: str,
    *,
    qapp: QApplication | None = None,
    inno_silent: bool = False,
    relaunch_exe: str | None = None,
) -> None:
    """Start ``installer_path`` fully detached, then quit the Qt application.

    If ``inno_silent`` is True (Windows only), passes Inno Setup silent switches so the
    downloaded ``Etlzone-windows.exe`` upgrades without UI; the .iss ``[Run]`` entry
    may start the app after install. This function now uses installer-only restart on
    Windows (no chained helper relaunch); ``relaunch_exe`` is accepted for backward
    compatibility but ignored.

    On Windows uses ``DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP`` so the child
    survives parent exit. Non-Windows uses ``start_new_session=True``.
    """
    path = os.path.normpath(os.path.abspath(installer_path))
    if not os.path.isfile(path):
        _relaunch_debug_append(f"[py_err] installer_missing path={path}")
        logger.error("Installer not found: %s", path)
        return

    app = qapp or QApplication.instance()

    # macOS .dmg: open in Finder; user drags the app to Applications (no headless install).
    if sys.platform == "darwin" and path.lower().endswith(".dmg"):
        logger.info("Opening disk image: %s", path)
        try:
            subprocess.Popen(
                ["open", path],
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            logger.exception("Failed to open .dmg: %s", exc)
            return
        if app is not None:
            app.quit()
        else:
            QCoreApplication.exit(0)
        return

    creationflags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )

    if relaunch_exe:
        logger.info("Ignoring relaunch_exe override (installer-only restart mode).")

    cmd: list[str] = [path]
    if inno_silent and sys.platform == "win32":
        cmd.extend(_INNO_SILENT_ARGS)
        logger.info("Launching Inno installer (silent): %s", " ".join(cmd))

    if not inno_silent or sys.platform != "win32":
        logger.info("Launching installer and exiting app: %s", path)

    try:
        if sys.platform == "win32":
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
