"""Create User Role Assignment — POST user-role/assign."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QDate, Qt, QStringListModel
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.user_management.users.user_create import _DatePickerEdit
from app.user_management.user_timepass.user_role_ui_helpers import _VIEW_USER_FIELD_HEIGHT
from core.api import api_assign_user_role, api_get_all_roles, api_get_all_users
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_FONT_SIZE_PX,
    FORM_PAGE_HEADER_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    placeholder_search_select,
)
from ui.post_save_navigation import schedule_after_success
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label, labeled_field_block


class CreateUserRoleAssignmentPage(QWidget):
    """Form to assign a role to a user."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._users: list[tuple[str, str]] = []
        self._roles: list[tuple[str, str]] = []
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
        title = QLabel("Create User Role Assignment")
        header_layout.addWidget(title)
        header_layout.addStretch()
        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._handle_back)
        header_layout.addWidget(back_btn)
        layout.addWidget(header)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card.setMaximumWidth(620)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        self.user_input = QLineEdit()
        self.user_input.setPlaceholderText(placeholder_search_select("User Id", "Username", "Name"))
        self.user_input.setStyleSheet(INPUT_STYLE)
        self.user_completer = QCompleter(self.user_input)
        self.user_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.user_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.user_completer.setMaxVisibleItems(12)
        self.user_input.setCompleter(self.user_completer)
        card_layout.addWidget(
            labeled_field_block(field_caption_label("User*", LABEL_STYLE), self.user_input)
        )

        self.role_input = QLineEdit()
        self.role_input.setPlaceholderText(placeholder_search_select("Role Id", "Role Name"))
        self.role_input.setStyleSheet(INPUT_STYLE)
        self.role_completer = QCompleter(self.role_input)
        self.role_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.role_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.role_completer.setMaxVisibleItems(12)
        self.role_input.setCompleter(self.role_completer)
        card_layout.addWidget(
            labeled_field_block(field_caption_label("Role*", LABEL_STYLE), self.role_input)
        )

        fh = _VIEW_USER_FIELD_HEIGHT
        self.valid_from_edit = _DatePickerEdit()
        self.valid_from_edit.setDate(QDate.currentDate())
        self.valid_from_edit.setMinimumWidth(240)
        self.valid_from_edit.setFixedHeight(fh)
        self.valid_from_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card_layout.addWidget(
            labeled_field_block(field_caption_label("Valid from*", LABEL_STYLE), self.valid_from_edit)
        )

        self.valid_to_edit = _DatePickerEdit()
        self.valid_to_edit.setDate(QDate.currentDate().addYears(1))
        self.valid_to_edit.setMinimumWidth(240)
        self.valid_to_edit.setFixedHeight(fh)
        self.valid_to_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card_layout.addWidget(
            labeled_field_block(field_caption_label("Valid to*", LABEL_STYLE), self.valid_to_edit)
        )

        self.default_role_chk = QCheckBox("Default Role")
        self.default_role_chk.setChecked(False)
        self.default_role_chk.setStyleSheet(
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: #0f172a;"
        )
        card_layout.addWidget(self.default_role_chk)

        self.error_label = QLabel()
        self.error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.error_label.setVisible(False)
        card_layout.addWidget(self.error_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        create_btn = QPushButton("Create")
        create_btn.setFixedWidth(100)
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        create_btn.clicked.connect(self._handle_create)
        btn_layout.addWidget(create_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self._handle_back)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        card_layout.addLayout(btn_layout)

        content_layout.addWidget(card)
        content_layout.addStretch()
        layout.addWidget(content)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._load_reference_lists()

    def _profile_token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _load_reference_lists(self) -> None:
        token = self._profile_token()
        users_result = api_get_all_users(token=token)
        roles_result = api_get_all_roles(token=token)

        users_data = users_result.get("data") or []
        self._users = []
        for u in users_data:
            if not isinstance(u, dict):
                continue
            uid = u.get("userId") or u.get("user_id") or u.get("id")
            if uid is None:
                continue
            uname = str(u.get("userName") or u.get("username") or "").strip()
            full = f"{u.get('firstName') or ''} {u.get('lastName') or ''}".strip()
            display = f"{uid} | {uname}"
            if full:
                display += f" | {full}"
            self._users.append((str(uid), display))

        roles_data = roles_result.get("data") or []
        self._roles = []
        for r in roles_data:
            if not isinstance(r, dict):
                continue
            rid = r.get("roleId") or r.get("role_id") or r.get("id")
            if rid is None:
                continue
            rname = str(r.get("roleName") or r.get("role_name") or r.get("name") or "").strip()
            disp = f"{rid} | {rname}" if rname else str(rid)
            self._roles.append((str(rid), disp))

        self.user_completer.setModel(QStringListModel([d for _, d in self._users]))
        self.role_completer.setModel(QStringListModel([d for _, d in self._roles]))

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)

    def _id_from_display(self, text: str) -> str:
        raw = (text or "").strip()
        if "|" in raw:
            raw = raw.split("|", 1)[0].strip()
        return raw

    def is_dirty(self) -> bool:
        if self.user_input.text().strip():
            return True
        if self.role_input.text().strip():
            return True
        if self.default_role_chk.isChecked():
            return True
        return False

    def reset_to_default(self) -> None:
        self.user_input.clear()
        self.role_input.clear()
        self.default_role_chk.setChecked(False)
        self.valid_from_edit.setDateTime(QDateTime.currentDateTime())
        self.valid_to_edit.setDateTime(QDateTime.currentDateTime().addYears(1))

    def _handle_back(self) -> None:
        if not self.is_dirty():
            if self.on_back:
                self.on_back()
            return
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard and leave?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Discard:
            self.reset_to_default()
            if self.on_back:
                self.on_back()

    def _handle_create(self) -> None:
        self._clear_error()
        user_disp = self.user_input.text().strip()
        role_disp = self.role_input.text().strip()
        allowed_users = {d for _, d in self._users}
        allowed_roles = {d for _, d in self._roles}
        if not user_disp or user_disp not in allowed_users:
            self._show_error(strict_list_selection_message("a user"))
            return
        if not role_disp or role_disp not in allowed_roles:
            self._show_error(strict_list_selection_message("a role"))
            return
        user_id = self._id_from_display(user_disp)
        role_id = self._id_from_display(role_disp)

        vf_ymd = self.valid_from_edit.date().strftime("%Y-%m-%d")
        vt_ymd = self.valid_to_edit.date().strftime("%Y-%m-%d")
        if self.valid_to_edit.date() < self.valid_from_edit.date():
            self._show_error("Valid to must be greater than or equal to valid from.")
            return

        token = self._profile_token()
        result = api_assign_user_role(
            user_id=int(user_id) if user_id.isdigit() else user_id,
            role_id=int(role_id) if role_id.isdigit() else role_id,
            valid_from=f"{vf_ymd}T00:00:00",
            valid_to=f"{vt_ymd}T23:59:59",
            default_role=self.default_role_chk.isChecked(),
            token=token,
        )

        if result.get("success"):
            self._show_success(result.get("message", "Role assigned successfully."))

            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(result.get("message", "Failed to assign role."))
