"""View / edit Module page."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.api import api_update_module
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_READONLY_INPUT_STYLE,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
)
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success


class ViewModulePage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._module: dict[str, Any] = {}
        self._before_edit_name = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QWidget()
        header.setStyleSheet(FORM_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("Module Details"))
        hl.addStretch()
        layout.addWidget(header)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(24, 20, 24, 20)
        cl.setSpacing(10)
        cl.addWidget(QLabel("Module Id"))
        self.module_id_edit = QLineEdit()
        self.module_id_edit.setReadOnly(True)
        self.module_id_edit.setStyleSheet(FORM_READONLY_INPUT_STYLE)
        self.module_id_edit.setFixedHeight(32)
        cl.addWidget(self.module_id_edit)
        cl.addWidget(QLabel("Module Name"))
        self.module_name_edit = QLineEdit()
        self.module_name_edit.setReadOnly(True)
        self.module_name_edit.setStyleSheet(FORM_READONLY_INPUT_STYLE)
        self.module_name_edit.setFixedHeight(32)
        cl.addWidget(self.module_name_edit)
        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._message_label.setVisible(False)
        cl.addWidget(self._message_label)

        display_btns = QWidget()
        dbl = QHBoxLayout(display_btns)
        dbl.setContentsMargins(0, 0, 0, 0)
        dbl.setSpacing(12)
        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._edit_btn.clicked.connect(self._handle_edit)
        dbl.addWidget(self._edit_btn)
        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self._handle_back)
        dbl.addWidget(self._back_btn)

        edit_btns = QWidget()
        ebl = QHBoxLayout(edit_btns)
        ebl.setContentsMargins(0, 0, 0, 0)
        ebl.setSpacing(12)
        self._save_btn = QPushButton("Save")
        self._save_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._save_btn.clicked.connect(self._handle_save)
        ebl.addWidget(self._save_btn)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._cancel_btn.clicked.connect(self._handle_cancel)
        ebl.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.addWidget(display_btns)
        self._btn_stack.addWidget(edit_btns)
        cl.addWidget(self._btn_stack)
        cl.addStretch(1)
        layout.addWidget(content, 1)

    def set_module(self, module: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._module = dict(module) if module else {}
        self.module_id_edit.setText(str(self._module.get("moduleId") or self._module.get("id") or ""))
        self.module_name_edit.setText(str(self._module.get("moduleName") or self._module.get("name") or ""))
        self._before_edit_name = self.module_name_edit.text().strip()
        if edit_mode:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _clear_message(self) -> None:
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.setText("")
        self._message_label.setVisible(False)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._message_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._message_label, message, error=False)

    def _switch_to_view_mode(self) -> None:
        self.module_name_edit.setReadOnly(True)
        self.module_name_edit.setStyleSheet(FORM_READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)

    def _switch_to_edit_mode(self) -> None:
        self.module_name_edit.setReadOnly(False)
        self.module_name_edit.setStyleSheet(FORM_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(1)

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1

    def _has_unsaved_changes(self) -> bool:
        return self.module_name_edit.text().strip() != self._before_edit_name

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _handle_edit(self) -> None:
        self._clear_message()
        self._before_edit_name = self.module_name_edit.text().strip()
        self._switch_to_edit_mode()

    def _handle_cancel(self) -> None:
        if self._has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Discard and leave?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Discard:
                return
        self.module_name_edit.setText(self._before_edit_name)
        self._switch_to_view_mode()
        self._clear_message()

    def _handle_save(self) -> None:
        self._clear_message()
        if not self._has_unsaved_changes():
            navigate_after_no_changes(
                show_non_error_message=self._show_success,
                clear_message=self._clear_message,
                on_back=self.on_back,
            )
            return
        name = self.module_name_edit.text().strip()
        if not name:
            self._show_error("Module name is required.")
            self.module_name_edit.setFocus()
            return
        module_id = self._module.get("moduleId") or self._module.get("id")
        if module_id is None:
            self._show_error("Module ID is missing.")
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_update_module(module_id, name, token=token)
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Failed to update module."))
            return
        self._module["moduleName"] = name
        self._before_edit_name = name
        self._show_success(str(result.get("message") or "Module updated successfully."))
        self._switch_to_view_mode()
        schedule_after_success(
            delay_ms=700,
            clear_error=self._clear_message,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )

