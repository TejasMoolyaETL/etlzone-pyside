"""Create DMT Object page — layout aligned with Create Module."""

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

from core.api import api_create_object, api_get_all_modules
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
    master_key_invalid_typed_text,
    master_key_seq_for_payload,
    require_master_key_seq_for_payload,
    populate_master_key_by_field_name,
    reset_searchable_combo,
    wire_searchable_master_key_combo,
)
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label, labeled_field_block


_DMT_OBJECT_STATUS_FIELD_NAME = "dmt_object_status"


class CreateDmtObjectPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._status_combo: QComboBox | None = None
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
        title = QLabel("Create Object")
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
        mod_lbl = field_caption_label("Module*", LABEL_STYLE)
        self.module_combo = QComboBox()
        self.module_combo.addItem("— Select module —", None)
        apply_form_combobox_field(
            self.module_combo,
            height_px=field_h,
            min_width=360,
        )
        card_layout.addWidget(labeled_field_block(mod_lbl, self.module_combo))

        name_lbl = field_caption_label("Object Name*", LABEL_STYLE)
        self.object_name_edit = QLineEdit()
        self.object_name_edit.setPlaceholderText(placeholder_example("Customer dimension"))
        self.object_name_edit.setStyleSheet(INPUT_STYLE)
        self.object_name_edit.setFixedHeight(field_h)
        self.object_name_edit.setMinimumWidth(360)
        self.object_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card_layout.addWidget(labeled_field_block(name_lbl, self.object_name_edit))

        status_lbl = field_caption_label("Status*", LABEL_STYLE)
        status_combo = QComboBox()
        status_combo.setMinimumWidth(360)
        status_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(status_combo, height_px=field_h)
        wire_searchable_master_key_combo(status_combo, search_field_label="Status")
        self._status_combo = status_combo
        card_layout.addWidget(labeled_field_block(status_lbl, status_combo))

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
        self._load_modules_into_combo()
        if self._status_combo is not None:
            populate_master_key_by_field_name(
                self._status_combo,
                _DMT_OBJECT_STATUS_FIELD_NAME,
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

    def _load_modules_into_combo(self) -> None:
        token = self._token()
        self.module_combo.blockSignals(True)
        self.module_combo.clear()
        self.module_combo.addItem("— Select module —", None)
        result = api_get_all_modules(token=token)
        if result.get("success"):
            rows = result.get("data") or []
            for r in rows:
                if not isinstance(r, dict):
                    continue
                mid = r.get("moduleId") or r.get("id")
                label = str(r.get("moduleName") or r.get("name") or mid or "?")
                if mid is not None:
                    self.module_combo.addItem(label, mid)
        else:
            self._show_error(str(result.get("message") or "Failed to load modules."))
        self.module_combo.setCurrentIndex(0)
        self.module_combo.blockSignals(False)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)

    def is_dirty(self) -> bool:
        if self.object_name_edit.text().strip():
            return True
        if self.module_combo.currentData() is not None:
            return True
        if self._status_combo is not None:
            seq = combo_resolved_master_key_seq(self._status_combo)
            if seq is not None and str(seq).strip() != "":
                return True
        return False

    def reset_to_default(self) -> None:
        self.object_name_edit.clear()
        self.module_combo.setCurrentIndex(0)
        if self._status_combo is not None:
            reset_searchable_combo(self._status_combo)
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
        mid = self.module_combo.currentData()
        if mid is None:
            self._show_error("Please select a module.")
            self.module_combo.setFocus()
            return
        name = self.object_name_edit.text().strip()
        if not name:
            self._show_error("Object name is required.")
            self.object_name_edit.setFocus()
            return
        status_id, status_err = require_master_key_seq_for_payload(
            self._status_combo, field_caption="Status", strict_phrase="a status"
        )
        if status_err:
            self._show_error(status_err)
            if self._status_combo is not None:
                self._status_combo.setFocus()
            return
        result = api_create_object(name, mid, status=status_id, token=self._token())
        if result.get("success"):
            self._show_success(str(result.get("message") or "Object created successfully."))
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(str(result.get("message") or "Failed to create object."))
