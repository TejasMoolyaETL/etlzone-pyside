"""View / edit DM: Company page."""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator, QShowEvent
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

from core.api import (
    api_update_dm_company,
    master_key_row_seq_value,
)
from core.world_locations_catalog import (
    geo_triple_from_company_record,
    load_world_locations_index,
    world_locations_available,
)
from core.app_preferences import format_datetime_display, is_datetime_field
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from core.validators import COUNTRY_CODES, validate_mobile
from ui.auto_hide_message import (
    cancel_auto_hide_message,
    show_api_result_message,
    show_auto_hiding_message,
)
from ui.blank_display import is_blank_display_value
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
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success
from ui.searchable_form_combo import (
    combo_resolved_item_data,
    combo_resolved_master_key_seq,
    master_key_invalid_typed_text,
    master_key_seq_for_payload,
    require_master_key_seq_for_payload,
    populate_master_key_by_field_name,
    reset_searchable_combo,
    set_searchable_combo_by_user_data,
    wire_searchable_master_key_combo,
)
from ui.world_location_cascade import (
    apply_world_location_selection,
    clear_world_location_inline_error,
    ensure_world_locations_cascade,
)
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label, labeled_field_block

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})
_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _coerce_master_seq_to_int(seq_val: Any) -> int:
    """Send master-key ``seq`` as integer in JSON (matches create company page)."""
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


_MK_FIELD_NAME_BY_UI_KEY: dict[str, str] = {
    "source": "lead_source",
    "city": "city",
    "state": "state",
    "country": "country",
    "status": "lead_company_status",
}

_MK_COMBO_KEYS: frozenset[str] = frozenset(_MK_FIELD_NAME_BY_UI_KEY.keys())

_COMPANY_FIELDS = (
    ("Company", ("companyId", "id")),
    ("Company Name*", ("companyName", "name")),
    ("Source*", ("source", "sourceSeq")),
    ("City*", ("city", "citySeq")),
    ("State*", ("state", "stateSeq")),
    ("Country*", ("country", "countrySeq")),
    ("Email 1", ("email1",)),
    ("Email 2", ("email2",)),
    ("Contact No 1", ("contactNo1",)),
    ("Contact No 2", ("contactNo2",)),
    ("Contact No 3", ("contactNo3",)),
    ("Comments", ("comments",)),
    ("Billing address", ("billingAddress",)),
    ("Industry*", ("industry", "indstry")),
    ("Status*", ("status", "statusSeq")),
    ("Website", ("website",)),
)

_READONLY_KEYS = frozenset({"companyId", "id"})


def _get_value(rec: dict[str, Any], keys: tuple[str, ...]) -> Any:
    flat = {k: v for k, v in rec.items() if k not in _HIDDEN_KEYS}
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


class ViewDmCompanyPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._company: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit] = {}
        self._mk_combo_by_key: dict[str, QComboBox] = {}
        self._mobile_rows: list[tuple[str, QComboBox, QLineEdit]] = []
        self._editable_keys: list[str] = []
        self._can_edit_action = True
        self._world_locations_mode = False
        self._world_geo_baseline: tuple[Any, Any, Any] = (None, None, None)
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
        hl.addWidget(QLabel("DM: Company Details"))
        hl.addStretch()
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
        card.setMaximumWidth(980)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        def new_section_grid() -> QGridLayout:
            grid = QGridLayout()
            grid.setHorizontalSpacing(24)
            grid.setVerticalSpacing(10)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            return grid

        def add_field(
            grid: QGridLayout,
            row: int,
            col: int,
            label_text: str,
            keys: tuple[str, ...],
            row_span: int = 1,
            col_span: int = 1,
        ) -> None:
            canonical = keys[0]
            if canonical not in _READONLY_KEYS:
                self._editable_keys.append(canonical)
            label_widget = field_caption_label(label_text, LABEL_STYLE)
            if canonical in _MK_COMBO_KEYS:
                combo = QComboBox()
                combo.setMinimumWidth(240)
                combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                apply_form_combobox_field(combo, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX)
                wire_searchable_master_key_combo(combo, search_field_label=canonical.title())
                self._mk_combo_by_key[canonical] = combo
                grid.addWidget(
                    labeled_field_block(label_widget, combo), row, col, row_span, col_span
                )
                return
            if canonical.startswith("contactNo"):
                container = QWidget()
                container.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
                row_lay = QHBoxLayout(container)
                row_lay.setContentsMargins(0, 0, 0, 0)
                row_lay.setSpacing(10)
                country = QComboBox()
                for code, country_name in COUNTRY_CODES:
                    country.addItem(f"{country_name} ({code})", code)
                apply_form_combobox_field(country, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX, min_width=120)
                number = QLineEdit()
                number.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\d*$")))
                number.setPlaceholderText(placeholder_example("9876543210"))
                number.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
                number.setMinimumWidth(120)
                number.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                country.currentIndexChanged.connect(
                    lambda _i, cc=country, num=number: self._update_mobile_row_style(cc, num)
                )
                number.textChanged.connect(
                    lambda _t, cc=country, num=number: self._update_mobile_row_style(cc, num)
                )
                row_lay.addWidget(country)
                row_lay.addWidget(number, 1)
                self._mobile_rows.append((canonical, country, number))
                self._field_edits[canonical] = number
                self._update_mobile_row_style(country, number)
                grid.addWidget(
                    labeled_field_block(label_widget, container), row, col, row_span, col_span
                )
                return
            value_edit = QLineEdit()
            value_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
            value_edit.setMinimumWidth(240)
            value_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            value_edit.setReadOnly(canonical in _READONLY_KEYS)
            value_edit.setStyleSheet(READONLY_INPUT_STYLE if canonical in _READONLY_KEYS else INPUT_STYLE)
            if canonical == "companyName":
                value_edit.setPlaceholderText(placeholder_example("Accenture 2"))
            elif canonical == "industry":
                value_edit.setPlaceholderText(placeholder_example("IT"))
            elif canonical == "email1":
                value_edit.setPlaceholderText(placeholder_example("hr@accenture.com"))
            elif canonical == "email2":
                value_edit.setPlaceholderText(placeholder_example("jobs@accenture.com"))
            elif canonical == "website":
                value_edit.setPlaceholderText(placeholder_example("websites"))
            elif canonical == "comments":
                value_edit.setPlaceholderText(placeholder_example("SAP migration project"))
            elif canonical == "billingAddress":
                value_edit.setPlaceholderText(placeholder_example("addresstext"))
            if canonical.startswith("email"):
                value_edit.textChanged.connect(lambda text, w=value_edit: self._update_email_style(w, text))
                self._update_email_style(value_edit, value_edit.text())
            self._field_edits[canonical] = value_edit
            grid.addWidget(
                labeled_field_block(label_widget, value_edit), row, col, row_span, col_span
            )

        fields_by_key: dict[str, tuple[str, tuple[str, ...]]] = {
            keys[0]: (label_text, keys) for (label_text, keys) in _COMPANY_FIELDS
        }

        basic_grid = new_section_grid()
        for row, left_key, right_key in (
            (0, "companyId", "companyName"),
            (1, "country", "state"),
            (2, "city", "source"),
            (3, "industry", "status"),
        ):
            left_label, left_keys = fields_by_key[left_key]
            add_field(basic_grid, row, 0, left_label, left_keys)
            right_label, right_keys = fields_by_key[right_key]
            add_field(basic_grid, row, 1, right_label, right_keys)
        card_layout.addLayout(basic_grid)
        self._location_hint_label = QLabel()
        self._location_hint_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._location_hint_label.setWordWrap(True)
        self._location_hint_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._location_hint_label.setVisible(False)
        card_layout.addWidget(self._location_hint_label)
        card_layout.addSpacing(4)

        contact_grid = new_section_grid()
        for row, left_key, right_key in (
            (0, "email1", "email2"),
            (1, "contactNo1", "contactNo2"),
            (2, "contactNo3", "website"),
        ):
            left_label, left_keys = fields_by_key[left_key]
            add_field(contact_grid, row, 0, left_label, left_keys)
            right_label, right_keys = fields_by_key[right_key]
            add_field(contact_grid, row, 1, right_label, right_keys)
        card_layout.addLayout(contact_grid)
        card_layout.addSpacing(4)

        additional_grid = new_section_grid()
        comments_label, comments_keys = fields_by_key["comments"]
        add_field(additional_grid, 0, 0, comments_label, comments_keys, col_span=2)
        billing_label, billing_keys = fields_by_key["billingAddress"]
        add_field(additional_grid, 1, 0, billing_label, billing_keys, col_span=2)
        card_layout.addLayout(additional_grid)

        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self._handle_back)
        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedWidth(100)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setStyleSheet(
            FORM_PRIMARY_BUTTON_STYLESHEET
            + " QPushButton:disabled {"
            + " background-color: #e5e7eb;"
            + " color: #6b7280;"
            + " border: 1px solid #cbd5e1;"
            + "}"
        )
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
        db = QHBoxLayout(display_btns)
        db.setContentsMargins(0, 0, 0, 0)
        db.setSpacing(12)
        db.setAlignment(Qt.AlignmentFlag.AlignLeft)
        db.addWidget(self._edit_btn)
        db.addWidget(self._back_btn)

        edit_btns = QWidget()
        edit_btns.setStyleSheet("background: transparent; border: none;")
        eb = QHBoxLayout(edit_btns)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.setSpacing(12)
        eb.setAlignment(Qt.AlignmentFlag.AlignLeft)
        eb.addWidget(self._save_btn)
        eb.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
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
        card_layout.addWidget(self._btn_stack, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        self._switch_to_view_mode()

    def _reload_reference_lists(self) -> None:
        self._world_locations_mode = world_locations_available()
        idx = load_world_locations_index() if self._world_locations_mode else None
        if self._world_locations_mode and idx is None:
            self._world_locations_mode = False
            idx = None
        for ui_key in _MK_COMBO_KEYS:
            if self._world_locations_mode and ui_key in ("country", "state", "city"):
                continue
            self._populate_mk_combo(ui_key)
        if self._world_locations_mode and idx is not None:
            cc = self._mk_combo_by_key.get("country")
            st = self._mk_combo_by_key.get("state")
            ci = self._mk_combo_by_key.get("city")
            if cc is not None and st is not None and ci is not None:
                ensure_world_locations_cascade(
                    cc,
                    st,
                    ci,
                    inline_error_label=self._location_hint_label,
                )
                gc, gs, gci = geo_triple_from_company_record(self._company, index=idx)
                self._world_geo_baseline = (gc, gs, gci)
                apply_world_location_selection(
                    cc,
                    st,
                    ci,
                    country_iso=gc,
                    state_code=gs,
                    city_geoname_id=gci,
                    index=idx,
                )
            else:
                self._world_geo_baseline = (None, None, None)
        else:
            self._world_geo_baseline = (None, None, None)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_edit_action_access()
        if not self._company:
            return
        self._reload_reference_lists()
        self._refresh_values()

    def set_company(self, company: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._company = dict(company) if company else {}
        self._refresh_edit_action_access()
        self._reload_reference_lists()
        self._refresh_values()
        if edit_mode and self._company and self._can_edit_action:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _refresh_edit_action_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_edit_action = True
        else:
            allowed_actions = collect_allowed_action_names(steps)
            self._can_edit_action = nav_action_visible(
                "DM: Company", "edit", allowed_actions
            )
        self._edit_btn.setEnabled(self._can_edit_action)
        self._edit_btn.setToolTip("" if self._can_edit_action else "Require Permission.")

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _refresh_values(self) -> None:
        for _label_text, keys in _COMPANY_FIELDS:
            canonical = keys[0]
            if canonical in _MK_COMBO_KEYS:
                if self._world_locations_mode and canonical in ("country", "state", "city"):
                    continue
                self._apply_mk_combo_from_record(canonical, keys)
                continue
            if canonical.startswith("contactNo"):
                raw = _format_value(_get_value(self._company, keys), keys[0], keys).strip()
                cc, nat = self._split_stored_mobile(raw)
                for m_key, country, number in self._mobile_rows:
                    if m_key != canonical:
                        continue
                    idx = country.findData(cc)
                    country.setCurrentIndex(idx if idx >= 0 else 0)
                    number.setText(nat)
                    self._update_mobile_row_style(country, number)
                continue
            value = _get_value(self._company, keys)
            text = _format_value(value, keys[0], keys)
            edit = self._field_edits.get(canonical)
            if edit:
                edit.setText(text)
                if canonical.startswith("email"):
                    self._update_email_style(edit, text)

    @staticmethod
    def _full_contact_number(country_code: str, national_digits: str) -> str:
        cc = str(country_code or "+91").strip()
        return f"{cc}{national_digits.strip()}"

    @staticmethod
    def _split_stored_mobile(raw: str) -> tuple[str, str]:
        s = (raw or "").strip()
        if not s:
            return "+91", ""
        if s.startswith("+"):
            for code, _ in sorted(COUNTRY_CODES, key=lambda x: len(x[0]), reverse=True):
                if s.startswith(code):
                    return code, s[len(code) :].lstrip()
        return "+91", s

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

    def _master_seq_from_record(self, keys: tuple[str, ...]) -> Any | None:
        for key in keys:
            v = self._company.get(key)
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

    def _populate_mk_combo(self, ui_key: str) -> None:
        combo = self._mk_combo_by_key.get(ui_key)
        if combo is None:
            return
        field_name = _MK_FIELD_NAME_BY_UI_KEY[ui_key]
        populate_master_key_by_field_name(
            combo,
            field_name,
            token=self._token(),
            include_placeholder=False,
        )

    def _apply_mk_combo_from_record(self, ui_key: str, keys: tuple[str, ...]) -> None:
        combo = self._mk_combo_by_key.get(ui_key)
        if combo is None:
            return
        seq = self._master_seq_from_record(keys)
        if seq is None:
            reset_searchable_combo(combo)
            return
        set_searchable_combo_by_user_data(combo, seq)

    def _show_error(self, message: str) -> None:
        # Validation handlers often set focus right after showing an error.
        # Keep the message visible instead of clearing on that focus change.
        show_auto_hiding_message(self, self._error_label, message, error=True, clear_on_user_activity=False)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)
        cmb = self._mk_combo_by_key.get("country")
        if cmb is not None:
            clear_world_location_inline_error(cmb)

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _handle_edit(self) -> None:
        if not self._can_edit_action:
            self._show_error("Require Permission.")
            return
        self._clear_error()
        for key in self._editable_keys:
            edit = self._field_edits.get(key)
            if edit:
                edit.setReadOnly(False)
                edit.setStyleSheet(INPUT_STYLE)
                if key.startswith("email"):
                    self._update_email_style(edit, edit.text())
        for key in _MK_COMBO_KEYS:
            combo = self._mk_combo_by_key.get(key)
            if combo is not None:
                combo.setEnabled(True)
        for _key, country, number in self._mobile_rows:
            country.setEnabled(True)
            number.setReadOnly(False)
            self._update_mobile_row_style(country, number)
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

    def _switch_to_view_mode(self) -> None:
        for _label_text, keys in _COMPANY_FIELDS:
            canonical = keys[0]
            edit = self._field_edits.get(canonical)
            if not edit:
                continue
            edit.setReadOnly(True)
            edit.setStyleSheet(READONLY_INPUT_STYLE)
            if canonical.startswith("email"):
                self._update_email_style(edit, edit.text())
        for key in _MK_COMBO_KEYS:
            combo = self._mk_combo_by_key.get(key)
            if combo is not None:
                combo.setEnabled(False)
        cmb = self._mk_combo_by_key.get("country")
        if cmb is not None:
            clear_world_location_inline_error(cmb)
        for _key, country, number in self._mobile_rows:
            country.setEnabled(False)
            number.setReadOnly(True)
            self._update_mobile_row_style(country, number)
        self._btn_stack.setCurrentIndex(0)

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1

    @staticmethod
    def _norm_geo_part(x: Any) -> str:
        if x is None:
            return ""
        return str(x).strip()

    def _current_world_geo_triple(self) -> tuple[str, str, str]:
        c = self._mk_combo_by_key.get("country")
        s = self._mk_combo_by_key.get("state")
        t = self._mk_combo_by_key.get("city")
        return (
            self._norm_geo_part(combo_resolved_item_data(c)),
            self._norm_geo_part(combo_resolved_item_data(s)),
            self._norm_geo_part(combo_resolved_item_data(t)),
        )

    def _baseline_world_geo_triple(self) -> tuple[str, str, str]:
        a, b, c = self._world_geo_baseline
        return (self._norm_geo_part(a), self._norm_geo_part(b), self._norm_geo_part(c))

    def _has_unsaved_changes(self) -> bool:
        for _label_text, keys in _COMPANY_FIELDS:
            canonical = keys[0]
            if canonical in _MK_COMBO_KEYS:
                if self._world_locations_mode and canonical in ("country", "state", "city"):
                    if canonical != "country":
                        continue
                    if self._current_world_geo_triple() != self._baseline_world_geo_triple():
                        return True
                    continue
                combo = self._mk_combo_by_key.get(canonical)
                cur = combo_resolved_master_key_seq(combo) if combo is not None else None
                prev = self._master_seq_from_record(keys)
                if cur != prev:
                    return True
                continue
            if canonical.startswith("contactNo"):
                for m_key, country, number in self._mobile_rows:
                    if m_key != canonical:
                        continue
                    new_m = ""
                    raw = number.text().strip()
                    if raw:
                        cc = str(country.currentData() or "+91").strip()
                        new_m = self._full_contact_number(cc, raw)
                    old_m = _format_value(_get_value(self._company, keys), keys[0], keys).strip()
                    if new_m != old_m:
                        return True
                continue
            if canonical in _READONLY_KEYS:
                continue
            current = self._field_edits.get(canonical).text().strip() if self._field_edits.get(canonical) else ""
            original = _format_value(_get_value(self._company, keys), keys[0], keys).strip()
            if current != original:
                return True
        return False

    def _handle_save(self) -> None:
        company_id = self._company.get("companyId") or self._company.get("id")
        if company_id is None:
            self._show_error("Company is missing.")
            return
        name_edit = self._field_edits.get("companyName")
        company_name = name_edit.text().strip() if name_edit else ""
        if not company_name:
            self._show_error("Company Name is required.")
            if name_edit is not None:
                name_edit.setFocus()
            return
        country_combo = self._mk_combo_by_key.get("country")
        if country_combo is None:
            self._show_error("Country is required.")
            return
        state_combo = self._mk_combo_by_key.get("state")
        city_combo = self._mk_combo_by_key.get("city")
        if self._world_locations_mode:
            country_raw = combo_resolved_item_data(country_combo)
            state_raw = combo_resolved_item_data(state_combo) if state_combo else None
            city_raw = combo_resolved_item_data(city_combo) if city_combo else None
        else:
            country_raw = combo_resolved_master_key_seq(country_combo)
            state_raw = combo_resolved_master_key_seq(state_combo) if state_combo else None
            city_raw = combo_resolved_master_key_seq(city_combo) if city_combo else None
        if country_raw is None or not str(country_raw).strip():
            typed = (country_combo.currentText() or "").strip()
            if typed:
                self._show_error(strict_list_selection_message("a country"))
            else:
                self._show_error("Country is required.")
            country_combo.setFocus()
            return
        if state_combo is None:
            self._show_error("State is required.")
            return
        if state_raw is None or not str(state_raw).strip():
            typed = (state_combo.currentText() or "").strip() if state_combo else ""
            if typed:
                self._show_error(strict_list_selection_message("a state"))
            else:
                self._show_error("State is required.")
            state_combo.setFocus()
            return
        if city_combo is None:
            self._show_error("City is required.")
            return
        if city_raw is None or not str(city_raw).strip():
            typed = (city_combo.currentText() or "").strip() if city_combo else ""
            if typed:
                self._show_error(strict_list_selection_message("a city"))
            else:
                self._show_error("City is required.")
            city_combo.setFocus()
            return
        source_combo = self._mk_combo_by_key.get("source")
        if source_combo is None:
            self._show_error("Source is required.")
            return
        source_id, source_err = require_master_key_seq_for_payload(
            source_combo, field_caption="Source", strict_phrase="a source"
        )
        if source_err:
            self._show_error(source_err)
            source_combo.setFocus()
            return
        for em_key in ("email1", "email2"):
            edit = self._field_edits.get(em_key)
            em = edit.text().strip() if edit is not None else ""
            if em and not _EMAIL_REGEX.match(em):
                self._show_error("Please enter a valid email address.")
                if edit is not None:
                    edit.setFocus()
                return
        for key, country, number in self._mobile_rows:
            raw = number.text().strip()
            if not raw:
                continue
            country_code = str(country.currentData() or "+91").strip()
            valid, msg = validate_mobile(country_code, raw)
            if not valid:
                self._show_error(msg)
                number.setFocus()
                return
        ind_edit = self._field_edits.get("industry")
        industry_val = ind_edit.text().strip() if ind_edit else ""
        if not industry_val:
            self._show_error("Industry is required.")
            if ind_edit is not None:
                ind_edit.setFocus()
            return
        status_combo = self._mk_combo_by_key.get("status")
        if status_combo is None:
            self._show_error("Status is required.")
            return
        status_id, status_err = require_master_key_seq_for_payload(
            status_combo, field_caption="Status", strict_phrase="a status"
        )
        if status_err:
            self._show_error(status_err)
            status_combo.setFocus()
            return
        if self._world_locations_mode:
            s_city = str(city_raw).strip()
            if not s_city.isdigit():
                self._show_error("City must be a valid selection from the list.")
                return
            idx = load_world_locations_index()
            if idx is None:
                self._show_error(
                    "Location data is unavailable. Run: python scripts/build_world_cities_json.py"
                )
                return
            api_country, api_state, api_city = idx.display_names_for_api(
                str(country_raw).strip().upper(),
                str(state_raw).strip(),
                s_city,
            )
            payload = {
                "companyName": company_name,
                "country": api_country,
                "state": api_state,
                "city": api_city,
                "source": source_id,
                "industry": industry_val,
                "status": status_id,
            }
        else:
            try:
                country_id = _coerce_master_seq_to_int(country_raw)
                city_id = _coerce_master_seq_to_int(city_raw)
                state_id = _coerce_master_seq_to_int(state_raw)
            except ValueError:
                self._show_error("Country, city, and state must be valid selections.")
                return
            payload = {
                "companyName": company_name,
                "country": country_id,
                "city": city_id,
                "state": state_id,
                "source": source_id,
                "industry": industry_val,
                "status": status_id,
            }
        for _label_text, keys in _COMPANY_FIELDS:
            canonical = keys[0]
            if canonical in _READONLY_KEYS or canonical in _MK_COMBO_KEYS or canonical.startswith("contactNo"):
                continue
            if canonical in ("companyName", "industry"):
                continue
            val = self._field_edits.get(canonical).text().strip() if self._field_edits.get(canonical) else ""
            if not val:
                continue
            payload[canonical] = val
        for key, country, number in self._mobile_rows:
            raw = number.text().strip()
            if not raw:
                continue
            cc = str(country.currentData() or "+91").strip()
            payload[key] = self._full_contact_number(cc, raw)

        result = api_update_dm_company(company_id, payload, token=self._token())
        ok = show_api_result_message(
            self,
            self._error_label,
            result,
            error_fallback="Failed to update company.",
            success_fallback="Company updated successfully.",
        )
        if not ok:
            return
        self._company.update(payload)
        if self._world_locations_mode:
            widx = load_world_locations_index()
            if widx is not None:
                self._world_geo_baseline = geo_triple_from_company_record(self._company, index=widx)
        self._refresh_values()
        self._switch_to_view_mode()
        schedule_after_success(
            delay_ms=600,
            clear_error=self._clear_error,
            reset=lambda: None,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )
