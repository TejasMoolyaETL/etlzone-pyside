"""View / edit Lead Contact Person page."""

from __future__ import annotations

import re
from typing import Any, Callable

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.api import (
    api_get_master_key_by_app_id_field_name,
    api_update_contact_person,
    master_key_row_display_label,
    master_key_row_seq_value,
)
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from core.validators import COUNTRY_CODES, validate_mobile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_FONT_SIZE_PX,
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
from ui.post_save_navigation import schedule_after_success
from ui.widgets.required_label import field_caption_label, labeled_field_block

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Master-key ``fieldName`` for ``api/master-setup/master-config/get-by-field-name``.
_MK_FIELD_NAME_BY_UI_KEY: dict[str, str] = {
    "position": "lead_contact_person_position",
    "country": "country",
    "state": "state",
    "city": "city",
    "status": "lead_contact_person_status",
}

_MK_COMBO_KEYS: frozenset[str] = frozenset(_MK_FIELD_NAME_BY_UI_KEY.keys())

# Same sample hints as :class:`CreateContactPersonPage` (``placeholder_example`` wrapping).
_LINE_EDIT_PLACEHOLDER_SPEC: dict[str, str] = {
    "name": "John Smith",
    "email": "john@test.com",
    "url": "linkedin.com/john",
}

# (edit_key, caption, read_only) — line edits except mobile, hierarchy, and master-key combos.
# Trailing ``*`` must match :class:`CreateContactPersonPage` (``field_caption_label`` → red asterisk).
_FIELDS = (
    ("contactId", "Contact Person", True),
    ("name", "Contact Person Name*", False),
    ("position", "Position*", False),
    ("email", "Email", False),
    ("mobile", "Mobile", False),
    ("country", "Country*", False),
    ("state", "State*", False),
    ("city", "City*", False),
    ("url", "URL / profile", False),
    ("status", "Status*", False),
    ("hierarchy", "Hierarchy", False),
)

_DISPLAY_KEYS: dict[str, tuple[str, ...]] = {
    "contactId": ("contactId", "contactPersonId", "id", "contact_person_id"),
    "name": ("name", "contactPersonName"),
    "position": ("position", "positionSeq", "position_seq", "designation"),
    "email": ("email", "email1"),
    "mobile": ("mobile", "contactNo"),
    "country": ("country", "countrySeq", "country_seq"),
    "state": ("state", "stateSeq", "state_seq"),
    "city": ("city", "citySeq", "city_seq"),
    "url": ("url",),
    "status": ("status", "statusSeq", "status_seq", "lead_contact_person_status"),
    "hierarchy": ("hierarchy",),
}


