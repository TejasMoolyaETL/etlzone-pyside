"""View / edit Company Contact Assignment page."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.api import (
    api_get_all_contact_persons,
    api_get_all_lead_companies,
    api_get_master_key_by_app_id_field_name,
    api_update_contact_person_company_assignment,
    master_key_row_seq_value,
)
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
)
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success
from ui.widgets.required_label import field_caption_label, labeled_field_block

_ASSIGNMENT_STATUS_FIELD_NAME = "lead_company_contact_assignment_status"


class ViewContactPersonCompanyAssignmentPage(QWidget):
    def __init__(self, on_back: Callable[[], None] | None = None, on_update_success: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._record: dict[str, Any] = {}
        self._can_edit_action = True
        self._company_combo: QComboBox | None = None
        self._contact_person_combo: QComboBox | None = None
        self._status_combo: QComboBox | None = None
        self._initial_status_seq: Any = None
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
        hl.addWidget(QLabel("Company Contant Assignment Details"))
        hl.addStretch()
        layout.addWidget(header)
        body = QWidget()
        bl = QVBoxLayout(body)
        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card.setMaximumWidth(620)
        card.setStyleSheet("#profileCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }")
        cl = QVBoxLayout(card)
        self.assignment_id = QLineEdit()
        self.assignment_id.setReadOnly(True)
        self.assignment_id.setStyleSheet(INPUT_STYLE)
        self.assignment_id.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
        self.assignment_id.setMinimumWidth(260)
        self.assignment_id.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cl.addWidget(labeled_field_block(field_caption_label("Assignment Id", LABEL_STYLE), self.assignment_id))

        self._company_combo = QComboBox()
        self._company_combo.setMinimumWidth(260)
        self._company_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(self._company_combo, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX)
        cl.addWidget(labeled_field_block(field_caption_label("Company*", LABEL_STYLE), self._company_combo))

        self._contact_person_combo = QComboBox()
        self._contact_person_combo.setMinimumWidth(260)
        self._contact_person_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(self._contact_person_combo, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX)
        cl.addWidget(labeled_field_block(field_caption_label("Contact Person*", LABEL_STYLE), self._contact_person_combo))

        self._status_combo = QComboBox()
        self._status_combo.setMinimumWidth(260)
        self._status_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_form_combobox_field(self._status_combo, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX)
        cl.addWidget(labeled_field_block(field_caption_label("Status*", LABEL_STYLE), self._status_combo))
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

    def _token(self) -> str | None:
        p = get_user_profile()
        t = p.get("token") or p.get("accessToken") or p.get("access_token") or p.get("jwt")
        return str(t) if t else None

    def set_assignment(self, rec: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._record = dict(rec) if rec else {}
        self._refresh_edit_action_access()
        self._populate_company_combo()
        self._populate_contact_person_combo()
        self._populate_status_combo()
        self._apply_record_to_fields()
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
            self._can_edit_action = nav_action_visible(
                "Lead: Company Contact Assignment", "edit", allowed
            )
        self._edit.setEnabled(self._can_edit_action)
        self._edit.setToolTip("" if self._can_edit_action else "Require Permission.")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_edit_action_access()
        self._populate_company_combo()
        self._populate_contact_person_combo()
        self._populate_status_combo()
        self._apply_record_to_fields()

    def _assignment_id(self) -> Any:
        return self._record.get("assignmentId") or self._record.get("companyContactId") or self._record.get("id") or self._record.get("linkId")

    def _record_company_id(self) -> Any:
        cid = self._record.get("companyId") or self._record.get("idCompany")
        if cid is not None:
            return cid
        company_obj = self._record.get("company")
        if isinstance(company_obj, dict):
            return company_obj.get("companyId") or company_obj.get("id")
        return None

    def _record_contact_id(self) -> Any:
        return self._record.get("contactPersonId") or self._record.get("contactId")

    def _record_status_seq(self) -> Any:
        for key in ("assignmentStatus", "assignment_status", "status", "statusSeq", "status_seq"):
            if key not in self._record:
                continue
            v = self._record.get(key)
            if v is None:
                continue
            if isinstance(v, dict):
                seq = v.get("seq")
                if seq is not None:
                    return seq
                continue
            return v
        return None

    def _set_combo_to_data(self, combo: QComboBox | None, value: Any) -> None:
        if combo is None or value is None:
            return
        idx = combo.findData(value)
        if idx < 0 and isinstance(value, int):
            idx = combo.findData(str(value))
        elif idx < 0:
            s = str(value).strip()
            if s.isdigit():
                idx = combo.findData(int(s))
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _apply_record_to_fields(self) -> None:
        self.assignment_id.setText(str(self._assignment_id() or ""))
        self._set_combo_to_data(self._company_combo, self._record_company_id())
        self._set_combo_to_data(self._contact_person_combo, self._record_contact_id())
        self._set_combo_to_data(self._status_combo, self._record_status_seq())
        self._initial_status_seq = self._status_combo.currentData() if self._status_combo is not None else None

    def _populate_company_combo(self) -> None:
        combo = self._company_combo
        if combo is None:
            return
        result = api_get_all_lead_companies(token=self._token())
        rows = result.get("data") if result.get("success") else []
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Select company…", None)
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
        combo.blockSignals(False)

    def _populate_contact_person_combo(self) -> None:
        combo = self._contact_person_combo
        if combo is None:
            return
        result = api_get_all_contact_persons(token=self._token())
        rows = result.get("data") if result.get("success") else []
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Select contact person…", None)
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
        combo.blockSignals(False)

    def _populate_status_combo(self) -> None:
        combo = self._status_combo
        if combo is None:
            return
        result = api_get_master_key_by_app_id_field_name(
            field_name=_ASSIGNMENT_STATUS_FIELD_NAME,
            token=self._token(),
        )
        rows = result.get("data") if result.get("success") else []
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Select status…", None)
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                seq_val = master_key_row_seq_value(row)
                if seq_val is None:
                    continue
                key_value = str(row.get("keyValue") or row.get("key_value") or "").strip()
                if not key_value:
                    continue
                combo.addItem(f"{seq_val} | {key_value}", seq_val)
        combo.blockSignals(False)

    def _switch_view(self) -> None:
        if self._company_combo is not None:
            self._company_combo.setEnabled(False)
        if self._contact_person_combo is not None:
            self._contact_person_combo.setEnabled(False)
        if self._status_combo is not None:
            self._status_combo.setEnabled(False)
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
            self._show_error(
                "Edit disabled: missing step access lead-company-contact-assignment-edit."
            )
            return
        if self._company_combo is not None:
            self._company_combo.setEnabled(False)
        if self._contact_person_combo is not None:
            self._contact_person_combo.setEnabled(False)
        if self._status_combo is not None:
            self._status_combo.setEnabled(True)
        self._btn_stack.setCurrentIndex(1)

    def _handle_cancel(self) -> None:
        self._apply_record_to_fields()
        self._switch_view()

    def _handle_save(self) -> None:
        aid = self._assignment_id()
        if aid is None:
            self._show_error("Assignment ID missing.")
            return
        if self._status_combo is None or self._status_combo.currentIndex() <= 0 or self._status_combo.currentData() is None:
            self._show_error("Status is required.")
            if self._status_combo is not None:
                self._status_combo.setFocus()
            return
        status_seq = self._status_combo.currentData()
        if status_seq == self._initial_status_seq:
            self._show_error("No changes to update.")
            return
        payload = {"status": status_seq}
        res = api_update_contact_person_company_assignment(aid, payload, token=self._token())
        if not res.get("success"):
            self._show_error(str(res.get("message") or "Failed to update assignment."))
            return
        self._record.update(payload)
        self._initial_status_seq = status_seq
        self._switch_view()
        self._show_success(str(res.get("message") or "Assignment updated successfully."))
        # Refresh list immediately (API call) before navigation.
        if callable(self.on_update_success):
            self.on_update_success()
        schedule_after_success(
            delay_ms=600,
            clear_error=self._clear_error,
            reset=lambda: None,
            on_back=self.on_back,
            on_success=None,
        )
