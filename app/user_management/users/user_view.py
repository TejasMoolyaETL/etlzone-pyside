"""View / edit User — two-column stacked field layout (same as Create User); fields from Users list."""

from __future__ import annotations

import re
from typing import Any, Callable

from PySide6.QtCore import Qt, QRegularExpression, QStringListModel
from PySide6.QtGui import QRegularExpressionValidator
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

from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import FORM_COMBOBOX_STYLE, apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_FIELD_SPACING_PX,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_FONT_SIZE_PX,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    placeholder_example,
    placeholder_search_select,
)
from ui.post_save_navigation import schedule_after_success
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label
from app.user_management.users.user_list import (
    _COLUMN_SPEC,
    _flatten_user,
    _format_cell,
    _bu_name,
    _dept_name,
    _organization_name,
    _position_name,
)

# User Details does not show or edit account status (not sent on update-user API).
_USER_DETAILS_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = tuple(
    (label, keys)
    for label, keys in _COLUMN_SPEC
    if frozenset(keys).isdisjoint(frozenset({"userStatus", "status"}))
    and (label or "").strip().lower() != "status"
)

# Hints when the field is empty (view mode read-only or edit mode).
_USER_DETAIL_LINE_PLACEHOLDERS: dict[str, str] = {
    "id": placeholder_example("12345"),
    "username": placeholder_example("jsmith"),
    "defaultRole": placeholder_example("USER"),
    "firstName": placeholder_example("Jane"),
    "lastName": placeholder_example("Doe"),
    "email": placeholder_example("jane@company.com"),
    "timezone": placeholder_example("Asia/Kolkata"),
    "createdBy": placeholder_example("admin"),
    "createdAt": placeholder_example("2025-01-15 10:30"),
    "modifiedBy": placeholder_example("admin"),
    "modifiedAt": placeholder_example("2025-01-16 09:00"),
}
from core.api import (
    api_get_all_depts,
    api_get_all_orgs,
    api_get_all_positions,
    api_update_user,
)
from core.user_context import get_user_profile
from core.validators import COUNTRY_CODES, parse_mobile, validate_mobile

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

_EDITABLE_LINE_KEYS = frozenset({
    "firstName",
    "lastName",
    "email",
    "organizationName",
    "deptName",
    "positionName",
})

_KEYS_ORG = (
    "organizationName",
    "organization_name",
    "orgName",
    "org_name",
    "organization",
)
_KEYS_DEPT = (
    "deptName",
    "dept_name",
    "departmentName",
    "department_name",
    "department",
    "dept",
)
_KEYS_POS = ("positionName", "position_name", "position")

_ORG_WIDGET_KEY = "organizationName"
_DEPT_WIDGET_KEY = "deptName"
_POS_WIDGET_KEY = "positionName"
_BU_WIDGET_KEY = "buName"
_KEYS_BU_DISPLAY = (
    "buName",
    "bu_name",
    "businessUnitName",
    "business_unit_name",
    "businessUnit",
    "bu",
)

_MANAGED_LOOKUP_KEYS = frozenset({
    "organizationName",
    "deptName",
    "positionName",
    "buName",
})

_LEFT_COL_COUNT = 7

# Red * only on personal/contact fields; Org / Dept / Position rows are optional in the UI.
_USER_DETAIL_MANDATORY_KEYS = frozenset({
    "email",
    "firstName",
    "lastName",
    "mobileNumber",
})


def _get_user_id(user: dict[str, Any]) -> int | str | None:
    for k in ("id", "userId", "user_id"):
        v = user.get(k)
        if v is not None:
            return v
    return None


def _get_raw_value(user: dict[str, Any], keys: tuple[str, ...]) -> Any:
    flat = _flatten_user(user)
    for key in keys:
        if key in flat and flat[key] is not None:
            return flat[key]
    return None


def _display_for_column(user: dict[str, Any], keys: tuple[str, ...]) -> str:
    value = _get_raw_value(user, keys)
    if keys == _KEYS_POS:
        value = _position_name(value)
    elif keys == _KEYS_ORG:
        value = _organization_name(value)
    elif keys == _KEYS_BU_DISPLAY:
        value = _bu_name(value)
    elif keys == _KEYS_DEPT:
        value = _dept_name(value)
    key0 = keys[0]
    return _format_cell(value, key0)


