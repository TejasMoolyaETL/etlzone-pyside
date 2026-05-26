"""View / edit Department — PUT departments/update-dept-by-id/{dept_id}."""

from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
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

from app.org_management.bu.bu_utils import (
    get_bu_id,
    get_bu_name,
    get_organization_name_from_bu,
)
from core.api import api_get_all_bu, api_get_all_depts, api_update_dept, master_key_row_seq_value
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
    placeholder_enter,
    placeholder_search_select,
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

_DEPT_STATUS_FIELD_NAME = "dept_status"


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


def _dept_status_nested(dept: dict[str, Any]) -> dict[str, Any] | None:
    flat = {k: v for k, v in dept.items() if k not in _HIDDEN_KEYS}
    nested = flat.get("status") or flat.get("deptStatus") or flat.get("dept_status")
    return nested if isinstance(nested, dict) else None


def _dept_status_seq(dept: dict[str, Any]) -> Any | None:
    nested = _dept_status_nested(dept)
    if nested is not None:
        return master_key_row_seq_value(nested)
    flat = {k: v for k, v in dept.items() if k not in _HIDDEN_KEYS}
    for k in ("status", "statusSeq", "status_seq"):
        v = flat.get(k)
        if v is not None and not isinstance(v, dict) and str(v).strip() != "":
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


def _dept_row_id(row: dict[str, Any]) -> Any:
    return row.get("deptId") or row.get("dept_id") or row.get("departmentId") or row.get("id")


def _dept_row_name(row: dict[str, Any]) -> str:
    return str(
        row.get("deptName")
        or row.get("dept_name")
        or row.get("departmentName")
        or row.get("name")
        or ""
    ).strip()


def _bu_name_from_dept_row(row: dict[str, Any]) -> str:
    bu = row.get("businessUnit") or row.get("bu")
    if isinstance(bu, dict):
        return str(bu.get("buName") or bu.get("bu_name") or "").strip() or ""
    return ""


def _parent_department_object_from_dept(dept: dict[str, Any]) -> dict[str, Any] | None:
    for k in ("parentDepartment", "parent_dept", "parentDept"):
        p = dept.get(k)
        if isinstance(p, dict):
            return p
    return None


def _get_bu_id_from_dept(dept: dict[str, Any]) -> Any:
    flat = {k: v for k, v in dept.items() if k not in _HIDDEN_KEYS}
    for key in ("buId", "bu_id", "businessUnitId", "business_unit_id"):
        if key in flat and not isinstance(flat[key], dict) and flat[key] is not None:
            return flat[key]
    bu = dept.get("businessUnit") or dept.get("bu")
    if isinstance(bu, dict):
        return get_bu_id(bu)
    return None


def _get_parent_dept_id_from_dept(dept: dict[str, Any]) -> Any:
    flat = {k: v for k, v in dept.items() if k not in _HIDDEN_KEYS}
    for key in ("parentDeptId", "parent_dept_id", "parentDepartmentId", "parent_department_id"):
        if key in flat and not isinstance(flat[key], dict) and flat[key] is not None:
            return flat[key]
    parent = _parent_department_object_from_dept(dept)
    if isinstance(parent, dict):
        return _dept_row_id(parent)
    return None


def _bu_search_display_from_dept(dept: dict[str, Any]) -> str | None:
    bu = dept.get("businessUnit") or dept.get("bu")
    if not isinstance(bu, dict):
        bid = _get_bu_id_from_dept(dept)
        return str(bid) if bid is not None else None
    bid = get_bu_id(bu)
    if bid is None:
        return None
    bname = get_bu_name(bu) or ""
    org_name = get_organization_name_from_bu(bu) or ""
    return f"{bid} | {bname} | Org: {org_name}"


def _parent_dept_search_display_from_dept(dept: dict[str, Any]) -> str | None:
    parent = _parent_department_object_from_dept(dept)
    if not isinstance(parent, dict):
        return None
    did = _dept_row_id(parent)
    if did is None:
        return None
    dname = _dept_row_name(parent) or ""
    bu_nm = _bu_name_from_dept_row(parent)
    return f"{did} | {dname} | BU: {bu_nm}"


def _get_value(dept: dict[str, Any], keys: tuple[str, ...]) -> Any:
    canonical = keys[0] if keys else ""

    if canonical == "buSearch":
        return _bu_search_display_from_dept(dept)

    if canonical == "parentDeptSearch":
        return _parent_dept_search_display_from_dept(dept)

    if keys and "status" in keys:
        flat = {k: v for k, v in dept.items() if k not in _HIDDEN_KEYS}
        nested = flat.get("status") or flat.get("deptStatus") or flat.get("dept_status")
        if isinstance(nested, dict):
            if nested.get("keyValue") is not None:
                return nested.get("keyValue")
            if nested.get("key_value") is not None:
                return nested.get("key_value")
        for key in ("status", "statusSeq", "status_seq"):
            if key in flat:
                v = flat[key]
                if not isinstance(v, dict) and v is not None:
                    return v
        return None

    if keys and keys[0] in ("deptId", "dept_id", "departmentId", "id"):
        flat = {k: v for k, v in dept.items() if k not in _HIDDEN_KEYS}
        for key in keys:
            if key in flat and not isinstance(flat[key], dict) and flat[key] is not None:
                return flat[key]
        return _dept_row_id(dept)

    if keys and keys[0] in ("buId", "bu_id", "businessUnitId", "business_unit_id"):
        return _get_bu_id_from_dept(dept)

    if keys and keys[0] in (
        "parentDeptId",
        "parent_dept_id",
        "parentDepartmentId",
        "parent_department_id",
    ):
        return _get_parent_dept_id_from_dept(dept)

    flat = {k: v for k, v in dept.items() if k not in _HIDDEN_KEYS}
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


def _get_dept_id(dept: dict[str, Any]) -> int | str | None:
    v = _dept_row_id(dept)
    return v


