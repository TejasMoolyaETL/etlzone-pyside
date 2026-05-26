"""Create DM: Company page."""

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

from core.api import api_create_dm_company
from core.world_locations_catalog import load_world_locations_index
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from core.validators import COUNTRY_CODES, validate_mobile
from ui.auto_hide_message import (
    cancel_auto_hide_message,
    show_api_result_message,
    show_auto_hiding_message,
)
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
    require_master_key_seq_for_payload,
    populate_master_key_by_field_name,
    reset_searchable_combo,
    wire_searchable_master_key_combo,
)
from ui.world_location_cascade import (
    clear_world_location_inline_error,
    ensure_world_locations_cascade,
    reset_world_locations_cascading,
)
from ui.strict_completer import strict_list_selection_message
from ui.theme import Theme
from ui.widgets.required_label import field_caption_label, labeled_field_block

_LEAD_SOURCE_FIELD_NAME = "lead_source"
# Master-key ``fieldName`` query params for ``api_get_master_key_by_app_id_field_name``.
_CITY_FIELD_NAME = "city"
_STATE_FIELD_NAME = "state"
_COUNTRY_FIELD_NAME = "country"
_STATUS_FIELD_NAME = "lead_company_status"

_EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
def _coerce_master_seq_to_int(seq_val: Any) -> int:
    """Send master-key ``seq`` as integer in JSON (matches ``country`` / ``city`` / ``state`` / ``source`` / ``status``)."""
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


class CreateDmCompanyPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._field_edits: dict[str, QLineEdit] = {}
        self._source_combo: QComboBox | None = None
        self._city_combo: QComboBox | None = None
        self._state_combo: QComboBox | None = None
        self._country_combo: QComboBox | None = None
        self._status_combo: QComboBox | None = None
        self._mobile_rows: list[tuple[str, QComboBox, QLineEdit]] = []
        self._can_create_company = True
        self._world_locations_mode = False
        self._build_ui()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_create_access()
        self._populate_master_key_seq_combo(self._source_combo, _LEAD_SOURCE_FIELD_NAME)
        self._world_locations_mode = bool(
            self._country_combo
            and self._state_combo
            and self._city_combo
            and ensure_world_locations_cascade(
                self._country_combo,
                self._state_combo,
                self._city_combo,
                inline_error_label=self._location_hint_label,
            )
        )
        if not self._world_locations_mode:
            self._populate_master_key_seq_combo(self._city_combo, _CITY_FIELD_NAME)
            self._populate_master_key_seq_combo(self._state_combo, _STATE_FIELD_NAME)
            self._populate_master_key_seq_combo(self._country_combo, _COUNTRY_FIELD_NAME)
        self._populate_master_key_seq_combo(self._status_combo, _STATUS_FIELD_NAME)

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
        hl.addWidget(QLabel("DM: Create Company"))
        hl.addStretch()
        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._handle_back)
        hl.addWidget(back_btn)
        layout.addWidget(header)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(12)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card.setMaximumWidth(980)
        card.setStyleSheet(
            f"#profileCard {{ background: {Theme.BG_WHITE}; border: 1px solid {Theme.BORDER_DEFAULT}; "
            "border-radius: 10px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        def new_section_grid() -> QGridLayout:
            section_grid = QGridLayout()
            section_grid.setHorizontalSpacing(24)
            section_grid.setVerticalSpacing(10)
            section_grid.setColumnStretch(0, 1)
            section_grid.setColumnStretch(1, 1)
            return section_grid

        field_h = MODAL_FIELD_HEIGHT_PX

        def add_text(
            grid: QGridLayout, key: str, label: str, row: int, col: int, ph: str
        ) -> None:
            edit = QLineEdit()
            edit.setPlaceholderText(ph)
            edit.setStyleSheet(INPUT_STYLE)
            edit.setFixedHeight(field_h)
            edit.setMinimumWidth(260)
            edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self._field_edits[key] = edit
            grid.addWidget(labeled_field_block(field_caption_label(label, LABEL_STYLE), edit), row, col)

        def add_email(
            grid: QGridLayout, key: str, label: str, row: int, col: int, ph: str
        ) -> None:
            edit = QLineEdit()
            edit.setPlaceholderText(ph)
            edit.setFixedHeight(field_h)
            edit.setMinimumWidth(260)
            edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            edit.textChanged.connect(lambda text, w=edit: self._update_email_style(w, text))
            self._field_edits[key] = edit
            self._update_email_style(edit, edit.text())
            grid.addWidget(labeled_field_block(field_caption_label(label, LABEL_STYLE), edit), row, col)

        def add_mobile_row(grid: QGridLayout, key: str, label: str, row: int, col: int) -> None:
            container = QWidget()
            container.setFixedHeight(field_h)
            row_lay = QHBoxLayout(container)
            row_lay.setContentsMargins(0, 0, 0, 0)
            row_lay.setSpacing(10)
            country = QComboBox()
            for code, country_name in COUNTRY_CODES:
                country.addItem(f"{country_name} ({code})", code)
            apply_form_combobox_field(country, height_px=field_h, min_width=120)
            number = QLineEdit()
            number.setValidator(
                QRegularExpressionValidator(QRegularExpression(r"^\d*$"))
            )
            number.setStyleSheet(INPUT_STYLE)
            number.setFixedHeight(field_h)
            number.setMinimumWidth(120)
            number.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            number.setPlaceholderText(placeholder_example("9876543210"))
            country.currentIndexChanged.connect(
                lambda _i, cc=country, num=number: self._update_mobile_row_style(cc, num)
            )
            number.textChanged.connect(
                lambda _t, cc=country, num=number: self._update_mobile_row_style(cc, num)
            )
            row_lay.addWidget(country)
            row_lay.addWidget(number, 1)
            self._mobile_rows.append((key, country, number))
            self._update_mobile_row_style(country, number)
            grid.addWidget(
                labeled_field_block(field_caption_label(label, LABEL_STYLE), container),
                row,
                col,
            )

        basic_grid = new_section_grid()
        add_text(
            basic_grid,
            "companyName",
            "Company Name*",
            0,
            0,
            placeholder_example("Accenture 2"),
        )
        country_combo = QComboBox()
        country_combo.setMinimumWidth(260)
        country_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(country_combo, height_px=field_h)
        wire_searchable_master_key_combo(country_combo, search_field_label="Country")
        self._country_combo = country_combo
        basic_grid.addWidget(
            labeled_field_block(field_caption_label("Country*", LABEL_STYLE), country_combo),
            0,
            1,
        )
        state_combo = QComboBox()
        state_combo.setMinimumWidth(260)
        state_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(state_combo, height_px=field_h)
        wire_searchable_master_key_combo(state_combo, search_field_label="State")
        self._state_combo = state_combo
        basic_grid.addWidget(
            labeled_field_block(field_caption_label("State*", LABEL_STYLE), state_combo),
            1,
            0,
        )
        city_combo = QComboBox()
        city_combo.setMinimumWidth(260)
        city_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(city_combo, height_px=field_h)
        wire_searchable_master_key_combo(city_combo, search_field_label="City")
        self._city_combo = city_combo
        basic_grid.addWidget(
            labeled_field_block(field_caption_label("City*", LABEL_STYLE), city_combo),
            1,
            1,
        )
        src_combo = QComboBox()
        src_combo.setMinimumWidth(260)
        src_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(src_combo, height_px=field_h)
        wire_searchable_master_key_combo(src_combo, search_field_label="Source")
        self._source_combo = src_combo
        basic_grid.addWidget(
            labeled_field_block(field_caption_label("Source*", LABEL_STYLE), src_combo),
            2,
            0,
        )
        add_text(basic_grid, "industry", "Industry*", 2, 1, placeholder_example("IT"))
        status_combo = QComboBox()
        status_combo.setMinimumWidth(260)
        status_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(status_combo, height_px=field_h)
        wire_searchable_master_key_combo(status_combo, search_field_label="Status")
        self._status_combo = status_combo
        basic_grid.addWidget(
            labeled_field_block(field_caption_label("Status*", LABEL_STYLE), status_combo),
            3,
            0,
        )
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
        add_email(
            contact_grid,
            "email1",
            "Email 1",
            0,
            0,
            placeholder_example("hr@accenture.com"),
        )
        add_email(
            contact_grid,
            "email2",
            "Email 2",
            0,
            1,
            placeholder_example("jobs@accenture.com"),
        )
        add_mobile_row(contact_grid, "contactNo1", "Contact No 1", 1, 0)
        add_mobile_row(contact_grid, "contactNo2", "Contact No 2", 1, 1)
        add_mobile_row(contact_grid, "contactNo3", "Contact No 3", 2, 0)
        website_edit = QLineEdit()
        website_edit.setPlaceholderText(placeholder_example("websites"))
        website_edit.setStyleSheet(INPUT_STYLE)
        website_edit.setFixedHeight(field_h)
        website_edit.setMinimumWidth(260)
        website_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._field_edits["website"] = website_edit
        contact_grid.addWidget(
            labeled_field_block(field_caption_label("Website", LABEL_STYLE), website_edit),
            2,
            1,
        )
        card_layout.addLayout(contact_grid)
        card_layout.addSpacing(4)

        additional_grid = new_section_grid()
        comments_edit = QLineEdit()
        comments_edit.setPlaceholderText(placeholder_example("SAP migration project"))
        comments_edit.setStyleSheet(INPUT_STYLE)
        comments_edit.setFixedHeight(field_h)
        comments_edit.setMinimumWidth(260)
        comments_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._field_edits["comments"] = comments_edit
        additional_grid.addWidget(
            labeled_field_block(field_caption_label("Comments", LABEL_STYLE), comments_edit),
            0,
            0,
            1,
            2,
        )
        billing = QLineEdit()
        billing.setPlaceholderText(placeholder_example("addresstext"))
        billing.setStyleSheet(INPUT_STYLE)
        billing.setFixedHeight(field_h)
        billing.setMinimumWidth(260)
        billing.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._field_edits["billingAddress"] = billing
        additional_grid.addWidget(
            labeled_field_block(field_caption_label("Billing address", LABEL_STYLE), billing),
            1,
            0,
            1,
            2,
        )
        card_layout.addLayout(additional_grid)
        card_layout.addSpacing(12)

        self.error_label = QLabel()
        self.error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.error_label.setVisible(False)
        card_layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self._create_btn = QPushButton("Create")
        self._create_btn.setFixedWidth(100)
        self._create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_btn.setStyleSheet(
            FORM_PRIMARY_BUTTON_STYLESHEET
            + " QPushButton:disabled {"
            + " background-color: #e5e7eb;"
            + " color: #6b7280;"
            + " border: 1px solid #cbd5e1;"
            + "}"
        )
        self._create_btn.clicked.connect(self._handle_create)
        btn_row.addWidget(self._create_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self._handle_back)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        cl.addWidget(card)
        cl.addStretch()
        layout.addWidget(content)

    def _refresh_create_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_create_company = True
        else:
            allowed = collect_allowed_action_names(steps)
            self._can_create_company = nav_action_visible("DM: Company", "create", allowed)
        self._create_btn.setEnabled(self._can_create_company)
        self._create_btn.setToolTip("" if self._can_create_company else "Require Permission.")

    def _populate_master_key_seq_combo(self, combo: QComboBox | None, field_name: str) -> None:
        populate_master_key_by_field_name(
            combo,
            field_name,
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

    @staticmethod
    def _full_contact_number(country_code: str, national_digits: str) -> str:
        """Dial code + national digits for API (e.g. ``+919876543210``)."""
        cc = str(country_code or "+91").strip()
        return f"{cc}{national_digits.strip()}"

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
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _show_error(self, message: str) -> None:
        # Validation handlers often set focus right after showing an error.
        # Keep the message visible instead of clearing on that focus change.
        show_auto_hiding_message(self, self.error_label, message, error=True, clear_on_user_activity=False)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)
        if self._country_combo is not None:
            clear_world_location_inline_error(self._country_combo)

    def is_dirty(self) -> bool:
        if any(edit.text().strip() for edit in self._field_edits.values()):
            return True
        if self._world_locations_mode:
            for combo in (self._country_combo, self._state_combo, self._city_combo):
                if combo is not None:
                    data = combo_resolved_item_data(combo)
                    if data is not None and str(data).strip() != "":
                        return True
        else:
            for combo in (
                self._source_combo,
                self._city_combo,
                self._state_combo,
                self._country_combo,
                self._status_combo,
            ):
                if combo is not None:
                    data = combo_resolved_master_key_seq(combo)
                    if data is not None and str(data).strip() != "":
                        return True
        for _key, cc, num in self._mobile_rows:
            if cc.currentIndex() != 0 or num.text().strip():
                return True
        return False

    def reset_to_default(self) -> None:
        for edit in self._field_edits.values():
            edit.clear()
        if self._source_combo is not None:
            reset_searchable_combo(self._source_combo)
        if self._world_locations_mode and self._country_combo and self._state_combo and self._city_combo:
            reset_world_locations_cascading(self._country_combo, self._state_combo, self._city_combo)
        else:
            if self._city_combo is not None:
                reset_searchable_combo(self._city_combo)
            if self._state_combo is not None:
                reset_searchable_combo(self._state_combo)
            if self._country_combo is not None:
                reset_searchable_combo(self._country_combo)
        if self._status_combo is not None:
            reset_searchable_combo(self._status_combo)
        for _key, cc, num in self._mobile_rows:
            cc.blockSignals(True)
            cc.setCurrentIndex(0)
            cc.blockSignals(False)
            num.clear()
            self._update_mobile_row_style(cc, num)
        for k in ("email1", "email2"):
            e = self._field_edits.get(k)
            if e is not None:
                self._update_email_style(e, e.text())
        self._clear_error()

    def _handle_back(self) -> None:
        if not self.is_dirty():
            if self.on_back:
                self.on_back()
            return
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard and leave?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Discard:
            self.reset_to_default()
            if self.on_back:
                self.on_back()

    def _handle_create(self) -> None:
        if not self._can_create_company:
            self._show_error("Create disabled: missing step access dm-company-create.")
            return
        self._clear_error()
        company_name = self._field_edits["companyName"].text().strip()
        if not company_name:
            self._show_error("Company Name is required.")
            self._field_edits["companyName"].setFocus()
            return
        if self._country_combo is None:
            self._show_error("Country is required.")
            return
        if self._world_locations_mode:
            country_raw = combo_resolved_item_data(self._country_combo)
            state_raw = combo_resolved_item_data(self._state_combo)
            city_raw = combo_resolved_item_data(self._city_combo)
        else:
            country_raw = combo_resolved_master_key_seq(self._country_combo)
            state_raw = (
                combo_resolved_master_key_seq(self._state_combo)
                if self._state_combo is not None
                else None
            )
            city_raw = (
                combo_resolved_master_key_seq(self._city_combo)
                if self._city_combo is not None
                else None
            )
        if country_raw is None or not str(country_raw).strip():
            typed = (self._country_combo.currentText() or "").strip()
            if typed:
                self._show_error(strict_list_selection_message("a country"))
            else:
                self._show_error("Country is required.")
            self._country_combo.setFocus()
            return
        if self._state_combo is None:
            self._show_error("State is required.")
            return
        if state_raw is None or not str(state_raw).strip():
            typed = (self._state_combo.currentText() or "").strip()
            if typed:
                self._show_error(strict_list_selection_message("a state"))
            else:
                self._show_error("State is required.")
            self._state_combo.setFocus()
            return
        if city_raw is None or not str(city_raw).strip():
            typed = (
                (self._city_combo.currentText() or "").strip()
                if self._city_combo is not None
                else ""
            )
            if typed:
                self._show_error(strict_list_selection_message("a city"))
            else:
                self._show_error("City is required.")
            if self._city_combo is not None:
                self._city_combo.setFocus()
            return
        if self._source_combo is None:
            self._show_error("Source is required.")
            return
        source_id, source_err = require_master_key_seq_for_payload(
            self._source_combo, field_caption="Source", strict_phrase="a source"
        )
        if source_err:
            self._show_error(source_err)
            self._source_combo.setFocus()
            return
        for em_key in ("email1", "email2"):
            edit = self._field_edits.get(em_key)
            if not edit:
                continue
            em = edit.text().strip()
            if em and not _EMAIL_REGEX.match(em):
                self._show_error("Please enter a valid email address.")
                edit.setFocus()
                return
        for key, cc, num in self._mobile_rows:
            raw = num.text().strip()
            if not raw:
                continue
            country_code = cc.currentData() or "+91"
            valid, msg = validate_mobile(country_code, raw)
            if not valid:
                self._show_error(msg)
                num.setFocus()
                return
        ind_edit = self._field_edits.get("industry")
        industry_val = ind_edit.text().strip() if ind_edit else ""
        if not industry_val:
            self._show_error("Industry is required.")
            if ind_edit:
                ind_edit.setFocus()
            return
        if self._status_combo is None:
            self._show_error("Status is required.")
            return
        status_id, status_err = require_master_key_seq_for_payload(
            self._status_combo, field_caption="Status", strict_phrase="a status"
        )
        if status_err:
            self._show_error(status_err)
            self._status_combo.setFocus()
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
        for key, edit in self._field_edits.items():
            if key in ("companyName", "industry"):
                continue
            val = edit.text().strip()
            if val:
                payload[key] = val
        for key, cc, num in self._mobile_rows:
            raw = num.text().strip()
            if raw:
                country_code = str(cc.currentData() or "+91").strip()
                payload[key] = self._full_contact_number(country_code, raw)
        result = api_create_dm_company(payload, token=self._token())
        ok = show_api_result_message(
            self,
            self.error_label,
            result,
            error_fallback="Failed to create company.",
            success_fallback="Company created successfully.",
        )
        if ok:
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