def _org_id_from_user(user: dict[str, Any]) -> str:
    for k in ("orgID", "orgId", "org_id", "organizationId"):
        v = user.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _dept_id_from_user(user: dict[str, Any]) -> str:
    for k in ("deptId", "dept_id", "departmentId"):
        v = user.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _position_id_from_user(user: dict[str, Any]) -> str:
    for k in ("positionId", "position_id"):
        v = user.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _extract_bu_from_dept_row(dept: dict[str, Any]) -> tuple[str, str]:
    """Return (bu_id, bu_name) from a department API row (root or nested businessUnit/bu)."""
    bu_obj = dept.get("businessUnit") or dept.get("bu")
    bu_id = ""
    for k in ("buId", "bu_id", "businessUnitId", "business_unit_id"):
        v = dept.get(k)
        if v is not None and str(v).strip():
            bu_id = str(v).strip()
            break
    if not bu_id and isinstance(bu_obj, dict):
        for k in ("buId", "bu_id", "businessUnitId", "id"):
            v = bu_obj.get(k)
            if v is not None and str(v).strip():
                bu_id = str(v).strip()
                break
    bu_name = ""
    for k in ("buName", "bu_name", "businessUnitName", "business_unit_name"):
        v = dept.get(k)
        if v is not None and str(v).strip():
            bu_name = str(v).strip()
            break
    if not bu_name and isinstance(bu_obj, dict):
        for k in ("buName", "bu_name", "name", "businessUnitName"):
            v = bu_obj.get(k)
            if v is not None and str(v).strip():
                bu_name = str(v).strip()
                break
    return (bu_id, bu_name)


def _bu_id_from_user(user: dict[str, Any]) -> str:
    for k in ("buId", "bu_id", "businessUnitId", "business_unit_id"):
        v = user.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    bu = user.get("businessUnit") or user.get("bu")
    if isinstance(bu, dict):
        for k in ("buId", "bu_id", "id"):
            v = bu.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
    return ""


