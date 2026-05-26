"""Create Company Contact Assignment page."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.api import (
    api_create_dm_contact_person_company_assignment,
    api_get_all_dm_contact_persons,
    api_get_all_dm_companies,
)
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    MODAL_FIELD_HEIGHT_PX,
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
    set_searchable_combo_by_user_data,
    wire_searchable_master_key_combo,
)
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label, labeled_field_block

_ASSIGNMENT_STATUS_FIELD_NAME = "lead_company_contact_assignment_status"


class CreateDmContactPersonCompanyAssignmentPage(QWidget):
    def __init__(self, on_back: Callable[[], None] | None = None, on_create_success: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._can_create = True
        self._company_combo: QComboBox | None = None
        self._contact_person_combo: QComboBox | None = None
        self._status_combo: QComboBox | None = None
        self._pending_prefill: dict[str, Any] | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        header = QWidget()
        header.setStyleSheet(FORM_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("DM: Create Company Contact Assignment"))
        hl.addStretch()
        back = QPushButton("Back")
        back.setFixedWidth(100)
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(self._handle_back)
        hl.addWidget(back)
        layout.addWidget(header)
        body = QWidget()
        bl = QVBoxLayout(body)
        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card.setMaximumWidth(620)
        card.setStyleSheet("#profileCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }")
        cl = QVBoxLayout(card)
        h = MODAL_FIELD_HEIGHT_PX
        self._company_combo = QComboBox()
        self._company_combo.setMinimumWidth(260)
        self._company_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(self._company_combo, height_px=h)
        wire_searchable_master_key_combo(self._company_combo, search_field_label="Company")
        cl.addWidget(labeled_field_block(field_caption_label("Company*", LABEL_STYLE), self._company_combo))
        self._contact_person_combo = QComboBox()
        self._contact_person_combo.setMinimumWidth(260)
        self._contact_person_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(self._contact_person_combo, height_px=h)
        wire_searchable_master_key_combo(self._contact_person_combo, search_field_label="Contact Person")
        cl.addWidget(labeled_field_block(field_caption_label("Contact Person*", LABEL_STYLE), self._contact_person_combo))
        self._status_combo = QComboBox()
        self._status_combo.setMinimumWidth(260)
        self._status_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(self._status_combo, height_px=h)
        wire_searchable_master_key_combo(self._status_combo, search_field_label="Status")
        cl.addWidget(labeled_field_block(field_caption_label("Status*", LABEL_STYLE), self._status_combo))
        self.error_label = QLabel()
        self.error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.error_label.setVisible(False)
        self.error_label.setWordWrap(True)
        cl.addWidget(self.error_label)
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
        cl.addLayout(br)
        bl.addWidget(card)
        bl.addStretch()
        layout.addWidget(body)

    def _refresh_create_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_create = True
        else:
            allowed = collect_allowed_action_names(steps)
            self._can_create = nav_action_visible(
                "DM: Company Contact Assignment", "create", allowed
            )
        self._create_btn.setEnabled(self._can_create)
        self._create_btn.setToolTip("" if self._can_create else "Require Permission.")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_create_access()
        self._populate_company_combo()
        self._populate_contact_person_combo()
        self._populate_status_combo()
        self._apply_pending_prefill()

    def _token(self) -> str | None:
        p = get_user_profile()
        t = p.get("token") or p.get("accessToken") or p.get("access_token") or p.get("jwt")
        return str(t) if t else None

    def _populate_company_combo(self) -> None:
        combo = self._company_combo
        if combo is None:
            return
        result = api_get_all_dm_companies(token=self._token())
        rows = result.get("data") if result.get("success") else []
        combo.blockSignals(True)
        combo.clear()
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cid = row.get("companyId") or row.get("id")
                if cid is None:
                    continue
                name = str(row.get("companyName") or row.get("name") or "").strip()
                label = f"{cid} | {name}" if name else str(cid)
                combo.addItem(label, cid)
        combo.setCurrentIndex(-1)
        le = combo.lineEdit()
        if le is not None:
            le.clear()
        combo.blockSignals(False)

    def _populate_contact_person_combo(self) -> None:
        combo = self._contact_person_combo
        if combo is None:
            return
        result = api_get_all_dm_contact_persons(token=self._token())
        rows = result.get("data") if result.get("success") else []
        combo.blockSignals(True)
        combo.clear()
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                contact_id = row.get("contactId") or row.get("contactPersonId") or row.get("id")
                if contact_id is None:
                    continue
                name = str(row.get("name") or row.get("contactPersonName") or "").strip()
                label = f"{contact_id} | {name}" if name else str(contact_id)
                combo.addItem(label, contact_id)
        combo.setCurrentIndex(-1)
        le = combo.lineEdit()
        if le is not None:
            le.clear()
        combo.blockSignals(False)

    def _populate_status_combo(self) -> None:
        populate_master_key_by_field_name(
            self._status_combo,
            _ASSIGNMENT_STATUS_FIELD_NAME,
            token=self._token(),
            include_placeholder=False,
        )

    def set_prefill(self, prefill: dict[str, Any] | None) -> None:
        self._pending_prefill = dict(prefill) if isinstance(prefill, dict) else None

    def _set_combo_to_data(self, combo: QComboBox | None, value: Any) -> None:
        if combo is None or value is None:
            return
        set_searchable_combo_by_user_data(combo, value)

    def _apply_pending_prefill(self) -> None:
        if not isinstance(self._pending_prefill, dict):
            return
        data = dict(self._pending_prefill)
        self._pending_prefill = None
        self._set_combo_to_data(self._company_combo, data.get("companyId"))
        self._set_combo_to_data(self._contact_person_combo, data.get("contactPersonId"))
        self._set_combo_to_data(self._status_combo, data.get("status"))

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)

    def _show_error(self, m: str) -> None:
        show_auto_hiding_message(self, self.error_label, m, error=True)

    def _show_success(self, m: str) -> None:
        show_auto_hiding_message(self, self.error_label, m, error=False)

    def is_dirty(self) -> bool:
        for combo in (self._company_combo, self._contact_person_combo, self._status_combo):
            if combo is None:
                continue
            data = combo_resolved_item_data(combo)
            if data is not None and str(data).strip() != "":
                return True
        return False

    def reset_to_default(self) -> None:
        reset_searchable_combo(self._company_combo)
        reset_searchable_combo(self._contact_person_combo)
        reset_searchable_combo(self._status_combo)
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
            self._show_error(
                "Create disabled: missing step access dm-company-contact-assignment-create."
            )
            return
        self._clear_error()
        company_id = combo_resolved_item_data(self._company_combo)
        if company_id is None or not str(company_id).strip():
            typed = (self._company_combo.currentText() or "").strip() if self._company_combo else ""
            if typed:
                self._show_error(strict_list_selection_message("a company"))
            else:
                self._show_error("Company is required.")
            if self._company_combo is not None:
                self._company_combo.setFocus()
            return
        contact_id = combo_resolved_item_data(self._contact_person_combo)
        if contact_id is None or not str(contact_id).strip():
            typed = (
                (self._contact_person_combo.currentText() or "").strip()
                if self._contact_person_combo is not None
                else ""
            )
            if typed:
                self._show_error(strict_list_selection_message("a contact person"))
            else:
                self._show_error("Contact Person is required.")
            if self._contact_person_combo is not None:
                self._contact_person_combo.setFocus()
            return
        status_seq, status_err = require_master_key_seq_for_payload(
            self._status_combo, field_caption="Status", strict_phrase="a status"
        )
        if status_err:
            self._show_error(status_err)
            if self._status_combo is not None:
                self._status_combo.setFocus()
            return
        payload: dict[str, Any] = {
            "companyId": company_id,
            "contactPersonId": contact_id,
            "status": status_seq,
        }
        res = api_create_dm_contact_person_company_assignment(payload, token=self._token())
        if res.get("success"):
            self._show_success(str(res.get("message") or "Assignment created successfully."))
            # Refresh list immediately (API call) before navigation.
            if callable(self.on_create_success):
                self.on_create_success()
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=None,
            )
        else:
            self._show_error(str(res.get("message") or "Failed to create assignment."))
