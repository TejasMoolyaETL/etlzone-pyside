"""View Profile page — layout aligned with Create User (header, scroll, card, two-column fields)."""

import json
import re
import ast
from typing import Any, Callable

from PySide6.QtCore import QRegularExpression, Qt, QTimer
from PySide6.QtGui import QRegularExpressionValidator, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.user_management.users.user_create import INPUT_STYLE, LABEL_STYLE, READONLY_INPUT_STYLE
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_LABEL_FIELD_SPACING_PX,
    FORM_PAGE_FONT_SIZE_PX,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
)
from core.app_preferences import format_datetime_display, is_datetime_field
from ui.blank_display import is_blank_display_value
from core.user_context import get_user_profile
from core.validators import COUNTRY_CODES, parse_mobile, validate_mobile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.post_save_navigation import navigate_after_no_changes
from ui.widgets.required_label import field_caption_label


# Email validation regex
_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Keys for email and mobile (for validation)
_EMAIL_KEYS = frozenset({"email"})
_MOBILE_KEYS = frozenset({"mobileNumber", "mobile_number"})

# Fields that show as textbox in edit mode but are read-only with grey background
_READONLY_EDIT_KEYS = frozenset(
    {
        "id",
        "userId",
        "user_id",
        "username",
        "userName",
        "user_name",
        "role",
        "userType",
        "user_type",
        "defaultRole",
        "default_role",
        "userStatus",
        "status",
        "timezone",
        "userTimezone",
        "user_timezone",
        "timeZone",
        "tzdata",
        "tz",
        "validFrom",
        "valid_from",
        "validTo",
        "valid_to",
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

# Fields to hide (sensitive or internal)
_HIDDEN_KEYS = frozenset(
    {
        "password",
        "token",
        "accessToken",
        "access_token",
        "jwt",
        "success",
        "message",
    }
)

# Audit fields: only shown when role is SADMIN
_AUDIT_KEYS = frozenset(
    {"createdBy", "created_by", "createdAt", "created_at", "modifiedBy", "modified_by", "modifiedAt", "modified_at"}
)

# Field groups: two columns like API: Project
# Col 1: main profile fields (* = mandatory in edit mode)
_PROFILE_COL1 = (
    ("Id", ("id", "userId", "user_id")),
    ("Username", ("username", "userName", "user_name")),
    ("Default Role", ("defaultRole", "default_role")),
    ("Firstname", ("firstName", "first_name")),
    ("Lastname", ("lastName", "last_name", "name")),
    ("Email*", ("email",)),
    ("Mobile", ("mobileNumber", "mobile_number")),
    ("Status", ("userStatus", "status")),
)
# Col 2: timezone and audit
_PROFILE_COL2 = (
    ("Timezone", ("timezone", "userTimezone", "user_timezone", "timeZone", "tzdata", "tz")),
    ("Created By", ("createdBy", "created_by")),
    ("Created At", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified At", ("modifiedAt", "modified_at")),
)
_FIELD_GROUPS = _PROFILE_COL1 + _PROFILE_COL2
_LABEL_OVERRIDES = {
    "id": "Id",
    "userType": "Role",
    "user_type": "Role",
    "userId": "Id",
    "user_id": "Id",
    "firstName": "Firstname",
    "first_name": "Firstname",
    "lastName": "Lastname",
    "last_name": "Lastname",
    "name": "Lastname",
    "userStatus": "Status",
    "defaultRole": "Default Role",
    "default_role": "Default Role",
    "mobileNumber": "Mobile",
    "mobile_number": "Mobile",
    "validFrom": "ValidFrom",
    "valid_from": "ValidFrom",
    "validTo": "ValidTo",
    "valid_to": "ValidTo",
    "createdBy": "CreatedBy",
    "created_by": "CreatedBy",
    "createdAt": "CreatedAt",
    "created_at": "CreatedAt",
    "modifiedBy": "ModifiedBy",
    "modified_by": "ModifiedBy",
    "modifiedAt": "ModifiedAt",
    "modified_at": "ModifiedAt",
    "timezone": "Timezone",
    "userTimezone": "Timezone",
    "user_timezone": "Timezone",
    "timeZone": "Timezone",
    "tzdata": "Timezone",
    "tz": "Timezone",
}

_ROLE_KEYS = frozenset({"role", "roles", "userType", "user_type", "defaultRole", "default_role"})


def _role_name(value: object) -> str:
    """Return plain role name from string/list/dict payloads."""
    if value is None:
        return ""
    if isinstance(value, str):
        s = value.strip()
        # Some APIs return role payload as a stringified dict/list.
        if s.startswith("{") or s.startswith("["):
            try:
                parsed = json.loads(s)
                return _role_name(parsed)
            except Exception:
                try:
                    parsed = ast.literal_eval(s)
                    return _role_name(parsed)
                except Exception:
                    pass
        return s if s else ""
    if isinstance(value, dict):
        role_status = ""
        for sk in ("roleStatus", "status"):
            sv = value.get(sk)
            if sv is not None and str(sv).strip():
                role_status = str(sv).strip().title()
                break
        for k in ("roleName", "role_name", "name", "defaultRole", "role", "userType"):
            v = value.get(k)
            if v is not None and str(v).strip():
                role_name = str(v).strip()
                return f"{role_name} ({role_status})" if role_status else role_name
        return ""
    if isinstance(value, list):
        names: list[str] = []
        for item in value:
            out = _role_name(item)
            if out:
                names.append(out)
        return ", ".join(names) if names else ""
    s = str(value).strip()
    return s if s else ""


def _format_value(value: object, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if key in _ROLE_KEYS:
        return _role_name(value)
    if is_blank_display_value(value):
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if key in _MOBILE_KEYS and value:
        cc, num = parse_mobile(str(value))
        if num:
            return f"{cc} {num}"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, indent=2, default=str)
    return str(value)


def _label_for_key(key: str) -> str:
    if key in _LABEL_OVERRIDES:
        return _LABEL_OVERRIDES[key]
    return key.replace("_", " ").title()


def _key_variants_for(key: str) -> tuple[str, ...]:
    """Return key variants for a canonical key."""
    for _, variants in _PROFILE_COL1 + _PROFILE_COL2:
        if variants[0] == key:
            return variants
    return (key,)


class ViewProfilePage(QWidget):
    """Profile from login session — same shell and field stacking as Create User."""

    def __init__(self, on_back: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.on_back = on_back
        self._field_edits: dict[str, QLineEdit | QComboBox | QWidget] = {}
        self._field_keys: list[str] = []
        self._editable_keys: list[str] = []
        self._mobile_country_combo: QComboBox | None = None
        self._mobile_number_edit: QLineEdit | None = None
        self._mobile_key: str | None = None
        self._profile_edit_baseline: dict[str, Any] | None = None
        self._build_ui()

    def _refresh_values(self) -> None:
        """Sync field values from profile."""
        profile = get_user_profile()
        for key in self._field_keys:
            val = next((profile.get(k) for k in _key_variants_for(key) if profile.get(k) is not None), None)
            if key in _MOBILE_KEYS and self._mobile_country_combo and self._mobile_number_edit:
                cc, num = parse_mobile(val)
                idx = self._mobile_country_combo.findData(cc)
                if idx >= 0:
                    self._mobile_country_combo.setCurrentIndex(idx)
                else:
                    self._mobile_country_combo.insertItem(0, f"Other ({cc})", cc)
                    self._mobile_country_combo.setCurrentIndex(0)
                self._mobile_number_edit.setText(num or "")
            else:
                edit = self._field_edits.get(key)
                if isinstance(edit, QComboBox):
                    txt = _format_value(val, key, _key_variants_for(key))
                    if txt and edit.findText(txt) < 0:
                        edit.addItem(txt)
                    edit.setCurrentText(txt or "")
                elif isinstance(edit, QLineEdit):
                    edit.setText(_format_value(val, key, _key_variants_for(key)))

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
        header_layout.addWidget(QLabel("View Profile"))
        header_layout.addStretch()
        back_hdr = QPushButton("Back")
        back_hdr.setFixedWidth(100)
        back_hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        back_hdr.clicked.connect(self._handle_back)
        header_layout.addWidget(back_hdr)
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

        profile = get_user_profile()
        readonly_keys = _READONLY_EDIT_KEYS | _AUDIT_KEYS | frozenset({
            "id",
            "userId",
            "user_id",
            "username",
            "userName",
            "user_name",
            "role",
            "userType",
            "user_type",
            "timezone",
            "userTimezone",
            "timeZone",
            "tzdata",
            "tz",
        })

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
        self._field_keys.clear()
        self._editable_keys.clear()
        self._field_edits.clear()

        def append_field(col_layout: QVBoxLayout, label_text: str, key_variants: tuple[str, ...]) -> None:
            chosen = key_variants[0]
            self._field_keys.append(chosen)
            if chosen not in readonly_keys:
                self._editable_keys.append(chosen)
            lbl = field_caption_label(label_text, LABEL_STYLE)
            val = next((profile.get(k) for k in key_variants if profile.get(k) is not None), None)
            val_str = _format_value(val, chosen, key_variants)

            if chosen in ("mobileNumber", "mobile_number"):
                self._mobile_key = chosen
                cc, num = parse_mobile(val)
                mobile_container = QWidget()
                mobile_container.setFixedHeight(field_h)
                mobile_row = QHBoxLayout(mobile_container)
                mobile_row.setContentsMargins(0, 0, 0, 0)
                mobile_row.setSpacing(10)
                country_combo = QComboBox()
                for code, country in COUNTRY_CODES:
                    country_combo.addItem(f"{country} ({code})", code)
                idx_cc = country_combo.findData(cc)
                if idx_cc >= 0:
                    country_combo.setCurrentIndex(idx_cc)
                else:
                    country_combo.insertItem(0, f"Other ({cc})", cc)
                    country_combo.setCurrentIndex(0)
                apply_form_combobox_field(country_combo, height_px=field_h, min_width=120)
                number_edit = QLineEdit()
                number_edit.setText(num or "")
                number_edit.setValidator(
                    QRegularExpressionValidator(QRegularExpression(r"^\d*$"))
                )
                number_edit.setFixedHeight(field_h)
                number_edit.setMinimumWidth(120)
                number_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                ro = chosen in readonly_keys
                number_edit.setReadOnly(ro)
                number_edit.setStyleSheet(READONLY_INPUT_STYLE if ro else INPUT_STYLE)
                country_combo.currentIndexChanged.connect(lambda: self._update_mobile_style())
                number_edit.textChanged.connect(lambda: self._update_mobile_style())
                number_edit.editingFinished.connect(self._validate_mobile_on_blur)
                mobile_row.addWidget(country_combo)
                mobile_row.addWidget(number_edit, 1)
                self._mobile_country_combo = country_combo
                self._mobile_number_edit = number_edit
                self._field_edits[chosen] = mobile_container
                _add_field_group(col_layout, lbl, mobile_container)
                return

            value_edit = QLineEdit()
            value_edit.setFixedHeight(field_h)
            value_edit.setMinimumWidth(240)
            value_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            value_edit.setText(val_str)
            value_edit.setReadOnly(chosen in readonly_keys)
            value_edit.setStyleSheet(READONLY_INPUT_STYLE if chosen in readonly_keys else INPUT_STYLE)
            if chosen in _EMAIL_KEYS:
                value_edit.textChanged.connect(
                    lambda t, w=value_edit: self._update_email_style(w, t)
                )
                value_edit.editingFinished.connect(
                    lambda w=value_edit: self._validate_email_on_blur(w)
                )
                self._update_email_style(value_edit, value_edit.text())

            self._field_edits[chosen] = value_edit
            _add_field_group(col_layout, lbl, value_edit)

        for lt, kv in _PROFILE_COL1:
            append_field(left_col, lt, kv)
        for lt, kv in _PROFILE_COL2:
            append_field(right_col, lt, kv)

        left_widget = QWidget()
        left_widget.setLayout(left_col)
        left_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        right_widget = QWidget()
        right_widget.setLayout(right_col)
        right_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        fields_grid.addWidget(left_widget, 0, 0, alignment=Qt.AlignmentFlag.AlignTop)
        fields_grid.addWidget(right_widget, 0, 1, alignment=Qt.AlignmentFlag.AlignTop)
        card_layout.addLayout(fields_grid)

        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._message_label.setVisible(False)
        card_layout.addWidget(self._message_label)

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
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._btn_stack.addWidget(display_btns)
        self._btn_stack.addWidget(edit_btns)
        self._btn_stack.setFixedWidth(100)

        bottom_btn_row = QHBoxLayout()
        bottom_btn_row.setContentsMargins(0, 0, 0, 0)
        bottom_btn_row.setSpacing(12)
        bottom_btn_row.addWidget(self._btn_stack)
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

        self._switch_to_view_mode()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_values()

    def _handle_back(self) -> None:
        """Go back to previous page (e.g. Dashboard)."""
        if self.on_back:
            self.on_back()

    def _update_email_style(self, widget: QLineEdit, text: str) -> None:
        """Update email field border color based on validity."""
        if widget.isReadOnly():
            return
        base = f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; padding: 4px 8px; border-radius: 4px;"
        if not text.strip():
            widget.setStyleSheet(f"{base} border: 1px solid #e2e8f0;")
        elif _EMAIL_REGEX.match(text.strip()):
            widget.setStyleSheet(f"{base} border: 1px solid #22c55e;")
        else:
            widget.setStyleSheet(f"{base} border: 1px solid #ef4444;")

    def _validate_email_on_blur(self, widget: QLineEdit) -> None:
        """Validate email when user leaves the field."""
        text = widget.text().strip()
        if text and not _EMAIL_REGEX.match(text):
            self._show_error("Please enter a valid email address.")
            widget.setFocus()

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._message_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._message_label, message, error=False)

    def _clear_message(self) -> None:
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.setText("")
        self._message_label.setVisible(False)

    def _update_mobile_style(self) -> None:
        """Update mobile number field border color based on validity."""
        if not self._mobile_number_edit or not self._mobile_country_combo:
            return
        if self._mobile_number_edit.isReadOnly():
            self._mobile_number_edit.setStyleSheet(READONLY_INPUT_STYLE)
            return
        base = f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; padding: 4px 8px; border-radius: 4px; background-color: #ffffff;"
        number = self._mobile_number_edit.text().strip()
        country_code = self._mobile_country_combo.currentData() or "+91"
        if not number:
            self._mobile_number_edit.setStyleSheet(f"{base} border: 1px solid #e2e8f0;")
        else:
            valid, _ = validate_mobile(country_code, number)
            color = "#22c55e" if valid else "#ef4444"
            self._mobile_number_edit.setStyleSheet(f"{base} border: 1px solid {color};")

    def _validate_mobile_on_blur(self) -> None:
        """Validate mobile number when user leaves the field."""
        if not self._mobile_number_edit or not self._mobile_country_combo:
            return
        number = self._mobile_number_edit.text().strip()
        if not number:
            return
        country_code = self._mobile_country_combo.currentData() or "+91"
        valid, msg = validate_mobile(country_code, number)
        if not valid:
            self._show_error(msg)
            self._mobile_number_edit.setFocus()

    def _capture_profile_edit_baseline(self) -> None:
        profile = get_user_profile()
        self._profile_edit_baseline = {}
        for key in self._editable_keys:
            if key in _MOBILE_KEYS:
                val = next(
                    (profile.get(k) for k in _key_variants_for(key) if profile.get(k) is not None),
                    None,
                )
                cc, num = parse_mobile(val)
                self._profile_edit_baseline["__cc__"] = str(cc or "+91")
                self._profile_edit_baseline["__num__"] = str(num or "").strip()
            else:
                val = next(
                    (profile.get(k) for k in _key_variants_for(key) if profile.get(k) is not None),
                    None,
                )
                self._profile_edit_baseline[key] = "" if val is None else str(val).strip()

    def _has_unsaved_profile_changes(self) -> bool:
        if not self._profile_edit_baseline:
            return True
        b = self._profile_edit_baseline
        for key in self._editable_keys:
            if key in _MOBILE_KEYS:
                if not self._mobile_country_combo or not self._mobile_number_edit:
                    continue
                cc = str(self._mobile_country_combo.currentData() or "+91")
                num = self._mobile_number_edit.text().strip()
                if cc != b.get("__cc__", "") or num != b.get("__num__", ""):
                    return True
            else:
                edit = self._field_edits.get(key)
                if isinstance(edit, QLineEdit):
                    if edit.text().strip() != b.get(key, ""):
                        return True
                elif isinstance(edit, QComboBox):
                    if edit.currentText().strip() != b.get(key, ""):
                        return True
        return False

    def _handle_edit(self) -> None:
        """Switch to edit mode: make fields editable, show Cancel and Save."""
        self._clear_message()
        for key in self._editable_keys:
            if key in _MOBILE_KEYS:
                if self._mobile_number_edit:
                    self._mobile_number_edit.setReadOnly(False)
                    self._mobile_number_edit.setStyleSheet(INPUT_STYLE)
                continue
            edit = self._field_edits.get(key)
            if edit:
                if isinstance(edit, QComboBox):
                    edit.setEnabled(True)
                elif isinstance(edit, QLineEdit):
                    edit.setReadOnly(False)
                edit.setStyleSheet(INPUT_STYLE)
        self._btn_stack.setFixedWidth(212)  # 100 + 12 + 100
        self._btn_stack.setCurrentIndex(1)
        self._capture_profile_edit_baseline()

    def _handle_save(self) -> None:
        """Save edited values via API and switch back to view mode."""
        from core.user_context import get_user_profile, set_user_profile

        if not self._has_unsaved_profile_changes():
            navigate_after_no_changes(
                show_non_error_message=self._show_success,
                clear_message=self._clear_message,
                on_back=self.on_back,
            )
            return

        profile = dict(get_user_profile())
        for key in self._editable_keys:
            edit = self._field_edits.get(key)
            if edit:
                if key in _MOBILE_KEYS and self._mobile_country_combo and self._mobile_number_edit:
                    country_code = self._mobile_country_combo.currentData() or "+91"
                    val = self._mobile_number_edit.text().strip()
                    if val:
                        valid, msg = validate_mobile(country_code, val)
                        if not valid:
                            self._show_error(msg)
                            return
                    profile["countryCode"] = country_code
                    profile[key] = val if val else None
                elif isinstance(edit, QLineEdit):
                    val = edit.text().strip()
                    if key in _EMAIL_KEYS and val:
                        if not _EMAIL_REGEX.match(val):
                            self._show_error("Please enter a valid email address.")
                            return
                    profile[key] = val if val else None

        from core.api import api_update_profile

        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_update_profile(profile, token=token)

        if not result.get("success"):
            self._show_error(result.get("message", "Failed to update profile."))
            return

        updated = result.get("data")
        if isinstance(updated, dict):
            for k, v in updated.items():
                if k not in ("password", "token") and v is not None:
                    profile[k] = v
        set_user_profile(profile)
        msg = result.get("message", "Profile updated successfully.")
        self._show_success(msg)
        def _do_after() -> None:
            self._clear_message()
            self._switch_to_view_mode()
        QTimer.singleShot(800, _do_after)

    def _handle_cancel(self) -> None:
        """Revert edits and switch back to view mode."""
        self._refresh_values()
        self._switch_to_view_mode()

    def is_edit_mode(self) -> bool:
        """Return True if profile is in edit mode (unsaved changes)."""
        return self._btn_stack.currentIndex() == 1

    def _switch_to_view_mode(self) -> None:
        """Switch to view mode: read-only fields, Edit button."""
        for key in self._editable_keys:
            if key in _MOBILE_KEYS:
                if self._mobile_number_edit:
                    self._mobile_number_edit.setReadOnly(True)
                    self._mobile_number_edit.setStyleSheet(READONLY_INPUT_STYLE)
                continue
            edit = self._field_edits.get(key)
            if edit:
                if isinstance(edit, QComboBox):
                    edit.setEnabled(False)
                elif isinstance(edit, QLineEdit):
                    edit.setReadOnly(True)
                edit.setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)
        self._btn_stack.setFixedWidth(100)