class ViewUserPage(QWidget):
    """User details; same shell as Position Details. Update sends full user body expected by API."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._user: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit] = {}
        self._editable_widget_keys: list[str] = []
        self._ref_loaded = False
        self._org_items: list[tuple[str, str]] = []
        self._dept_items: list[tuple[str, str]] = []
        self._dept_bu_by_dept_id: dict[str, tuple[str, str]] = {}
        self._position_items: list[tuple[str, str]] = []
        self._org_completer: QCompleter | None = None
        self._dept_completer: QCompleter | None = None
        self._pos_completer: QCompleter | None = None
        self._user_before_edit: dict[str, Any] | None = None
        self._mobile_country: QComboBox | None = None
        self._mobile_number: QLineEdit | None = None
        self._build_ui()

    def set_user(self, user: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._user = dict(user) if user else {}
        # Load org/dept/position catalogs before refresh so lookup lines match edit mode (id | name).
        if self._user:
            self._ensure_reference_data_loaded()
        self._refresh_values()
        if edit_mode and self._user:
            self._ensure_reference_data_loaded()
            self._handle_edit()
        else:
            self._switch_to_view_mode()

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
        header_layout.addWidget(QLabel("User Details"))
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
        card.setMaximumWidth(920)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        fields_grid = QGridLayout()
        fields_grid.setHorizontalSpacing(24)
        fields_grid.setVerticalSpacing(0)
        fields_grid.setColumnStretch(0, 1)
        fields_grid.setColumnStretch(1, 1)
        field_h = FORM_SINGLELINE_FIELD_HEIGHT_PX

        def _make_col() -> QVBoxLayout:
            col = QVBoxLayout()
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(10)
            return col

        def _add_field_group(col_layout: QVBoxLayout, label: QLabel, field: QWidget) -> None:
            group = QVBoxLayout()
            group.setContentsMargins(0, 0, 0, 0)
            group.setSpacing(FORM_LABEL_FIELD_SPACING_PX)
            label.setMinimumWidth(0)
            label.setMaximumWidth(16777215)
            group.addWidget(label)
            group.addWidget(field)
            wrap = QWidget()
            wrap.setLayout(group)
            col_layout.addWidget(wrap)

        left_col = _make_col()
        right_col = _make_col()

        def register_editable(canonical: str) -> None:
            if canonical not in self._editable_widget_keys:
                self._editable_widget_keys.append(canonical)

        def add_field(col: int, label_text: str, keys: tuple[str, ...]) -> None:
            canonical = keys[0]
            col_layout = left_col if col == 0 else right_col
            lbl = field_caption_label(
                label_text,
                LABEL_STYLE,
                required=canonical in _USER_DETAIL_MANDATORY_KEYS,
            )

            editable = (
                canonical in _EDITABLE_LINE_KEYS
                or keys == ("mobileNumber", "mobile_number")
            )

            if keys == ("mobileNumber", "mobile_number"):
                mobile_container = QWidget()
                mobile_container.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
                mobile_row = QHBoxLayout(mobile_container)
                mobile_row.setContentsMargins(0, 0, 0, 0)
                mobile_row.setSpacing(10)
                self._mobile_country = QComboBox()
                for code, country in COUNTRY_CODES:
                    self._mobile_country.addItem(f"{country} ({code})", code)
                apply_form_combobox_field(self._mobile_country, height_px=field_h, min_width=120)
                self._mobile_country.setEnabled(False)
                self._mobile_number = QLineEdit()
                self._mobile_number.setValidator(
                    QRegularExpressionValidator(QRegularExpression(r"^\d*$"))
                )
                self._mobile_number.setReadOnly(True)
                self._mobile_number.setStyleSheet(READONLY_INPUT_STYLE)
                self._mobile_number.setMinimumWidth(120)
                self._mobile_number.setFixedHeight(field_h)
                self._mobile_country.currentIndexChanged.connect(self._update_mobile_style)
                self._mobile_number.textChanged.connect(self._update_mobile_style)
                mobile_row.addWidget(self._mobile_country)
                mobile_row.addWidget(self._mobile_number, 1)
                self._field_edits["mobileNumber"] = self._mobile_number
                _add_field_group(col_layout, lbl, mobile_container)
                return

            value_edit = QLineEdit()
            value_edit.setFixedHeight(field_h)
            value_edit.setMinimumWidth(240)
            value_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            ro = not editable
            value_edit.setReadOnly(ro)
            value_edit.setStyleSheet(READONLY_INPUT_STYLE if ro else INPUT_STYLE)
            value_edit.setText("")

            if canonical == "email":
                value_edit.textChanged.connect(
                    lambda t, w=value_edit: self._update_email_style(w, t)
                )
                value_edit.editingFinished.connect(
                    lambda w=value_edit: self._validate_email_on_blur(w)
                )
                self._update_email_style(value_edit, value_edit.text())

            ph = _USER_DETAIL_LINE_PLACEHOLDERS.get(canonical)
            if ph:
                value_edit.setPlaceholderText(ph)

            if editable:
                register_editable(canonical)

            self._field_edits[canonical] = value_edit
            _add_field_group(col_layout, lbl, value_edit)

        left = list(_USER_DETAILS_COLUMN_SPEC[:_LEFT_COL_COUNT])
        for label_text, keys in left:
            add_field(0, label_text, keys)

        # Left column: Org (BU / Dept / Position stay on the right)
        label_org = QLabel("Org:")
        label_org.setStyleSheet(LABEL_STYLE)
        self.org_name_edit = QLineEdit()
        self.org_name_edit.setPlaceholderText(placeholder_search_select("Org Id", "Org Name"))
        self.org_name_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self.org_name_edit.setFixedHeight(field_h)
        self.org_name_edit.setMinimumWidth(240)
        self.org_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._field_edits[_ORG_WIDGET_KEY] = self.org_name_edit
        register_editable(_ORG_WIDGET_KEY)
        _add_field_group(left_col, label_org, self.org_name_edit)

        # Right column: BU / Dept / Position — same pattern as Create User
        label_bu = QLabel("BU Name:")
        label_bu.setStyleSheet(LABEL_STYLE)
        self.bu_name_edit = QLineEdit()
        self.bu_name_edit.setReadOnly(True)
        self.bu_name_edit.setPlaceholderText(placeholder_example("Engineering"))
        self.bu_name_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self.bu_name_edit.setFixedHeight(field_h)
        self.bu_name_edit.setMinimumWidth(240)
        self.bu_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._field_edits[_BU_WIDGET_KEY] = self.bu_name_edit
        _add_field_group(right_col, label_bu, self.bu_name_edit)

        label_dept = QLabel("Dept:")
        label_dept.setStyleSheet(LABEL_STYLE)
        self.dept_name_edit = QLineEdit()
        self.dept_name_edit.setPlaceholderText(placeholder_search_select("Dept Id", "Dept Name"))
        self.dept_name_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self.dept_name_edit.setFixedHeight(field_h)
        self.dept_name_edit.setMinimumWidth(240)
        self.dept_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.dept_name_edit.textEdited.connect(self._on_dept_name_text_edited)
        self._field_edits[_DEPT_WIDGET_KEY] = self.dept_name_edit
        register_editable(_DEPT_WIDGET_KEY)
        _add_field_group(right_col, label_dept, self.dept_name_edit)

        label_position = QLabel("Position:")
        label_position.setStyleSheet(LABEL_STYLE)
        self.position_name_edit = QLineEdit()
        self.position_name_edit.setPlaceholderText(placeholder_search_select("Position Id", "Position Name"))
        self.position_name_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self.position_name_edit.setFixedHeight(field_h)
        self.position_name_edit.setMinimumWidth(240)
        self.position_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._field_edits[_POS_WIDGET_KEY] = self.position_name_edit
        register_editable(_POS_WIDGET_KEY)
        _add_field_group(right_col, label_position, self.position_name_edit)

        right_tail = [
            (lt, ks)
            for lt, ks in _USER_DETAILS_COLUMN_SPEC[_LEFT_COL_COUNT:]
            if ks[0] not in _MANAGED_LOOKUP_KEYS
        ]
        for label_text, keys in right_tail:
            add_field(1, label_text, keys)

        left_widget = QWidget()
        left_widget.setLayout(left_col)
        left_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        right_widget = QWidget()
        right_widget.setLayout(right_col)
        right_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        fields_grid.addWidget(left_widget, 0, 0, alignment=Qt.AlignmentFlag.AlignTop)
        fields_grid.addWidget(right_widget, 0, 1, alignment=Qt.AlignmentFlag.AlignTop)
        card_layout.addLayout(fields_grid)

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

        _btn_area_bg = "background-color: #ffffff; border: none;"
        display_btns = QWidget()
        display_btns.setStyleSheet(f"QWidget {{ {_btn_area_bg} }}")
        dbl = QHBoxLayout(display_btns)
        dbl.setContentsMargins(0, 0, 0, 0)
        dbl.setSpacing(12)
        dbl.addWidget(self._edit_btn)
        dbl.addWidget(self._back_btn)

        edit_btns = QWidget()
        edit_btns.setStyleSheet(f"QWidget {{ {_btn_area_bg} }}")
        ebl = QHBoxLayout(edit_btns)
        ebl.setContentsMargins(0, 0, 0, 0)
        ebl.setSpacing(12)
        ebl.addWidget(self._save_btn)
        ebl.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setStyleSheet(
            f"QStackedWidget {{ {_btn_area_bg} }}"
        )
        self._btn_stack.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
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

        card_layout.addWidget(self._error_label)

        bottom_btn_row = QHBoxLayout()
        bottom_btn_row.setContentsMargins(0, 0, 0, 0)
        bottom_btn_row.setSpacing(12)
        bottom_btn_row.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        bottom_btn_row.addWidget(
            self._btn_stack,
            0,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        bottom_btn_row.addStretch(1)

        bottom_btn_wrap = QWidget()
        bottom_btn_wrap.setMinimumHeight(52)
        bottom_btn_wrap.setStyleSheet(f"QWidget {{ {_btn_area_bg} }}")
        bottom_btn_wrap.setLayout(bottom_btn_row)
        card_layout.addWidget(bottom_btn_wrap)

        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        self._wire_completers()
        self._switch_to_view_mode()

    def _wire_completers(self) -> None:
        self._org_completer = QCompleter(self.org_name_edit)
        self._org_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._org_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._org_completer.setMaxVisibleItems(12)
        self.org_name_edit.setCompleter(self._org_completer)
        self._org_completer.activated.connect(self._on_org_selected)

        self._dept_completer = QCompleter(self.dept_name_edit)
        self._dept_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._dept_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._dept_completer.setMaxVisibleItems(12)
        self.dept_name_edit.setCompleter(self._dept_completer)
        self._dept_completer.activated.connect(self._on_dept_selected)

        self._pos_completer = QCompleter(self.position_name_edit)
        self._pos_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._pos_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._pos_completer.setMaxVisibleItems(12)
        self.position_name_edit.setCompleter(self._pos_completer)
        self._pos_completer.activated.connect(self._on_position_selected)

    @staticmethod
    def _id_from_lookup_line(line: str) -> str:
        t = (line or "").strip()
        if not t:
            return ""
        return t.split("|", 1)[0].strip()

    def _on_org_selected(self, text: str) -> None:
        self.org_name_edit.setText(text)

    def _on_dept_selected(self, text: str) -> None:
        self.dept_name_edit.setText(text)
        self._refresh_bu_display_for_dept_id(self._id_from_lookup_line(text))

    def _on_dept_name_text_edited(self, _t: str) -> None:
        self._refresh_bu_display_for_dept_id(self._id_from_lookup_line(self.dept_name_edit.text()))

    def _bu_display_and_id_for_dept(self, dept_id: str) -> tuple[str, str]:
        if dept_id and dept_id in self._dept_bu_by_dept_id:
            bid, bname = self._dept_bu_by_dept_id[dept_id]
            label = bname.strip() if bname.strip() else bid
            return (label if label else "", bid)
        return ("", "")

    def _refresh_bu_display_for_dept_id(self, dept_id: str) -> None:
        label, _bid = self._bu_display_and_id_for_dept(dept_id)
        if label:
            self.bu_name_edit.setText(label)
            return
        txt = _display_for_column(self._user, _KEYS_BU_DISPLAY)
        self.bu_name_edit.setText(txt)

    def _bu_id_for_current_dept_selection(self) -> str:
        did = self._id_from_lookup_line(self.dept_name_edit.text())
        if did and did in self._dept_bu_by_dept_id:
            bid, _ = self._dept_bu_by_dept_id[did]
            return bid.strip()
        return _bu_id_from_user(self._user).strip()

    def _on_position_selected(self, text: str) -> None:
        self.position_name_edit.setText(text)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._ensure_reference_data_loaded(force=True)
        if self._user:
            self._refresh_lookup_displays_from_user()

    def _ensure_reference_data_loaded(self, *, force: bool = False) -> None:
        if self._ref_loaded and not force:
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        self._org_items = self._extract_id_name_items(
            (api_get_all_orgs(token=token).get("data") or []),
            id_keys=("orgID", "orgId", "org_id", "organizationId", "id"),
            name_keys=("orgName", "org_name", "organizationName", "name"),
        )
        dept_rows = api_get_all_depts(token=token).get("data") or []
        self._dept_items = self._extract_id_name_items(
            dept_rows,
            id_keys=("deptId", "dept_id", "departmentId", "id"),
            name_keys=("deptName", "dept_name", "departmentName", "name"),
        )
        self._dept_bu_by_dept_id = {}
        for row in dept_rows:
            if not isinstance(row, dict):
                continue
            did = None
            for k in ("deptId", "dept_id", "departmentId", "id"):
                v = row.get(k)
                if v is not None and str(v).strip():
                    did = str(v).strip()
                    break
            if not did:
                continue
            bid, bnm = _extract_bu_from_dept_row(row)
            self._dept_bu_by_dept_id[did] = (bid, bnm)
        self._position_items = self._extract_id_name_items(
            (api_get_all_positions(token=token).get("data") or []),
            id_keys=("positionId", "position_id", "id"),
            name_keys=("positionName", "position_name", "name"),
        )
        if self._org_completer:
            self._org_completer.setModel(QStringListModel(self._format_items(self._org_items)))
        if self._dept_completer:
            self._dept_completer.setModel(QStringListModel(self._format_items(self._dept_items)))
        if self._pos_completer:
            self._pos_completer.setModel(QStringListModel(self._format_items(self._position_items)))
        self._ref_loaded = True

    def _extract_id_name_items(
        self,
        rows: list,
        *,
        id_keys: tuple[str, ...],
        name_keys: tuple[str, ...],
    ) -> list[tuple[str, str]]:
        items: list[tuple[str, str]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            _id = None
            _name = None
            for k in id_keys:
                v = row.get(k)
                if v is not None and str(v).strip():
                    _id = str(v).strip()
                    break
            for k in name_keys:
                v = row.get(k)
                if v is not None and str(v).strip():
                    _name = str(v).strip()
                    break
            if _id:
                items.append((_id, _name or ""))
        return items

    def _format_items(self, items: list[tuple[str, str]]) -> list[str]:
        return [f"{i} | {n}" if n else i for i, n in items]

    def _refresh_mobile_from_user(self) -> None:
        if not self._mobile_country or not self._mobile_number:
            return
        raw = _get_raw_value(self._user, ("mobileNumber", "mobile_number"))
        cc, num = parse_mobile(str(raw) if raw is not None else None)
        self._mobile_country.blockSignals(True)
        self._mobile_number.blockSignals(True)
        while (
            self._mobile_country.count() > 0
            and self._mobile_country.itemText(0).startswith("Other (")
        ):
            self._mobile_country.removeItem(0)
        idx = self._mobile_country.findData(cc)
        if idx >= 0:
            self._mobile_country.setCurrentIndex(idx)
        else:
            self._mobile_country.insertItem(0, f"Other ({cc})", cc)
            self._mobile_country.setCurrentIndex(0)
        self._mobile_number.setText(num or "")
        self._mobile_country.blockSignals(False)
        self._mobile_number.blockSignals(False)
        self._update_mobile_style()

    def _update_email_style(self, widget: QLineEdit, text: str) -> None:
        base = f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; padding: 4px 8px; border-radius: 4px; background-color: #ffffff;"
        if widget.isReadOnly():
            return
        if not text.strip():
            widget.setStyleSheet(f"{base} border: 1px solid #e2e8f0;")
        elif _EMAIL_REGEX.match(text.strip()):
            widget.setStyleSheet(f"{base} border: 1px solid #22c55e;")
        else:
            widget.setStyleSheet(f"{base} border: 1px solid #ef4444;")

    def _validate_email_on_blur(self, widget: QLineEdit) -> None:
        if widget.isReadOnly():
            return
        text = widget.text().strip()
        if text and not _EMAIL_REGEX.match(text):
            self._show_error("Please enter a valid email address.")
            widget.setFocus()

    def _update_mobile_style(self) -> None:
        if not self._mobile_number or not self._mobile_country:
            return
        base = f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; padding: 4px 8px; border-radius: 4px; background-color: #ffffff;"
        if self._mobile_number.isReadOnly():
            self._mobile_number.setStyleSheet(READONLY_INPUT_STYLE)
            return
        number = self._mobile_number.text().strip()
        country_code = self._mobile_country.currentData() or "+91"
        if not number:
            self._mobile_number.setStyleSheet(f"{base} border: 1px solid #e2e8f0;")
        else:
            valid, _ = validate_mobile(country_code, number)
            color = "#22c55e" if valid else "#ef4444"
            self._mobile_number.setStyleSheet(f"{base} border: 1px solid {color};")

    def _apply_lookup_line(
        self,
        edit: QLineEdit,
        entity_id: str,
        items: list[tuple[str, str]],
        keys: tuple[str, ...],
    ) -> None:
        if entity_id and items:
            for i, n in items:
                if i == entity_id:
                    edit.setText(f"{i} | {n}" if n else i)
                    return
        txt = _display_for_column(self._user, keys)
        edit.setText(txt)

    def _refresh_lookup_displays_from_user(self) -> None:
        oid = _org_id_from_user(self._user)
        self._apply_lookup_line(self.org_name_edit, oid, self._org_items, _KEYS_ORG)

        did = _dept_id_from_user(self._user)
        self._apply_lookup_line(self.dept_name_edit, did, self._dept_items, _KEYS_DEPT)
        self._refresh_bu_display_for_dept_id(did)

        pid = _position_id_from_user(self._user)
        self._apply_lookup_line(self.position_name_edit, pid, self._position_items, _KEYS_POS)

    def _refresh_values(self) -> None:
        for _label_text, keys in _USER_DETAILS_COLUMN_SPEC:
            if keys[0] in _MANAGED_LOOKUP_KEYS:
                continue
            if keys == ("mobileNumber", "mobile_number"):
                self._refresh_mobile_from_user()
                continue
            canonical = keys[0]
            edit = self._field_edits.get(canonical)
            if not isinstance(edit, QLineEdit):
                continue
            text = _display_for_column(self._user, keys)
            edit.setText(text)
        self._refresh_lookup_displays_from_user()
        email_w = self._field_edits.get("email")
        if isinstance(email_w, QLineEdit) and email_w.isReadOnly():
            email_w.setStyleSheet(READONLY_INPUT_STYLE)

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=False)

    def _get_edit_text(self, key: str) -> str:
        w = self._field_edits.get(key)
        if isinstance(w, QLineEdit):
            t = w.text().strip()
            return "" if t in ("", "\u2014") else t
        return ""

    def _snapshot_from_form(self) -> dict[str, Any]:
        cc = (
            str(self._mobile_country.currentData() or "+91")
            if self._mobile_country
            else "+91"
        )
        num = self._mobile_number.text().strip() if self._mobile_number else ""
        return {
            "firstName": self._get_edit_text("firstName"),
            "lastName": self._get_edit_text("lastName"),
            "email": self._get_edit_text("email"),
            "countryCode": cc,
            "mobileNumber": num if num else "",
            "organizationName": self._get_edit_text(_ORG_WIDGET_KEY),
            "deptName": self._get_edit_text(_DEPT_WIDGET_KEY),
            "positionName": self._get_edit_text(_POS_WIDGET_KEY),
            "buName": self._get_edit_text(_BU_WIDGET_KEY),
            "orgId": self._id_from_lookup_line(self.org_name_edit.text()),
            "deptId": self._id_from_lookup_line(self.dept_name_edit.text()),
            "positionId": self._id_from_lookup_line(self.position_name_edit.text()),
        }

    def _snapshot_from_user(self) -> dict[str, Any]:
        u = self._user
        mob_raw = str(_get_raw_value(u, ("mobileNumber", "mobile_number")) or "").strip()
        cc, num = parse_mobile(mob_raw if mob_raw else None)
        return {
            "firstName": _display_for_column(u, ("firstName", "first_name")),
            "lastName": _display_for_column(u, ("lastName", "last_name", "name")),
            "email": _display_for_column(u, ("email",)),
            "countryCode": cc,
            "mobileNumber": num if num else "",
            "organizationName": _display_for_column(u, _KEYS_ORG),
            "deptName": _display_for_column(u, _KEYS_DEPT),
            "positionName": _display_for_column(u, _KEYS_POS),
            "buName": _display_for_column(u, _KEYS_BU_DISPLAY),
            "orgId": _org_id_from_user(u),
            "deptId": _dept_id_from_user(u),
            "positionId": _position_id_from_user(u),
        }

    def _has_unsaved_changes(self) -> bool:
        a = self._snapshot_from_user()
        b = self._snapshot_from_form()
        for k in b:
            if (a.get(k) or "").strip() != (b.get(k) or "").strip():
                return True
        return False

    def _handle_edit(self) -> None:
        self._clear_error()
        self._user_before_edit = dict(self._user)
        # Always refresh lookup lists on edit so newly created Org/Dept/Position entries appear.
        self._ensure_reference_data_loaded(force=True)
        for key in self._editable_widget_keys:
            edit = self._field_edits.get(key)
            if isinstance(edit, QLineEdit):
                edit.setReadOnly(False)
                edit.setStyleSheet(INPUT_STYLE)
                if not edit.text().strip() or edit.text().strip() == "\u2014":
                    edit.clear()
        self._prefill_lookup_rows_for_edit()
        if self._mobile_country and self._mobile_number:
            self._mobile_country.setEnabled(True)
            self._mobile_country.setStyleSheet(FORM_COMBOBOX_STYLE)
            self._mobile_number.setReadOnly(False)
            self._mobile_number.setStyleSheet(INPUT_STYLE)
            self._update_mobile_style()
        em = self._field_edits.get("email")
        if isinstance(em, QLineEdit):
            self._update_email_style(em, em.text())
        self._btn_stack.setCurrentIndex(1)

    def _prefill_lookup_rows_for_edit(self) -> None:
        self._refresh_lookup_displays_from_user()

    def _handle_cancel(self) -> None:
        if not self._has_unsaved_changes():
            self._clear_error()
            if self._user_before_edit is not None:
                self._user = dict(self._user_before_edit)
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
            if self._user_before_edit is not None:
                self._user = dict(self._user_before_edit)
            self._refresh_values()
            self._switch_to_view_mode()

    def _switch_to_view_mode(self) -> None:
        for key in self._editable_widget_keys:
            edit = self._field_edits.get(key)
            if isinstance(edit, QLineEdit):
                edit.setReadOnly(True)
                edit.setStyleSheet(READONLY_INPUT_STYLE)
        if self._mobile_country and self._mobile_number:
            self._mobile_country.setEnabled(False)
            self._mobile_country.setStyleSheet(FORM_COMBOBOX_STYLE)
            self._mobile_number.setReadOnly(True)
            self._mobile_number.setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)

    def _handle_save(self) -> None:
        self._clear_error()
        if not self._has_unsaved_changes():
            self._show_success("No changes have been made!")
            return
        first_name = self._get_edit_text("firstName")
        last_name = self._get_edit_text("lastName")
        email = self._get_edit_text("email")
        country_code = (
            str(self._mobile_country.currentData() or "+91")
            if self._mobile_country
            else "+91"
        )
        num = self._mobile_number.text().strip() if self._mobile_number else ""

        if not first_name:
            self._show_error("First name is required.")
            w = self._field_edits.get("firstName")
            if isinstance(w, QLineEdit):
                w.setFocus()
            return
        if not last_name:
            self._show_error("Last name is required.")
            w = self._field_edits.get("lastName")
            if isinstance(w, QLineEdit):
                w.setFocus()
            return
        if not email:
            self._show_error("Email is required.")
            w = self._field_edits.get("email")
            if isinstance(w, QLineEdit):
                w.setFocus()
            return
        if not _EMAIL_REGEX.match(email):
            self._show_error("Please enter a valid email address.")
            w = self._field_edits.get("email")
            if isinstance(w, QLineEdit):
                w.setFocus()
            return
        if not num:
            self._show_error("Mobile number is required.")
            if self._mobile_number:
                self._mobile_number.setFocus()
            return
        valid, msg = validate_mobile(country_code, num)
        if not valid:
            self._show_error(msg or "Invalid mobile number.")
            if self._mobile_number:
                self._mobile_number.setFocus()
            return

        org_text = self.org_name_edit.text().strip()
        if org_text:
            if org_text not in set(self._format_items(self._org_items)):
                self._show_error(strict_list_selection_message("an organization"))
                self.org_name_edit.setFocus()
                return
            org_id = org_text.split("|", 1)[0].strip()
        else:
            org_id = None

        dept_text = self.dept_name_edit.text().strip()
        if dept_text:
            if dept_text not in set(self._format_items(self._dept_items)):
                self._show_error(strict_list_selection_message("a department"))
                self.dept_name_edit.setFocus()
                return
            dept_id = dept_text.split("|", 1)[0].strip()
        else:
            dept_id = None

        pos_text = self.position_name_edit.text().strip()
        if pos_text:
            if pos_text not in set(self._format_items(self._position_items)):
                self._show_error(strict_list_selection_message("a position"))
                self.position_name_edit.setFocus()
                return
            position_id = pos_text.split("|", 1)[0].strip()
        else:
            position_id = None

        uid = _get_user_id(self._user)
        if uid is None:
            self._show_error("User Id is missing.")
            return

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        def _as_optional_int(s: str | None) -> int | None:
            if not s or not str(s).strip():
                return None
            s2 = str(s).strip()
            return int(s2) if s2.isdigit() else None

        oid = _as_optional_int(org_id)
        did = _as_optional_int(dept_id)
        pid = _as_optional_int(position_id)

        mobile_full = f"{country_code}{num}"

        result = api_update_user(
            uid,
            token=token,
            firstName=first_name or None,
            lastName=last_name or None,
            email=email or None,
            mobileNumber=mobile_full or None,
            orgId=oid,
            deptId=did,
            positionId=pid,
        )

        if not result.get("success"):
            self._show_error(result.get("message", "Failed to update user."))
            return

        updated = result.get("data")
        if isinstance(updated, dict):
            for k, v in updated.items():
                if v is not None:
                    self._user[k] = v
        else:
            self._user["email"] = email
            self._user["firstName"] = first_name
            self._user["lastName"] = last_name
            self._user["mobileNumber"] = mobile_full
            if org_id:
                self._user["orgId"] = int(org_id) if str(org_id).isdigit() else org_id
            else:
                for k in ("orgID", "orgId", "org_id", "organizationId"):
                    self._user.pop(k, None)
            if dept_id:
                self._user["deptId"] = int(dept_id) if str(dept_id).isdigit() else dept_id
            else:
                for k in ("deptId", "dept_id", "departmentId"):
                    self._user.pop(k, None)
            if position_id:
                self._user["positionId"] = int(position_id) if str(position_id).isdigit() else position_id
            else:
                for k in ("positionId", "position_id"):
                    self._user.pop(k, None)

        self._show_success(result.get("message", "User updated successfully."))
        self._refresh_values()
        self._switch_to_view_mode()

        schedule_after_success(
            delay_ms=800,
            clear_error=self._clear_error,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1
