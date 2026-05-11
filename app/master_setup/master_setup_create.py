"""Create Master Setup page."""

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

from core.api import (
    api_create_master_key_value,
    api_get_all_master_setup_key_entries,
    master_setup_key_entry_category_combo_options,
)
from app.master_setup.master_setup_view import category_id_from_master_setup_category_combo
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    placeholder_example,
)
from ui.post_save_navigation import schedule_after_success
from ui.widgets.required_label import field_caption_label, labeled_field_block


class CreateMasterSetupPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._allowed_category_ids: set[int] = set()
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
        title = QLabel("Create Master Setup Value")
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

        category_lbl = field_caption_label("Category*", LABEL_STYLE)
        self.category_combo = QComboBox()
        self.category_combo.setEditable(False)
        self.category_combo.addItem("— Select category —", None)
        apply_form_combobox_field(
            self.category_combo,
            height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX,
            min_width=280,
        )
        card_layout.addWidget(labeled_field_block(category_lbl, self.category_combo))

        seq_lbl = field_caption_label("Seq*", LABEL_STYLE)
        self.seq_edit = QLineEdit()
        self.seq_edit.setPlaceholderText(placeholder_example("1"))
        self.seq_edit.setStyleSheet(INPUT_STYLE)
        self.seq_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
        card_layout.addWidget(labeled_field_block(seq_lbl, self.seq_edit))

        key_value_lbl = field_caption_label("Key Value*", LABEL_STYLE)
        self.key_value_edit = QLineEdit()
        self.key_value_edit.setPlaceholderText(placeholder_example("In Scope"))
        self.key_value_edit.setStyleSheet(INPUT_STYLE)
        self.key_value_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
        card_layout.addWidget(labeled_field_block(key_value_lbl, self.key_value_edit))

        desc_lbl = field_caption_label("Description", LABEL_STYLE)
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText(placeholder_example("Added from app"))
        self.description_edit.setStyleSheet(INPUT_STYLE)
        self.description_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
        card_layout.addWidget(labeled_field_block(desc_lbl, self.description_edit))

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

    def is_dirty(self) -> bool:
        return (
            category_id_from_master_setup_category_combo(self.category_combo) is not None
            or bool(self.seq_edit.text().strip())
            or bool(self.key_value_edit.text().strip())
            or bool(self.description_edit.text().strip())
        )

    def reset_to_default(self) -> None:
        self.category_combo.setCurrentIndex(0)
        self.seq_edit.clear()
        self.key_value_edit.clear()
        self.description_edit.clear()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        preserve = category_id_from_master_setup_category_combo(self.category_combo)
        self._load_categories(preserve_category_id=preserve)

    def refresh_categories(self) -> None:
        """Reload master-key options (e.g. after creating a Master Setup Key elsewhere)."""
        pid = category_id_from_master_setup_category_combo(self.category_combo)
        self._load_categories(preserve_category_id=pid)

    def _load_categories(self, *, preserve_category_id: int | None = None) -> None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_master_setup_key_entries(token=token)
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("— Select category —", None)
        self._allowed_category_ids.clear()
        if result.get("success"):
            rows = result.get("data") or []
            for label, cid in master_setup_key_entry_category_combo_options(rows):
                self.category_combo.addItem(label, cid)
                self._allowed_category_ids.add(cid)
        if preserve_category_id is not None:
            idx = self.category_combo.findData(preserve_category_id)
            if idx >= 0:
                self.category_combo.setCurrentIndex(idx)
            else:
                self.category_combo.setCurrentIndex(0)
        else:
            self.category_combo.setCurrentIndex(0)
        self.category_combo.blockSignals(False)

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
        category_id = category_id_from_master_setup_category_combo(self.category_combo)
        if category_id is None:
            self._show_error("Category is required.")
            self.category_combo.setFocus()
            return
        if category_id not in self._allowed_category_ids:
            self._show_error("Category must be selected from the available list.")
            self.category_combo.setFocus()
            return
        seq_text = self.seq_edit.text().strip()
        if not seq_text:
            self._show_error("Seq is required.")
            self.seq_edit.setFocus()
            return
        key_value = self.key_value_edit.text().strip()
        if not key_value:
            self._show_error("Key value is required.")
            self.key_value_edit.setFocus()
            return
        description = self.description_edit.text().strip()

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_create_master_key_value(
            category_id=category_id,
            seq=seq_text,
            key_value=key_value,
            description=description,
            token=token,
        )
        if result.get("success"):
            self._show_success(str(result.get("message") or "Master setup entry created successfully."))
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(str(result.get("message") or "Failed to create master setup entry."))
