"""View / edit DMT User page."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.api import api_update_dmt_user
from core.app_preferences import format_datetime_display, is_datetime_field
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.blank_display import is_blank_display_value
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    placeholder_example,
)
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success
from ui.widgets.required_label import field_caption_label, labeled_field_block

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})
_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _get_value(rec: dict[str, Any], keys: tuple[str, ...]) -> Any:
    flat = {k: v for k, v in rec.items() if k not in _HIDDEN_KEYS}
    for key in keys:
        if key in flat:
            return flat[key]
    return None


def _format_value(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


def _get_user_id(rec: dict[str, Any]) -> int | str | None:
    for k in ("userId", "id"):
        v = rec.get(k)
        if v is not None:
            return v
    return None


_USER_COL1 = (
    ("User Id", ("userId", "id")),
    ("First Name*", ("firstName", "first_name")),
    ("Last Name*", ("lastName", "last_name")),
    ("Status*", ("status",)),
    ("Email*", ("email",)),
    ("Mobile*", ("mobile", "mobileNumber")),
)
_USER_COL2 = (
    ("Created By", ("createdBy", "created_by")),
    ("Created On", ("createdOn", "created_on", "createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified On", ("modifiedOn", "modified_on", "modifiedAt", "modified_at", "updatedAt", "updated_at")),
)
_USER_FIELD_GROUPS = _USER_COL1 + _USER_COL2

_READONLY_KEYS = frozenset(
    {
        "userId",
        "id",
        "createdBy",
        "created_by",
        "createdOn",
        "created_on",
        "createdAt",
        "created_at",
        "modifiedBy",
        "modified_by",
        "modifiedOn",
        "modified_on",
        "modifiedAt",
        "modified_at",
        "updatedAt",
        "updated_at",
    }
)


class ViewDmtUserPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._user: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit] = {}
        self._editable_keys: list[str] = []
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
        title = QLabel("DMT User Details")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll_content = QWidget()
        scroll_content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        card.setMinimumWidth(520)
        card.setMaximumWidth(800)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        def add_field(col: int, idx: int, label_text: str, keys: tuple[str, ...]) -> None:
            canonical = keys[0]
            if canonical not in _READONLY_KEYS:
                self._editable_keys.append(canonical)

            label_widget = field_caption_label(label_text, LABEL_STYLE)
            value_edit = QLineEdit()
            value_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
            value_edit.setMinimumWidth(240)
            value_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            value_edit.setReadOnly(canonical in _READONLY_KEYS)
            value_edit.setStyleSheet(READONLY_INPUT_STYLE if canonical in _READONLY_KEYS else INPUT_STYLE)
            value_edit.setText("")
            if canonical == "firstName":
                value_edit.setPlaceholderText(placeholder_example("ali"))
            elif canonical == "lastName":
                value_edit.setPlaceholderText(placeholder_example("java team"))
            elif canonical == "email":
                value_edit.setPlaceholderText(placeholder_example("abc@gmail.com"))
            elif canonical == "mobile":
                value_edit.setPlaceholderText(placeholder_example("80808080"))
            self._field_edits[canonical] = value_edit
            grid.addWidget(labeled_field_block(label_widget, value_edit), idx, col)

        for idx, (label_text, keys) in enumerate(_USER_COL1):
            add_field(0, idx, label_text, keys)
        for idx, (label_text, keys) in enumerate(_USER_COL2):
            add_field(1, idx, label_text, keys)

        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self._handle_back)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedWidth(100)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._edit_btn.clicked.connect(self._handle_edit)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._cancel_btn.clicked.connect(self._handle_cancel)

        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedWidth(100)
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._save_btn.clicked.connect(self._handle_save)

        display_btns = QWidget()
        display_btns_layout = QHBoxLayout(display_btns)
        display_btns_layout.setContentsMargins(0, 0, 0, 0)
        display_btns_layout.setSpacing(12)
        display_btns_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        display_btns_layout.addWidget(self._edit_btn)
        display_btns_layout.addWidget(self._back_btn)

        edit_btns = QWidget()
        edit_btns_layout = QHBoxLayout(edit_btns)
        edit_btns_layout.setContentsMargins(0, 0, 0, 0)
        edit_btns_layout.setSpacing(12)
        edit_btns_layout.addWidget(self._save_btn)
        edit_btns_layout.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.addWidget(display_btns)
        self._btn_stack.addWidget(edit_btns)

        self._error_label = QLabel()
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setWordWrap(True)
        self._error_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._error_label.setVisible(False)

        btn_row = max(len(_USER_COL1), len(_USER_COL2))
        grid.addWidget(self._error_label, btn_row, 0, 1, 2)
        grid.addWidget(
            self._btn_stack,
            btn_row + 1,
            0,
            1,
            2,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        grid.setRowMinimumHeight(btn_row + 1, 52)

        card_layout.addLayout(grid)
        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        self._switch_to_view_mode()

    def set_user(self, user: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._user = dict(user) if user else {}
        self._refresh_values()
        if edit_mode and self._user:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _refresh_values(self) -> None:
        for _label_text, keys in _USER_FIELD_GROUPS:
            canonical = keys[0]
            value = _get_value(self._user, keys)
            text = _format_value(value, keys[0], keys)
            edit = self._field_edits.get(canonical)
            if edit:
                edit.setText(text)

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def _get_edit_value(self, *keys: str) -> str:
        for key in keys:
            edit = self._field_edits.get(key)
            if edit:
                return edit.text().strip()
        return ""

    def _handle_edit(self) -> None:
        self._clear_error()
        for key in self._editable_keys:
            edit = self._field_edits.get(key)
            if edit:
                edit.setReadOnly(False)
                edit.setStyleSheet(INPUT_STYLE)
        self._btn_stack.setCurrentIndex(1)

    def _handle_cancel(self) -> None:
        if not self._has_unsaved_changes():
            self._clear_error()
            self._refresh_values()
            self._switch_to_view_mode()
            return
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard and leave?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Discard:
            self._clear_error()
            self._refresh_values()
            self._switch_to_view_mode()

    def _has_unsaved_changes(self) -> bool:
        for _label_text, keys in _USER_FIELD_GROUPS:
            canonical = keys[0]
            if canonical in _READONLY_KEYS:
                continue
            current = self._field_edits.get(canonical).text().strip() if self._field_edits.get(canonical) else ""
            original = _format_value(_get_value(self._user, keys), keys[0], keys).strip()
            if current != original:
                return True
        return False

    def _switch_to_view_mode(self) -> None:
        for _label_text, keys in _USER_FIELD_GROUPS:
            canonical = keys[0]
            edit = self._field_edits.get(canonical)
            if not edit:
                continue
            if canonical in _READONLY_KEYS:
                edit.setReadOnly(True)
                edit.setStyleSheet(READONLY_INPUT_STYLE)
            else:
                edit.setReadOnly(True)
                edit.setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1

    def _handle_save(self) -> None:
        uid = _get_user_id(self._user)
        if uid is None:
            self._show_error("User ID is missing.")
            return
        first_name = self._get_edit_value("firstName", "first_name")
        last_name = self._get_edit_value("lastName", "last_name")
        email = self._get_edit_value("email")
        mobile = self._get_edit_value("mobile", "mobileNumber")
        status = self._get_edit_value("status")

        if not first_name:
            self._show_error("First name is required.")
            fe = self._field_edits.get("firstName")
            if fe is not None:
                fe.setFocus()
            return
        if not last_name:
            self._show_error("Last name is required.")
            le = self._field_edits.get("lastName")
            if le is not None:
                le.setFocus()
            return
        if not email:
            self._show_error("Email is required.")
            ee = self._field_edits.get("email")
            if ee is not None:
                ee.setFocus()
            return
        if not _EMAIL_REGEX.match(email):
            self._show_error("Please enter a valid email address.")
            ee = self._field_edits.get("email")
            if ee is not None:
                ee.setFocus()
            return
        if not mobile:
            self._show_error("Mobile is required.")
            me = self._field_edits.get("mobile")
            if me is not None:
                me.setFocus()
            return
        if not status:
            self._show_error("Status is required.")
            se = self._field_edits.get("status")
            if se is not None:
                se.setFocus()
            return

        result = api_update_dmt_user(
            user_id=uid,
            first_name=first_name,
            last_name=last_name,
            status=status,
            email=email,
            mobile=mobile,
            token=self._token(),
        )
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Failed to update user."))
            return

        self._user.update(
            {
                "firstName": first_name,
                "lastName": last_name,
                "status": status,
                "email": email,
                "mobile": mobile,
            }
        )
        self._refresh_values()
        self._switch_to_view_mode()
        self._show_success(str(result.get("message") or "DMT user updated successfully."))
        schedule_after_success(
            delay_ms=600,
            clear_error=self._clear_error,
            reset=lambda: None,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )
