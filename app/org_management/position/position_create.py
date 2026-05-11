"""Create Position — POST api/positions/create-position."""

from __future__ import annotations

from typing import Any, Callable

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

from core.api import (
    api_create_position,
    api_get_master_key_by_app_id_field_name,
    master_key_row_display_label,
    master_key_row_seq_value,
)
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

_POSITION_STATUS_FIELD_NAME = "position_status"


def _coerce_master_seq_to_int(seq_val: Any) -> int:
    """Send master-key seq as integer in JSON payload."""
    if isinstance(seq_val, bool):
        return int(seq_val)
    if isinstance(seq_val, int):
        return seq_val
    if isinstance(seq_val, float) and seq_val == int(seq_val):
        return int(seq_val)
    s = str(seq_val).strip()
    if s.isdigit():
        return int(s)
    raise ValueError(f"Not a whole number: {seq_val!r}")


class CreatePositionPage(QWidget):
    """Form: positionName + hierarchyLevel."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._hierarchy_values = [str(i) for i in range(1, 31)]
        self._default_hierarchy = "1"
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
        title = QLabel("Create Position")
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

        label_name = field_caption_label("Position Name*", LABEL_STYLE)
        self.position_name_edit = QLineEdit()
        self.position_name_edit.setPlaceholderText(placeholder_example("Developer"))
        self.position_name_edit.setStyleSheet(INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_name, self.position_name_edit))

        label_level = field_caption_label("Hierarchy Level*", LABEL_STYLE)
        self.hierarchy_combo = QComboBox()
        self.hierarchy_combo.addItems(self._hierarchy_values)
        self.hierarchy_combo.setCurrentText(self._default_hierarchy)
        apply_form_combobox_field(self.hierarchy_combo, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX)
        card_layout.addWidget(labeled_field_block(label_level, self.hierarchy_combo))

        label_status = field_caption_label("Status*", LABEL_STYLE)
        self.status_combo = QComboBox()
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

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._populate_master_key_seq_combo(
            self.status_combo,
            _POSITION_STATUS_FIELD_NAME,
            "Select status…",
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

    def _populate_master_key_seq_combo(
        self,
        combo: QComboBox | None,
        field_name: str,
        placeholder: str,
    ) -> None:
        if combo is None:
            return
        result = api_get_master_key_by_app_id_field_name(
            field_name=field_name,
            token=self._token(),
        )
        rows = result.get("data") if result.get("success") else []
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(placeholder, None)
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                seq_val = master_key_row_seq_value(row)
                if seq_val is None:
                    continue
                label = master_key_row_display_label(row).strip()
                if not label:
                    continue
                combo.addItem(label, seq_val)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)

    def is_dirty(self) -> bool:
        if self.position_name_edit.text().strip():
            return True
        if self.hierarchy_combo.currentText().strip() != self._default_hierarchy:
            return True
        if self.status_combo.currentIndex() > 0:
            return True
        return False

    def reset_to_default(self) -> None:
        self.position_name_edit.clear()
        self.hierarchy_combo.setCurrentText(self._default_hierarchy)
        self.status_combo.setCurrentIndex(0)

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
        name = self.position_name_edit.text().strip()
        if not name:
            self._show_error("Position name is required.")
            return

        if self.status_combo.currentIndex() <= 0:
            self._show_error("Status is required.")
            self.status_combo.setFocus()
            return
        status_raw = self.status_combo.currentData()
        if status_raw is None:
            self._show_error("Status is required.")
            self.status_combo.setFocus()
            return
        try:
            status_seq = _coerce_master_seq_to_int(status_raw)
        except ValueError:
            self._show_error("Status must be a valid selection.")
            self.status_combo.setFocus()
            return

        result = api_create_position(
            name,
            int(self.hierarchy_combo.currentText()),
            status=status_seq,
            token=self._token(),
        )

        if result.get("success"):
            self._show_success(result.get("message", "Position created successfully."))

            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(result.get("message", "Failed to create position."))
