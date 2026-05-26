"""Create Lead Contact Person page."""

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
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.api import api_create_dm_contact_person
from core.world_locations_catalog import load_world_locations_index
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
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    MODAL_FIELD_HEIGHT_PX,
    placeholder_example,
)
from ui.post_save_navigation import schedule_after_success
from ui.searchable_form_combo import (
    combo_resolved_item_data,
    combo_resolved_master_key_seq,
    master_key_invalid_typed_text,
    master_key_seq_for_payload,
    reference_id_for_payload,
    require_master_key_seq_for_payload,
    populate_master_key_by_field_name,
    reset_searchable_combo,
    wire_searchable_labeled_rows_combo,
    wire_searchable_master_key_combo,
)
from ui.world_location_cascade import (
    clear_world_location_inline_error,
    ensure_world_locations_cascade,
    reset_world_locations_cascading,
)
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label, labeled_field_block

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Master-key ``fieldName`` values (``api/master-setup/master-config/get-by-field-name``).
_LEAD_CONTACT_POSITION_FIELD_NAME = "lead_contact_person_position"
_MASTER_KEY_COUNTRY_FIELD_NAME = "country"
_MASTER_KEY_STATE_FIELD_NAME = "state"
_MASTER_KEY_CITY_FIELD_NAME = "city"
_LEAD_CONTACT_PERSON_STATUS_FIELD_NAME = "lead_contact_person_status"


def _coerce_master_seq_to_int(seq_val: Any) -> int:
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


