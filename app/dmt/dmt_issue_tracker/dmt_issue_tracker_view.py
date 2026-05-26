"""View / edit DMT Issue Tracker record page."""

from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
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

from core.api import (
    api_get_all_modules,
    api_get_all_objects,
    api_update_issue_tracker,
    master_key_row_seq_value,
)
from core.app_preferences import format_datetime_display, is_datetime_field
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.blank_display import is_blank_display_value
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    placeholder_example,
)
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success
from ui.searchable_form_combo import (
    combo_resolved_master_key_seq,
    master_key_invalid_typed_text,
    master_key_seq_for_payload,
    require_master_key_seq_for_payload,
    populate_master_key_by_field_name,
    reset_searchable_combo,
    set_searchable_combo_by_user_data,
    wire_searchable_master_key_combo,
)
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label, labeled_field_block

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})
_FIELD_STATUS = "dmt_issue_tracker_status"
_FIELD_PRIORITY = "dmt_issue_priority"

_ISSUE_FIELDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Issue Id", ("issueTrackerId", "id")),
    ("Module", ("moduleId", "module_id")),
    ("Object", ("objectId", "object_id")),
    ("Issue Title*", ("issueTitle", "title")),
    ("Description", ("issueDescription", "description")),
    ("Status*", ("status",)),
    ("Priority", ("priority",)),
    ("Created By", ("createdBy", "created_by")),
    ("Created At", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified At", ("modifiedAt", "modified_at")),
)
_READONLY_KEYS = frozenset(
    {
        "issueTrackerId",
        "id",
        "createdBy",
        "created_by",
        "createdAt",
        "created_at",
        "modifiedBy",
        "modified_by",
        "modifiedAt",
        "modified_at",
    }
)


def _get_value(rec: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in rec:
            return rec[key]
    return None


def _format_value(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, dict):
        return json.dumps(value, default=str)
    return str(value)


def _seq_from_record(rec: dict[str, Any], *keys: str) -> Any | None:
    for key in keys:
        v = rec.get(key)
        if v is None:
            continue
        if isinstance(v, dict):
            seq = master_key_row_seq_value(v)
            if seq is not None:
                return seq
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v == int(v):
            return int(v)
        s = str(v).strip()
        if s.isdigit():
            return int(s)
    return None


def _issue_id(rec: dict[str, Any]) -> Any:
    return rec.get("issueTrackerId") or rec.get("id")


class ViewDmtIssueTrackerPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._record: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit] = {}
        self._description_edit: QPlainTextEdit | None = None
        self._module_combo: QComboBox | None = None
        self._object_combo: QComboBox | None = None
        self._status_combo: QComboBox | None = None
        self._priority_combo: QComboBox | None = None
        self._editable_keys: list[str] = []
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
        hl.addWidget(QLabel("Issue Details"))
        hl.addStretch()
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setMaximumWidth(720)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
        field_h = FORM_SINGLELINE_FIELD_HEIGHT_PX

        row = 0
        for label_text, keys in _ISSUE_FIELDS:
            canonical = keys[0]
            label_widget = field_caption_label(label_text, LABEL_STYLE)
            if canonical == "status":
                combo = QComboBox()
                apply_form_combobox_field(combo, height_px=field_h, min_width=280)
                wire_searchable_master_key_combo(combo, search_field_label="Status")
                self._status_combo = combo
                self._editable_keys.append(canonical)
                grid.addWidget(labeled_field_block(label_widget, combo), row, 0, 1, 2)
                row += 1
                continue
            if canonical == "priority":
                combo = QComboBox()
                apply_form_combobox_field(combo, height_px=field_h, min_width=280)
                wire_searchable_master_key_combo(combo, search_field_label="Priority")
                self._priority_combo = combo
                self._editable_keys.append(canonical)
                grid.addWidget(labeled_field_block(label_widget, combo), row, 0, 1, 2)
                row += 1
                continue
            if canonical in ("moduleId", "module_id"):
                combo = QComboBox()
                apply_form_combobox_field(combo, height_px=field_h, min_width=280)
                self._module_combo = combo
                self._module_combo.currentIndexChanged.connect(self._on_module_changed)
                self._editable_keys.append("moduleId")
                grid.addWidget(labeled_field_block(label_widget, combo), row, 0, 1, 2)
                row += 1
                continue
            if canonical in ("objectId", "object_id"):
                combo = QComboBox()
                apply_form_combobox_field(combo, height_px=field_h, min_width=280)
                self._object_combo = combo
                self._editable_keys.append("objectId")
                grid.addWidget(labeled_field_block(label_widget, combo), row, 0, 1, 2)
                row += 1
                continue
            if canonical in ("issueDescription", "description"):
                edit = QPlainTextEdit()
                edit.setFixedHeight(100)
                edit.setStyleSheet(INPUT_STYLE)
                self._description_edit = edit
                if canonical not in _READONLY_KEYS:
                    self._editable_keys.append(canonical)
                grid.addWidget(labeled_field_block(label_widget, edit), row, 0, 1, 2)
                row += 1
                continue
            if canonical not in _READONLY_KEYS:
                self._editable_keys.append(canonical)
            edit = QLineEdit()
            edit.setFixedHeight(field_h)
            edit.setReadOnly(canonical in _READONLY_KEYS)
            edit.setStyleSheet(READONLY_INPUT_STYLE if canonical in _READONLY_KEYS else INPUT_STYLE)
            if canonical in ("issueTitle", "title"):
                edit.setPlaceholderText(placeholder_example("Data load failure"))
            self._field_edits[canonical] = edit
            grid.addWidget(labeled_field_block(label_widget, edit), row, 0, 1, 2)
            row += 1

        card_layout.addLayout(grid)

        self._error_label = QLabel()
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)
        card_layout.addWidget(self._error_label)

        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self._handle_back)
        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedWidth(100)
        self._edit_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._edit_btn.clicked.connect(self._handle_edit)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._cancel_btn.clicked.connect(self._handle_cancel)
        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedWidth(100)
        self._save_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._save_btn.clicked.connect(self._handle_save)

        display_btns = QWidget()
        db = QHBoxLayout(display_btns)
        db.setContentsMargins(0, 0, 0, 0)
        db.setSpacing(12)
        db.addWidget(self._edit_btn)
        db.addWidget(self._back_btn)
        edit_btns = QWidget()
        eb = QHBoxLayout(edit_btns)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.setSpacing(12)
        eb.addWidget(self._save_btn)
        eb.addWidget(self._cancel_btn)
        self._btn_stack = QStackedWidget()
        self._btn_stack.addWidget(display_btns)
        self._btn_stack.addWidget(edit_btns)
        card_layout.addWidget(self._btn_stack)

        content_layout.addWidget(card)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)
        self._switch_to_view_mode()

    def set_record(self, record: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._record = dict(record) if record else {}
        self._load_reference_combos()
        self._refresh_values()
        self._apply_combos_from_record()
        if edit_mode and self._record:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._record:
            self._load_reference_combos()
            if not self.is_edit_mode():
                self._apply_combos_from_record()

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _load_reference_combos(self) -> None:
        if self._status_combo is not None:
            populate_master_key_by_field_name(
                self._status_combo, _FIELD_STATUS, token=self._token(), include_placeholder=False
            )
        if self._priority_combo is not None:
            populate_master_key_by_field_name(
                self._priority_combo, _FIELD_PRIORITY, token=self._token(), include_placeholder=False
            )
        if self._module_combo is not None:
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
            self._module_combo.blockSignals(False)
        self._reload_objects_for_module()

    def _on_module_changed(self) -> None:
        self._reload_objects_for_module()

    def _reload_objects_for_module(self) -> None:
        if self._object_combo is None:
            return
        module_id = self._module_combo.currentData() if self._module_combo else None
        saved_object = _seq_from_record(self._record, "objectId", "object_id")
        self._object_combo.blockSignals(True)
        self._object_combo.clear()
        self._object_combo.addItem("— Select object —", None)
        if module_id is not None:
            result = api_get_all_objects(token=self._token())
            if result.get("success"):
                for row in result.get("data") or []:
                    if not isinstance(row, dict):
                        continue
                    row_module = row.get("moduleId") or row.get("module_id")
                    if row_module is not None and str(row_module) != str(module_id):
                        continue
                    oid = row.get("objectId") or row.get("id")
                    label = str(row.get("objectName") or row.get("name") or oid or "?")
                    if oid is not None:
                        self._object_combo.addItem(label, oid)
        if saved_object is not None:
            set_searchable_combo_by_user_data(self._object_combo, saved_object)
        self._object_combo.blockSignals(False)

    def _apply_combos_from_record(self) -> None:
        mid = _seq_from_record(self._record, "moduleId", "module_id")
        if self._module_combo is not None and mid is not None:
            set_searchable_combo_by_user_data(self._module_combo, mid)
        self._reload_objects_for_module()
        status = _seq_from_record(self._record, "status", "dmt_issue_tracker_status")
        if self._status_combo is not None:
            if status is None:
                reset_searchable_combo(self._status_combo)
            else:
                set_searchable_combo_by_user_data(self._status_combo, status)
        priority = _seq_from_record(self._record, "priority", "dmt_issue_priority")
        if self._priority_combo is not None:
            if priority is None:
                reset_searchable_combo(self._priority_combo)
            else:
                set_searchable_combo_by_user_data(self._priority_combo, priority)

    def _refresh_values(self) -> None:
        for _label, keys in _ISSUE_FIELDS:
            canonical = keys[0]
            if canonical in ("status", "priority", "moduleId", "module_id", "objectId", "object_id"):
                continue
            if canonical in ("issueDescription", "description"):
                if self._description_edit is not None:
                    self._description_edit.setPlainText(
                        _format_value(_get_value(self._record, keys), keys[0], keys)
                    )
                continue
            edit = self._field_edits.get(canonical)
            if edit is None:
                continue
            if canonical in ("issueTrackerId", "id"):
                edit.setText(str(_issue_id(self._record) or ""))
            else:
                edit.setText(_format_value(_get_value(self._record, keys), keys[0], keys))

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
        for key, edit in self._field_edits.items():
            if key in _READONLY_KEYS:
                continue
            edit.setReadOnly(False)
            edit.setStyleSheet(INPUT_STYLE)
        if self._description_edit is not None:
            self._description_edit.setReadOnly(False)
            self._description_edit.setStyleSheet(INPUT_STYLE)
        for combo in (self._module_combo, self._object_combo, self._status_combo, self._priority_combo):
            if combo is not None:
                combo.setEnabled(True)
        self._btn_stack.setCurrentIndex(1)

    def _handle_cancel(self) -> None:
        if not self._has_unsaved_changes():
            self._clear_error()
            self._refresh_values()
            self._apply_combos_from_record()
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
            self._apply_combos_from_record()
            self._switch_to_view_mode()

    def _switch_to_view_mode(self) -> None:
        for key, edit in self._field_edits.items():
            edit.setReadOnly(True)
            edit.setStyleSheet(READONLY_INPUT_STYLE)
        if self._description_edit is not None:
            self._description_edit.setReadOnly(True)
        for combo in (self._module_combo, self._object_combo, self._status_combo, self._priority_combo):
            if combo is not None:
                combo.setEnabled(False)
        self._btn_stack.setCurrentIndex(0)

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1

    def _has_unsaved_changes(self) -> bool:
        title_edit = self._field_edits.get("issueTitle") or self._field_edits.get("title")
        cur_title = title_edit.text().strip() if title_edit else ""
        orig_title = _format_value(_get_value(self._record, ("issueTitle", "title")), "issueTitle").strip()
        if cur_title != orig_title:
            return True
        if self._description_edit is not None:
            cur_desc = self._description_edit.toPlainText().strip()
            orig_desc = _format_value(
                _get_value(self._record, ("issueDescription", "description")), "issueDescription"
            ).strip()
            if cur_desc != orig_desc:
                return True
        if self._module_combo is not None:
            cur = self._module_combo.currentData()
            orig = _seq_from_record(self._record, "moduleId", "module_id")
            if str(cur) != str(orig) if (cur is not None or orig is not None) else False:
                return True
        if self._object_combo is not None:
            cur = self._object_combo.currentData()
            orig = _seq_from_record(self._record, "objectId", "object_id")
            if str(cur) != str(orig) if (cur is not None or orig is not None) else False:
                return True
        if self._status_combo is not None:
            cur = combo_resolved_master_key_seq(self._status_combo)
            orig = _seq_from_record(self._record, "status", "dmt_issue_tracker_status")
            if str(cur) != str(orig) if (cur is not None or orig is not None) else False:
                return True
        if self._priority_combo is not None:
            cur = combo_resolved_master_key_seq(self._priority_combo)
            orig = _seq_from_record(self._record, "priority", "dmt_issue_priority")
            if str(cur) != str(orig) if (cur is not None or orig is not None) else False:
                return True
        return False

    def _handle_save(self) -> None:
        self._clear_error()
        if not self._has_unsaved_changes():
            navigate_after_no_changes(
                show_non_error_message=self._show_success,
                clear_message=self._clear_error,
                on_back=self.on_back,
            )
            return
        iid = _issue_id(self._record)
        if iid is None:
            self._show_error("Issue ID is missing.")
            return
        module_id = self._module_combo.currentData() if self._module_combo else None
        object_id = self._object_combo.currentData() if self._object_combo else None
        title_edit = self._field_edits.get("issueTitle") or self._field_edits.get("title")
        title = title_edit.text().strip() if title_edit else ""
        if module_id is None:
            self._show_error("Please select a module.")
            return
        if object_id is None:
            self._show_error("Please select an object.")
            return
        if not title:
            self._show_error("Issue title is required.")
            return
        status_id, status_err = require_master_key_seq_for_payload(
            self._status_combo, field_caption="Status", strict_phrase="a status"
        )
        if status_err:
            self._show_error(status_err)
            return
        if master_key_invalid_typed_text(self._priority_combo):
            self._show_error(strict_list_selection_message("a priority"))
            return
        payload: dict[str, Any] = {
            "moduleId": module_id,
            "objectId": object_id,
            "issueTitle": title,
            "status": status_id,
            "priority": master_key_seq_for_payload(self._priority_combo),
        }
        if self._description_edit is not None:
            payload["issueDescription"] = self._description_edit.toPlainText().strip()
        result = api_update_issue_tracker(iid, payload, token=self._token())
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Failed to update issue."))
            return
        data = result.get("data")
        if isinstance(data, dict):
            self._record.update(data)
        else:
            self._record.update(payload)
        self._refresh_values()
        self._apply_combos_from_record()
        self._switch_to_view_mode()
        self._show_success(str(result.get("message") or "Issue updated successfully."))
        schedule_after_success(
            delay_ms=600,
            clear_error=self._clear_error,
            reset=lambda: None,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )
