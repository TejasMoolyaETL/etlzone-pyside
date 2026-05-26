"""Lead Company Contact Assignment list page (company + linked contacts)."""

from __future__ import annotations

import json
import traceback
from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QShowEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.api import (
    api_delete_contact_person_company_assignment,
    api_get_all_lead_companies,
)
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.data_table import (
    MIN_DATA_COL_WIDTH_PX,
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    data_row_offset,
    filter_dict_rows_by_column_edits,
    format_data_table_cell,
    install_filter_row,
    resize_data_table_columns_to_content,
    sync_vertical_header_labels,
)
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.styles import CONTEXT_MENU_STYLESHEET

# Left: companies (subset of fields for split view).
_COMPANY_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Company", ("companyId", "id")),
    ("Company Name", ("companyName", "name")),
    ("City", ("city", "citySeq")),
    ("State", ("state", "stateSeq")),
    ("Country", ("country", "countrySeq")),
    ("Status", ("status",)),
)

# Right: contacts returned by get-contact-by-company-id (flexible keys).
_CONTACT_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Assignment Id", ("assignmentId", "companyContactId", "id", "linkId")),
    ("Assignment Status", ("assignmentStatus", "assignment_status")),
    ("Hierarchy", ("hierarchy",)),
    ("Name", ("name", "contactPersonName")),
    ("Email", ("email", "email1")),
    ("Mobile", ("mobile", "contactNo")),
    ("Position", ("position", "designation")),
    ("Contact Status", ("status", "lead_contact_person_status", "statusSeq", "status_seq")),
)


def _pick(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k not in row:
            continue
        val = row[k]
        if val is not None:
            return val
    return None


def _lookup_key_value_label(obj: dict[str, Any]) -> str:
    for kk in ("keyValue", "key_value"):
        v = obj.get(kk)
        if v is not None and not isinstance(v, (dict, list)):
            return str(v)
    return ""


def _format_cell_value(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, dict):
        if "keyValue" in val or "key_value" in val:
            text = _lookup_key_value_label(val)
            if text:
                return text
        try:
            return json.dumps(val, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(val)
    if isinstance(val, list):
        try:
            return json.dumps(val, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(val)
    return str(val)


def _value_pick_tuple(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for k in keys:
        if k in row and row.get(k) is not None:
            return row.get(k), k
    return _pick(row, keys), keys[0]


def _format_cell_for_filter(
    value: Any, key: str = "", key_candidates: tuple[str, ...] = ()
) -> str:
    return format_data_table_cell(value, key, key_candidates)


class ContactPersonCompanyAssignmentListPage(QWidget):
    def __init__(
        self,
        on_create_clicked: Callable[[dict[str, Any] | None], None] | None = None,
        on_edit_clicked: Callable[[dict[str, Any], bool], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_create_clicked = on_create_clicked
        self.on_edit_clicked = on_edit_clicked
        self._company_source_rows: list[dict[str, Any]] = []
        self._company_filter_visible = False
        self._company_filter_apply_timer = QTimer(self)
        self._company_filter_apply_timer.setSingleShot(True)
        self._company_filter_apply_timer.setInterval(200)
        self._company_filter_apply_timer.timeout.connect(self._apply_company_column_filters_refresh)
        self._current_company_id: Any = None
        self._save_company_id_for_restore: Any = None
        self._can_create = True
        self._can_display = True
        self._can_edit = True
        self._can_delete = True
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
        hl.addWidget(QLabel("Lead: Company Contact Assignment"))
        hl.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        hl.addWidget(refresh_btn)
        self._company_filter_btn = QPushButton("Filters")
        self._company_filter_btn.setCheckable(True)
        self._company_filter_btn.setFixedWidth(100)
        self._company_filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._company_filter_btn.toggled.connect(self._on_company_filter_toggle)
        hl.addWidget(self._company_filter_btn)
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
        self._create_btn.clicked.connect(self._emit_create)
        hl.addWidget(self._create_btn)
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )

        content = QWidget()
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        content.setMinimumHeight(320)
        content.setMinimumWidth(560)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self._msg = QLabel()
        self._msg.setWordWrap(True)
        self._msg.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._msg.setVisible(False)
        content_layout.addWidget(self._msg)

        self._company_table = QTableWidget()
        apply_data_table_appearance(self._company_table)
        self._company_table.setSortingEnabled(False)
        self._company_table.setColumnCount(len(_COMPANY_COLUMNS))
        self._company_table.setHorizontalHeaderLabels([h for h, _ in _COMPANY_COLUMNS])
        ch = self._company_table.horizontalHeader()
        ch.setStretchLastSection(False)
        for col in range(len(_COMPANY_COLUMNS)):
            ch.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        ch.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        self._company_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._company_table.customContextMenuRequested.connect(self._on_company_context_menu)
        self._company_table.itemSelectionChanged.connect(self._on_company_selection_changed)
        attach_table_copy_shortcut(self._company_table)

        right_panel = QWidget()
        right_panel.setMinimumWidth(420)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._contacts_table = QTableWidget()
        apply_data_table_appearance(self._contacts_table)
        self._contacts_table.setColumnCount(len(_CONTACT_COLUMNS))
        self._contacts_table.setHorizontalHeaderLabels([h for h, _ in _CONTACT_COLUMNS])
        rh = self._contacts_table.horizontalHeader()
        rh.setStretchLastSection(False)
        for col in range(len(_CONTACT_COLUMNS)):
            rh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        rh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        self._contacts_table.setSortingEnabled(False)
        self._contacts_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._contacts_table.customContextMenuRequested.connect(self._on_contact_context_menu)
        self._contacts_table.itemDoubleClicked.connect(self._on_contact_double_click)
        attach_table_copy_shortcut(self._contacts_table)
        right_layout.addWidget(self._contacts_table, 1)

        self._contacts_msg = QLabel("")
        self._contacts_msg.setVisible(False)
        self._contacts_msg.setWordWrap(True)
        right_layout.addWidget(self._contacts_msg)

        main_split = QSplitter(Qt.Orientation.Horizontal)
        main_split.setChildrenCollapsible(False)
        main_split.setHandleWidth(6)
        main_split.setMinimumHeight(260)
        main_split.addWidget(self._company_table)
        main_split.addWidget(right_panel)
        main_split.setStretchFactor(0, 1)
        main_split.setStretchFactor(1, 1)
        main_split.setSizes([480, 520])
        content_layout.addWidget(main_split, 1)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

    def _emit_create(self) -> None:
        if not self._can_create:
            show_auto_hiding_message(
                self,
                self._msg,
                "Create disabled: missing step access lead-company-contact-assignment-create.",
                error=True,
            )
            return
        if self.on_create_clicked:
            self.on_create_clicked(None)

    def _refresh_action_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_create = True
            self._can_display = True
            self._can_edit = True
            self._can_delete = True
        else:
            allowed = collect_allowed_action_names(steps)
            lbl = "Lead: Company Contact Assignment"
            self._can_create = nav_action_visible(lbl, "create", allowed)
            self._can_display = nav_action_visible(lbl, "display", allowed)
            self._can_edit = nav_action_visible(lbl, "edit", allowed)
            self._can_delete = nav_action_visible(lbl, "delete", allowed)
        self._create_btn.setEnabled(self._can_create)
        self._create_btn.setToolTip("" if self._can_create else "Require Permission.")

    def _token(self) -> str | None:
        p = get_user_profile()
        t = p.get("token") or p.get("accessToken") or p.get("access_token") or p.get("jwt")
        return str(t) if t else None

    def _company_id(self, row: dict[str, Any]) -> Any:
        return row.get("companyId") or row.get("id")

    def _company_data_row_offset(self) -> int:
        return data_row_offset(self._company_filter_visible)

    def _selected_company_row_index(self) -> int:
        off = self._company_data_row_offset()
        sm = self._company_table.selectionModel()
        if sm is not None:
            srows = sm.selectedRows(0)
            if srows:
                r = int(srows[0].row())
                if r < off:
                    return -1
                return r
        r = self._company_table.currentRow()
        if r < off:
            return -1
        return r if r >= 0 else -1

    def _company_row_data(self, row_index: int) -> dict[str, Any] | None:
        off = self._company_data_row_offset()
        if row_index < off or row_index >= self._company_table.rowCount():
            return None
        it = self._company_table.item(row_index, 0)
        d = it.data(Qt.ItemDataRole.UserRole) if it else None
        return d if isinstance(d, dict) else None

    def _contacts_from_company_row(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        contacts = row.get("contacts")
        if isinstance(contacts, list):
            return [c for c in contacts if isinstance(c, dict)]
        return []

    def _clear_contacts_panel(self, *, message: str = "", error: bool = False) -> None:
        self._current_company_id = None
        self._contacts_table.setSortingEnabled(False)
        self._contacts_table.setRowCount(0)
        self._contacts_table.setSortingEnabled(True)
        self._resize_columns_to_content(self._contacts_table)
        if message:
            self._contacts_msg.setStyleSheet(FORM_ERROR_LABEL_STYLE if error else "")
            self._contacts_msg.setText(message)
            self._contacts_msg.setVisible(True)
        else:
            self._contacts_msg.setVisible(False)

    def _resize_columns_to_content(self, table: QTableWidget) -> None:
        table.resizeColumnsToContents()
        for col in range(table.columnCount()):
            if table.columnWidth(col) < MIN_DATA_COL_WIDTH_PX:
                table.setColumnWidth(col, MIN_DATA_COL_WIDTH_PX)

    def _schedule_company_filter_apply(self) -> None:
        if self._company_filter_visible:
            self._company_filter_apply_timer.start()

    def _filtered_company_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._company_source_rows,
            self._company_table,
            list(_COMPANY_COLUMNS),
            self._company_filter_visible,
            _value_pick_tuple,
            _format_cell_for_filter,
        )

    def _write_company_data_rows(self, rows: list[dict[str, Any]]) -> None:
        off = self._company_data_row_offset()
        self._company_table.blockSignals(True)
        self._company_table.setSortingEnabled(False)
        total = off + len(rows)
        if self._company_filter_visible and total < 1:
            total = 1
        self._company_table.setRowCount(total)
        if self._company_filter_visible:
            for c in range(self._company_table.columnCount()):
                self._company_table.takeItem(0, c)
            install_filter_row(
                self._company_table,
                self._company_table.columnCount(),
                on_text_changed=self._schedule_company_filter_apply,
            )
        for r, row in enumerate(rows):
            tr = off + r
            for c, (_, keys) in enumerate(_COMPANY_COLUMNS):
                val, ku = _value_pick_tuple(row, keys)
                it = QTableWidgetItem(format_data_table_cell(val, ku, keys))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 0:
                    it.setData(Qt.ItemDataRole.UserRole, row)
                self._company_table.setItem(tr, c, it)
        sync_vertical_header_labels(
            self._company_table,
            filter_visible=self._company_filter_visible,
            data_row_count=len(rows),
        )
        resize_data_table_columns_to_content(
            self._company_table,
            list(_COMPANY_COLUMNS),
            self._company_source_rows,
            _value_pick_tuple,
            _format_cell_for_filter,
        )
        self._company_table.setSortingEnabled(not self._company_filter_visible)
        self._company_table.blockSignals(False)

    def _apply_company_column_filters_refresh(self) -> None:
        if not self._company_filter_visible or not self._company_source_rows:
            return
        self._write_company_data_rows(self._filtered_company_rows())

    def _on_company_filter_toggle(self, checked: bool) -> None:
        self._company_filter_visible = checked
        if not checked:
            self._company_filter_apply_timer.stop()
            clear_filter_row_widgets(self._company_table)
        if self._company_source_rows:
            rows = self._filtered_company_rows() if checked else list(self._company_source_rows)
            self._write_company_data_rows(rows)
        else:
            self._company_table.setSortingEnabled(False)
            clear_filter_row_widgets(self._company_table)
            self._company_table.setRowCount(0)
            self._company_table.setColumnCount(len(_COMPANY_COLUMNS))
            self._company_table.setHorizontalHeaderLabels([h for h, _ in _COMPANY_COLUMNS])

    def _populate_companies(self, rows: list[dict[str, Any]]) -> None:
        self._company_source_rows = rows
        rows_to_show = self._filtered_company_rows() if self._company_filter_visible else list(rows)
        self._write_company_data_rows(rows_to_show)

    def _populate_contacts(self, rows: list[dict[str, Any]]) -> None:
        self._contacts_table.setSortingEnabled(False)
        self._contacts_table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, (_, keys) in enumerate(_CONTACT_COLUMNS):
                val, ku = _value_pick_tuple(row, keys)
                it = QTableWidgetItem(format_data_table_cell(val, ku, keys))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 0:
                    it.setData(Qt.ItemDataRole.UserRole, row)
                self._contacts_table.setItem(r, c, it)
        sync_vertical_header_labels(
            self._contacts_table,
            filter_visible=False,
            data_row_count=len(rows),
        )
        self._resize_columns_to_content(self._contacts_table)
        self._contacts_table.setSortingEnabled(True)

    def _restore_company_selection(self, company_id: Any) -> bool:
        if company_id is None:
            return False
        target = str(company_id)
        off = self._company_data_row_offset()
        for row in range(off, self._company_table.rowCount()):
            data = self._company_row_data(row)
            if not data:
                continue
            cid = self._company_id(data)
            if cid is not None and str(cid) == target:
                self._company_table.setCurrentCell(row, 0)
                self._company_table.selectRow(row)
                return True
        return False

    def refresh(self) -> None:
        self._save_company_id_for_restore = self._current_company_id
        token = self._token()
        result = api_get_all_lead_companies(token=token)
        if not result.get("success"):
            show_auto_hiding_message(
                self, self._msg, str(result.get("message") or "Failed to load companies."), error=True
            )
            self._populate_companies([])
            self._clear_contacts_panel(message="Select a company after companies load.")
            self._save_company_id_for_restore = None
            return
        show_auto_hiding_message(self, self._msg, "")
        rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
        self._populate_companies(rows)
        restored = False
        if self._save_company_id_for_restore is not None:
            restored = self._restore_company_selection(self._save_company_id_for_restore)
        self._save_company_id_for_restore = None
        if not rows:
            self._clear_contacts_panel(message="No companies returned.")
        else:
            if not restored:
                self._company_table.selectRow(self._company_data_row_offset())
            # Always sync right table from the freshly fetched company row data.
            self._on_company_selection_changed()

    def _on_company_selection_changed(self) -> None:
        idx = self._selected_company_row_index()
        if idx < 0:
            self._clear_contacts_panel()
            return
        data = self._company_row_data(idx)
        if not data:
            self._clear_contacts_panel()
            return
        cid = self._company_id(data)
        if cid is None:
            self._clear_contacts_panel(message="Selected company is missing a company id.", error=True)
            return
        self._current_company_id = cid
        self._contacts_msg.setVisible(False)
        contacts = self._contacts_from_company_row(data)
        self._populate_contacts(contacts)
        if not contacts:
            self._contacts_msg.setStyleSheet("")
            self._contacts_msg.setText("No contacts linked to this company.")
            self._contacts_msg.setVisible(True)

    def _contact_row_data(self, row: int) -> dict[str, Any] | None:
        if row < 0 or row >= self._contacts_table.rowCount():
            return None
        it = self._contacts_table.item(row, 0)
        d = it.data(Qt.ItemDataRole.UserRole) if it else None
        return d if isinstance(d, dict) else None

    def _first_contact_row_with_assignment(self) -> tuple[int, dict[str, Any]] | None:
        for r in range(self._contacts_table.rowCount()):
            row = self._contact_row_data(r)
            if row and (
                row.get("assignmentId") is not None
                or row.get("companyContactId") is not None
                or row.get("id") is not None
                or row.get("linkId") is not None
            ):
                return r, row
        return None

    def _assignment_row_id(self, row: dict[str, Any] | None) -> Any:
        if not isinstance(row, dict):
            return None
        return row.get("assignmentId") or row.get("companyContactId") or row.get("id") or row.get("linkId")

    def _status_seq_from_row(self, row: dict[str, Any]) -> Any | None:
        for key in ("assignmentStatus", "assignment_status", "status", "statusSeq", "status_seq"):
            if key not in row:
                continue
            v = row.get(key)
            if v is None:
                continue
            if isinstance(v, dict):
                seq = v.get("seq")
                if seq is None:
                    continue
                if isinstance(seq, int):
                    return seq
                s = str(seq).strip()
                if s.isdigit():
                    return int(s)
                return seq
            if isinstance(v, int):
                return v
            s = str(v).strip()
            if s.isdigit():
                return int(s)
        return None

    def _prefill_for_add(self, company_row: dict[str, Any] | None, contact_row: dict[str, Any] | None) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if isinstance(company_row, dict):
            cid = self._company_id(company_row)
            if cid is not None:
                out["companyId"] = cid
        _ = contact_row
        return out

    def _enrich_contact_with_company(self, contact_row: dict[str, Any]) -> dict[str, Any]:
        out = dict(contact_row)
        idx = self._selected_company_row_index()
        company_row = self._company_row_data(idx) if idx >= 0 else None
        if isinstance(company_row, dict):
            cid = self._company_id(company_row)
            if cid is not None:
                out["companyId"] = cid
            out["company"] = company_row
        return out

    def _show_assignment_context_menu(self, contact_row: dict[str, Any] | None, global_pos: QPoint) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(
            CONTEXT_MENU_STYLESHEET
            + " QMenu::item:disabled { background: #9ca3af; color: #6b7280; }"
            + " QMenu::item:disabled:selected, QMenu::item:disabled:hover {"
            + " background: #9ca3af; color: #6b7280; }"
        )
        add = menu.addAction("Add assignment")
        view = menu.addAction("Display assignment")
        edit = menu.addAction("Edit assignment")
        delete = menu.addAction("Delete assignment")
        has_assignment = self._assignment_row_id(contact_row) is not None
        add.setEnabled(self._can_create)
        view.setEnabled(has_assignment and self.on_edit_clicked is not None and self._can_display)
        edit.setEnabled(has_assignment and self.on_edit_clicked is not None and self._can_edit)
        delete.setEnabled(has_assignment and self._can_delete)
        act = menu.exec(global_pos)
        if act == add:
            if not self._can_create:
                show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
                return
            if self.on_create_clicked:
                idx = self._selected_company_row_index()
                company_row = self._company_row_data(idx) if idx >= 0 else None
                self.on_create_clicked(self._prefill_for_add(company_row, contact_row))
        elif act in (view, edit) and contact_row and self.on_edit_clicked and has_assignment:
            if act == view and not self._can_display:
                show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
                return
            if act == edit and not self._can_edit:
                show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
                return
            self.on_edit_clicked(self._enrich_contact_with_company(contact_row), act == edit)
        elif act == delete and contact_row and has_assignment:
            if not self._can_delete:
                show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
                return
            rid = self._assignment_row_id(contact_row)
            if rid is None:
                return
            if (
                QMessageBox.question(
                    self,
                    "Delete assignment",
                    "Are you sure you want to delete this assignment?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                != QMessageBox.StandardButton.Yes
            ):
                return
            res = api_delete_contact_person_company_assignment(rid, token=self._token())
            show_auto_hiding_message(self, self._msg, str(res.get("message") or ""), error=not bool(res.get("success")))
            if res.get("success"):
                # Optimistic UI update so deleted row disappears immediately.
                kept_rows: list[dict[str, Any]] = []
                for r in range(self._contacts_table.rowCount()):
                    row_obj = self._contact_row_data(r)
                    if not isinstance(row_obj, dict):
                        continue
                    if self._assignment_row_id(row_obj) == rid:
                        continue
                    kept_rows.append(row_obj)
                self._populate_contacts([r for r in kept_rows if isinstance(r, dict)])
                if not kept_rows:
                    self._contacts_msg.setStyleSheet("")
                    self._contacts_msg.setText("No contacts linked to this company.")
                    self._contacts_msg.setVisible(True)
                # Then sync with backend source of truth.
                QTimer.singleShot(150, self.refresh)

    def _on_contact_double_click(self, item: QTableWidgetItem) -> None:
        row = self._contact_row_data(item.row())
        if not self._can_display:
            show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
            return
        if row and self.on_edit_clicked and self._assignment_row_id(row) is not None:
            self.on_edit_clicked(self._enrich_contact_with_company(row), False)

    def _on_company_context_menu(self, pos: QPoint) -> None:
        clicked = self._company_table.itemAt(pos)
        if clicked is not None and clicked.row() >= self._company_data_row_offset():
            self._company_table.setCurrentCell(clicked.row(), clicked.column())
            self._company_table.selectRow(clicked.row())
        idx = self._company_table.indexAt(pos)
        company_row: dict[str, Any] | None = None
        if idx.isValid() and idx.row() >= self._company_data_row_offset():
            company_row = self._company_row_data(idx.row())
        if company_row is None and clicked is not None and clicked.row() >= self._company_data_row_offset():
            company_row = self._company_row_data(clicked.row())
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add = menu.addAction("Add assignment")
        add.setEnabled(self._can_create)
        act = menu.exec(QCursor.pos())
        if act == add:
            if not self._can_create:
                show_auto_hiding_message(self, self._msg, "Require Permission.", error=True)
                return
            if self.on_create_clicked:
                cr = self._contacts_table.currentRow()
                selected_contact = self._contact_row_data(cr) if cr >= 0 else None
                self.on_create_clicked(self._prefill_for_add(company_row, selected_contact))

    def _on_contact_context_menu(self, pos: QPoint) -> None:
        clicked = self._contacts_table.itemAt(pos)
        if clicked is not None:
            self._contacts_table.setCurrentCell(clicked.row(), clicked.column())
            self._contacts_table.selectRow(clicked.row())
        idx = self._contacts_table.indexAt(pos)
        row = self._contact_row_data(idx.row()) if idx.isValid() else None
        self._show_assignment_context_menu(row, QCursor.pos())

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        try:
            self._refresh_action_access()
            self.refresh()
        except Exception:
            traceback.print_exc()
