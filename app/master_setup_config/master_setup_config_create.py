"""Create Master Setup Config page."""

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

from app.master_setup.master_setup_view import category_id_from_master_setup_category_combo
from core.api import (
    api_create_master_setup_config,
    api_get_all_master_setup_key_entries,
    master_setup_key_entry_category_combo_options,
)
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
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    placeholder_example,
)
from ui.post_save_navigation import schedule_after_success
from ui.widgets.required_label import field_caption_label, labeled_field_block


class CreateMasterSetupConfigPage(QWidget):
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
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("Create Master Setup Config"))
        hl.addStretch()
        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._handle_back)
        hl.addWidget(back_btn)
        layout.addWidget(header)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(12)
        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card.setMaximumWidth(620)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        field_lbl = field_caption_label("Field*", LABEL_STYLE)
        self.field_edit = QLineEdit()
        self.field_edit.setPlaceholderText(placeholder_example("api_status"))
        self.field_edit.setStyleSheet(INPUT_STYLE)
        self.field_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
        card_layout.addWidget(labeled_field_block(field_lbl, self.field_edit))

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

        card_layout.addSpacing(16)
        self.error_label = QLabel()
        self.error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.error_label.setWordWrap(True)
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

        cl.addWidget(card)
        cl.addStretch()
        layout.addWidget(content)

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = profile.get("token") or profile.get("accessToken") or profile.get("access_token") or profile.get("jwt")
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
        return bool(
            self.field_edit.text().strip()
            or category_id_from_master_setup_category_combo(self.category_combo) is not None
        )

    def reset_to_default(self) -> None:
        self.field_edit.clear()
        self.category_combo.setCurrentIndex(0)
        self._clear_error()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self._load_categories()

    def _load_categories(self) -> None:
        result = api_get_all_master_setup_key_entries(token=self._token())
        rows = result.get("data") if result.get("success") else []
        preserve = category_id_from_master_setup_category_combo(self.category_combo)
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItem("— Select category —", None)
        self._allowed_category_ids.clear()
        if isinstance(rows, list):
            for label, cid in master_setup_key_entry_category_combo_options(rows):
                self.category_combo.addItem(label, cid)
                self._allowed_category_ids.add(cid)
        if preserve is not None:
            idx = self.category_combo.findData(preserve)
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
        field = self.field_edit.text().strip()
        category_id = category_id_from_master_setup_category_combo(self.category_combo)
        if not field:
            self._show_error("Field is required.")
            return
        if category_id is None:
            self._show_error("Category is required.")
            self.category_combo.setFocus()
            return
        if category_id not in self._allowed_category_ids:
            self._show_error("Category must be selected from the available list.")
            self.category_combo.setFocus()
            return
        result = api_create_master_setup_config(
            field=field,
            category_id=category_id,
            token=self._token(),
        )
        if result.get("success"):
            self._show_success(str(result.get("message") or "Master setup config created successfully."))
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(str(result.get("message") or "Failed to create master setup config."))
