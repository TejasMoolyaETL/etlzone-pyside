"""Reset user password: same user table as Users; row opens password dialog (POST api/user/reset-user-password by default)."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.user_management.users.user_create import READONLY_INPUT_STYLE
from app.user_management.users.user_list import UsersPage
from core.api import api_reset_user_password
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_page_styles import (
    APP_FONT_SIZE_PX,
    FORM_ERROR_LABEL_STYLE,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET,
    MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET,
    MODAL_FEEDBACK_SUCCESS_STYLE,
    MODAL_FIELD_LABEL_STYLE,
    placeholder_confirm,
    placeholder_enter,
)
from ui.theme import Theme
from ui.widgets.password_edit import PasswordLineEdit


def _username_for_api(user: dict[str, Any]) -> str:
    for k in ("username", "userName", "user_name"):
        v = user.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


class ResetPasswordDialog(QDialog):
    """Prompt for new password and confirmation; POST api/user/reset-user-password (see ETL_RESET_USER_PASSWORD_PATH)."""

    def __init__(self, user: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._user = user
        self._username = _username_for_api(user)
        self.setWindowTitle("Reset password")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setStyleSheet("QDialog { background: #ffffff; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(0, 0, 0, 0)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(14)

        _field_h = FORM_SINGLELINE_FIELD_HEIGHT_PX
        _login_password_shell = (
            f"border: 1px solid {Theme.BORDER_INPUT}; border-radius: 6px; "
            f"background-color: {Theme.BG_WHITE};"
        )

        self._username_edit = QLineEdit()
        self._username_edit.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._username_edit.setText(self._username or "")
        self._username_edit.setReadOnly(True)
        self._username_edit.setFixedHeight(_field_h)
        self._username_edit.setStyleSheet(READONLY_INPUT_STYLE)
        user_lbl = QLabel("Username")
        user_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        user_lbl.setMinimumWidth(64)
        form.addRow(user_lbl, self._username_edit)

        self._pwd = PasswordLineEdit(use_default_style=False)
        self._pwd.setPlaceholderText(placeholder_enter("new password"))
        self._pwd.setText("")
        self._pwd.setFixedHeight(_field_h)
        self._pwd.setStyleSheet(_login_password_shell)
        self._pwd.set_inner_padding(
            "2px 8px",
            font_size_px=APP_FONT_SIZE_PX,
            color=Theme.TEXT_INPUT,
        )
        pwd_lbl = QLabel("New password")
        pwd_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        pwd_lbl.setMinimumWidth(64)
        form.addRow(pwd_lbl, self._pwd)

        self._confirm = PasswordLineEdit(use_default_style=False)
        self._confirm.setPlaceholderText(placeholder_confirm("new password"))
        self._confirm.setText("")
        self._confirm.setFixedHeight(_field_h)
        self._confirm.setStyleSheet(_login_password_shell)
        self._confirm.set_inner_padding(
            "2px 8px",
            font_size_px=APP_FONT_SIZE_PX,
            color=Theme.TEXT_INPUT,
        )
        confirm_lbl = QLabel("Confirm new password")
        confirm_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        confirm_lbl.setMinimumWidth(64)
        form.addRow(confirm_lbl, self._confirm)

        layout.addLayout(form)

        self._error_label = QLabel()
        self._error_label.setWordWrap(True)
        self._error_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._error_label.setVisible(False)
        layout.addWidget(self._error_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        reset_btn = QPushButton("Reset password")
        reset_btn.setMinimumWidth(128)
        reset_btn.setDefault(True)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        reset_btn.clicked.connect(self._submit)
        btn_row.addWidget(reset_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(96)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def _show_error(self, msg: str) -> None:
        show_auto_hiding_message(self, self._error_label, msg, error=True)

    def _show_success(self, msg: str) -> None:
        show_auto_hiding_message(self, self._error_label, msg, error=False)

    def _submit(self) -> None:
        self._clear_error()
        if not self._username:
            self._show_error("This user has no username in the list; cannot reset password.")
            return
        p1 = self._pwd.text()
        p2 = self._confirm.text()
        if not p1:
            self._show_error("Please enter a new password.")
            self._pwd.setFocus()
            return
        if len(p1) < 6:
            self._show_error("Password must be at least 6 characters.")
            self._pwd.setFocus()
            return
        if p1 != p2:
            self._show_error("Password and confirm password do not match.")
            self._confirm.setFocus()
            return

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_reset_user_password(self._username, p1, token=token)
        if not result.get("success"):
            self._show_error(result.get("message", "Failed to reset password."))
            return

        self._show_success("Password reset successfully.")
        QTimer.singleShot(900, self.accept)


class ResetUserPasswordPage(QWidget):
    """User table (same shell as Users list); double-click or context menu opens reset dialog."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self._page_message = QLabel("")
        self._page_message.setWordWrap(True)
        self._page_message.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._page_message.setVisible(False)
        layout.addWidget(self._page_message)
        self._list = UsersPage(
            on_create_clicked=None,
            on_edit_clicked=None,
            page_title="Reset User Password",
            show_create_button=False,
            on_row_activate=self._on_user_selected,
        )
        layout.addWidget(self._list)

    def _show_page_message(self, text: str, *, error: bool) -> None:
        self._page_message.setStyleSheet(
            FORM_ERROR_LABEL_STYLE if error else MODAL_FEEDBACK_SUCCESS_STYLE
        )
        self._page_message.setText(text)
        self._page_message.setVisible(bool(text))

    def _on_user_selected(self, user: dict[str, Any]) -> None:
        if not _username_for_api(user):
            self._show_page_message("This row has no username; cannot call reset API.", error=True)
            return
        self._page_message.setText("")
        self._page_message.setVisible(False)
        dlg = ResetPasswordDialog(user, self)
        dlg.exec()

    def refresh(self) -> None:
        self._list.refresh()
