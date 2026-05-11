"""Create Lead Contact Person page."""

from __future__ import annotations

import re
from typing import Callable

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

from core.api import (
    api_create_contact_person,
    api_get_master_key_by_app_id_field_name,
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
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    MODAL_FIELD_HEIGHT_PX,
    placeholder_example,
)
from ui.post_save_navigation import schedule_after_success
from ui.widgets.required_label import field_caption_label, labeled_field_block

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Master-key ``fieldName`` values (``api/master-setup/master-config/get-by-field-name``).
_LEAD_CONTACT_POSITION_FIELD_NAME = "lead_contact_person_position"
_MASTER_KEY_COUNTRY_FIELD_NAME = "country"
_MASTER_KEY_STATE_FIELD_NAME = "state"
_MASTER_KEY_CITY_FIELD_NAME = "city"
_LEAD_CONTACT_PERSON_STATUS_FIELD_NAME = "lead_contact_person_status"

class CreateContactPersonPage(QWidget):
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
        self._build_ui()

    @staticmethod
    def _full_contact_number(country_code: str, national_digits: str) -> str:
        cc = str(country_code or "+91").strip()
        return f"{cc}{national_digits.strip()}"

    def _add_master_key_combo(self, grid: QGridLayout, *, row: int, col: int, label: str, h: int) -> QComboBox:
        combo = QComboBox()
        combo.setMinimumWidth(260)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(combo, height_px=h)
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
        hl.addWidget(QLabel("Create Contact Person"))
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
            basic_grid, row=1, col=0, label="Position*", h=h
        )
        self._master_status_combo = self._add_master_key_combo(
            basic_grid, row=1, col=1, label="Status*", h=h
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
            contact_grid, row=0, col=1, label="Country*", h=h
        )
        self._master_state_combo = self._add_master_key_combo(
            contact_grid, row=1, col=0, label="State*", h=h
        )
        self._master_city_combo = self._add_master_key_combo(
            contact_grid, row=1, col=1, label="City*", h=h
        )

        hierarchy_combo = QComboBox()
        apply_form_combobox_field(hierarchy_combo, height_px=h, min_width=120)
        for n in range(1, 21):
            hierarchy_combo.addItem(str(n), n)
        hierarchy_combo.setCurrentIndex(0)
        self._hierarchy_combo = hierarchy_combo
        contact_grid.addWidget(
            labeled_field_block(field_caption_label("Hierarchy", LABEL_STYLE), hierarchy_combo),
            2,
            0,
        )
        card_layout.addLayout(contact_grid)
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
            self._can_create = nav_action_visible("Lead: Contact Person", "create", allowed)
        self._create_btn.setEnabled(self._can_create)
        self._create_btn.setToolTip("" if self._can_create else "Require Permission.")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_create_access()
        self._populate_master_key_seq_combo(
            self._position_combo,
            _LEAD_CONTACT_POSITION_FIELD_NAME,
            "Select position…",
        )
        self._populate_master_key_seq_combo(
            self._master_country_combo,
            _MASTER_KEY_COUNTRY_FIELD_NAME,
            "Select country…",
        )
        self._populate_master_key_seq_combo(
            self._master_state_combo,
            _MASTER_KEY_STATE_FIELD_NAME,
            "Select state…",
        )
        self._populate_master_key_seq_combo(
            self._master_city_combo,
            _MASTER_KEY_CITY_FIELD_NAME,
            "Select city…",
        )
        self._populate_master_key_seq_combo(
            self._master_status_combo,
            _LEAD_CONTACT_PERSON_STATUS_FIELD_NAME,
            "Select status…",
        )

    def _populate_master_key_seq_combo(
        self,
        combo: QComboBox | None,
        field_name: str,
        placeholder: str,
    ) -> None:
        """Load master-key rows: label ``seq | keyValue``, ``userData`` = seq for API (same as company Source)."""
        if combo is None:
            return
        result = api_get_master_key_by_app_id_field_name(
            field_name=field_name,
            token=self._token(),
        )
        rows = result.get("data") if result.get("success") else []
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(placeholder, None)
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
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

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

    def _show_error(self, msg: str) -> None:
        # Keep validation errors visible even when focus is moved to invalid field.
        show_auto_hiding_message(self, self.error_label, msg, error=True, clear_on_user_activity=False)

    def _show_success(self, msg: str) -> None:
        show_auto_hiding_message(self, self.error_label, msg, error=False)

    def _master_combo_dirty(self, combo: QComboBox | None) -> bool:
        return combo is not None and combo.currentIndex() > 0

    def is_dirty(self) -> bool:
        if any(e.text().strip() for e in self._edits.values()):
            return True
        for c in (
            self._position_combo,
            self._master_country_combo,
            self._master_state_combo,
            self._master_city_combo,
            self._master_status_combo,
        ):
            if self._master_combo_dirty(c):
                return True
        if self._mobile_number and self._mobile_number.text().strip():
            return True
        if self._mobile_country and self._mobile_country.currentIndex() != 0:
            return True
        if self._hierarchy_combo and self._hierarchy_combo.currentIndex() != 0:
            return True
        return False

    def reset_to_default(self) -> None:
        for e in self._edits.values():
            e.clear()
        for c in (
            self._position_combo,
            self._master_country_combo,
            self._master_state_combo,
            self._master_city_combo,
            self._master_status_combo,
        ):
            if c is not None:
                c.setCurrentIndex(0)
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

    def _require_master_combo_seq(
        self,
        combo: QComboBox | None,
        field_label: str,
    ) -> Any | None:
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

    def _handle_create(self) -> None:
        if not self._can_create:
            self._show_error("Create disabled: missing step access lead-contact-person-create.")
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

        pos_seq = self._require_master_combo_seq(self._position_combo, "Position")
        if pos_seq is None:
            return
        country_seq = self._require_master_combo_seq(self._master_country_combo, "Country")
        if country_seq is None:
            return
        state_seq = self._require_master_combo_seq(self._master_state_combo, "State")
        if state_seq is None:
            return
        city_seq = self._require_master_combo_seq(self._master_city_combo, "City")
        if city_seq is None:
            return
        status_seq = self._require_master_combo_seq(self._master_status_combo, "Status")
        if status_seq is None:
            return

        payload: dict[str, str | int] = {
            "name": name,
            "position": pos_seq,
            "country": country_seq,
            "state": state_seq,
            "city": city_seq,
            "status": status_seq,
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
            hd = self._hierarchy_combo.currentData()
            if hd is not None:
                payload["hierarchy"] = int(hd)

        result = api_create_contact_person(payload, token=self._token())
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
