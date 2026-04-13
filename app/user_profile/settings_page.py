"""Settings page with app preferences and Change Password."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.api import api_change_password, api_update_user_timezone
from core.app_preferences import get_iana_timezone_list, get_timezone, set_display_timezone
from core.user_context import get_user_profile, set_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    APP_FONT_SIZE_PX,
    FORM_ERROR_LABEL_STYLE,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    PAGE_SUBTITLE_STYLE,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET,
    MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET,
    MODAL_FIELD_HEIGHT_PX,
    MODAL_FIELD_LABEL_STYLE,
    MODAL_FEEDBACK_SUCCESS_STYLE,
)
from ui.post_save_navigation import NO_CHANGES_MESSAGE
from ui.widgets.password_edit import PasswordLineEdit
from ui.widgets.required_label import field_caption_label, labeled_field_block

LABEL_STYLE = (
    "color: #64748b; font-size: 10px; font-weight: 600; "
    "letter-spacing: 0.5px; text-transform: uppercase;"
)
SECTION_LABEL = (
    "font-size: 10px; font-weight: 600; color: #64748b; text-transform: uppercase; "
    "letter-spacing: 0.5px; padding: 0; margin: 0; border: none;"
)

# PasswordLineEdit outer shell (compact; eye toggle stays visible)
PWD_FIELD_STYLE = (
    f"#passwordLineEdit {{ font-size: {APP_FONT_SIZE_PX}px; border: 1px solid #e2e8f0; border-radius: 4px; "
    f"background-color: #ffffff; min-height: {MODAL_FIELD_HEIGHT_PX}px; max-height: {MODAL_FIELD_HEIGHT_PX}px; padding: 0 4px 0 8px; }} "
    "#passwordLineEdit:hover { border-color: #cbd5e1; } "
    f"#passwordLineEdit QLineEdit {{ border: none; background: transparent; font-size: {APP_FONT_SIZE_PX}px; padding: 2px 2px; }}"
)


class ChangePasswordDialog(QDialog):
    """Minimal change-password form (no duplicate copy; errors explain rules)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Change password")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setStyleSheet("QDialog { background: #ffffff; }")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)
        form.setContentsMargins(0, 0, 0, 0)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(14)

        for label_text, attr in [
            ("Current", "current_pwd"),
            ("New", "new_pwd"),
            ("Confirm", "confirm_pwd"),
        ]:
            lbl = QLabel(label_text)
            lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
            lbl.setMinimumWidth(64)
            edit = PasswordLineEdit(use_default_style=False)
            edit.setFixedHeight(MODAL_FIELD_HEIGHT_PX)
            edit.setStyleSheet(PWD_FIELD_STYLE)
            setattr(self, attr, edit)
            form.addRow(lbl, edit)

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

        change_btn = QPushButton("Update password")
        change_btn.setMinimumWidth(128)
        change_btn.setDefault(True)
        change_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        change_btn.clicked.connect(self._validate_and_accept)
        btn_row.addWidget(change_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(96)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    def _set_error(self, message: str) -> None:
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setText(message)
        self._error_label.setVisible(bool(message))

    def _set_success(self, message: str) -> None:
        self._error_label.setStyleSheet(MODAL_FEEDBACK_SUCCESS_STYLE)
        self._error_label.setText(message)
        self._error_label.setVisible(bool(message))

    def _validate_and_accept(self) -> None:
        current = self.current_pwd.text()
        new = self.new_pwd.text()
        confirm = self.confirm_pwd.text()

        self._set_error("")

        if not current:
            self._set_error("Please enter your current password.")
            return
        if not new:
            self._set_error("Please enter a new password.")
            return
        if len(new) < 6:
            self._set_error("New password must be at least 6 characters.")
            return
        if new != confirm:
            self._set_error("New password and confirmation do not match.")
            return

        profile = get_user_profile()
        user_name = profile.get("username") or profile.get("userName") or profile.get("user_name") or ""
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        if not user_name:
            self._set_error("User session not found. Please log in again.")
            return
        if not token:
            self._set_error("Session expired. Please log in again.")
            return

        result = api_change_password(
            current,
            new,
            token=token,
        )

        if result.get("success"):
            self._set_success(result.get("message", "Password updated successfully."))

            def _do_after() -> None:
                self._error_label.setText("")
                self._error_label.setVisible(False)
                self.accept()

            QTimer.singleShot(800, _do_after)
        else:
            self._set_error(result.get("message", "Password change failed."))


class SettingsPage(QWidget):
    """Settings page with preferences and Change Password (layout aligned with Users list)."""

    def __init__(self) -> None:
        super().__init__()
        self._build_ui()

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
        hl.addWidget(QLabel("Settings"))
        hl.addStretch()

        change_pwd_btn = QPushButton("Change Password")
        change_pwd_btn.setFixedWidth(150)
        change_pwd_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        change_pwd_btn.clicked.connect(self._show_change_password)
        hl.addWidget(change_pwd_btn)

        layout.addWidget(header)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(12)

        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._message_label.setVisible(False)
        content_layout.addWidget(self._message_label)

        subtitle = QLabel("Manage your account and app preferences.")
        subtitle.setStyleSheet(PAGE_SUBTITLE_STYLE)
        content_layout.addWidget(subtitle)

        prefs_card = QFrame()
        prefs_card.setObjectName("settingsPrefsCard")
        prefs_card.setStyleSheet(
            "#settingsPrefsCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        prefs_layout = QVBoxLayout(prefs_card)
        prefs_layout.setContentsMargins(20, 16, 20, 20)
        prefs_layout.setSpacing(16)

        section_label = QLabel("Preferences")
        section_label.setStyleSheet(SECTION_LABEL)
        section_label.setFixedHeight(20)
        prefs_layout.addWidget(section_label)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)

        self.timezone_combo = QComboBox()
        tz_list = get_iana_timezone_list()
        self.timezone_combo.addItem("Local (System)", "")
        for tz_id in tz_list:
            if tz_id:
                self.timezone_combo.addItem(tz_id, tz_id)
        apply_form_combobox_field(
            self.timezone_combo, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX, min_width=280
        )
        self._apply_saved_timezone()

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Light", "Dark", "System"])
        apply_form_combobox_field(
            self.theme_combo, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX, min_width=200
        )

        self.notifications_check = QCheckBox("Enable notifications")
        self.notifications_check.setChecked(True)

        grid.addWidget(
            labeled_field_block(field_caption_label("Timezone", LABEL_STYLE), self.timezone_combo),
            0,
            0,
            1,
            2,
        )
        grid.addWidget(
            labeled_field_block(field_caption_label("Theme", LABEL_STYLE), self.theme_combo),
            1,
            0,
            1,
            2,
        )
        grid.addWidget(self.notifications_check, 2, 0, 1, 2)
        prefs_layout.addLayout(grid)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        save_prefs_btn = QPushButton("Save preferences")
        save_prefs_btn.setMinimumWidth(120)
        save_prefs_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_prefs_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        save_prefs_btn.clicked.connect(self._save_preferences)
        btn_row.addWidget(save_prefs_btn)
        btn_row.addStretch()
        prefs_layout.addLayout(btn_row)

        content_layout.addWidget(prefs_card)
        content_layout.addStretch()

        layout.addWidget(content, 1)

    def _apply_saved_timezone(self) -> None:
        """Fill timezone from user profile (backend)."""
        saved = get_timezone()
        for i in range(self.timezone_combo.count()):
            if self.timezone_combo.itemData(i) == saved:
                self.timezone_combo.setCurrentIndex(i)
                return
        self.timezone_combo.setCurrentIndex(0)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, "timezone_combo"):
            self._apply_saved_timezone()

    def _show_change_password(self) -> None:
        dialog = ChangePasswordDialog(self)
        dialog.exec()

    def _save_preferences(self) -> None:
        tz_id = self.timezone_combo.currentData() or ""
        if (tz_id or "") == (get_timezone() or ""):
            show_auto_hiding_message(self, self._message_label, NO_CHANGES_MESSAGE, error=False)
            return
        profile = dict(get_user_profile())
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        user_id = (
            profile.get("id")
            or profile.get("userId")
            or profile.get("internalId")
            or profile.get("user_id")
            or profile.get("internal_id")
        )
        api_ok = True
        if user_id is not None and token:
            result = api_update_user_timezone(
                user_id=user_id,
                timezone=tz_id,
                token=token,
            )
            api_ok = result.get("success", False)
            if not api_ok:
                show_auto_hiding_message(
                    self,
                    self._message_label,
                    result.get("message", "Failed to save timezone to backend.")
                    + " Display will use selected timezone for this session.",
                    error=True,
                )

        profile["timezone"] = tz_id
        set_user_profile(profile)
        set_display_timezone(tz_id)

        if api_ok:
            theme = self.theme_combo.currentText()
            notifications = self.notifications_check.isChecked()
            tz_label = self.timezone_combo.currentText()
            msg = (
                f"Preferences saved. Timezone: {tz_label}, Theme: {theme}, "
                f"Notifications: {'On' if notifications else 'Off'}."
            )
            show_auto_hiding_message(self, self._message_label, msg, error=False)
