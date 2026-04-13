"""Create Organization page - form to add a new organization."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
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

from core.api import api_create_org
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    placeholder_example,
)
from ui.post_save_navigation import schedule_after_success
from ui.widgets.required_label import field_caption_label, labeled_field_block

_ORG_STATUS = ("ACTIVE", "INACTIVE", "DISABLE", "COMPLETE")


class CreateOrgPage(QWidget):
    """Page with form to create a new organization."""

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
        title = QLabel("Create Organization")
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
        card.setMaximumWidth(520)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        # Org Name
        label_name = field_caption_label("Organization Name*", LABEL_STYLE)
        self.org_name_edit = QLineEdit()
        self.org_name_edit.setPlaceholderText(placeholder_example("ETLZONE2"))
        self.org_name_edit.setStyleSheet(INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_name, self.org_name_edit))

        # Org Code
        label_code = field_caption_label("Organization Code*", LABEL_STYLE)
        self.org_code_edit = QLineEdit()
        self.org_code_edit.setPlaceholderText(placeholder_example("ETL123"))
        self.org_code_edit.setStyleSheet(INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_code, self.org_code_edit))

        # Industry
        label_industry = field_caption_label("Industry*", LABEL_STYLE)
        self.industry_edit = QLineEdit()
        self.industry_edit.setPlaceholderText(placeholder_example("IT"))
        self.industry_edit.setStyleSheet(INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_industry, self.industry_edit))

        # Status
        label_status = QLabel("Status:")
        label_status.setStyleSheet(LABEL_STYLE)
        self.status_combo = QComboBox()
        self.status_combo.addItems(_ORG_STATUS)
        self.status_combo.setCurrentText("ACTIVE")
        apply_form_combobox_field(self.status_combo, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX)
        card_layout.addWidget(labeled_field_block(label_status, self.status_combo))

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

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)

    def _get_default_values(self) -> dict[str, str]:
        return {
            "org_name": "",
            "org_code": "",
            "industry": "",
            "status": "ACTIVE",
        }

    def is_dirty(self) -> bool:
        d = self._get_default_values()
        return (
            self.org_name_edit.text().strip() != d["org_name"]
            or self.org_code_edit.text().strip() != d["org_code"]
            or self.industry_edit.text().strip() != d["industry"]
            or self.status_combo.currentText() != d["status"]
        )

    def reset_to_default(self) -> None:
        self.org_name_edit.clear()
        self.org_code_edit.clear()
        self.industry_edit.clear()
        self.status_combo.setCurrentText("ACTIVE")

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
        org_name = self.org_name_edit.text().strip()
        if not org_name:
            self._show_error("Organization name is required.")
            return
        org_code = self.org_code_edit.text().strip()
        if not org_code:
            self._show_error("Organization code is required.")
            return
        industry = self.industry_edit.text().strip()
        if not industry:
            self._show_error("Industry is required.")
            return
        status = self.status_combo.currentText() or "ACTIVE"

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_create_org(
            org_name=org_name,
            org_code=org_code,
            industry=industry,
            status=status,
            token=token,
        )

        if result.get("success"):
            self._show_success(result.get("message", "Organization created successfully."))

            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(result.get("message", "Failed to create organization."))
