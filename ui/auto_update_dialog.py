"""Modal flow: prompt → download with progress → launch installer or extracted build and quit.

**Primary (recommended):** ``downloadUrl`` points to your **Inno Setup** build
``Etlzone-windows.exe`` (see ``installer/MY_ETLZONE_App.iss``). With
``inno_silent_install=True`` and ``update_package=\"setup\"`` (default), the app downloads
to temp, quits, and runs the installer with ``/VERYSILENT`` / ``/CLOSEAPPLICATIONS``;
the ``.iss`` ``[Run]`` entry restarts the application.

**macOS:** a **``.dmg``** URL with ``packageType: dmg`` (or a path ending in ``.dmg``). After
download the app runs ``open`` on the image, then quits; the user drags the ``.app`` into
**Applications** (not a silent in-place install like Inno).

**Legacy / optional:** a **``.zip``** of the PyInstaller **onedir** folder (Windows). Use
``update_package=\"zip\"`` (or server ``packageType: zip``).

Optional env ``ETL_UPDATE_MAIN_EXE`` if the executable inside a zip has another name.

Integration example::

    AutoUpdateDialog(
        parent_window,
        new_version=\"1.0.2\",
        download_url=\"https://.../Etlzone-windows.exe\",
        checksum=optional_sha256_of_the_downloaded_file,
        extra_message=server_message,
        update_package=\"setup\",
        inno_silent_install=True,
    ).exec()
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from urllib.parse import unquote, urlparse

from PySide6.QtCore import QThread, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.app_updater import (
    DownloadUpdateWorker,
    launch_installer_and_quit,
    log_relaunch_stage,
    make_temp_download_path,
    resolve_launch_path,
    verify_file_sha256,
)
from ui.form_page_styles import APP_FONT_SIZE_PX, MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET
from ui.theme import Theme
from ui.version_check_dialog import _header_bar, _primary_btn, _secondary_btn

logger = logging.getLogger(__name__)

_fs = APP_FONT_SIZE_PX


def _body_label(text: str, *, muted: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    color = Theme.TEXT_SECONDARY if muted else Theme.TEXT_PRIMARY
    weight = "400" if muted else "600"
    lbl.setStyleSheet(
        f"color: {color}; font-size: {_fs}px; font-weight: {weight}; line-height: 1.45;"
    )
    return lbl


class AutoUpdateDialog(QDialog):
    """Update Available → Update Now / Later → progress → verify → launch installer."""

    # Prevents starting a second in-app update download while one is active (any dialog instance).
    _download_in_progress = False

    def __init__(
        self,
        parent: QWidget | None,
        *,
        new_version: str,
        download_url: str,
        checksum: str | None = None,
        extra_message: str = "",
        main_exe_name: str | None = None,
        inno_silent_install: bool = True,
        update_package: str = "setup",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Update Available")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setStyleSheet(f"QDialog {{ background: {Theme.BG_WHITE}; border-radius: 8px; }}")

        self._url = (download_url or "").strip()
        self._version = (new_version or "").strip() or "?"
        self._checksum = (checksum or "").strip() or None
        self._extra = (extra_message or "").strip()
        self._main_exe_name = (main_exe_name or "").strip() or None
        self._inno_silent_install = inno_silent_install
        pkg = (update_package or "setup").strip().lower()
        if pkg == "zip":
            self._update_package = "zip"
        elif pkg == "dmg":
            self._update_package = "dmg"
        else:
            self._update_package = "setup"
        self._cancel_event = threading.Event()
        self._thread: QThread | None = None
        self._worker: DownloadUpdateWorker | None = None
        self._dest_path: str | None = None
        self._download_active = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(_header_bar("Update Available"))

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(20, 20, 20, 16)
        bl.setSpacing(12)

        if self._update_package == "zip":
            prompt = (
                f"A new version ({self._version}) is available. "
                "Download the update package (.zip)? The app will extract it and start the new build."
            )
        elif self._update_package == "dmg":
            prompt = (
                f"A new version ({self._version}) is available. "
                "Download the macOS disk image (.dmg)? After download, the image will open so you can drag "
                "the app into Applications to replace the current version."
            )
        else:
            prompt = (
                f"A new version ({self._version}) is available. "
                "Download the Windows installer to update the installed application?"
            )
        self._prompt_lbl = _body_label(prompt)
        bl.addWidget(self._prompt_lbl)

        if self._extra:
            bl.addWidget(_body_label(self._extra, muted=True))

        self._progress = QProgressBar()
        self._progress.setMinimumHeight(22)
        self._progress.setTextVisible(True)
        self._progress.setFormat("%p%")
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setStyleSheet(
            "QProgressBar { border: 1px solid #cbd5e1; border-radius: 6px; text-align: center; }"
            "QProgressBar::chunk { background-color: #0f2340; border-radius: 5px; }"
        )
        bl.addWidget(self._progress)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; font-size: {_fs - 1}px; font-weight: 400;"
        )
        self._status_lbl.setVisible(False)
        bl.addWidget(self._status_lbl)

        outer.addWidget(body)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background-color: {Theme.BORDER_DEFAULT}; border: none;")
        outer.addWidget(sep)

        btn_row = QWidget()
        br = QHBoxLayout(btn_row)
        br.setContentsMargins(20, 12, 20, 16)
        br.setSpacing(10)
        br.addStretch()

        self._btn_update = _primary_btn("Update Now")
        self._btn_update.setDefault(True)
        self._btn_update.clicked.connect(self._on_update_now)

        self._btn_later = _secondary_btn("Later")
        self._btn_later.clicked.connect(self.reject)

        br.addWidget(self._btn_update)
        br.addWidget(self._btn_later)
        outer.addWidget(btn_row)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._download_active:
            self._cancel_event.set()
        super().closeEvent(event)

    def reject(self) -> None:
        if self._download_active:
            self._cancel_event.set()
            self._status_lbl.setText("Cancelling…")
        super().reject()

    @Slot()
    def _on_update_now(self) -> None:
        if self._download_active or not self._url:
            return
        if AutoUpdateDialog._download_in_progress:
            QMessageBox.information(
                self,
                "Update",
                "An update download is already in progress.",
            )
            return
        AutoUpdateDialog._download_in_progress = True
        self._download_active = True
        self._cancel_event.clear()
        self._btn_update.setEnabled(False)
        self._btn_later.setText("Cancel")
        self._btn_later.setEnabled(True)
        try:
            self._btn_later.clicked.disconnect()
        except TypeError:
            pass
        self._btn_later.clicked.connect(self._on_cancel_download)

        self._progress.setVisible(True)
        self._progress.setRange(0, 0)
        self._status_lbl.setVisible(True)
        self._status_lbl.setText("Downloading…")
        self._prompt_lbl.setVisible(False)

        parsed = urlparse(self._url)
        raw_path = unquote((parsed.path or "").strip())
        suggested = os.path.basename(raw_path.rstrip("/")) or "update"
        self._dest_path = make_temp_download_path(suggested)

        self._thread = QThread(self)
        self._worker = DownloadUpdateWorker(
            self._url,
            self._dest_path,
            cancel_event=self._cancel_event,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_download_progress)
        self._worker.finished_ok.connect(self._on_download_finished)
        self._worker.failed.connect(self._on_download_failed)
        self._worker.finished_ok.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()
        logger.info("Auto-update download started for version %s", self._version)

    @Slot()
    def _on_cancel_download(self) -> None:
        self._cancel_event.set()
        self._btn_later.setEnabled(False)
        self._status_lbl.setText("Cancelling…")

    @Slot(int, int)
    def _on_download_progress(self, done: int, total: int) -> None:
        if total > 0:
            self._progress.setRange(0, 100)
            pct = min(100, int(100 * done / total))
            self._progress.setValue(pct)
            self._status_lbl.setText(f"Downloaded {done:,} / {total:,} bytes")
        else:
            self._progress.setRange(0, 0)
            self._status_lbl.setText(f"Downloaded {done:,} bytes…")

    @Slot(str)
    def _on_download_finished(self, path: str) -> None:
        self._download_active = False
        self._progress.setRange(0, 100)
        self._progress.setValue(100)
        self._status_lbl.setText("Verifying…")

        if self._checksum:
            if not verify_file_sha256(path, self._checksum):
                logger.error("Checksum mismatch for %s", path)
                AutoUpdateDialog._download_in_progress = False
                self._status_lbl.setText("")
                QMessageBox.critical(
                    self,
                    "Update failed",
                    "Downloaded file did not match the expected checksum. Try again or download manually.",
                )
                self._reset_prompt_ui()
                return

        self._status_lbl.setText("Preparing update…")
        try:
            launch_path = resolve_launch_path(path, main_exe_name=self._main_exe_name)
        except ValueError as exc:
            logger.error("Could not prepare update launch: %s", exc)
            AutoUpdateDialog._download_in_progress = False
            self._status_lbl.setText("")
            QMessageBox.critical(self, "Update failed", str(exc))
            self._reset_prompt_ui()
            return

        self._status_lbl.setText("Ready to start new version.")
        norm_launch = os.path.normpath(os.path.abspath(launch_path))
        norm_dl = os.path.normpath(os.path.abspath(path))
        is_dmg = launch_path.lower().endswith(".dmg")
        run_inno_silent = (
            self._inno_silent_install
            and sys.platform == "win32"
            and norm_launch == norm_dl
            and launch_path.lower().endswith(".exe")
        )
        if run_inno_silent:
            body = (
                "Download complete. The update installer will run silently, replace the "
                "previous version, and start the new application. This window will close.\n\n"
                "Save your work before continuing."
            )
        elif is_dmg:
            body = (
                "Download complete. The disk image will open in Finder. Drag the application into "
                "Applications to replace the old version, then launch it from Applications.\n\n"
                "This window will close. Save your work before continuing."
            )
        else:
            body = (
                "Download complete. The new version will start and this application will close.\n\n"
                "Save your work before continuing."
            )
        reply = QMessageBox.question(
            self,
            "Install update",
            body,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply != QMessageBox.StandardButton.Yes:
            AutoUpdateDialog._download_in_progress = False
            self._reset_prompt_ui()
            return

        logger.info("User confirmed update; launching %s (inno_silent=%s)", launch_path, run_inno_silent)
        AutoUpdateDialog._download_in_progress = False
        self.accept()
        relaunch_exe: str | None = None
        if run_inno_silent and sys.platform == "win32":
            env_override = (os.environ.get("ETL_RELAUNCH_EXE") or "").strip().strip('"')
            if env_override and os.path.isfile(env_override):
                relaunch_exe = env_override
            else:
                ex = (sys.executable or "").strip()
                if ex.lower().endswith(".exe") and os.path.isfile(ex):
                    if os.path.basename(ex).lower() not in ("python.exe", "pythonw.exe"):
                        relaunch_exe = ex
        log_relaunch_stage(
            f"[ui] install_confirmed inno_silent={run_inno_silent} "
            f"download={path!r} launch={launch_path!r}"
        )
        if relaunch_exe:
            log_relaunch_stage(f"[ui] relaunch_exe={relaunch_exe!r}")
        elif run_inno_silent and sys.platform == "win32":
            log_relaunch_stage("[ui] relaunch_exe=(none; resolved inside launch_installer_and_quit)")
        launch_installer_and_quit(
            launch_path,
            inno_silent=run_inno_silent,
            relaunch_exe=relaunch_exe,
        )

    @Slot(str)
    def _on_download_failed(self, message: str) -> None:
        self._download_active = False
        AutoUpdateDialog._download_in_progress = False
        logger.warning("Update download failed: %s", message)
        self._progress.setVisible(False)
        self._status_lbl.setVisible(False)
        if "cancel" in message.lower():
            self._reset_prompt_ui()
            return
        QMessageBox.warning(self, "Download failed", message)
        self._reset_prompt_ui()

    def _reset_prompt_ui(self) -> None:
        self._btn_update.setEnabled(True)
        self._btn_later.setText("Later")
        try:
            self._btn_later.clicked.disconnect()
        except TypeError:
            pass
        self._btn_later.clicked.connect(self.reject)
        self._btn_later.setEnabled(True)
        self._progress.setVisible(False)
        self._prompt_lbl.setVisible(True)
        self._status_lbl.setVisible(False)

    @Slot()
    def _cleanup_thread(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None