class CreateDmContactPersonPage(QWidget):
    def __init__(self, on_back: Callable[[], None] | None = None, on_create_success: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._can_create = True
        self._edits: dict[str, QLineEdit] = {}
        self._position_combo: QComboBox | None = None
        self._master_country_combo: QComboBox | None = None
        self._master_state_combo: QComboBox | None = None
        self._master_city_combo: QComboBox | None = None
        self._master_status_combo: QComboBox | None = None
        self._mobile_country: QComboBox | None = None
        self._mobile_number: QLineEdit | None = None
        self._hierarchy_combo: QComboBox | None = None
        self._world_locations_mode = False
        self._build_ui()

    @staticmethod
    def _full_contact_number(country_code: str, national_digits: str) -> str:
        cc = str(country_code or "+91").strip()
        return f"{cc}{national_digits.strip()}"

    def _add_master_key_combo(
        self,
        grid: QGridLayout,
        *,
        row: int,
        col: int,
        label: str,
        h: int,
        search_field_label: str,
    ) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumWidth(260)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(combo, height_px=h)
        wire_searchable_master_key_combo(combo, search_field_label=search_field_label)
        grid.addWidget(labeled_field_block(field_caption_label(label, LABEL_STYLE), combo), row, col)
        return combo

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QWidget()
        header.setStyleSheet(FORM_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("DM: Create Contact Person"))
        hl.addStretch()
        back = QPushButton("Back")
        back.setFixedWidth(100)
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self._handle_back)
        hl.addWidget(back)
        layout.addWidget(header)
        content = QWidget()
        cl = QVBoxLayout(content)
        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card.setMaximumWidth(920)
        card.setStyleSheet("#profileCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }")
        card_layout = QVBoxLayout(card)

        def new_section_grid() -> QGridLayout:
            grid = QGridLayout()
            grid.setHorizontalSpacing(24)
            grid.setVerticalSpacing(10)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            return grid

        h = MODAL_FIELD_HEIGHT_PX

        def add_text(
            grid: QGridLayout, *, key: str, label: str, placeholder: str, row: int, col: int
        ) -> None:
            e = QLineEdit()
            e.setPlaceholderText(placeholder_example(placeholder))
            e.setStyleSheet(INPUT_STYLE)
            e.setFixedHeight(h)
            e.setMinimumWidth(260)
            e.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if key == "email":
                e.textChanged.connect(lambda text, w=e: self._update_email_style(w, text))
                self._update_email_style(e, e.text())
            self._edits[key] = e
            grid.addWidget(
                labeled_field_block(field_caption_label(label, LABEL_STYLE), e), row, col
            )
        basic_grid = new_section_grid()
        add_text(
            basic_grid,
            key="name",
            label="Contact Person Name*",
            placeholder="John Smith",
            row=0,
            col=0,
        )
        add_text(
            basic_grid,
            key="email",
            label="Email",
            placeholder="john@test.com",
            row=0,
            col=1,
        )
        self._position_combo = self._add_master_key_combo(
            basic_grid, row=1, col=0, label="Position*", h=h, search_field_label="Position"
        )
        self._master_status_combo = self._add_master_key_combo(
            basic_grid, row=1, col=1, label="Status*", h=h, search_field_label="Status"
        )
        card_layout.addLayout(basic_grid)
        card_layout.addSpacing(4)

        mobile_container = QWidget()
        mobile_container.setFixedHeight(h)
        mlay = QHBoxLayout(mobile_container)
        mlay.setContentsMargins(0, 0, 0, 0)
        mlay.setSpacing(10)
        country = QComboBox()
        for code, country_name in COUNTRY_CODES:
            country.addItem(f"{country_name} ({code})", code)
        apply_form_combobox_field(country, height_px=h, min_width=120)
        number = QLineEdit()
        number.setValidator(QRegularExpressionValidator(QRegularExpression(r"^\d*$")))
        number.setStyleSheet(INPUT_STYLE)
        number.setFixedHeight(h)
        number.setMinimumWidth(120)
        number.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        number.setPlaceholderText(placeholder_example("9876543210"))
        country.currentIndexChanged.connect(lambda _i, cc=country, num=number: self._update_mobile_row_style(cc, num))
        number.textChanged.connect(lambda _t, cc=country, num=number: self._update_mobile_row_style(cc, num))
        mlay.addWidget(country)
        mlay.addWidget(number, 1)
        self._mobile_country = country
        self._mobile_number = number
        self._update_mobile_row_style(country, number)
        contact_grid = new_section_grid()
        contact_grid.addWidget(
            labeled_field_block(field_caption_label("Mobile", LABEL_STYLE), mobile_container),
            0,
            0,
        )

        self._master_country_combo = self._add_master_key_combo(
            contact_grid, row=0, col=1, label="Country*", h=h, search_field_label="Country"
        )
        self._master_state_combo = self._add_master_key_combo(
            contact_grid, row=1, col=0, label="State*", h=h, search_field_label="State"
        )
        self._master_city_combo = self._add_master_key_combo(
            contact_grid, row=1, col=1, label="City*", h=h, search_field_label="City"
        )

        hierarchy_combo = QComboBox()
        apply_form_combobox_field(hierarchy_combo, height_px=h, min_width=120)
        wire_searchable_labeled_rows_combo(
            hierarchy_combo,
            rows=[(str(n), n) for n in range(1, 21)],
            search_field_label="Hierarchy",
            default_display_text="1",
        )
        self._hierarchy_combo = hierarchy_combo
        contact_grid.addWidget(
            labeled_field_block(field_caption_label("Hierarchy", LABEL_STYLE), hierarchy_combo),
            2,
            0,
        )
        card_layout.addLayout(contact_grid)
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

        additional_grid = new_section_grid()
        add_text(
            additional_grid,
            key="url",
            label="URL / profile",
            placeholder="linkedin.com/john",
            row=0,
            col=0,
        )
        additional_grid.setColumnStretch(0, 1)
        additional_grid.setColumnStretch(1, 0)
        card_layout.addLayout(additional_grid)
        self.error_label = QLabel()
        self.error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)
        card_layout.addWidget(self.error_label)
        br = QHBoxLayout()
        self._create_btn = QPushButton("Create")
        self._create_btn.setFixedWidth(100)
        self._create_btn.setStyleSheet(
            FORM_PRIMARY_BUTTON_STYLESHEET
            + " QPushButton:disabled {"
            + " background-color: #e5e7eb;"
            + " color: #6b7280;"
            + " border: 1px solid #cbd5e1;"
            + "}"
        )
        self._create_btn.clicked.connect(self._handle_create)
        cancel = QPushButton("Cancel")
        cancel.setFixedWidth(100)
        cancel.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        cancel.clicked.connect(self._handle_back)
        br.addWidget(self._create_btn)
        br.addWidget(cancel)
        br.addStretch()
        card_layout.addLayout(br)
        cl.addWidget(card)
        cl.addStretch()
        layout.addWidget(content)

    def _refresh_create_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_create = True
        else:
            allowed = collect_allowed_action_names(steps)
            self._can_create = nav_action_visible("DM: Contact Person", "create", allowed)
        self._create_btn.setEnabled(self._can_create)
        self._create_btn.setToolTip("" if self._can_create else "Require Permission.")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_create_access()
        populate_master_key_by_field_name(
            self._position_combo,
            _LEAD_CONTACT_POSITION_FIELD_NAME,
            token=self._token(),
            include_placeholder=False,
        )
        self._world_locations_mode = bool(
            self._master_country_combo
            and self._master_state_combo
            and self._master_city_combo
            and ensure_world_locations_cascade(
                self._master_country_combo,
                self._master_state_combo,
                self._master_city_combo,
                inline_error_label=self._location_hint_label,
            )
        )
        if not self._world_locations_mode:
            populate_master_key_by_field_name(
                self._master_country_combo,
                _MASTER_KEY_COUNTRY_FIELD_NAME,
                token=self._token(),
                include_placeholder=False,
            )
            populate_master_key_by_field_name(
                self._master_state_combo,
                _MASTER_KEY_STATE_FIELD_NAME,
                token=self._token(),
                include_placeholder=False,
            )
            populate_master_key_by_field_name(
                self._master_city_combo,
                _MASTER_KEY_CITY_FIELD_NAME,
                token=self._token(),
                include_placeholder=False,
            )
        populate_master_key_by_field_name(
            self._master_status_combo,
            _LEAD_CONTACT_PERSON_STATUS_FIELD_NAME,
            token=self._token(),
            include_placeholder=False,
        )

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

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)
        if self._master_country_combo is not None:
            clear_world_location_inline_error(self._master_country_combo)

    def _show_error(self, msg: str) -> None:
        # Keep validation errors visible even when focus is moved to invalid field.
        show_auto_hiding_message(self, self.error_label, msg, error=True, clear_on_user_activity=False)

    def _show_success(self, msg: str) -> None:
        show_auto_hiding_message(self, self.error_label, msg, error=False)

    def is_dirty(self) -> bool:
        if any(e.text().strip() for e in self._edits.values()):
            return True
        if self._world_locations_mode:
            for c in (
                self._master_country_combo,
                self._master_state_combo,
                self._master_city_combo,
            ):
                if c is not None:
                    data = combo_resolved_item_data(c)
                    if data is not None and str(data).strip() != "":
                        return True
        else:
            for c in (
                self._master_country_combo,
                self._master_state_combo,
                self._master_city_combo,
            ):
                if c is not None:
                    data = combo_resolved_master_key_seq(c)
                    if data is not None and str(data).strip() != "":
                        return True
        for c in (self._position_combo, self._master_status_combo):
            if c is not None:
                data = combo_resolved_master_key_seq(c)
                if data is not None and str(data).strip() != "":
                    return True
        if self._mobile_number and self._mobile_number.text().strip():
            return True
        if self._mobile_country and self._mobile_country.currentIndex() != 0:
            return True
        if self._hierarchy_combo and reference_id_for_payload(self._hierarchy_combo) is not None:
            return True
        return False

    def reset_to_default(self) -> None:
        for e in self._edits.values():
            e.clear()
        if self._position_combo is not None:
            reset_searchable_combo(self._position_combo)
        if (
            self._world_locations_mode
            and self._master_country_combo
            and self._master_state_combo
            and self._master_city_combo
        ):
            reset_world_locations_cascading(
                self._master_country_combo,
                self._master_state_combo,
                self._master_city_combo,
            )
        else:
            for c in (
                self._master_country_combo,
                self._master_state_combo,
                self._master_city_combo,
            ):
                reset_searchable_combo(c)
        if self._master_status_combo is not None:
            reset_searchable_combo(self._master_status_combo)
        if self._mobile_country is not None:
            self._mobile_country.blockSignals(True)
            self._mobile_country.setCurrentIndex(0)
            self._mobile_country.blockSignals(False)
        if self._mobile_number is not None:
            self._mobile_number.clear()
        if self._mobile_country is not None and self._mobile_number is not None:
            self._update_mobile_row_style(self._mobile_country, self._mobile_number)
        if self._hierarchy_combo is not None:
            self._hierarchy_combo.setCurrentIndex(0)
        em = self._edits.get("email")
        if em is not None:
            self._update_email_style(em, em.text())
        self._clear_error()

    def _handle_back(self) -> None:
        if not self.is_dirty():
            if self.on_back:
                self.on_back()
            return
        if QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard and leave?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        ) == QMessageBox.StandardButton.Discard:
            self.reset_to_default()
            if self.on_back:
                self.on_back()

    def _handle_create(self) -> None:
        if not self._can_create:
            self._show_error("Create disabled: missing step access dm-contact-person-create.")
            return
        self._clear_error()
        name = self._edits["name"].text().strip()
        if not name:
            self._show_error("Contact Person Name is required.")
            self._edits["name"].setFocus()
            return
        em = self._edits["email"].text().strip()
        if em and not _EMAIL_REGEX.match(em):
            self._show_error("Please enter a valid email address.")
            self._edits["email"].setFocus()
            return
        if self._mobile_number and self._mobile_country:
            raw = self._mobile_number.text().strip()
            if raw:
                country_code = str(self._mobile_country.currentData() or "+91").strip()
                valid, msg = validate_mobile(country_code, raw)
                if not valid:
                    self._show_error(msg)
                    self._mobile_number.setFocus()
                    return

        pos_id, pos_err = require_master_key_seq_for_payload(
            self._position_combo, field_caption="Position", strict_phrase="a position"
        )
        if pos_err:
            self._show_error(pos_err)
            if self._position_combo is not None:
                self._position_combo.setFocus()
            return
        if self._world_locations_mode:
            country_raw = combo_resolved_item_data(self._master_country_combo)
            state_raw = combo_resolved_item_data(self._master_state_combo)
            city_raw = combo_resolved_item_data(self._master_city_combo)
        else:
            country_raw = combo_resolved_master_key_seq(self._master_country_combo)
            state_raw = combo_resolved_master_key_seq(self._master_state_combo)
            city_raw = combo_resolved_master_key_seq(self._master_city_combo)
        if country_raw is None or not str(country_raw).strip():
            typed = (
                (self._master_country_combo.currentText() or "").strip()
                if self._master_country_combo is not None
                else ""
            )
            if typed:
                self._show_error(strict_list_selection_message("a country"))
            else:
                self._show_error("Country is required.")
            if self._master_country_combo is not None:
                self._master_country_combo.setFocus()
            return
        if state_raw is None or not str(state_raw).strip():
            typed = (
                (self._master_state_combo.currentText() or "").strip()
                if self._master_state_combo is not None
                else ""
            )
            if typed:
                self._show_error(strict_list_selection_message("a state"))
            else:
                self._show_error("State is required.")
            if self._master_state_combo is not None:
                self._master_state_combo.setFocus()
            return
        if city_raw is None or not str(city_raw).strip():
            typed = (
                (self._master_city_combo.currentText() or "").strip()
                if self._master_city_combo is not None
                else ""
            )
            if typed:
                self._show_error(strict_list_selection_message("a city"))
            else:
                self._show_error("City is required.")
            if self._master_city_combo is not None:
                self._master_city_combo.setFocus()
            return
        status_id, status_err = require_master_key_seq_for_payload(
            self._master_status_combo, field_caption="Status", strict_phrase="a status"
        )
        if status_err:
            self._show_error(status_err)
            if self._master_status_combo is not None:
                self._master_status_combo.setFocus()
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
            payload: dict[str, str | int] = {
                "name": name,
                "position": pos_id,
                "country": api_country,
                "state": api_state,
                "city": api_city,
                "status": status_id,
            }
        else:
            try:
                country_id = _coerce_master_seq_to_int(country_raw)
                state_id = _coerce_master_seq_to_int(state_raw)
                city_id = _coerce_master_seq_to_int(city_raw)
            except ValueError:
                self._show_error("Country, city, and state must be valid selections.")
                return
            payload = {
                "name": name,
                "position": pos_id,
                "country": country_id,
                "state": state_id,
                "city": city_id,
                "status": status_id,
            }
        for k, e in self._edits.items():
            if k == "name":
                continue
            v = e.text().strip()
            if not v:
                continue
            payload[k] = v
        if self._mobile_number and self._mobile_country:
            raw = self._mobile_number.text().strip()
            if raw:
                cc = str(self._mobile_country.currentData() or "+91").strip()
                payload["mobile"] = self._full_contact_number(cc, raw)
        if self._hierarchy_combo is not None:
            hier = reference_id_for_payload(self._hierarchy_combo)
            if hier is not None:
                payload["hierarchy"] = hier

        result = api_create_dm_contact_person(payload, token=self._token())
        if result.get("success"):
            self._show_success(str(result.get("message") or "Contact person created successfully."))
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(str(result.get("message") or "Failed to create contact person."))
