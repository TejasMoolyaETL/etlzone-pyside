"""Create Module page."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.api import api_create_module
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
)
from ui.post_save_navigation import schedule_after_success


class CreateModulePage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(FORM_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        header_layout.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        header_layout.addWidget(QLabel("Create Module"))
        header_layout.addStretch()
        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self.request_back)
        header_layout.addWidget(back_btn)
        layout.addWidget(header)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(24, 20, 24, 20)
        content_layout.setSpacing(10)

        name_lbl = QLabel("Module Name")
        content_layout.addWidget(name_lbl)
        self.module_name_edit = QLineEdit()
        self.module_name_edit.setStyleSheet(FORM_INPUT_STYLE)
        self.module_name_edit.setFixedHeight(32)
        self.module_name_edit.setPlaceholderText("Enter module name")
        content_layout.addWidget(self.module_name_edit)

        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._message_label.setVisible(False)
        content_layout.addWidget(self._message_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        create_btn = QPushButton("Create Module")
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        create_btn.clicked.connect(self._handle_create)
        btn_row.addWidget(create_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self.request_back)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch(1)
        content_layout.addLayout(btn_row)
        content_layout.addStretch(1)

        layout.addWidget(content, 1)

    def _clear_message(self) -> None:
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.setText("")
        self._message_label.setVisible(False)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._message_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._message_label, message, error=False)

    def is_dirty(self) -> bool:
        return bool(self.module_name_edit.text().strip())

    def reset_to_default(self) -> None:
        self.module_name_edit.clear()
        self._clear_message()

    def request_back(self) -> None:
        self.reset_to_default()
        if self.on_back:
            self.on_back()

    def _handle_create(self) -> None:
        self._clear_message()
        name = self.module_name_edit.text().strip()
        if not name:
            self._show_error("Module name is required.")
            self.module_name_edit.setFocus()
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_create_module(name, token=token)
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Failed to create module."))
            return
        self._show_success(str(result.get("message") or "Module created successfully."))
        schedule_after_success(
            delay_ms=700,
            clear_error=self._clear_message,
            reset=self.reset_to_default,
            on_back=self.on_back,
            on_success=self.on_create_success,
        )