_DEPT_COL1 = (
    ("Department Id", ("deptId", "dept_id", "departmentId", "id")),
    ("Department Name*", ("deptName", "dept_name", "departmentName", "department_name", "name")),
    ("BU*", ("buSearch",)),
    ("Parent Dept", ("parentDeptSearch",)),
    ("Status", ("status",)),
)
_DEPT_COL2 = (
    ("Created By", ("createdBy", "created_by")),
    ("Created On", ("createdOn", "created_on", "createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified On", ("modifiedOn", "modified_on", "modifiedAt", "modified_at", "updatedAt", "updated_at")),
)
_DEPT_FIELD_GROUPS = _DEPT_COL1 + _DEPT_COL2

_READONLY_KEYS = frozenset({
    "deptId", "dept_id", "departmentId", "id",
    "createdBy", "created_by", "createdOn", "created_on", "createdAt", "created_at",
    "modifiedBy", "modified_by", "modifiedOn", "modified_on", "modifiedAt", "modified_at", "updatedAt", "updated_at",
})


class ViewDeptPage(QWidget):
    """Display department details; editable deptName, BU, parent department."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._dept: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit | QComboBox] = {}
        self._editable_keys: list[str] = []
        self._all_bus: list[dict[str, Any]] = []
        self._all_depts: list[dict[str, Any]] = []
        self._bu_completions: list[tuple[str, Any]] = []
        self._parent_dept_completions: list[tuple[str, Any]] = []
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
        title = QLabel("Department Details")
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
            if canonical == "buSearch":
                value_edit.setPlaceholderText(placeholder_search_select("BU Id", "BU Name", "Org Name"))
                completer = QCompleter(value_edit)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
                value_edit.setCompleter(completer)
            elif canonical == "parentDeptSearch":
                value_edit.setPlaceholderText(
                    placeholder_search_select("Dept Id", "Dept Name", "BU: BU Name")
                )
                completer = QCompleter(value_edit)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
                value_edit.setCompleter(completer)
            elif canonical == "deptName":
                value_edit.setPlaceholderText(placeholder_enter("department name"))
            elif canonical != "status":
                value_edit.setText("")

            self._field_edits[canonical] = value_edit
            grid.addWidget(labeled_field_block(label_widget, value_edit), idx, col)

        for idx, (label_text, keys) in enumerate(_DEPT_COL1):
            add_field(0, idx, label_text, keys)
        for idx, (label_text, keys) in enumerate(_DEPT_COL2):
            add_field(1, idx, label_text, keys)

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
        display_btns.setStyleSheet("background: transparent; border: none;")
        display_btns.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        display_btns_layout = QHBoxLayout(display_btns)
        display_btns_layout.setContentsMargins(0, 0, 0, 0)
        display_btns_layout.setSpacing(12)
        display_btns_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        display_btns_layout.addWidget(self._edit_btn)
        display_btns_layout.addWidget(self._back_btn)

        edit_btns = QWidget()
        edit_btns.setStyleSheet("background: transparent; border: none;")
        edit_btns.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        edit_btns_layout = QHBoxLayout(edit_btns)
        edit_btns_layout.setContentsMargins(0, 0, 0, 0)
        edit_btns_layout.setSpacing(12)
        edit_btns_layout.addWidget(self._save_btn)
        edit_btns_layout.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setFrameShape(QFrame.Shape.NoFrame)
        self._btn_stack.setStyleSheet(
            "QStackedWidget { border: none; background: transparent; }"
        )
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

        btn_row = max(len(_DEPT_COL1), len(_DEPT_COL2))
        grid.addWidget(self._error_label, btn_row, 0, 1, 2)
        grid.addWidget(
            self._btn_stack,
            btn_row + 1,
            0,
            1,
            2,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        grid.setRowMinimumHeight(btn_row + 1, 52)

        card_layout.addLayout(grid)
        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        self._switch_to_view_mode()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._dept:
            return
        self._load_bu_options()
        self._load_parent_dept_options()
        combo = self._field_edits.get("status")
        if isinstance(combo, QComboBox):
            populate_master_key_by_field_name(
                combo,
                _DEPT_STATUS_FIELD_NAME,
                token=self._token(),
                include_placeholder=False,
            )
        self._refresh_values()

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _sync_status_combo_from_dept(self) -> None:
        combo = self._field_edits.get("status")
        if not isinstance(combo, QComboBox) or combo.count() == 0:
            return
        seq = _dept_status_seq(self._dept)
        if seq is not None:
            set_searchable_combo_by_user_data(combo, seq)
            if combo_resolved_master_key_seq(combo) is not None:
                return
        kv = _get_value(self._dept, ("status",))
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

    def set_dept(self, dept: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._dept = dict(dept) if dept else {}
        self._load_bu_options()
        self._load_parent_dept_options()
        combo = self._field_edits.get("status")
        if isinstance(combo, QComboBox):
            populate_master_key_by_field_name(
                combo,
                _DEPT_STATUS_FIELD_NAME,
                token=self._token(),
                include_placeholder=False,
            )
        self._refresh_values()
        if edit_mode and self._dept:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _refresh_values(self) -> None:
        for _label_text, keys in _DEPT_FIELD_GROUPS:
            canonical = keys[0]
            if canonical == "status":
                continue
            value = _get_value(self._dept, keys)
            text = _format_value(value, keys[0], keys)
            edit = self._field_edits.get(canonical)
            if edit:
                if canonical == "buSearch":
                    self._set_bu_search_from_value()
                elif canonical == "parentDeptSearch":
                    self._set_parent_dept_search_from_value()
                elif isinstance(edit, QLineEdit):
                    edit.setText(text)
        self._sync_status_combo_from_dept()

    def _load_bu_options(self) -> None:
        bu_edit = self._field_edits.get("buSearch")
        if not isinstance(bu_edit, QLineEdit):
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_bu(token=token)
        bu_edit.blockSignals(True)
        self._all_bus = []
        self._bu_completions = []
        if result.get("success"):
            data = result.get("data") or []
            self._all_bus = [b for b in data if isinstance(b, dict)]
            self._all_bus.sort(key=lambda b: str(get_bu_name(b) or "").lower())
            for bu in self._all_bus:
                bid = get_bu_id(bu)
                if bid is None:
                    continue
                bu_name = get_bu_name(bu) or ""
                org_name = get_organization_name_from_bu(bu) or ""
                display = f"{bid} | {bu_name} | Org: {org_name}"
                self._bu_completions.append((display, bid))
        names = [d for d, _ in self._bu_completions]
        c = bu_edit.completer()
        if c is not None:
            c.setModel(QStringListModel(names))
        bu_edit.blockSignals(False)

    def _set_bu_search_from_value(self) -> None:
        bu_edit = self._field_edits.get("buSearch")
        if not isinstance(bu_edit, QLineEdit):
            return
        target = _get_bu_id_from_dept(self._dept)
        if target is None:
            bu_edit.clear()
            return
        target_str = str(target).strip()
        for disp, bid in self._bu_completions:
            if str(bid).strip() == target_str:
                bu_edit.setText(disp)
                return
        disp = _bu_search_display_from_dept(self._dept)
        if disp:
            bu_edit.setText(disp)
        else:
            bu_edit.setText(target_str)

    def _load_parent_dept_options(self) -> None:
        p_edit = self._field_edits.get("parentDeptSearch")
        if not isinstance(p_edit, QLineEdit):
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_depts(token=token)
        p_edit.blockSignals(True)
        self._all_depts = []
        self._parent_dept_completions = []
        current_id = _get_dept_id(self._dept)
        current_str = str(current_id).strip() if current_id is not None else ""
        if result.get("success"):
            data = result.get("data") or []
            self._all_depts = [d for d in data if isinstance(d, dict)]
            self._all_depts = [
                d for d in self._all_depts if str(_dept_row_id(d) or "").strip() != current_str
            ]
            self._all_depts.sort(key=lambda d: (_dept_row_name(d) or "").lower())
            for d in self._all_depts:
                did = _dept_row_id(d)
                if did is None:
                    continue
                dname = _dept_row_name(d) or ""
                bu_nm = _bu_name_from_dept_row(d)
                display = f"{did} | {dname} | BU: {bu_nm}"
                self._parent_dept_completions.append((display, did))
        names = [d for d, _ in self._parent_dept_completions]
        c = p_edit.completer()
        if c is not None:
            c.setModel(QStringListModel(names))
        p_edit.blockSignals(False)

    def _set_parent_dept_search_from_value(self) -> None:
        p_edit = self._field_edits.get("parentDeptSearch")
        if not isinstance(p_edit, QLineEdit):
            return
        target = _get_parent_dept_id_from_dept(self._dept)
        if target is None:
            p_edit.clear()
            return
        target_str = str(target).strip()
        for disp, pid in self._parent_dept_completions:
            if str(pid).strip() == target_str:
                p_edit.setText(disp)
                return
        disp = _parent_dept_search_display_from_dept(self._dept)
        if disp:
            p_edit.setText(disp)
        else:
            p_edit.setText(target_str)

    def _is_valid_bu_selection(self) -> bool:
        edit = self._field_edits.get("buSearch")
        if not isinstance(edit, QLineEdit):
            return False
        text = edit.text().strip()
        if not text:
            return False
        return text in {disp for disp, _ in self._bu_completions}

    def _is_valid_parent_dept_selection(self) -> bool:
        edit = self._field_edits.get("parentDeptSearch")
        if not isinstance(edit, QLineEdit):
            return False
        text = edit.text().strip()
        return text in {disp for disp, _ in self._parent_dept_completions}

    def _resolve_bu_id_from_ui(self) -> int | None:
        edit = self._field_edits.get("buSearch")
        if not isinstance(edit, QLineEdit):
            return None
        text = edit.text().strip()
        if not text:
            return None
        for disp, bid in self._bu_completions:
            if disp == text:
                try:
                    return int(bid)
                except (TypeError, ValueError):
                    return None
        return None

    def _resolve_parent_dept_id_from_ui(self) -> int | None:
        edit = self._field_edits.get("parentDeptSearch")
        if not isinstance(edit, QLineEdit):
            return None
        text = edit.text().strip()
        if not text:
            return None
        for disp, pid in self._parent_dept_completions:
            if disp == text:
                try:
                    return int(pid)
                except (TypeError, ValueError):
                    return None
        return None

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

    def _original_display_for_editable(self, canonical: str, keys: tuple[str, ...]) -> str:
        original = _get_value(self._dept, keys)
        if original is None:
            return ""
        return str(original).strip()

    def _has_unsaved_changes(self) -> bool:
        for _label_text, keys in _DEPT_FIELD_GROUPS:
            canonical = keys[0]
            if canonical not in self._editable_keys:
                continue
            if canonical == "buSearch":
                orig = _get_bu_id_from_dept(self._dept)
                cur = self._resolve_bu_id_from_ui()
                if ("" if orig is None else str(orig)) != ("" if cur is None else str(cur)):
                    return True
                continue
            if canonical == "parentDeptSearch":
                orig = _get_parent_dept_id_from_dept(self._dept)
                cur = self._resolve_parent_dept_id_from_ui()
                if ("" if orig is None else str(orig)) != ("" if cur is None else str(cur)):
                    return True
                continue
            if canonical == "status":
                combo = self._field_edits.get("status")
                if not isinstance(combo, QComboBox):
                    continue
                orig_seq = _dept_status_seq(self._dept)
                cur_seq = combo_resolved_master_key_seq(combo)
                if str(orig_seq or "").strip() != str(cur_seq or "").strip():
                    return True
                continue
            orig_str = self._original_display_for_editable(canonical, keys)
            current = self._get_edit_value(canonical)
            if orig_str != (current or "").strip():
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
        dept_name = self._get_edit_value("deptName", "dept_name", "departmentName", "name")
        if not dept_name:
            self._show_error("Department name is required.")
            return

        bu_text = self._get_edit_value("buSearch")
        if not bu_text:
            self._show_error("Please select a BU from the BU field.")
            return
        if not self._is_valid_bu_selection():
            self._show_error(strict_list_selection_message("a BU"))
            return
        bu_id = self._resolve_bu_id_from_ui()
        if bu_id is None:
            self._show_error("Please select a valid BU from the list.")
            return

        parent_text = self._get_edit_value("parentDeptSearch")
        if parent_text and not self._is_valid_parent_dept_selection():
            self._show_error(strict_list_selection_message("a parent department"))
            return
        parent_dept_id = self._resolve_parent_dept_id_from_ui()

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

        dept_id = _get_dept_id(self._dept)
        if dept_id is None:
            self._show_error("Department Id is missing.")
            return

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_update_dept(
            dept_id,
            bu_id=bu_id,
            dept_name=dept_name,
            parent_dept_id=parent_dept_id,
            status=status,
            token=token,
        )

        if not result.get("success"):
            self._show_error(result.get("message", "Failed to update department."))
            return

        self._dept["deptName"] = dept_name
        self._dept["buId"] = bu_id
        bu_line = self._get_edit_value("buSearch")
        if bu_line:
            bu_obj = None
            for b in self._all_bus:
                if get_bu_id(b) == bu_id:
                    bu_obj = dict(b)
                    break
            if bu_obj is not None:
                self._dept["businessUnit"] = bu_obj
        if parent_dept_id is not None:
            self._dept["parentDeptId"] = parent_dept_id
            p_line = self._get_edit_value("parentDeptSearch")
            if p_line:
                p_obj = None
                for d in self._all_depts:
                    if _dept_row_id(d) == parent_dept_id:
                        p_obj = dict(d)
                        break
                if p_obj is not None:
                    self._dept["parentDepartment"] = p_obj
        else:
            self._dept.pop("parentDeptId", None)
            self._dept.pop("parentDepartment", None)

        kv = (
            _combo_status_key_value(status_combo)
            if isinstance(status_combo, QComboBox)
            else str(status).strip().upper()
        )
        nested_st = _dept_status_nested(self._dept)
        if isinstance(nested_st, dict) and isinstance(status_combo, QComboBox):
            nested_st = dict(nested_st)
            nested_st["seq"] = status
            if kv:
                nested_st["keyValue"] = kv
            self._dept["status"] = nested_st
        elif isinstance(status_combo, QComboBox) and kv:
            self._dept["status"] = {"keyValue": kv, "seq": status}
        else:
            self._dept["status"] = kv or str(status)

        self._show_success(result.get("message", "Department updated successfully."))

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
