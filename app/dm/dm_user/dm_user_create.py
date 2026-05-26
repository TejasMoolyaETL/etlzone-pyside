"""Create DM User page."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.dm.dm_user.dm_user_form_helpers import (
    DM_USER_STATUS_FIELD_NAME,
    create_mobile_field_row,
    update_email_style,
    update_mobile_style,
    full_mobile_number,
    validate_email_input,
    validate_mobile_input,
    wire_mobile_live_validation,
)
from core.api import api_create_dmt_user
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    MODAL_FIELD_HEIGHT_PX,
    placeholder_example,
)
from ui.post_save_navigation import schedule_after_success
from ui.searchable_form_combo import (
    combo_resolved_master_key_seq,
    require_master_key_seq_for_payload,
    populate_master_key_by_field_name,
    reset_searchable_combo,
    wire_searchable_master_key_combo,
)
from ui.widgets.required_label import field_caption_label, labeled_field_block


class CreateDmUserPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._status_combo: QComboBox | None = None
        self._mobile_country: QComboBox | None = None
        self._mobile_number: QLineEdit | None = None
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
        title = QLabel("Create User")
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

        field_h = MODAL_FIELD_HEIGHT_PX

        self.first_name_edit = QLineEdit()
        self.first_name_edit.setPlaceholderText(placeholder_example("ali"))
        self.first_name_edit.setStyleSheet(INPUT_STYLE)
        self.first_name_edit.setFixedHeight(field_h)
        self.first_name_edit.setMinimumWidth(360)
        self.first_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card_layout.addWidget(
            labeled_field_block(field_caption_label("First name*", LABEL_STYLE), self.first_name_edit)
        )

        self.last_name_edit = QLineEdit()
        self.last_name_edit.setPlaceholderText(placeholder_example("java team"))
        self.last_name_edit.setStyleSheet(INPUT_STYLE)
        self.last_name_edit.setFixedHeight(field_h)
        self.last_name_edit.setMinimumWidth(360)
        self.last_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card_layout.addWidget(
            labeled_field_block(field_caption_label("Last name*", LABEL_STYLE), self.last_name_edit)
        )

        status_combo = QComboBox()
        apply_form_combobox_field(status_combo, height_px=field_h, min_width=360)
        wire_searchable_master_key_combo(status_combo, search_field_label="Status")
        self._status_combo = status_combo
        card_layout.addWidget(
            labeled_field_block(field_caption_label("Status*", LABEL_STYLE), status_combo)
        )

        self.email_edit = QLineEdit()
        self.email_edit.setPlaceholderText(placeholder_example("abc@gmail.com"))
        self.email_edit.setStyleSheet(INPUT_STYLE)
        self.email_edit.setFixedHeight(field_h)
        self.email_edit.setMinimumWidth(360)
        self.email_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.email_edit.textChanged.connect(
            lambda text: update_email_style(self.email_edit, text)
        )
        card_layout.addWidget(
            labeled_field_block(field_caption_label("Email*", LABEL_STYLE), self.email_edit)
        )

        mobile_container, self._mobile_country, self._mobile_number = create_mobile_field_row(
            field_h=field_h
        )
        wire_mobile_live_validation(self._mobile_country, self._mobile_number)
        card_layout.addWidget(
            labeled_field_block(field_caption_label("Mobile*", LABEL_STYLE), mobile_container)
        )

        card_layout.addSpacing(16)
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
        if self._status_combo is not None:
            populate_master_key_by_field_name(
                self._status_combo,
                DM_USER_STATUS_FIELD_NAME,
                token=self._token(),
                include_placeholder=False,
            )

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)

    def is_dirty(self) -> bool:
        if self.first_name_edit.text().strip() or self.last_name_edit.text().strip():
            return True
        if self.email_edit.text().strip():
            return True
        if self._mobile_number and self._mobile_number.text().strip():
            return True
        if self._status_combo is not None:
            seq = combo_resolved_master_key_seq(self._status_combo)
            if seq is not None and str(seq).strip() != "":
                return True
        return False

    def reset_to_default(self) -> None:
        self.first_name_edit.clear()
        self.last_name_edit.clear()
        if self._status_combo is not None:
            reset_searchable_combo(self._status_combo)
        self.email_edit.clear()
        if self._mobile_country is not None:
            self._mobile_country.blockSignals(True)
            self._mobile_country.setCurrentIndex(0)
            self._mobile_country.blockSignals(False)
        if self._mobile_number is not None:
            self._mobile_number.clear()
        update_email_style(self.email_edit, "")
        if self._mobile_country is not None and self._mobile_number is not None:
            update_mobile_style(self._mobile_country, self._mobile_number)
        self._clear_error()

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
        first_name = self.first_name_edit.text().strip()
        last_name = self.last_name_edit.text().strip()
        email = self.email_edit.text().strip()

        if not first_name:
            self._show_error("First name is required.")
            self.first_name_edit.setFocus()
            return
        if not last_name:
            self._show_error("Last name is required.")
            self.last_name_edit.setFocus()
            return

        email_err = validate_email_input(email)
        if email_err:
            self._show_error(email_err)
            self.email_edit.setFocus()
            return

        if self._mobile_country is None or self._mobile_number is None:
            self._show_error("Mobile fields are not available.")
            return
        mobile_err, country_code, mobile = validate_mobile_input(
            self._mobile_country, self._mobile_number
        )
        if mobile_err:
            self._show_error(mobile_err)
            self._mobile_number.setFocus()
            return

        status_id, status_err = require_master_key_seq_for_payload(
            self._status_combo, field_caption="Status", strict_phrase="a status"
        )
        if status_err:
            self._show_error(status_err)
            if self._status_combo is not None:
                self._status_combo.setFocus()
            return

        result = api_create_dmt_user(
            first_name=first_name,
            last_name=last_name,
            email=email,
            mobile=full_mobile_number(country_code, mobile),
            status=status_id,
            token=self._token(),
        )
        if result.get("success"):
            self._show_success(str(result.get("message") or "User created successfully."))
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(str(result.get("message") or "Failed to create user."))
