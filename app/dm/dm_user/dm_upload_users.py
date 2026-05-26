"""Upload DM users from a spreadsheet file."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.api import api_upload_dm_users_from_file
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_page_styles import (
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    MODAL_FIELD_LABEL_STYLE,
)

_UPLOAD_FILE_FILTER = (
    "Spreadsheets (*.xlsx *.xls *.csv);;Excel (*.xlsx *.xls);;CSV (*.csv);;All files (*.*)"
)


class DmUploadUsersPage(QWidget):
    """Select a user spreadsheet and POST it to the DM user upload API."""

    def __init__(self, on_back: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.on_back = on_back
        self._selected_path: str = ""
        self._uploading = False
        self._build_ui()

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        back_btn.clicked.connect(self._handle_back)
        hl.addWidget(back_btn)
        hl.addWidget(QLabel("Upload users"))
        hl.addStretch()
        layout.addWidget(header)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 24, 24, 24)
        bl.setSpacing(16)

        hint = QLabel(
            "Choose a spreadsheet (.xlsx, .xls, or .csv) containing users to import into DM."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        bl.addWidget(hint)

        file_row = QHBoxLayout()
        file_row.setSpacing(12)
        self._file_label = QLabel("No file selected")
        self._file_label.setWordWrap(True)
        self._file_label.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        file_row.addWidget(self._file_label, 1)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(100)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        browse_btn.clicked.connect(self._browse_file)
        file_row.addWidget(browse_btn)
        bl.addLayout(file_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self._upload_btn = QPushButton("Upload")
        self._upload_btn.setFixedWidth(120)
        self._upload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._upload_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._upload_btn.clicked.connect(self._handle_upload)
        btn_row.addWidget(self._upload_btn)
        btn_row.addStretch()
        bl.addLayout(btn_row)

        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setVisible(False)
        bl.addWidget(self._message_label)
        bl.addStretch()
        layout.addWidget(body, 1)

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select user spreadsheet",
            "",
            _UPLOAD_FILE_FILTER,
        )
        if not path:
            return
        self._selected_path = path
        self._file_label.setText(Path(path).name)
        self._clear_message()

    def _set_upload_enabled(self, enabled: bool) -> None:
        self._uploading = not enabled
        self._upload_btn.setEnabled(enabled)

    def _clear_message(self) -> None:
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.setText("")
        self._message_label.setVisible(False)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._message_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._message_label, message, error=False)

    def _handle_upload(self) -> None:
        if self._uploading:
            return
        if not self._selected_path:
            self._show_error("Select a file before uploading.")
            return
        self._clear_message()
        self._set_upload_enabled(False)
        try:
            result = api_upload_dm_users_from_file(self._selected_path, token=self._token())
        finally:
            self._set_upload_enabled(True)
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Upload users failed."))
            return
        self._show_success(str(result.get("message") or "Users uploaded successfully."))
