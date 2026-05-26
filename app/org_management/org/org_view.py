"""View Organization page - display and edit organization details."""

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
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.api import api_update_org, master_key_row_seq_value
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


def _get_value(org: dict[str, Any], keys: tuple[str, ...]) -> Any:
    flat = {k: v for k, v in org.items() if k not in _HIDDEN_KEYS}
    for key in keys:
        if key in flat:
            return flat[key]
    # API returns nested orgStatus { keyValue, ... } instead of flat status
    if "status" in keys:
        nested = flat.get("orgStatus") or flat.get("org_status")
        if isinstance(nested, dict):
            if "keyValue" in nested:
                return nested.get("keyValue")
            if "key_value" in nested:
                return nested.get("key_value")
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


def _get_org_id(org: dict[str, Any]) -> int | str | None:
    for k in ("orgID", "orgId", "org_id", "id"):
        v = org.get(k)
        if v is not None:
            return v
    return None


_ORG_STATUS_FIELD_NAME = "org_status"


def _coerce_master_seq_to_int(seq_val: Any) -> int:
    """Send master-key seq as integer in JSON payload (same as Create Org)."""
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


def _org_status_nested(org: dict[str, Any]) -> dict[str, Any] | None:
    flat = {k: v for k, v in org.items() if k not in _HIDDEN_KEYS}
    nested = flat.get("orgStatus") or flat.get("org_status")
    return nested if isinstance(nested, dict) else None


def _org_status_seq(org: dict[str, Any]) -> Any | None:
    nested = _org_status_nested(org)
    if nested is not None:
        return master_key_row_seq_value(nested)
    flat = {k: v for k, v in org.items() if k not in _HIDDEN_KEYS}
    for k in ("status", "statusSeq", "status_seq"):
        v = flat.get(k)
        if v is not None and str(v).strip() != "":
            return v
    return None


def _combo_status_key_value(combo: QComboBox) -> str:
    """Key value portion of master-key label (e.g. ``1 | ACTIVE`` → ``ACTIVE``)."""
    t = (combo.currentText() or "").strip()
    if not t:
        return ""
    if " | " in t:
        return t.split(" | ", 1)[-1].strip().upper()
    return t.upper()

