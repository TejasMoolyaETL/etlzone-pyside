"""Lead list page."""

from __future__ import annotations

import json
import re
import traceback
from ast import literal_eval
from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.lead_management.leads.lead_create import _DateTimePickerField
from core.api import (
    api_add_lead_comment,
    api_delete_lead_comment_by_id,
    api_delete_lead,
    api_get_all_lead_comments_by_lead_id,
    api_get_lead_contact_persons_by_lead_id,
    api_get_all_leads,
    api_update_lead_comment_by_id,
)
from core.app_preferences import format_field_display_value, to_utc_iso
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
from ui.data_table import (
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    data_row_offset,
    filter_dict_rows_by_column_edits,
    install_filter_row,
    resize_data_table_columns_to_content,
    sync_vertical_header_labels,
)
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET,
    MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET,
    MODAL_FIELD_HEIGHT_PX,
    MODAL_FIELD_LABEL_STYLE,
)
from ui.styles import CONTEXT_MENU_STYLESHEET

_STRICT_KEYVALUE_ONLY_KEYS = frozenset(
    {
        "contractType",
        "ContractType",
        "contract_type",
        "contracttype",
        "leadCommunicationChannel",
        "LeadCommunicationChannel",
        "lead_communication_channel",
        "leadcommunicationchannel",
        "nextAction",
        "NextAction",
        "next_action",
        "nextaction",
        "accommodationOwnership",
        "AccommodationOwnership",
        "accommodation_ownership",
        "accommodationownership",
    }
)
_KEYVALUE_RE = re.compile(r"(?:^|[,{]\s*)keyValue\s*[:=]\s*['\"]?([^,'\"}]+)")

_LEAD_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Lead Id", ("leadId", "id")),
    ("Company", ("companyName", "companyId")),
    ("Contact Person", ("contactPersonName", "contactPersonId")),
    ("Contract Type", ("contractType", "ContractType", "contract_type", "contracttype")),
    ("Project Type", ("projectType",)),
    ("Role", ("role",)),
    ("Source", ("source",)),
    ("Lead Communication Channel", ("leadCommunicationChannel",)),
    ("Lead Status", ("leadStatus",)),
    ("Lead Stage", ("leadStage",)),
    ("Next Action", ("nextAction",)),
    ("Job Location", ("jobLocation",)),
    ("Experience Needed", ("experienceNeeded",)),
    ("Job Desc", ("jobDesc",)),
    ("Mandatory Skills", ("mandatorySkills",)),
    ("Optional Skills", ("optionalSkills",)),
    ("Currency", ("currency",)),
    ("Expected Billing", ("expectedBilling",)),
    ("End Client Name", ("endClientName",)),
    ("Intermediate Client 1", ("intermediateClient1",)),
    ("Intermediate Client 2", ("intermediateClient2",)),
    ("Intermediate Client 3", ("intermediateClient3",)),
    ("Intermediate Client 4", ("intermediateClient4",)),
    ("Next Follow Up On", ("nextFollowUpOn",)),
    ("Last Contacted", ("lastContacted",)),
    ("Estimated Start Date", ("estimatedStartDate",)),
    ("Estimated End Date", ("estimatedEndDate",)),
    ("Laptop Ownership", ("laptopOwnership",)),
    ("Accommodation Ownership", ("accommodationOwnership",)),
    ("Travel Expense Ownership", ("travelExpenseOwnership",)),
    ("Per Diem Ownership", ("perDiemOwnership",)),
    ("Description", ("desc",)),
    ("Lead Remarks", ("leadRemarks",)),
    ("Comment At ETLZone", ("commentAtEtlzone",)),
    ("Status", ("status",)),
    ("Created At", ("createdAt",)),
    ("Created By", ("createdBy",)),
    ("Modified At", ("modifiedAt",)),
    ("Modified By", ("modifiedBy",)),
)

_LEAD_COMMENT_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Comment Id", ("commentId", "leadCommentId", "id")),
    ("Comment By", ("commentByUsername", "commentBy", "username")),
    ("Comment On Date", ("commentOnDate", "createdAt")),
    ("Comment", ("comment", "commentText")),
    ("Created At", ("createdAt",)),
    ("Created By", ("createdBy",)),
    ("Modified At", ("modifiedAt",)),
    ("Modified By", ("modifiedBy",)),
)


def _value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return None


def _value_for_lead_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    v = _value_for_column(row, keys)
    return v, keys[0]


def _format_lead_filter_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    ks = key_candidates if key_candidates else (key,)
    return _display_value(value, key, ks)


def _display_value(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    all_keys = {k for k in (key, *key_candidates) if isinstance(k, str)}
    if all_keys & _STRICT_KEYVALUE_ONLY_KEYS:
        if isinstance(value, dict):
            return str(value.get("keyValue") or value.get("key_value") or "").strip()
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return ""
            if raw.startswith("{") and raw.endswith("}"):
                try:
                    parsed = json.loads(raw)
                    if isinstance(parsed, dict):
                        return str(parsed.get("keyValue") or parsed.get("key_value") or "").strip()
                except Exception:
                    try:
                        parsed = literal_eval(raw)
                        if isinstance(parsed, dict):
                            return str(parsed.get("keyValue") or parsed.get("key_value") or "").strip()
                    except Exception:
                        pass
                m = _KEYVALUE_RE.search(raw)
                if m:
                    return str(m.group(1) or "").strip()
        return ""
    return format_field_display_value(value, key, key_candidates)


class _LeadCommentDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        title: str,
        lead_id: str = "",
        token: str | None = None,
        initial: dict[str, Any] | None = None,
        view_edit_mode: bool = False,
        allow_comment_edit: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setStyleSheet("QDialog { background: #ffffff; }")
        self._view_edit_mode = bool(view_edit_mode)
        self._allow_comment_edit = bool(allow_comment_edit)
        self._token = token
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        self._msg = QLabel()
        self._msg.setWordWrap(True)
        self._msg.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._msg.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._msg.setVisible(False)
        lay.addWidget(self._msg)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._lead_id_edit = QLineEdit()
        self._by_combo = QComboBox()
        self._date_edit = _DateTimePickerField(MODAL_FIELD_HEIGHT_PX)
        self._comment_edit = QPlainTextEdit()
        self._lead_id_edit.setFixedHeight(MODAL_FIELD_HEIGHT_PX)
        apply_form_combobox_field(self._by_combo, height_px=MODAL_FIELD_HEIGHT_PX)
        self._lead_id_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self._comment_edit.setStyleSheet(
            "QPlainTextEdit { font-size: 10px; padding: 4px 8px; border: 1px solid #e2e8f0; border-radius: 4px; background: #ffffff; }"
        )
        self._comment_edit.setMinimumHeight(140)
        self._comment_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        lead_id_lbl = QLabel("Lead Id:")
        by_lbl = QLabel("Comment By Username:")
        date_lbl = QLabel("Comment On Date:")
        c_lbl = QLabel("Comment:")
        lead_id_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        by_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        date_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        c_lbl.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        form.addRow(lead_id_lbl, self._lead_id_edit)
        form.addRow(by_lbl, self._by_combo)
        form.addRow(date_lbl, self._date_edit)
        form.addRow(c_lbl, self._comment_edit)
        lay.addLayout(form)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #cbd5e1; border: none; max-height: 1px;")
        lay.addWidget(sep)

        ok_btn = QPushButton("Save")
        ok_btn.setFixedWidth(100)
        ok_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        ok_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        cancel_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        src = initial or {}
        resolved_lead_id = str(
            lead_id
            or src.get("leadId")
            or src.get("lead_id")
            or src.get("id")
            or ""
        ).strip()
        self._lead_id_edit.setText(resolved_lead_id)
        self._lead_id_edit.setReadOnly(True)
        self._populate_comment_by_combo(resolved_lead_id)
        self._set_comment_by_value(str(src.get("commentByUsername") or src.get("commentBy") or src.get("username") or ""))
        raw_comment_on_date = src.get("commentOnDate") or src.get("createdAt") or ""
        if str(raw_comment_on_date or "").strip():
            self._date_edit.set_iso_timestamp(raw_comment_on_date)
        else:
            self._date_edit.set_defaults_today_midnight()
        self._comment_edit.setPlainText(str(src.get("comment") or src.get("commentText") or ""))

        if self._view_edit_mode:
            self._set_read_only(True)
        else:
            self._set_read_only(False)

        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self.reject)
        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedWidth(100)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        self._edit_btn.clicked.connect(lambda: self._set_read_only(False))
        if self._view_edit_mode and not self._allow_comment_edit:
            self._edit_btn.setVisible(False)

        display_btns = QWidget()
        db = QHBoxLayout(display_btns)
        db.setContentsMargins(0, 0, 0, 0)
        db.setSpacing(12)
        db.setAlignment(Qt.AlignmentFlag.AlignLeft)
        db.addWidget(self._edit_btn)
        db.addWidget(self._back_btn)
        db.addStretch(1)

        edit_btns = QWidget()
        eb = QHBoxLayout(edit_btns)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.setSpacing(12)
        eb.setAlignment(Qt.AlignmentFlag.AlignLeft)
        eb.addWidget(ok_btn)
        eb.addWidget(cancel_btn)
        eb.addStretch(1)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setFrameShape(QFrame.Shape.NoFrame)
        self._btn_stack.setStyleSheet("QStackedWidget { border: none; background: transparent; }")
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._btn_stack.addWidget(display_btns)
        self._btn_stack.addWidget(edit_btns)
        if self._view_edit_mode:
            self._btn_stack.setCurrentIndex(0)
        else:
            self._btn_stack.setCurrentIndex(1)
        lay.addWidget(self._btn_stack)

    def payload(self) -> dict[str, Any]:
        iso_local = self._date_edit.iso_timestamp()
        return {
            "commentByUsername": str(self._by_combo.currentData() or self._by_combo.currentText() or "").strip(),
            "commentOnDate": to_utc_iso(iso_local) or iso_local,
            "comment": self._comment_edit.toPlainText().strip(),
        }

    def _set_read_only(self, read_only: bool) -> None:
        self._by_combo.setEnabled(not read_only)
        self._date_edit.setEnabled(not read_only)
        self._comment_edit.setReadOnly(read_only)
        self._comment_edit.setStyleSheet(
            (
                "QPlainTextEdit { font-size: 10px; padding: 4px 8px; border: 1px solid #e2e8f0; border-radius: 4px; "
                "background: #f1f5f9; color: #64748b; }"
            )
            if read_only
            else "QPlainTextEdit { font-size: 10px; padding: 4px 8px; border: 1px solid #e2e8f0; border-radius: 4px; background: #ffffff; }"
        )
        if hasattr(self, "_btn_stack"):
            self._btn_stack.setCurrentIndex(0 if read_only else 1)

    def _populate_comment_by_combo(self, lead_id: str) -> None:
        self._by_combo.blockSignals(True)
        self._by_combo.clear()
        self._by_combo.addItem("Select username…", "")
        result = api_get_lead_contact_persons_by_lead_id(lead_id, token=self._token)
        rows = result.get("data") or []
        seen: set[str] = set()
        if isinstance(rows, list):
            for row in rows:
                username = ""
                if isinstance(row, dict):
                    username = str(
                        row.get("commentByUsername")
                        or row.get("username")
                        or row.get("userName")
                        or row.get("contactPersonUsername")
                        or row.get("contactUsername")
                        or row.get("loginId")
                        or row.get("email")
                        or row.get("contactPersonName")
                        or ""
                    ).strip()
                elif row is not None:
                    username = str(row).strip()
                if not username or username in seen:
                    continue
                seen.add(username)
                self._by_combo.addItem(username, username)
        self._by_combo.setCurrentIndex(0)
        self._by_combo.blockSignals(False)

    def _set_comment_by_value(self, value: str) -> None:
        target = str(value or "").strip()
        if not target:
            return
        idx = self._by_combo.findData(target)
        if idx < 0:
            idx = self._by_combo.findText(target)
        if idx < 0:
            self._by_combo.addItem(target, target)
            idx = self._by_combo.findData(target)
        if idx >= 0:
            self._by_combo.setCurrentIndex(idx)


class LeadListPage(QWidget):
    def __init__(
        self,
        on_create_clicked: Callable[[], None] | None = None,
        on_edit_clicked: Callable[[dict[str, Any], bool], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_create_clicked = on_create_clicked
        self.on_edit_clicked = on_edit_clicked
        self._source_rows: list[dict[str, Any]] = []
        self._filter_visible = False
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.setInterval(200)
        self._filter_apply_timer.timeout.connect(self._apply_column_filters_refresh)
        self._comment_rows: list[dict[str, Any]] = []
        self._selected_lead_id: str = ""
        self._can_create_lead = True
        self._can_display_lead = True
        self._can_edit_lead = True
        self._can_delete_lead = True
        self._can_comment_create = True
        self._can_comment_display = True
        self._can_comment_edit = True
        self._can_comment_delete = True
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("Leads"))
        hl.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        hl.addWidget(refresh_btn)
        self._filter_btn = QPushButton("Filters")
        self._filter_btn.setCheckable(True)
        self._filter_btn.setFixedWidth(100)
        self._filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_btn.toggled.connect(self._on_filter_toggle)
        hl.addWidget(self._filter_btn)
        self._create_btn = QPushButton("Create")
        self._create_btn.setFixedWidth(100)
        self._create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_btn.setStyleSheet(
            "QPushButton:disabled {"
            " background-color: #9ca3af;"
            " color: #6b7280;"
            " border: 1px solid #9ca3af;"
            "}"
        )
        self._create_btn.clicked.connect(self._emit_create_lead)
        hl.addWidget(self._create_btn)
        layout.addWidget(header)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(12)
        split = QSplitter(Qt.Orientation.Horizontal)
        left_panel = QWidget()
        ll = QVBoxLayout(left_panel)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(8)
        self._message_label = QLabel()
        self._message_label.setVisible(False)
        ll.addWidget(self._message_label)
        self.table = QTableWidget()
        apply_data_table_appearance(self.table)
        self.table.setSortingEnabled(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        self.table.itemSelectionChanged.connect(self._on_lead_selection_changed)
        attach_table_copy_shortcut(self.table)
        ll.addWidget(self.table, 1)
        split.addWidget(left_panel)

        right_panel = QWidget()
        rl = QVBoxLayout(right_panel)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(8)
        self._comment_message_label = QLabel()
        self._comment_message_label.setVisible(False)
        rl.addWidget(self._comment_message_label)
        rl.addSpacing(10)
        comment_actions_row = QHBoxLayout()
        comment_actions_row.setContentsMargins(0, 0, 0, 0)
        comment_actions_row.setSpacing(6)
        _comment_btn_h = 20
        _comment_btn_w = 62
        btn_style = (
            "QPushButton {"
            " font-size: 10px;"
            " font-weight: 600;"
            " border: 1px solid #cbd5e1;"
            " border-radius: 4px;"
            " background: #ffffff;"
            " color: #334155;"
            " padding: 0 8px;"
            "}"
            "QPushButton:hover:enabled { background: #f8fafc; border-color: #94a3b8; }"
            "QPushButton:pressed:enabled { background: #f1f5f9; border-color: #64748b; }"
            "QPushButton:disabled {"
            " background: #e5e7eb;"
            " color: #9ca3af;"
            " border: 1px solid #d1d5db;"
            "}"
            "QPushButton:disabled:hover, QPushButton:disabled:pressed {"
            " background: #e5e7eb;"
            " color: #9ca3af;"
            " border: 1px solid #d1d5db;"
            "}"
        )
        self._comment_add_btn = QPushButton("Add")
        self._comment_add_btn.setFixedSize(_comment_btn_w, _comment_btn_h)
        self._comment_add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._comment_add_btn.setStyleSheet(btn_style)
        self._comment_add_btn.clicked.connect(self._on_add_comment_clicked)
        self._comment_update_btn = QPushButton("Update")
        self._comment_update_btn.setFixedSize(_comment_btn_w, _comment_btn_h)
        self._comment_update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._comment_update_btn.setStyleSheet(btn_style)
        self._comment_update_btn.clicked.connect(self._on_update_comment_clicked)
        self._comment_delete_btn = QPushButton("Delete")
        self._comment_delete_btn.setFixedSize(_comment_btn_w, _comment_btn_h)
        self._comment_delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._comment_delete_btn.setStyleSheet(btn_style)
        self._comment_delete_btn.clicked.connect(self._on_delete_comment_clicked)
        comment_actions_row.addStretch()
        comment_actions_row.addWidget(self._comment_add_btn)
        comment_actions_row.addWidget(self._comment_update_btn)
        comment_actions_row.addWidget(self._comment_delete_btn)
        rl.addLayout(comment_actions_row)
        self._comment_table = QTableWidget()
        apply_data_table_appearance(self._comment_table)
        self._comment_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._comment_table.customContextMenuRequested.connect(self._on_comment_context_menu)
        self._comment_table.itemDoubleClicked.connect(self._on_comment_double_clicked)
        attach_table_copy_shortcut(self._comment_table)
        rl.addWidget(self._comment_table, 1)
        split.addWidget(right_panel)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        cl.addWidget(split, 1)
        layout.addWidget(content, 1)

    def _emit_create_lead(self) -> None:
        if not self._can_create_lead:
            show_auto_hiding_message(
                self,
                self._message_label,
                "Create disabled: missing step access lead-create.",
                error=True,
            )
            return
        if self.on_create_clicked:
            self.on_create_clicked()

    def _refresh_action_access(self) -> None:
        steps = get_nav_access_steps()
        lbl = "Leads"
        if steps is None:
            self._can_create_lead = True
            self._can_display_lead = True
            self._can_edit_lead = True
            self._can_delete_lead = True
            self._can_comment_create = True
            self._can_comment_display = True
            self._can_comment_edit = True
            self._can_comment_delete = True
        else:
            allowed = collect_allowed_action_names(steps)
            self._can_create_lead = nav_action_visible(lbl, "create", allowed)
            self._can_display_lead = nav_action_visible(lbl, "display", allowed)
            self._can_edit_lead = nav_action_visible(lbl, "edit", allowed)
            self._can_delete_lead = nav_action_visible(lbl, "delete", allowed)
            self._can_comment_create = nav_action_visible(lbl, "comment_create", allowed)
            self._can_comment_display = nav_action_visible(lbl, "comment_display", allowed)
            self._can_comment_edit = nav_action_visible(lbl, "comment_edit", allowed)
            self._can_comment_delete = nav_action_visible(lbl, "comment_delete", allowed)
        self._create_btn.setEnabled(self._can_create_lead)
        self._create_btn.setToolTip("" if self._can_create_lead else "Require Permission.")
        self._comment_add_btn.setEnabled(self._can_comment_create)
        self._comment_add_btn.setToolTip("" if self._can_comment_create else "Require Permission.")
        can_view_or_edit_comment = self._can_comment_display or self._can_comment_edit
        self._comment_update_btn.setEnabled(can_view_or_edit_comment)
        self._comment_update_btn.setToolTip(
            "" if can_view_or_edit_comment else "Require Permission."
        )
        self._comment_delete_btn.setEnabled(self._can_comment_delete)
        self._comment_delete_btn.setToolTip("" if self._can_comment_delete else "Require Permission.")

    def _data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _schedule_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_source_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._source_rows,
            self.table,
            list(_LEAD_COLUMNS),
            self._filter_visible,
            _value_for_lead_column,
            _format_lead_filter_cell,
        )

    def _write_lead_data_rows(self, rows: list[dict[str, Any]]) -> None:
        off = self._data_row_offset()
        self.table.setSortingEnabled(False)
        total = off + len(rows)
        if self._filter_visible and total < 1:
            total = 1
        self.table.setRowCount(total)
        if self._filter_visible:
            for c in range(self.table.columnCount()):
                self.table.takeItem(0, c)
            install_filter_row(self.table, self.table.columnCount(), on_text_changed=self._schedule_filter_apply)
        for row_idx, row in enumerate(rows):
            tr = off + row_idx
            for col_idx, (_header, keys) in enumerate(_LEAD_COLUMNS):
                value = _value_for_column(row, keys)
                item = QTableWidgetItem(_display_value(value, keys[0], keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(tr, col_idx, item)
        sync_vertical_header_labels(self.table, filter_visible=self._filter_visible, data_row_count=len(rows))
        resize_data_table_columns_to_content(
            self.table,
            list(_LEAD_COLUMNS),
            self._source_rows,
            _value_for_lead_column,
            _format_lead_filter_cell,
        )
        self.table.setSortingEnabled(not self._filter_visible)

    def _apply_column_filters_refresh(self) -> None:
        if not self._filter_visible or not self._source_rows:
            return
        self._write_lead_data_rows(self._filtered_source_rows())

    def _on_filter_toggle(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            self._filter_apply_timer.stop()
            clear_filter_row_widgets(self.table)
        if self._source_rows:
            rows = self._filtered_source_rows() if checked else list(self._source_rows)
            self._write_lead_data_rows(rows)
        else:
            self._show_empty_lead_table()

    def _show_empty_lead_table(self) -> None:
        self._source_rows = []
        self.table.setSortingEnabled(False)
        clear_filter_row_widgets(self.table)
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = profile.get("token") or profile.get("accessToken") or profile.get("access_token") or profile.get("jwt")
        return str(token) if token else None

    def _lead_at_row(self, row: int) -> dict[str, Any] | None:
        if row < self._data_row_offset() or row >= self.table.rowCount():
            return None
        item = self.table.item(row, 0)
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        return data if isinstance(data, dict) else None

    def _lead_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        idx = self.table.indexAt(pos)
        if idx.isValid():
            return self._lead_at_row(idx.row())
        item = self.table.itemAt(pos)
        if item:
            return self._lead_at_row(item.row())
        return None

    def _comment_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        idx = self._comment_table.indexAt(pos)
        if idx.isValid():
            return self._comment_at_row(idx.row())
        item = self._comment_table.itemAt(pos)
        if item:
            return self._comment_at_row(item.row())
        return None

    def _on_comment_double_clicked(self, _item: QTableWidgetItem) -> None:
        self._on_update_comment_clicked()

    def _on_comment_context_menu(self, pos: QPoint) -> None:
        lead_id = self._selected_lead_id
        selected_comment = self._comment_at_pos(pos)
        menu = QMenu(self)
        menu.setStyleSheet(
            CONTEXT_MENU_STYLESHEET
            + " QMenu::item:disabled { background: #9ca3af; color: #6b7280; }"
            + " QMenu::item:disabled:selected, QMenu::item:disabled:hover {"
            + " background: #9ca3af; color: #6b7280; }"
        )
        add_action = menu.addAction("Add Comment")
        update_action = menu.addAction("Update Comment")
        delete_action = menu.addAction("Delete Comment")
        add_action.setEnabled(bool(lead_id) and self._can_comment_create)
        can_view_comment = self._can_comment_display or self._can_comment_edit
        update_action.setEnabled(selected_comment is not None and can_view_comment)
        delete_action.setEnabled(selected_comment is not None and self._can_comment_delete)
        action = menu.exec(QCursor.pos())
        if action == add_action:
            self._on_add_comment_clicked()
        elif action == update_action:
            if selected_comment is not None:
                row = self._comment_table.indexAt(pos).row()
                if row >= 0:
                    self._comment_table.selectRow(row)
            self._on_update_comment_clicked()
        elif action == delete_action:
            if selected_comment is not None:
                row = self._comment_table.indexAt(pos).row()
                if row >= 0:
                    self._comment_table.selectRow(row)
            self._on_delete_comment_clicked()

    def _comment_at_row(self, row: int) -> dict[str, Any] | None:
        if row < 0 or row >= len(self._comment_rows):
            return None
        return self._comment_rows[row]

    def _lead_id_from_row(self, lead: dict[str, Any] | None) -> str:
        if not isinstance(lead, dict):
            return ""
        lid = lead.get("leadId") or lead.get("id")
        return str(lid).strip() if lid is not None else ""

    def _render_comment_table(self) -> None:
        self._comment_table.clear()
        self._comment_table.setColumnCount(len(_LEAD_COMMENT_COLUMNS))
        self._comment_table.setHorizontalHeaderLabels([h for h, _ in _LEAD_COMMENT_COLUMNS])
        self._comment_table.setRowCount(len(self._comment_rows))
        for row_idx, row in enumerate(self._comment_rows):
            for col_idx, (_header, keys) in enumerate(_LEAD_COMMENT_COLUMNS):
                value = _value_for_column(row, keys)
                item = QTableWidgetItem(_display_value(value, keys[0], keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self._comment_table.setItem(row_idx, col_idx, item)
        resize_data_table_columns_to_content(
            self._comment_table,
            list(_LEAD_COMMENT_COLUMNS),
            self._comment_rows,
            lambda row, keys: (_value_for_column(row, keys), keys[0]),
            lambda value, _k="", _ks=(): _display_value(value, _k, _ks),
        )

    def _on_lead_selection_changed(self) -> None:
        row = self.table.currentRow()
        lead = self._lead_at_row(row)
        self._selected_lead_id = self._lead_id_from_row(lead)
        self._refresh_comments_for_selected_lead(show_message=False)

    def _refresh_comments_for_selected_lead(self, *, show_message: bool) -> None:
        lead_id = self._selected_lead_id
        if not lead_id:
            self._comment_rows = []
            self._render_comment_table()
            if show_message:
                show_auto_hiding_message(self, self._comment_message_label, "Select a lead row first.", error=True)
            return
        result = api_get_all_lead_comments_by_lead_id(lead_id, token=self._token())
        if not result.get("success"):
            self._comment_rows = []
            self._render_comment_table()
            show_auto_hiding_message(
                self,
                self._comment_message_label,
                str(result.get("message") or "Failed to load lead comments."),
                error=True,
            )
            return
        self._comment_rows = [r for r in (result.get("comments") or []) if isinstance(r, dict)]
        self._render_comment_table()
        if show_message:
            show_auto_hiding_message(
                self,
                self._comment_message_label,
                str(result.get("message") or "Comments loaded."),
                error=False,
            )

    def _on_add_comment_clicked(self) -> None:
        if not self._can_comment_create:
            show_auto_hiding_message(self, self._comment_message_label, "Require Permission.", error=True)
            return
        lead_id = self._selected_lead_id
        if not lead_id:
            show_auto_hiding_message(self, self._comment_message_label, "Select a lead row first.", error=True)
            return
        dlg = _LeadCommentDialog(self, title=f"Add Comment (Lead ID: {lead_id})", lead_id=str(lead_id), token=self._token())
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        body = dlg.payload()
        if not body.get("comment"):
            show_auto_hiding_message(self, self._comment_message_label, "Comment is required.", error=True)
            return
        result = api_add_lead_comment(lead_id, body, token=self._token())
        show_auto_hiding_message(
            self,
            self._comment_message_label,
            str(result.get("message") or ("Comment added." if result.get("success") else "Add comment failed.")),
            error=not bool(result.get("success")),
        )
        if result.get("success"):
            self._refresh_comments_for_selected_lead(show_message=False)

    def _on_update_comment_clicked(self) -> None:
        if not (self._can_comment_display or self._can_comment_edit):
            show_auto_hiding_message(self, self._comment_message_label, "Require Permission.", error=True)
            return
        row = self._comment_table.currentRow()
        data = self._comment_at_row(row)
        if not data:
            show_auto_hiding_message(self, self._comment_message_label, "Select a comment row to update.", error=True)
            return
        comment_id = data.get("commentId")
        if comment_id is None or str(comment_id).strip() == "":
            show_auto_hiding_message(self, self._comment_message_label, "Selected comment has no comment ID.", error=True)
            return
        dlg = _LeadCommentDialog(
            self,
            title="Lead Comment",
            lead_id=str(self._selected_lead_id or ""),
            token=self._token(),
            initial=data,
            view_edit_mode=True,
            allow_comment_edit=self._can_comment_edit,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if not self._can_comment_edit:
            return
        body = dlg.payload()
        if not body.get("comment"):
            show_auto_hiding_message(self, self._comment_message_label, "Comment is required.", error=True)
            return
        result = api_update_lead_comment_by_id(comment_id, body, token=self._token())
        show_auto_hiding_message(
            self,
            self._comment_message_label,
            str(result.get("message") or ("Comment updated." if result.get("success") else "Update comment failed.")),
            error=not bool(result.get("success")),
        )
        if result.get("success"):
            self._refresh_comments_for_selected_lead(show_message=False)

    def _on_delete_comment_clicked(self) -> None:
        if not self._can_comment_delete:
            show_auto_hiding_message(self, self._comment_message_label, "Require Permission.", error=True)
            return
        row = self._comment_table.currentRow()
        data = self._comment_at_row(row)
        if not data:
            show_auto_hiding_message(self, self._comment_message_label, "Select a comment row to delete.", error=True)
            return
        comment_id = data.get("commentId")
        if comment_id is None or str(comment_id).strip() == "":
            show_auto_hiding_message(self, self._comment_message_label, "Selected comment has no comment ID.", error=True)
            return
        reply = QMessageBox.question(
            self,
            "Delete Comment",
            f"Are you sure you want to delete comment '{comment_id}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = api_delete_lead_comment_by_id(comment_id, token=self._token())
        show_auto_hiding_message(
            self,
            self._comment_message_label,
            str(result.get("message") or ("Comment deleted." if result.get("success") else "Delete comment failed.")),
            error=not bool(result.get("success")),
        )
        if result.get("success"):
            self._refresh_comments_for_selected_lead(show_message=False)

    def _on_context_menu(self, pos: QPoint) -> None:
        clicked_item = self.table.itemAt(pos)
        if clicked_item is not None and clicked_item.row() >= self._data_row_offset():
            self.table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self.table.selectRow(clicked_item.row())
        lead = self._lead_at_pos(pos)
        if lead is None and clicked_item is not None and clicked_item.row() >= self._data_row_offset():
            lead = self._lead_at_row(clicked_item.row())
        menu = QMenu(self)
        menu.setStyleSheet(
            CONTEXT_MENU_STYLESHEET
            + " QMenu::item:disabled { background: #9ca3af; color: #6b7280; }"
            + " QMenu::item:disabled:selected, QMenu::item:disabled:hover {"
            + " background: #9ca3af; color: #6b7280; }"
        )
        add_action = menu.addAction("Add Lead")
        display_action = menu.addAction("Display Lead")
        edit_action = menu.addAction("Edit Lead")
        delete_action = menu.addAction("Delete Lead")
        add_action.setEnabled(self._can_create_lead)
        has_row = lead is not None
        display_action.setEnabled(has_row and self.on_edit_clicked is not None and self._can_display_lead)
        edit_action.setEnabled(has_row and self.on_edit_clicked is not None and self._can_edit_lead)
        delete_action.setEnabled(has_row and self._can_delete_lead)
        action = menu.exec(QCursor.pos())
        if action == add_action:
            self._emit_create_lead()
        elif action == display_action and lead is not None and self.on_edit_clicked:
            if not self._can_display_lead:
                show_auto_hiding_message(self, self._message_label, "Require Permission.", error=True)
                return
            self.on_edit_clicked(lead, False)
        elif action == edit_action and lead is not None and self.on_edit_clicked:
            if not self._can_edit_lead:
                show_auto_hiding_message(self, self._message_label, "Require Permission.", error=True)
                return
            self.on_edit_clicked(lead, True)
        elif action == delete_action and lead is not None:
            self._handle_delete_lead(lead)

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if item.row() < self._data_row_offset():
            return
        if not self._can_display_lead:
            show_auto_hiding_message(self, self._message_label, "Require Permission.", error=True)
            return
        lead = self._lead_at_row(item.row())
        if lead is not None and self.on_edit_clicked:
            self.on_edit_clicked(lead, False)

    def _handle_delete_lead(self, lead: dict[str, Any]) -> None:
        if not self._can_delete_lead:
            show_auto_hiding_message(self, self._message_label, "Require Permission.", error=True)
            return
        lead_id = lead.get("leadId") or lead.get("id")
        if lead_id is None:
            show_auto_hiding_message(self, self._message_label, "Cannot delete: Lead ID is missing.", error=True)
            return
        reply = QMessageBox.question(
            self,
            "Delete Lead",
            f"Are you sure you want to delete lead '{lead_id}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = api_delete_lead(lead_id, token=self._token())
        show_auto_hiding_message(
            self,
            self._message_label,
            str(result.get("message") or ("Deleted." if result.get("success") else "Delete failed.")),
            error=not bool(result.get("success")),
        )
        if result.get("success"):
            self.refresh()

    def refresh(self) -> None:
        prev_lead_id = self._selected_lead_id
        result = api_get_all_leads(token=self._token())
        if not result.get("success"):
            self._show_empty_lead_table()
            self._selected_lead_id = ""
            self._comment_rows = []
            self._render_comment_table()
            show_auto_hiding_message(self, self._message_label, str(result.get("message") or "Failed to load leads."), error=True)
            return
        rows = result.get("data") or []
        self._source_rows = [r for r in rows if isinstance(r, dict)]
        self.table.clear()
        self.table.setColumnCount(len(_LEAD_COLUMNS))
        self.table.setHorizontalHeaderLabels([h for h, _ in _LEAD_COLUMNS])
        rows_to_show = self._filtered_source_rows() if self._filter_visible else list(self._source_rows)
        self._write_lead_data_rows(rows_to_show)
        if self._source_rows:
            off = self._data_row_offset()
            displayed = self._filtered_source_rows() if self._filter_visible else list(self._source_rows)
            target_row = off
            prev = str(prev_lead_id or "").strip()
            if prev and displayed:
                for fi, row in enumerate(displayed):
                    lid = row.get("leadId") or row.get("id")
                    if lid is not None and str(lid).strip() == prev:
                        target_row = off + fi
                        break
            if displayed and off < self.table.rowCount():
                if target_row >= self.table.rowCount():
                    target_row = off
                self.table.selectRow(target_row)
                lead = self._lead_at_row(target_row)
                self._selected_lead_id = self._lead_id_from_row(lead)
                self._refresh_comments_for_selected_lead(show_message=False)
            else:
                self._selected_lead_id = ""
                self._comment_rows = []
                self._render_comment_table()
        else:
            self._selected_lead_id = ""
            self._refresh_comments_for_selected_lead(show_message=False)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        try:
            self._refresh_action_access()
            self.refresh()
        except Exception:
            traceback.print_exc()
