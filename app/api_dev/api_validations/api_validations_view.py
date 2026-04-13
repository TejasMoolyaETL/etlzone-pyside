"""View API Validation — layout aligned with View API Detail."""

from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.api import api_get_all_user_type_in_api_project, api_update_api_validation_by_id
from core.app_preferences import format_datetime_display, is_datetime_field
from ui.blank_display import is_blank_display_value
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import FORM_COMBOBOX_STYLE, apply_form_combobox_field
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
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    FORM_SECONDARY_BUTTON_STYLESHEET,
)
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success
from ui.widgets.required_label import field_caption_label, labeled_field_block

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})


def _get_value(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    flat = {k: v for k, v in record.items() if k not in _HIDDEN_KEYS}
    for key in keys:
        if key in flat:
            return flat[key]
    return None


def _format_value(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


# Match api_validations_create multiline fields (API Validation, Error/Success Message).
_MULTILINE_HEIGHT = 80

_DETAIL_COL1 = (
    ("API Validation Id (Internal)", ("id", "internalId", "internal_id")),
    ("Project Id", ("projectId", "projectid", "project_id")),
    ("Project Name", ("projectName", "project_name")),
    ("API Id", ("apiId", "api_id")),
    ("API name", ("apiName", "api_name", "name")),
    ("Field Name*", ("fieldName", "field_name")),
    ("API Summary*", ("apiValidationSummary", "api_validation_summary")),
    ("Role", ("userType", "user_type")),
)
_DETAIL_COL2 = (
    ("API Validation", ("apiValidation", "api_validation")),
    ("Validation Type", ("validationType", "validation_type")),
    ("API Validation Status", ("apiValidationStatus", "api_validation_status")),
    ("Error Message", ("errorMessage", "error_message")),
    ("Success Message", ("successMessage", "success_message")),
)
_DETAIL_COL3 = (
    ("Created By", ("createdBy", "created_by", "CreatedBy")),
    ("Created At", ("createdAt", "created_at", "CreatedAt")),
    ("Modified By", ("modifiedBy", "modified_by", "ModifiedBy")),
    ("Modified At", ("modifiedAt", "modified_at", "ModifiedAt", "updatedAt", "updated_at")),
)
_DETAIL_FIELD_GROUPS = _DETAIL_COL1 + _DETAIL_COL2 + _DETAIL_COL3

_READONLY_KEYS = frozenset({
    "id", "internalId", "internal_id",
    "projectId", "projectid", "project_id",
    "projectName", "project_name",
    "apiId", "api_id",
    "apiName", "api_name", "name",
    "createdBy", "created_by", "CreatedBy",
    "createdAt", "created_at", "CreatedAt",
    "modifiedBy", "modified_by", "ModifiedBy",
    "modifiedAt", "modified_at", "ModifiedAt", "updatedAt", "updated_at",
})

_EDITABLE_KEYS = frozenset(
    {
        "fieldName",
        "field_name",
        "apiValidationSummary",
        "api_validation_summary",
        "userType",
        "user_type",
        "apiValidation",
        "api_validation",
        "validationType",
        "validation_type",
        "apiValidationStatus",
        "api_validation_status",
        "errorMessage",
        "error_message",
        "successMessage",
        "success_message",
    }
)


class ViewAPIValidationPage(QWidget):
    """Display and edit an API validation row — same pattern as ViewAPIDetailPage."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._record: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit | QPlainTextEdit | QComboBox] = {}
        self._editable_keys: list[str] = []
        self._edit_baseline: dict[str, str] = {}
        self._build_ui()

    def set_record(self, record: dict[str, Any], edit_mode: bool = False) -> None:
        self._record = dict(record)
        self._refresh_values()
        if edit_mode and self._record:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _populate_role_combo(self) -> None:
        """Same source as Create API Validation: user types for the record's project."""
        combo = self._field_edits.get("userType")
        if not isinstance(combo, QComboBox):
            return
        combo.clear()
        pid = self._record.get("projectId") or self._record.get("project_id")
        if pid is None or str(pid).strip() == "":
            combo.addItem("")
            return
        project_id_str = str(pid)
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_user_type_in_api_project(token=token)
        records = result.get("data", []) if result.get("success") else []
        roles: set[str] = set()
        for r in records:
            if not isinstance(r, dict):
                continue
            rpid = r.get("projectId") or r.get("project_id")
            if str(rpid) != project_id_str:
                continue
            ut = (r.get("userType") or r.get("user_type") or "").strip()
            if ut:
                roles.add(ut)
        items = sorted(roles)
        if items:
            combo.addItems(items)
        else:
            combo.addItem("")

    def _set_role_combo_text(self, text: str) -> None:
        combo = self._field_edits.get("userType")
        if not isinstance(combo, QComboBox):
            return
        self._populate_role_combo()
        t = (text or "").strip()
        if t and combo.findText(t) < 0:
            combo.insertItem(0, t)
        combo.setCurrentText(t)

    def _refresh_values(self) -> None:
        for _label_text, keys in _DETAIL_FIELD_GROUPS:
            canonical = keys[0]
            value = _get_value(self._record, keys)
            text = _format_value(value, keys[0], keys)
            widget = self._field_edits.get(canonical)
            if widget:
                if isinstance(widget, QComboBox):
                    if canonical == "userType":
                        self._set_role_combo_text(text)
                    else:
                        widget.setCurrentText(text if text else "ACTIVE")
                elif isinstance(widget, QPlainTextEdit):
                    widget.setPlainText(text)
                else:
                    widget.setText(text)

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
        title = QLabel("API Validation")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll_content = QWidget()
        scroll_content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        card.setMinimumWidth(720)
        card.setMaximumWidth(1320)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        _col_spacing = 10
        cols_row = QHBoxLayout()
        cols_row.setSpacing(24)
        cols_row.setContentsMargins(0, 0, 0, 0)

        col1_lay = QVBoxLayout()
        col1_lay.setSpacing(_col_spacing)
        col1_lay.setContentsMargins(0, 0, 0, 0)
        col2_lay = QVBoxLayout()
        col2_lay.setSpacing(_col_spacing)
        col2_lay.setContentsMargins(0, 0, 0, 0)
        col3_lay = QVBoxLayout()
        col3_lay.setSpacing(_col_spacing)
        col3_lay.setContentsMargins(0, 0, 0, 0)

        col1_w = QWidget()
        col1_w.setLayout(col1_lay)
        col1_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        col2_w = QWidget()
        col2_w.setLayout(col2_lay)
        col2_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        col3_w = QWidget()
        col3_w.setLayout(col3_lay)
        col3_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        cols_row.addWidget(col1_w, 1)
        cols_row.addWidget(col2_w, 1)
        cols_row.addWidget(col3_w, 1)

        def add_field(stack: QVBoxLayout, label_text: str, key_variants: tuple[str, ...]) -> None:
            chosen = key_variants[0]
            if chosen in _EDITABLE_KEYS and chosen not in self._editable_keys:
                self._editable_keys.append(chosen)

            label_widget = field_caption_label(label_text, LABEL_STYLE)
            is_read_only = chosen in _READONLY_KEYS or not (chosen in _EDITABLE_KEYS)

            if chosen in ("apiValidationStatus", "api_validation_status"):
                value_widget = QComboBox()
                value_widget.addItems(["ACTIVE", "INACTIVE"])
                apply_form_combobox_field(
                    value_widget, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX, min_width=240
                )
                value_widget.setEnabled(chosen in _EDITABLE_KEYS)
                self._field_edits["apiValidationStatus"] = value_widget
            elif chosen == "userType":
                value_widget = QComboBox()
                value_widget.setEditable(False)
                apply_form_combobox_field(
                    value_widget, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX, min_width=240
                )
                value_widget.setEnabled(chosen in _EDITABLE_KEYS)
                self._field_edits["userType"] = value_widget
            elif chosen in (
                "apiValidation",
                "api_validation",
                "errorMessage",
                "error_message",
                "successMessage",
                "success_message",
            ):
                value_widget = QPlainTextEdit()
                value_widget.setFixedHeight(_MULTILINE_HEIGHT)
                value_widget.setReadOnly(is_read_only)
                value_widget.setStyleSheet(READONLY_INPUT_STYLE if is_read_only else INPUT_STYLE)
                self._field_edits[chosen] = value_widget
            else:
                value_widget = QLineEdit()
                value_widget.setReadOnly(is_read_only)
                value_widget.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
                value_widget.setMinimumWidth(240)
                value_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                value_widget.setStyleSheet(
                    READONLY_INPUT_STYLE if is_read_only else INPUT_STYLE
                )
                self._field_edits[chosen] = value_widget

            stack.addWidget(labeled_field_block(label_widget, value_widget))

        for lt, keys in _DETAIL_COL1:
            add_field(col1_lay, lt, keys)
        for lt, keys in _DETAIL_COL2:
            add_field(col2_lay, lt, keys)
        for lt, keys in _DETAIL_COL3:
            add_field(col3_lay, lt, keys)

        col1_lay.addStretch()
        col2_lay.addStretch()
        col3_lay.addStretch()

        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self._handle_back)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedWidth(100)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._edit_btn.clicked.connect(self._handle_edit)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._cancel_btn.clicked.connect(self._handle_cancel)

        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedWidth(100)
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._save_btn.clicked.connect(self._handle_save)

        display_btns = QWidget()
        display_btns.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        display_btns.setStyleSheet("background: transparent;")
        dbl = QHBoxLayout(display_btns)
        dbl.setContentsMargins(0, 0, 0, 0)
        dbl.setSpacing(12)
        dbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        dbl.addWidget(self._edit_btn)
        dbl.addWidget(self._back_btn)

        edit_btns = QWidget()
        edit_btns.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        edit_btns.setStyleSheet("background: transparent;")
        ebl = QHBoxLayout(edit_btns)
        ebl.setContentsMargins(0, 0, 0, 0)
        ebl.setSpacing(12)
        ebl.addWidget(self._save_btn)
        ebl.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._btn_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self._btn_stack.addWidget(display_btns)
        self._btn_stack.addWidget(edit_btns)

        self._error_label = QLabel()
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setWordWrap(True)
        self._error_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._error_label.setVisible(False)

        card_layout.addLayout(cols_row)
        card_layout.addWidget(self._error_label)
        card_layout.addWidget(self._btn_stack, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        self._switch_to_view_mode()

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def _handle_edit(self) -> None:
        self._clear_error()
        role_combo = self._field_edits.get("userType")
        if isinstance(role_combo, QComboBox):
            cur = role_combo.currentText()
            self._set_role_combo_text(cur)
        self._edit_baseline = {}
        for key in self._editable_keys:
            self._edit_baseline[key] = self._get_edit_value(key)
        for key in self._editable_keys:
            widget = self._field_edits.get(key)
            if widget:
                if isinstance(widget, QComboBox):
                    widget.setEnabled(True)
                    widget.setStyleSheet(FORM_COMBOBOX_STYLE)
                elif isinstance(widget, QPlainTextEdit):
                    widget.setReadOnly(False)
                    widget.setStyleSheet(INPUT_STYLE)
                else:
                    widget.setReadOnly(False)
                    widget.setStyleSheet(INPUT_STYLE)
        self._btn_stack.setCurrentIndex(1)

    def _handle_save(self) -> None:
        self._clear_error()
        if not self._has_unsaved_changes():
            navigate_after_no_changes(
                show_non_error_message=self._show_success,
                clear_message=self._clear_error,
                on_back=self.on_back,
            )
            return
        validation_id = (
            self._record.get("id")
            or self._record.get("internalId")
            or self._record.get("internal_id")
        )
        if validation_id is None:
            self._show_error("API Validation Id (Internal) is missing.")
            return

        field_name = self._get_edit_value("fieldName") or self._get_edit_value("field_name")
        if not field_name:
            self._show_error("Field Name is required.")
            return

        api_summary = self._get_edit_value("apiValidationSummary") or self._get_edit_value(
            "api_validation_summary"
        )
        if not api_summary:
            self._show_error("API Summary is required.")
            return

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_update_api_validation_by_id(
            validation_id,
            token=token,
            field_name=field_name,
            api_validation_summary=api_summary,
            role=self._get_edit_value("userType") or self._get_edit_value("user_type"),
            api_validation=self._get_edit_value("apiValidation") or self._get_edit_value("api_validation"),
            validation_type=self._get_edit_value("validationType") or self._get_edit_value("validation_type"),
            api_validation_status=self._get_edit_value("apiValidationStatus")
            or self._get_edit_value("api_validation_status"),
            error_message=self._get_edit_value("errorMessage") or self._get_edit_value("error_message"),
            success_message=self._get_edit_value("successMessage") or self._get_edit_value("success_message"),
        )

        if not result.get("success"):
            self._show_error(result.get("message", "Failed to update API validation."))
            return
        self._show_success(result.get("message", "API validation updated successfully."))
        schedule_after_success(
            delay_ms=800,
            clear_error=self._clear_error,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )

    def _get_edit_value(self, key: str) -> str:
        widget = self._field_edits.get(key)
        if not widget:
            return ""
        if isinstance(widget, QComboBox):
            return widget.currentText().strip()
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText().strip()
        return widget.text().strip()

    def _has_unsaved_changes(self) -> bool:
        if not self._edit_baseline:
            return False
        for key in self._editable_keys:
            baseline = self._edit_baseline.get(key, "")
            current = self._get_edit_value(key)
            if str(baseline or "").strip() != str(current or "").strip():
                return True
        return False

    def _handle_cancel(self) -> None:
        if not self._has_unsaved_changes():
            self._clear_error()
            self._refresh_values()
            self._switch_to_view_mode()
            return
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard and leave?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Discard:
            self._clear_error()
            self._refresh_values()
            self._switch_to_view_mode()

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1

    def _switch_to_view_mode(self) -> None:
        for key in self._editable_keys:
            widget = self._field_edits.get(key)
            if widget:
                if isinstance(widget, QComboBox):
                    widget.setEnabled(False)
                    widget.setStyleSheet(FORM_COMBOBOX_STYLE)
                elif isinstance(widget, QPlainTextEdit):
                    widget.setReadOnly(True)
                    widget.setStyleSheet(READONLY_INPUT_STYLE)
                else:
                    widget.setReadOnly(True)
                    widget.setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)
