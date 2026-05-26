"""Create DMT Issue Tracker record page."""

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
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.api import api_create_issue_tracker, api_get_all_modules, api_get_all_objects
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

_FIELD_STATUS = "dmt_issue_tracker_status"
_FIELD_PRIORITY = "dmt_issue_priority"


class CreateDmtIssueTrackerPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._module_combo: QComboBox | None = None
        self._object_combo: QComboBox | None = None
        self._status_combo: QComboBox | None = None
        self._priority_combo: QComboBox | None = None
        self._object_rows: list[dict[str, Any]] = []
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
        header_layout.addWidget(QLabel("Create Issue"))
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
        card.setMaximumWidth(720)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)
        field_h = MODAL_FIELD_HEIGHT_PX

        self._module_combo = QComboBox()
        apply_form_combobox_field(self._module_combo, height_px=field_h, min_width=360)
        self._module_combo.currentIndexChanged.connect(self._on_module_changed)
        card_layout.addWidget(
            labeled_field_block(field_caption_label("Module*", LABEL_STYLE), self._module_combo)
        )

        self._object_combo = QComboBox()
        apply_form_combobox_field(self._object_combo, height_px=field_h, min_width=360)
        card_layout.addWidget(
            labeled_field_block(field_caption_label("Object*", LABEL_STYLE), self._object_combo)
        )

        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(placeholder_example("Data load failure in LIS"))
        self.title_edit.setStyleSheet(INPUT_STYLE)
        self.title_edit.setFixedHeight(field_h)
        card_layout.addWidget(
            labeled_field_block(field_caption_label("Issue title*", LABEL_STYLE), self.title_edit)
        )

        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText(placeholder_example("Describe the issue…"))
        self.description_edit.setStyleSheet(INPUT_STYLE)
        self.description_edit.setFixedHeight(100)
        card_layout.addWidget(
            labeled_field_block(field_caption_label("Description", LABEL_STYLE), self.description_edit)
        )

        self._status_combo = QComboBox()
        apply_form_combobox_field(self._status_combo, height_px=field_h, min_width=360)
        wire_searchable_master_key_combo(self._status_combo, search_field_label="Status")
        card_layout.addWidget(
            labeled_field_block(field_caption_label("Status*", LABEL_STYLE), self._status_combo)
        )

        self._priority_combo = QComboBox()
        apply_form_combobox_field(self._priority_combo, height_px=field_h, min_width=360)
        wire_searchable_master_key_combo(self._priority_combo, search_field_label="Priority")
        card_layout.addWidget(
            labeled_field_block(field_caption_label("Priority", LABEL_STYLE), self._priority_combo)
        )

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

        content_layout.addWidget(card)
        content_layout.addStretch()
        layout.addWidget(content)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._load_modules()
        if self._status_combo is not None:
            populate_master_key_by_field_name(
                self._status_combo, _FIELD_STATUS, token=self._token(), include_placeholder=False
            )
        if self._priority_combo is not None:
            populate_master_key_by_field_name(
                self._priority_combo, _FIELD_PRIORITY, token=self._token(), include_placeholder=False
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

    def _load_modules(self) -> None:
        if self._module_combo is None:
            return
        self._module_combo.blockSignals(True)
        self._module_combo.clear()
        self._module_combo.addItem("— Select module —", None)
        result = api_get_all_modules(token=self._token())
        if result.get("success"):
            for row in result.get("data") or []:
                if not isinstance(row, dict):
                    continue
                mid = row.get("moduleId") or row.get("id")
                label = str(row.get("moduleName") or row.get("name") or mid or "?")
                if mid is not None:
                    self._module_combo.addItem(label, mid)
        else:
            self._show_error(str(result.get("message") or "Failed to load modules."))
        self._module_combo.setCurrentIndex(0)
        self._module_combo.blockSignals(False)
        self._reload_objects_for_module()

    def _on_module_changed(self) -> None:
        self._reload_objects_for_module()

    def _reload_objects_for_module(self) -> None:
        if self._object_combo is None:
            return
        self._object_combo.blockSignals(True)
        self._object_combo.clear()
        self._object_combo.addItem("— Select object —", None)
        module_id = self._module_combo.currentData() if self._module_combo else None
        if module_id is None:
            self._object_combo.setCurrentIndex(0)
            self._object_combo.blockSignals(False)
            return
        result = api_get_all_objects(token=self._token())
        if result.get("success"):
            self._object_rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
            for row in self._object_rows:
                row_module = row.get("moduleId") or row.get("module_id")
                if row_module is not None and str(row_module) != str(module_id):
                    continue
                oid = row.get("objectId") or row.get("id")
                label = str(row.get("objectName") or row.get("name") or oid or "?")
                if oid is not None:
                    self._object_combo.addItem(label, oid)
        self._object_combo.setCurrentIndex(0)
        self._object_combo.blockSignals(False)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=True)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)

    def is_dirty(self) -> bool:
        if self.title_edit.text().strip() or self.description_edit.toPlainText().strip():
            return True
        if self._module_combo and self._module_combo.currentData() is not None:
            return True
        if self._object_combo and self._object_combo.currentData() is not None:
            return True
        for combo in (self._status_combo, self._priority_combo):
            if combo is not None:
                seq = combo_resolved_master_key_seq(combo)
                if seq is not None and str(seq).strip():
                    return True
        return False

    def reset_to_default(self) -> None:
        self.title_edit.clear()
        self.description_edit.clear()
        if self._module_combo is not None:
            self._module_combo.setCurrentIndex(0)
        if self._object_combo is not None:
            self._object_combo.setCurrentIndex(0)
        for combo in (self._status_combo, self._priority_combo):
            if combo is not None:
                reset_searchable_combo(combo)
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
        module_id = self._module_combo.currentData() if self._module_combo else None
        if module_id is None:
            self._show_error("Please select a module.")
            if self._module_combo is not None:
                self._module_combo.setFocus()
            return
        object_id = self._object_combo.currentData() if self._object_combo else None
        if object_id is None:
            self._show_error("Please select an object.")
            if self._object_combo is not None:
                self._object_combo.setFocus()
            return
        title = self.title_edit.text().strip()
        if not title:
            self._show_error("Issue title is required.")
            self.title_edit.setFocus()
            return
        status_id, status_err = require_master_key_seq_for_payload(
            self._status_combo, field_caption="Status", strict_phrase="a status"
        )
        if status_err:
            self._show_error(status_err)
            if self._status_combo is not None:
                self._status_combo.setFocus()
            return
        if master_key_invalid_typed_text(self._priority_combo):
            self._show_error(strict_list_selection_message("a priority"))
            if self._priority_combo is not None:
                self._priority_combo.setFocus()
            return

        payload: dict[str, Any] = {
            "moduleId": module_id,
            "objectId": object_id,
            "issueTitle": title,
            "status": status_id,
            "priority": master_key_seq_for_payload(self._priority_combo),
        }
        description = self.description_edit.toPlainText().strip()
        if description:
            payload["issueDescription"] = description

        result = api_create_issue_tracker(payload, token=self._token())
        if result.get("success"):
            show_auto_hiding_message(
                self,
                self.error_label,
                str(result.get("message") or "Issue created successfully."),
                error=False,
            )
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(str(result.get("message") or "Failed to create issue."))