# Column 1: main org fields (canonical key first)
_ORG_COL1 = (
    ("Org Id", ("orgId", "orgID", "org_id", "id")),
    ("Org Code*", ("orgCode", "org_code")),
    ("Org Name*", ("orgName", "org_name")),
    ("Industry*", ("industry",)),
    ("Status*", ("status",)),
)
# Column 2: audit fields (read-only)
_ORG_COL2 = (
    ("Created By", ("createdBy", "created_by")),
    ("Created On", ("createdOn", "created_on", "createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified On", ("modifiedOn", "modified_on", "modifiedAt", "modified_at", "updatedAt", "updated_at")),
)
_ORG_FIELD_GROUPS = _ORG_COL1 + _ORG_COL2

_READONLY_KEYS = frozenset({
    "orgID", "orgId", "org_id", "id",
    "createdBy", "created_by", "createdOn", "created_on", "createdAt", "created_at",
    "modifiedBy", "modified_by", "modifiedOn", "modified_on", "modifiedAt", "modified_at", "updatedAt", "updated_at",
})


class ViewOrgPage(QWidget):
    """Page that displays organization details with view and edit modes."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._org: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit | QComboBox] = {}
        self._editable_keys: list[str] = []
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
        title = QLabel("Organization Details")
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
        card.setMinimumWidth(520)
        card.setMaximumWidth(800)
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
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        def add_field(col: int, idx: int, label_text: str, keys: tuple[str, ...]) -> None:
            canonical = keys[0]
            if canonical not in _READONLY_KEYS:
                self._editable_keys.append(canonical)

            label_widget = field_caption_label(label_text, LABEL_STYLE)

            if canonical == "status":
                value_edit = QComboBox()
                apply_form_combobox_field(
                    value_edit, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX, min_width=240
                )
                wire_searchable_master_key_combo(value_edit, search_field_label="Status")
                if canonical in _READONLY_KEYS:
                    value_edit.setEnabled(False)
                else:
                    value_edit.setEnabled(True)
            else:
                value_edit = QLineEdit()
                value_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
                value_edit.setMinimumWidth(240)
                value_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                value_edit.setReadOnly(canonical in _READONLY_KEYS)
                value_edit.setStyleSheet(READONLY_INPUT_STYLE if canonical in _READONLY_KEYS else INPUT_STYLE)
                value_edit.setText("")
                if canonical == "orgName":
                    value_edit.setPlaceholderText(placeholder_example("ETLZONE2"))
                elif canonical == "orgCode":
                    value_edit.setPlaceholderText(placeholder_example("ETL123"))
                elif canonical == "industry":
                    value_edit.setPlaceholderText(placeholder_example("IT"))

            self._field_edits[canonical] = value_edit
            grid.addWidget(labeled_field_block(label_widget, value_edit), idx, col)

        for idx, (label_text, keys) in enumerate(_ORG_COL1):
            add_field(0, idx, label_text, keys)
        for idx, (label_text, keys) in enumerate(_ORG_COL2):
            add_field(1, idx, label_text, keys)

        # Buttons: view mode = Edit + Back; edit mode = Save + Cancel
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
        display_btns.setStyleSheet("background: transparent;")
        display_btns.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        display_btns_layout = QHBoxLayout(display_btns)
        display_btns_layout.setContentsMargins(0, 0, 0, 0)
        display_btns_layout.setSpacing(12)
        display_btns_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        display_btns_layout.addWidget(self._edit_btn)
        display_btns_layout.addWidget(self._back_btn)

        edit_btns = QWidget()
        edit_btns.setStyleSheet("background: transparent;")
        edit_btns.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        edit_btns_layout = QHBoxLayout(edit_btns)
        edit_btns_layout.setContentsMargins(0, 0, 0, 0)
        edit_btns_layout.setSpacing(12)
        edit_btns_layout.addWidget(self._save_btn)
        edit_btns_layout.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
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

        btn_row = max(len(_ORG_COL1), len(_ORG_COL2))
        grid.addWidget(self._error_label, btn_row, 0, 1, 2)
        grid.addWidget(self._btn_stack, btn_row + 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.setRowMinimumHeight(btn_row + 1, 52)

        card_layout.addLayout(grid)
        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        self._switch_to_view_mode()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self.is_edit_mode():
            return
        combo = self._field_edits.get("status")
        if isinstance(combo, QComboBox):
            populate_master_key_by_field_name(
                combo,
                _ORG_STATUS_FIELD_NAME,
                token=self._token(),
                include_placeholder=False,
            )
            self._sync_status_combo_from_org()

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _sync_status_combo_from_org(self) -> None:
        combo = self._field_edits.get("status")
        if not isinstance(combo, QComboBox) or combo.count() == 0:
            return
        seq = _org_status_seq(self._org)
        if seq is not None:
            set_searchable_combo_by_user_data(combo, seq)
            if combo_resolved_master_key_seq(combo) is not None:
                return
        kv = _get_value(self._org, ("status",))
        if kv is not None and str(kv).strip():
            kv_up = str(kv).strip().upper()
            for i in range(combo.count()):
                data = combo.itemData(i)
                if data is None:
                    continue
                label_up = combo.itemText(i).strip().upper()
                if kv_up == label_up or kv_up in label_up or label_up.endswith(kv_up) or f"| {kv_up}" in label_up:
                    set_searchable_combo_by_user_data(combo, data)
                    return
        reset_searchable_combo(combo)

    def set_org(self, org: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        """Load and display the given organization record. If edit_mode=True, open in edit mode."""
        self._org = dict(org) if org else {}
        combo = self._field_edits.get("status")
        if isinstance(combo, QComboBox):
            populate_master_key_by_field_name(
                combo,
                _ORG_STATUS_FIELD_NAME,
                token=self._token(),
                include_placeholder=False,
            )
        self._refresh_values()
        if edit_mode and self._org:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _refresh_values(self) -> None:
        """Sync field values from _org."""
        for label_text, keys in _ORG_FIELD_GROUPS:
            canonical = keys[0]
            if canonical == "status":
                continue
            value = _get_value(self._org, keys)
            text = _format_value(value, keys[0], keys)
            edit = self._field_edits.get(canonical)
            if edit and isinstance(edit, QLineEdit):
                edit.setText(text)
        self._sync_status_combo_from_org()

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

    def _get_edit_value(self, *keys: str) -> str:
        for key in keys:
            edit = self._field_edits.get(key)
            if edit:
                if isinstance(edit, QComboBox):
                    return edit.currentText().strip()
                return edit.text().strip()
        return ""

    def _handle_edit(self) -> None:
        self._clear_error()
        for key in self._editable_keys:
            edit = self._field_edits.get(key)
            if edit:
                if isinstance(edit, QComboBox):
                    edit.setEnabled(True)
                    edit.setStyleSheet(FORM_COMBOBOX_STYLE)
                else:
                    edit.setReadOnly(False)
                    edit.setStyleSheet(INPUT_STYLE)
        self._btn_stack.setCurrentIndex(1)

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

    def _has_unsaved_changes(self) -> bool:
        for label_text, keys in _ORG_FIELD_GROUPS:
            canonical = keys[0]
            if canonical not in self._editable_keys:
                continue
            if canonical == "status":
                combo = self._field_edits.get("status")
                if not isinstance(combo, QComboBox):
                    continue
                orig_seq = _org_status_seq(self._org)
                cur_seq = combo_resolved_master_key_seq(combo)
                if str(orig_seq or "").strip() != str(cur_seq or "").strip():
                    return True
                continue
            original = _get_value(self._org, keys)
            orig_str = _format_value(original, keys[0], keys)
            current = self._get_edit_value(canonical)
            if orig_str.strip() != (current or "").strip():
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
        org_name = self._get_edit_value("orgName", "org_name")
        org_code = self._get_edit_value("orgCode", "org_code")
        industry = self._get_edit_value("industry")

        if not org_name:
            self._show_error("Organization name is required.")
            name_edit = self._field_edits.get("orgName")
            if isinstance(name_edit, QLineEdit):
                name_edit.setFocus()
            return
        if not org_code:
            self._show_error("Organization code is required.")
            code_edit = self._field_edits.get("orgCode")
            if isinstance(code_edit, QLineEdit):
                code_edit.setFocus()
            return
        if not industry:
            self._show_error("Industry is required.")
            ind_edit = self._field_edits.get("industry")
            if isinstance(ind_edit, QLineEdit):
                ind_edit.setFocus()
            return

        status_combo = self._field_edits.get("status")
        if isinstance(status_combo, QComboBox):
            status, status_err = require_master_key_seq_for_payload(
                status_combo, field_caption="Status", strict_phrase="a status"
            )
            if status_err:
                self._show_error(status_err)
                status_combo.setFocus()
                return
        else:
            status = self._get_edit_value("status") or "ACTIVE"

        org_id = _get_org_id(self._org)
        if org_id is None:
            self._show_error("Org Id is missing.")
            return

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_update_org(
            org_id,
            org_name=org_name,
            org_code=org_code,
            industry=industry,
            status=status,
            token=token,
        )

        if not result.get("success"):
            self._show_error(result.get("message", "Failed to update organization."))
            return

        self._org["orgName"] = org_name
        self._org["orgCode"] = org_code
        self._org["industry"] = industry
        kv = (
            _combo_status_key_value(status_combo)
            if isinstance(status_combo, QComboBox)
            else str(status).strip().upper()
        )
        self._org["status"] = kv or str(status)
        nested = _org_status_nested(self._org)
        if isinstance(nested, dict) and isinstance(status_combo, QComboBox):
            nested = dict(nested)
            nested["seq"] = status
            if kv:
                nested["keyValue"] = kv
            self._org["orgStatus"] = nested
        elif isinstance(status_combo, QComboBox) and kv:
            self._org["orgStatus"] = {"keyValue": kv, "seq": status}
        self._show_success(result.get("message", "Organization updated successfully."))

        schedule_after_success(
            delay_ms=800,
            clear_error=self._clear_error,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )

    def _switch_to_view_mode(self) -> None:
        for key in self._editable_keys:
            edit = self._field_edits.get(key)
            if edit:
                if isinstance(edit, QComboBox):
                    edit.setEnabled(False)
                    edit.setStyleSheet(FORM_COMBOBOX_STYLE)
                else:
                    edit.setReadOnly(True)
                    edit.setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1