def _pick_display(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        if key not in row:
            continue
        val = row[key]
        if val is None:
            continue
        s = str(val).strip()
        if s != "":
            return s
    return ""


def _master_seq_from_record(rec: dict[str, Any], keys: tuple[str, ...]) -> Any | None:
    """First numeric seq-like value from record keys (for master-key combo ``userData``)."""
    for key in keys:
        v = rec.get(key)
        if v is None:
            continue
        if isinstance(v, dict):
            seq_from_obj = master_key_row_seq_value(v)
            if seq_from_obj is not None:
                return seq_from_obj
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


def _split_stored_mobile(raw: str) -> tuple[str, str]:
    """Best-effort split stored value into dial code + national digits (for editing)."""
    s = (raw or "").strip()
    if not s:
        return "+91", ""
    if s.startswith("+"):
        for code, _ in sorted(COUNTRY_CODES, key=lambda x: len(x[0]), reverse=True):
            if s.startswith(code):
                return code, s[len(code) :].lstrip()
    return "+91", s


class ViewContactPersonPage(QWidget):
    def __init__(self, on_back: Callable[[], None] | None = None, on_update_success: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._record: dict[str, Any] = {}
        self._can_edit_action = True
        self._line_edits: dict[str, QLineEdit] = {}
        self._mk_combo_by_key: dict[str, QComboBox] = {}
        self._mobile_country: QComboBox | None = None
        self._mobile_number: QLineEdit | None = None
        self._hierarchy_combo: QComboBox | None = None
        self._build_ui()

    @staticmethod
    def _full_contact_number(country_code: str, national_digits: str) -> str:
        cc = str(country_code or "+91").strip()
        return f"{cc}{national_digits.strip()}"

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QWidget()
        header.setStyleSheet(FORM_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("Contact Person Details"))
        hl.addStretch()
        layout.addWidget(header)
        body = QWidget()
        bl = QVBoxLayout(body)
        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card.setMaximumWidth(920)
        card.setStyleSheet("#profileCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }")
        cl = QVBoxLayout(card)
        def new_section_grid() -> QGridLayout:
            grid = QGridLayout()
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            grid.setHorizontalSpacing(24)
            grid.setVerticalSpacing(10)
            return grid

        basic_grid = new_section_grid()
        contact_grid = new_section_grid()
        additional_grid = new_section_grid()
        layout_grid_by_name = {
            "basic": basic_grid,
            "contact": contact_grid,
            "additional": additional_grid,
        }
        placements: dict[str, tuple[str, int, int]] = {
            "contactId": ("basic", 0, 0),
            "name": ("basic", 0, 1),
            "position": ("basic", 1, 0),
            "status": ("basic", 1, 1),
            "email": ("contact", 0, 0),
            "mobile": ("contact", 0, 1),
            "country": ("contact", 1, 0),
            "state": ("contact", 1, 1),
            "city": ("contact", 2, 0),
            "hierarchy": ("contact", 2, 1),
            "url": ("additional", 0, 0),
        }
        fh = FORM_SINGLELINE_FIELD_HEIGHT_PX
        for k, label, ro in _FIELDS:
            group_name, r, c = placements.get(k, ("additional", 1, 1))
            grid = layout_grid_by_name[group_name]
            if k == "mobile":
                container = QWidget()
                container.setFixedHeight(fh)
                mlay = QHBoxLayout(container)
                mlay.setContentsMargins(0, 0, 0, 0)
                mlay.setSpacing(10)
                country = QComboBox()
                for code, country_name in COUNTRY_CODES:
                    country.addItem(f"{country_name} ({code})", code)
                apply_form_combobox_field(country, height_px=fh, min_width=120)
                number = QLineEdit()
                number.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\d*$")))
                number.setStyleSheet(INPUT_STYLE if not ro else READONLY_INPUT_STYLE)
                number.setFixedHeight(fh)
                number.setMinimumWidth(120)
                number.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                number.setReadOnly(ro)
                number.setPlaceholderText(placeholder_example("9876543210"))
                country.currentIndexChanged.connect(lambda _i, cc=country, num=number: self._update_mobile_row_style(cc, num))
                number.textChanged.connect(lambda _t, cc=country, num=number: self._update_mobile_row_style(cc, num))
                mlay.addWidget(country)
                mlay.addWidget(number, 1)
                self._mobile_country = country
                self._mobile_number = number
                self._update_mobile_row_style(country, number)
                grid.addWidget(labeled_field_block(field_caption_label(label, LABEL_STYLE), container), r, c)
            elif k == "hierarchy":
                combo = QComboBox()
                apply_form_combobox_field(combo, height_px=fh, min_width=120)
                for n in range(1, 21):
                    combo.addItem(str(n), n)
                combo.setCurrentIndex(0)
                self._hierarchy_combo = combo
                grid.addWidget(labeled_field_block(field_caption_label(label, LABEL_STYLE), combo), r, c)
            elif k in _MK_COMBO_KEYS:
                combo = QComboBox()
                combo.setMinimumWidth(240)
                combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                apply_form_combobox_field(combo, height_px=fh)
                self._mk_combo_by_key[k] = combo
                grid.addWidget(labeled_field_block(field_caption_label(label, LABEL_STYLE), combo), r, c)
            else:
                e = QLineEdit()
                e.setFixedHeight(fh)
                e.setMinimumWidth(240)
                e.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                e.setReadOnly(ro)
                e.setStyleSheet(READONLY_INPUT_STYLE if ro else INPUT_STYLE)
                ph_spec = _LINE_EDIT_PLACEHOLDER_SPEC.get(k)
                if ph_spec:
                    e.setPlaceholderText(placeholder_example(ph_spec))
                if k == "email":
                    e.textChanged.connect(lambda text, w=e: self._update_email_style(w, text))
                    self._update_email_style(e, e.text())
                self._line_edits[k] = e
                if k == "url":
                    grid.addWidget(
                        labeled_field_block(field_caption_label(label, LABEL_STYLE), e),
                        r,
                        c,
                        1,
                        2,
                    )
                else:
                    grid.addWidget(
                        labeled_field_block(field_caption_label(label, LABEL_STYLE), e), r, c
                    )
        cl.addLayout(basic_grid)
        cl.addSpacing(4)
        cl.addLayout(contact_grid)
        cl.addSpacing(4)
        cl.addLayout(additional_grid)
        self._error = QLabel()
        self._error.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error.setVisible(False)
        self._error.setWordWrap(True)
        cl.addWidget(self._error)
        self._back = QPushButton("Back")
        self._back.setFixedWidth(100)
        self._back.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._back.clicked.connect(self._handle_back)
        self._edit = QPushButton("Edit")
        self._edit.setFixedWidth(100)
        self._edit.setStyleSheet(
            FORM_PRIMARY_BUTTON_STYLESHEET
            + " QPushButton:disabled {"
            + " background-color: #e5e7eb;"
            + " color: #6b7280;"
            + " border: 1px solid #cbd5e1;"
            + "}"
        )
        self._edit.clicked.connect(self._handle_edit)
        self._cancel = QPushButton("Cancel")
        self._cancel.setFixedWidth(100)
        self._cancel.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._cancel.clicked.connect(self._handle_cancel)
        self._save = QPushButton("Save")
        self._save.setFixedWidth(100)
        self._save.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._save.clicked.connect(self._handle_save)
        view_btns = QWidget()
        view_btns.setStyleSheet("background: transparent; border: none;")
        vbl = QHBoxLayout(view_btns)
        vbl.setContentsMargins(0, 0, 0, 0)
        vbl.setSpacing(12)
        vbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        vbl.addWidget(self._edit)
        vbl.addWidget(self._back)
        edit_btns = QWidget()
        edit_btns.setStyleSheet("background: transparent; border: none;")
        ebl = QHBoxLayout(edit_btns)
        ebl.setContentsMargins(0, 0, 0, 0)
        ebl.setSpacing(12)
        ebl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        ebl.addWidget(self._save)
        ebl.addWidget(self._cancel)
        self._btn_stack = QStackedWidget()
        self._btn_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._btn_stack.addWidget(view_btns)
        self._btn_stack.addWidget(edit_btns)
        cl.addWidget(self._btn_stack, 0, Qt.AlignmentFlag.AlignLeft)
        bl.addWidget(card)
        bl.addStretch()
        layout.addWidget(body)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_edit_action_access()
        for ui_key in _MK_COMBO_KEYS:
            self._populate_mk_combo(ui_key)
        for ui_key in _MK_COMBO_KEYS:
            self._apply_mk_combo_from_record(ui_key)

    def _populate_mk_combo(self, ui_key: str) -> None:
        combo = self._mk_combo_by_key.get(ui_key)
        if combo is None:
            return
        field_name = _MK_FIELD_NAME_BY_UI_KEY[ui_key]
        result = api_get_master_key_by_app_id_field_name(
            field_name=field_name,
            token=self._token(),
        )
        rows = result.get("data") if result.get("success") else []
        prev_seq = combo.currentData() if combo.currentIndex() > 0 else None
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(f"Select {ui_key}…", None)
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                seq_val = master_key_row_seq_value(row)
                if seq_val is None:
                    continue
                label = master_key_row_display_label(row).strip()
                if not label:
                    continue
                combo.addItem(label, seq_val)
        if prev_seq is not None:
            idx = combo.findData(prev_seq)
            if idx < 0 and isinstance(prev_seq, int):
                idx = combo.findData(str(prev_seq))
            combo.setCurrentIndex(idx if idx >= 0 else 0)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _apply_mk_combo_from_record(self, ui_key: str) -> None:
        combo = self._mk_combo_by_key.get(ui_key)
        if combo is None:
            return
        keys = _DISPLAY_KEYS.get(ui_key, (ui_key,))
        seq = _master_seq_from_record(self._record, keys)
        if seq is None:
            combo.setCurrentIndex(0)
            return
        idx = combo.findData(seq)
        if idx < 0 and isinstance(seq, int):
            idx = combo.findData(str(seq))
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _update_email_style(self, widget: QLineEdit, text: str) -> None:
        base = (
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; padding: 4px 8px; border-radius: 4px;"
        )
        if not text.strip():
            widget.setStyleSheet(f"{base} border: 1px solid #e2e8f0; background-color: #ffffff;")
        elif _EMAIL_REGEX.match(text.strip()):
            widget.setStyleSheet(f"{base} border: 1px solid #22c55e; background-color: #ffffff;")
        else:
            widget.setStyleSheet(f"{base} border: 1px solid #ef4444; background-color: #ffffff;")

    def _update_mobile_row_style(self, country_combo: QComboBox, number_edit: QLineEdit) -> None:
        base = (
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; padding: 4px 8px; border-radius: 4px; "
            "background-color: #ffffff;"
        )
        number = number_edit.text().strip()
        country_code = country_combo.currentData() or "+91"
        if not number:
            number_edit.setStyleSheet(f"{base} border: 1px solid #e2e8f0;")
        else:
            valid, _ = validate_mobile(country_code, number)
            color = "#22c55e" if valid else "#ef4444"
            number_edit.setStyleSheet(f"{base} border: 1px solid {color};")

    def _token(self) -> str | None:
        p = get_user_profile()
        t = p.get("token") or p.get("accessToken") or p.get("access_token") or p.get("jwt")
        return str(t) if t else None

    def _apply_record_to_edits(self) -> None:
        rec = self._record
        for k, _, _ in _FIELDS:
            if k == "mobile":
                raw = _pick_display(rec, _DISPLAY_KEYS["mobile"])
                cc, nat = _split_stored_mobile(raw)
                if self._mobile_country is not None:
                    idx = self._mobile_country.findData(cc)
                    self._mobile_country.setCurrentIndex(idx if idx >= 0 else 0)
                if self._mobile_number is not None:
                    self._mobile_number.setText(nat)
                if self._mobile_country is not None and self._mobile_number is not None:
                    self._update_mobile_row_style(self._mobile_country, self._mobile_number)
            elif k == "hierarchy":
                h = _pick_display(rec, _DISPLAY_KEYS["hierarchy"])
                if self._hierarchy_combo is not None:
                    if h.isdigit():
                        idx = self._hierarchy_combo.findData(int(h))
                        self._hierarchy_combo.setCurrentIndex(idx if idx >= 0 else 0)
                    else:
                        self._hierarchy_combo.setCurrentIndex(0)
            elif k in _MK_COMBO_KEYS:
                self._apply_mk_combo_from_record(k)
            else:
                keys = _DISPLAY_KEYS.get(k, (k,))
                self._line_edits[k].setText(_pick_display(rec, keys))

    def set_contact_person(self, rec: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._record = dict(rec) if rec else {}
        self._refresh_edit_action_access()
        for ui_key in _MK_COMBO_KEYS:
            self._populate_mk_combo(ui_key)
        self._apply_record_to_edits()
        if edit_mode and self._record and self._can_edit_action:
            self._handle_edit()
        else:
            self._switch_view()

    def _refresh_edit_action_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_edit_action = True
        else:
            allowed = collect_allowed_action_names(steps)
            self._can_edit_action = nav_action_visible("Lead: Contact Person", "edit", allowed)
        self._edit.setEnabled(self._can_edit_action)
        self._edit.setToolTip("" if self._can_edit_action else "Require Permission.")

    def _switch_view(self) -> None:
        for k, _, ro in _FIELDS:
            if k == "mobile":
                if self._mobile_country is not None:
                    self._mobile_country.setEnabled(False)
                if self._mobile_number is not None:
                    self._mobile_number.setReadOnly(True)
                    self._mobile_number.setStyleSheet(READONLY_INPUT_STYLE)
                if self._mobile_country is not None and self._mobile_number is not None:
                    self._update_mobile_row_style(self._mobile_country, self._mobile_number)
            elif k == "hierarchy":
                if self._hierarchy_combo is not None:
                    self._hierarchy_combo.setEnabled(False)
            elif k in _MK_COMBO_KEYS:
                c = self._mk_combo_by_key.get(k)
                if c is not None:
                    c.setEnabled(False)
            else:
                self._line_edits[k].setReadOnly(True)
                self._line_edits[k].setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1

    def _show_error(self, m: str) -> None:
        show_auto_hiding_message(self, self._error, m, error=True)

    def _show_success(self, m: str) -> None:
        show_auto_hiding_message(self, self._error, m, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error)
        self._error.setText("")
        self._error.setVisible(False)

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _handle_edit(self) -> None:
        if not self._can_edit_action:
            self._show_error("Edit disabled: missing step access lead-contact-person-edit.")
            return
        self._clear_error()
        for k, _, ro in _FIELDS:
            if k == "mobile":
                if self._mobile_country is not None:
                    self._mobile_country.setEnabled(True)
                if self._mobile_number is not None:
                    self._mobile_number.setReadOnly(False)
                    self._mobile_number.setStyleSheet(INPUT_STYLE)
                if self._mobile_country is not None and self._mobile_number is not None:
                    self._update_mobile_row_style(self._mobile_country, self._mobile_number)
            elif k == "hierarchy":
                if self._hierarchy_combo is not None:
                    self._hierarchy_combo.setEnabled(True)
            elif k in _MK_COMBO_KEYS:
                c = self._mk_combo_by_key.get(k)
                if c is not None:
                    c.setEnabled(True)
            elif not ro:
                self._line_edits[k].setReadOnly(False)
                self._line_edits[k].setStyleSheet(INPUT_STYLE)
                if k == "email":
                    self._update_email_style(self._line_edits[k], self._line_edits[k].text())
        self._btn_stack.setCurrentIndex(1)

    def _handle_cancel(self) -> None:
        self._apply_record_to_edits()
        self._switch_view()

    def _record_person_id(self) -> Any:
        return self._record.get("contactId") or self._record.get("contactPersonId") or self._record.get("id")

    def _hierarchy_int_from_record(self) -> int | None:
        h = self._record.get("hierarchy")
        if h is None:
            return None
        s = str(h).strip()
        return int(s) if s.isdigit() else None

    def _require_master_combo_seq(self, combo: QComboBox | None, field_label: str) -> Any | None:
        """Same rule as :meth:`CreateContactPersonPage._require_master_combo_seq`."""
        if combo is None or combo.currentIndex() <= 0:
            self._show_error(f"{field_label} is required.")
            if combo is not None:
                combo.setFocus()
            return None
        data = combo.currentData()
        if data is None:
            self._show_error(f"{field_label} is required.")
            if combo is not None:
                combo.setFocus()
            return None
        return data

    def _handle_save(self) -> None:
        pid = self._record_person_id()
        if pid is None:
            self._show_error("Contact Person is missing.")
            return
        name = self._line_edits["name"].text().strip()
        if not name:
            self._show_error("Contact Person Name is required.")
            self._line_edits["name"].setFocus()
            return
        em = self._line_edits["email"].text().strip()
        if em and not _EMAIL_REGEX.match(em):
            self._show_error("Please enter a valid email address.")
            self._line_edits["email"].setFocus()
            return
        if self._mobile_number is not None and self._mobile_country is not None:
            raw = self._mobile_number.text().strip()
            if raw:
                country_code = str(self._mobile_country.currentData() or "+91").strip()
                valid, msg = validate_mobile(country_code, raw)
                if not valid:
                    self._show_error(msg)
                    self._mobile_number.setFocus()
                    return

        pos_seq = self._require_master_combo_seq(self._mk_combo_by_key.get("position"), "Position")
        if pos_seq is None:
            return
        country_seq = self._require_master_combo_seq(self._mk_combo_by_key.get("country"), "Country")
        if country_seq is None:
            return
        state_seq = self._require_master_combo_seq(self._mk_combo_by_key.get("state"), "State")
        if state_seq is None:
            return
        city_seq = self._require_master_combo_seq(self._mk_combo_by_key.get("city"), "City")
        if city_seq is None:
            return
        status_seq = self._require_master_combo_seq(self._mk_combo_by_key.get("status"), "Status")
        if status_seq is None:
            return

        payload: dict[str, str | int] = {}
        for k, _, ro in _FIELDS:
            if ro or k == "contactPersonId" or k in ("mobile", "hierarchy") or k in _MK_COMBO_KEYS:
                continue
            v = self._line_edits[k].text().strip()
            prev = _pick_display(self._record, _DISPLAY_KEYS.get(k, (k,)))
            if v != prev:
                payload[k] = v

        for mk_key in _MK_COMBO_KEYS:
            combo = self._mk_combo_by_key.get(mk_key)
            if combo is None or combo.currentIndex() <= 0:
                continue
            cur = combo.currentData()
            prev = _master_seq_from_record(self._record, _DISPLAY_KEYS.get(mk_key, (mk_key,)))
            if cur != prev:
                payload[mk_key] = cur

        if self._mobile_number is not None and self._mobile_country is not None:
            raw = self._mobile_number.text().strip()
            new_m = ""
            if raw:
                cc = str(self._mobile_country.currentData() or "+91").strip()
                new_m = self._full_contact_number(cc, raw)
            old_m = _pick_display(self._record, _DISPLAY_KEYS["mobile"])
            if new_m and new_m != old_m:
                payload["mobile"] = new_m

        if self._hierarchy_combo is not None:
            cur_h = self._hierarchy_combo.currentData()
            if isinstance(cur_h, int):
                rec_hi = self._hierarchy_int_from_record()
                effective_rec = 1 if rec_hi is None else rec_hi
                if cur_h != effective_rec:
                    payload["hierarchy"] = cur_h

        if not payload:
            self._show_error("No changes to update.")
            return
        res = api_update_contact_person(pid, payload, token=self._token())
        if not res.get("success"):
            self._show_error(str(res.get("message") or "Failed to update contact person."))
            return
        self._record.update(payload)
        self._apply_record_to_edits()
        self._switch_view()
        self._show_success(str(res.get("message") or "Contact person updated successfully."))
        schedule_after_success(
            delay_ms=600,
            clear_error=self._clear_error,
            reset=lambda: None,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )
