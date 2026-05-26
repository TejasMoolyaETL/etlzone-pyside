"""Create Project page — layout aligned with org_create (CreateOrgPage)."""

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

from core.api import api_create_project
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
from ui.searchable_form_combo import wire_searchable_labeled_rows_combo
from ui.widgets.required_label import field_caption_label, labeled_field_block

_PROJECT_STATUS = ("ACTIVE", "INACTIVE", "DISABLE", "COMPLETE")


class CreateProjectPage(QWidget):
    """Page with form to create a new API project (same pattern as CreateOrgPage)."""

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
        title = QLabel("Create Project")
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

        label_name = field_caption_label("Project Name*", LABEL_STYLE)
        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText(placeholder_example("Etlzone App"))
        self.project_name_edit.setStyleSheet(INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_name, self.project_name_edit))

        label_desc = field_caption_label("Project Description", LABEL_STYLE)
        self.project_desc_edit = QLineEdit()
        self.project_desc_edit.setPlaceholderText("Optional")
        self.project_desc_edit.setStyleSheet(INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_desc, self.project_desc_edit))

        label_owner = field_caption_label("Project Owner User ID*", LABEL_STYLE)
        self.project_owner_edit = QLineEdit()
        self.project_owner_edit.setPlaceholderText("Required")
        self.project_owner_edit.setStyleSheet(INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_owner, self.project_owner_edit))

        label_status = QLabel("Project Status:")
        label_status.setStyleSheet(LABEL_STYLE)
        self.project_status_combo = QComboBox()
        apply_form_combobox_field(self.project_status_combo, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX)
        wire_searchable_labeled_rows_combo(
            self.project_status_combo,
            rows=[(s, s) for s in _PROJECT_STATUS],
            search_field_label="Project status",
            default_display_text="ACTIVE",
        )
        card_layout.addWidget(labeled_field_block(label_status, self.project_status_combo))

        label_server = QLabel("Project Server:")
        label_server.setStyleSheet(LABEL_STYLE)
        self.project_server_edit = QLineEdit()
        self.project_server_edit.setPlaceholderText(placeholder_example("192.168.1.100"))
        self.project_server_edit.setStyleSheet(INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_server, self.project_server_edit))

        label_port = QLabel("Project Port:")
        label_port.setStyleSheet(LABEL_STYLE)
        self.project_port_edit = QLineEdit()
        self.project_port_edit.setPlaceholderText(placeholder_example("9091"))
        self.project_port_edit.setStyleSheet(INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_port, self.project_port_edit))

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
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self._handle_back)
        btn_layout.addWidget(create_btn)
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
            "project_name": "",
            "project_desc": "",
            "project_owner": "",
            "project_status": "ACTIVE",
            "project_server": "",
            "project_port": "",
        }

    def is_dirty(self) -> bool:
        d = self._get_default_values()
        return (
            self.project_name_edit.text().strip() != d["project_name"]
            or self.project_desc_edit.text().strip() != d["project_desc"]
            or self.project_owner_edit.text().strip() != d["project_owner"]
            or self.project_status_combo.currentText() != d["project_status"]
            or self.project_server_edit.text().strip() != d["project_server"]
            or self.project_port_edit.text().strip() != d["project_port"]
        )

    def reset_to_default(self) -> None:
        self.project_name_edit.clear()
        self.project_desc_edit.clear()
        self.project_owner_edit.clear()
        self.project_status_combo.setCurrentText("ACTIVE")
        self.project_server_edit.clear()
        self.project_port_edit.clear()

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
        project_name = self.project_name_edit.text().strip()
        if not project_name:
            self._show_error("Project name is required.")
            return

        project_owner = self.project_owner_edit.text().strip()
        if not project_owner:
            self._show_error("Project Owner User ID is required.")
            return

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_create_project(
            project_name,
            token=token,
            project_desc=self.project_desc_edit.text().strip() or None,
            project_owner_user_id=project_owner,
            project_status=self.project_status_combo.currentText() or "ACTIVE",
            project_server=self.project_server_edit.text().strip() or None,
            project_port=self.project_port_edit.text().strip() or None,
        )

        if result.get("success"):
            self._show_success(result.get("message", "Project created successfully."))

            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(result.get("message", "Failed to create project."))
