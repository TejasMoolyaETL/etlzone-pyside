"""Lead Company list page."""

from __future__ import annotations

import ast
import json
import re
import traceback
from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.api import api_delete_lead_company, api_get_all_lead_companies
from core.app_preferences import format_datetime_display, is_datetime_field
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.blank_display import is_blank_display_value
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
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.styles import CONTEXT_MENU_STYLESHEET

# Columns whose API values are master-config style objects: ``{ keyValue, category, seq, ... }``.
_LOOKUP_STYLE_COLUMN_KEYS: frozenset[str] = frozenset(
    {"city", "location", "region", "state", "country", "source", "status"}
)

_COMPANY_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Company", ("companyId", "id")),
    ("Company Name", ("companyName", "name")),
    ("Source", ("source",)),
    ("City", ("city",)),
    ("State", ("state",)),
    ("Country", ("country",)),
    ("Email 1", ("email1",)),
    ("Email 2", ("email2",)),
    ("Contact No 1", ("contactNo1",)),
    ("Contact No 2", ("contactNo2",)),
    ("Contact No 3", ("contactNo3",)),
    ("Billing address", ("billingAddress",)),
    ("Industry", ("industry", "indstry")),
    ("Status", ("status",)),
    ("Website", ("website",)),
    ("Comments", ("comments",)),
    ("Created At", ("createdAt", "created_at")),
    ("Created By", ("createdBy", "created_by")),
    ("Modified At", ("modifiedAt", "modified_at", "updatedAt", "updated_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
)


def _value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key), key
    return None, keys[0]


def _lookup_style_display(obj: dict[str, Any]) -> str:
    """Same display rule for Country, City, State, Source, Status: prefer ``keyValue`` on the object."""
    for k in ("keyValue", "key_value"):
        v = obj.get(k)
        if v is not None and not isinstance(v, (dict, list)):
            return str(v)
    for k in ("name", "category"):
        v = obj.get(k)
        if v is not None and not isinstance(v, (dict, list)):
            return str(v)
    return ""


def _format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, dict):
        if key in _LOOKUP_STYLE_COLUMN_KEYS:
            text = _lookup_style_display(value)
            return text if text else str(value)
        # Other nested dicts (rare in this list): shallow scan for a scalar label.
        def _extract_preferred(obj: Any, seen: set[int] | None = None) -> str:
            if seen is None:
                seen = set()
            if isinstance(obj, dict):
                oid = id(obj)
                if oid in seen:
                    return ""
                seen.add(oid)
                for k in ("keyValue", "key_value", "name", "category"):
                    v = obj.get(k)
                    if v is not None and not isinstance(v, (dict, list)):
                        return str(v)
                for v in obj.values():
                    t = _extract_preferred(v, seen)
                    if t:
                        return t
            elif isinstance(obj, list):
                for item in obj:
                    t = _extract_preferred(item, seen)
                    if t:
                        return t
            return ""

        text = _extract_preferred(value)
        if text:
            return text
        return str(value)
    if isinstance(value, str) and key in _LOOKUP_STYLE_COLUMN_KEYS:
        s = value.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                parsed = ast.literal_eval(s)
            except (ValueError, SyntaxError):
                try:
                    parsed = json.loads(s)
                except (ValueError, TypeError):
                    parsed = None
            if isinstance(parsed, dict):
                text = _lookup_style_display(parsed)
                return text if text else str(parsed)
        # Last resort: extract ``keyValue`` from serialized object text.
        m = re.search(r"""['"]keyValue['"]\s*:\s*['"]([^'"]+)['"]""", s)
        if m:
            return m.group(1)
    if isinstance(value, list):
        # Response uses ``contacts``: list[{id,name,mobile,email,...}] -> show contact names.
        names: list[str] = []
        for row in value:
            if isinstance(row, dict):
                n = row.get("name")
                if n is not None and str(n).strip():
                    names.append(str(n).strip())
        if names:
            return ", ".join(names)
        return str(len(value))
    return str(value)


class CompanyListPage(QWidget):
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
        self._can_create_company = True
        self._can_display_company = True
        self._can_edit_company = True
        self._can_delete_company = True
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
        hl.addWidget(QLabel("Lead: Company"))
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
        self._create_btn.clicked.connect(self._emit_create)
        hl.addWidget(self._create_btn)
        layout.addWidget(header)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(12)
        self._message_label = QLabel()
        self._message_label.setVisible(False)
        cl.addWidget(self._message_label)
        self.table = QTableWidget()
        apply_data_table_appearance(self.table)
        self.table.setSortingEnabled(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        attach_table_copy_shortcut(self.table)
        cl.addWidget(self.table, 1)
        layout.addWidget(content, 1)

    def _emit_create(self) -> None:
        if not self._can_create_company:
            show_auto_hiding_message(
                self,
                self._message_label,
                "Create disabled: missing step access lead-company-create.",
                error=True,
            )
            return
        if self.on_create_clicked:
            self.on_create_clicked()

    def _refresh_action_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_create_company = True
            self._can_display_company = True
            self._can_edit_company = True
            self._can_delete_company = True
        else:
            allowed = collect_allowed_action_names(steps)
            self._can_create_company = nav_action_visible("Lead: Company", "create", allowed)
            self._can_display_company = nav_action_visible("Lead: Company", "display", allowed)
            self._can_edit_company = nav_action_visible("Lead: Company", "edit", allowed)
            self._can_delete_company = nav_action_visible("Lead: Company", "delete", allowed)
        self._create_btn.setEnabled(self._can_create_company)
        self._create_btn.setToolTip("" if self._can_create_company else "Require Permission.")

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _schedule_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_source_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._source_rows,
            self.table,
            list(_COMPANY_COLUMNS),
            self._filter_visible,
            _value_for_column,
            _format_cell,
        )

    def _write_data_rows(self, rows: list[dict[str, Any]]) -> None:
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
        for r, row in enumerate(rows):
            tr = off + r
            for col, (_, keys) in enumerate(_COMPANY_COLUMNS):
                value, key_used = _value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(tr, col, item)
        sync_vertical_header_labels(self.table, filter_visible=self._filter_visible, data_row_count=len(rows))
        resize_data_table_columns_to_content(
            self.table,
            list(_COMPANY_COLUMNS),
            self._source_rows,
            _value_for_column,
            _format_cell,
        )
        self.table.setSortingEnabled(not self._filter_visible)

    def _apply_column_filters_refresh(self) -> None:
        if not self._filter_visible or not self._source_rows:
            return
        self._write_data_rows(self._filtered_source_rows())

    def _on_filter_toggle(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            self._filter_apply_timer.stop()
            clear_filter_row_widgets(self.table)
        if self._source_rows:
            rows = self._filtered_source_rows() if checked else list(self._source_rows)
            self._write_data_rows(rows)
        else:
            self._show_empty_table()

    def _show_empty_table(self) -> None:
        self._source_rows = []
        self.table.setSortingEnabled(False)
        clear_filter_row_widgets(self.table)
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

    def _get_company_at_row(self, row: int) -> dict[str, Any] | None:
        if row < self._data_row_offset() or row >= self.table.rowCount():
            return None
        item = self.table.item(row, 0)
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        return data if isinstance(data, dict) else None

    def _company_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        idx = self.table.indexAt(pos)
        if idx.isValid():
            return self._get_company_at_row(idx.row())
        item = self.table.itemAt(pos)
        if item:
            return self._get_company_at_row(item.row())
        return None

    def _on_context_menu(self, pos: QPoint) -> None:
        clicked_item = self.table.itemAt(pos)
        if clicked_item is not None and clicked_item.row() >= self._data_row_offset():
            self.table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self.table.selectRow(clicked_item.row())
        company = self._company_at_pos(pos)
        if company is None and clicked_item is not None and clicked_item.row() >= self._data_row_offset():
            company = self._get_company_at_row(clicked_item.row())
        menu = QMenu(self)
        menu.setStyleSheet(
            CONTEXT_MENU_STYLESHEET
            + " QMenu::item:disabled { background: #9ca3af; color: #6b7280; }"
            + " QMenu::item:disabled:selected, QMenu::item:disabled:hover {"
            + " background: #9ca3af; color: #6b7280; }"
        )
        add_action = menu.addAction("Add Company")
        display_action = menu.addAction("Display Company")
        edit_action = menu.addAction("Edit Company")
        delete_action = menu.addAction("Delete Company")
        add_action.setEnabled(self._can_create_company)
        has_row = company is not None
        display_action.setEnabled(
            has_row and self.on_edit_clicked is not None and self._can_display_company
        )
        edit_action.setEnabled(has_row and self.on_edit_clicked is not None and self._can_edit_company)
        delete_action.setEnabled(has_row and self._can_delete_company)
        action = menu.exec(QCursor.pos())
        if action == add_action:
            self._emit_create()
        elif action == display_action and company is not None and self.on_edit_clicked:
            if not self._can_display_company:
                show_auto_hiding_message(self, self._message_label, "Require Permission.", error=True)
                return
            self.on_edit_clicked(company, False)
        elif action == edit_action and company is not None and self.on_edit_clicked:
            if not self._can_edit_company:
                show_auto_hiding_message(self, self._message_label, "Require Permission.", error=True)
                return
            self.on_edit_clicked(company, True)
        elif action == delete_action and company is not None:
            self._handle_delete_company(company)

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if item.row() < self._data_row_offset():
            return
        company = self._get_company_at_row(item.row())
        if not self._can_display_company:
            show_auto_hiding_message(self, self._message_label, "Require Permission.", error=True)
            return
        if company is not None and self.on_edit_clicked:
            self.on_edit_clicked(company, False)

    def _handle_delete_company(self, company: dict[str, Any]) -> None:
        if not self._can_delete_company:
            show_auto_hiding_message(self, self._message_label, "Require Permission.", error=True)
            return
        cid = company.get("companyId") or company.get("id")
        if cid is None:
            show_auto_hiding_message(self, self._message_label, "Cannot delete: Company is missing.", error=True)
            return
        name = company.get("companyName") or company.get("name") or "this company"
        reply = QMessageBox.question(
            self,
            "Delete Company",
            f"Are you sure you want to delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = api_delete_lead_company(cid, token=self._token())
        show_auto_hiding_message(
            self,
            self._message_label,
            str(result.get("message") or ("Deleted." if result.get("success") else "Delete failed.")),
            error=not bool(result.get("success")),
        )
        if result.get("success"):
            self.refresh()

    def _load_companies(self) -> None:
        result = api_get_all_lead_companies(token=self._token())
        if not result.get("success"):
            self._show_empty_table()
            show_auto_hiding_message(
                self,
                self._message_label,
                str(result.get("message") or "Failed to load companies."),
                error=True,
            )
            return
        rows = result.get("data") or []
        self._source_rows = [r for r in rows if isinstance(r, dict)]
        self.table.clear()
        self.table.setColumnCount(len(_COMPANY_COLUMNS))
        self.table.setHorizontalHeaderLabels([h for h, _ in _COMPANY_COLUMNS])
        rows_to_show = self._filtered_source_rows() if self._filter_visible else list(self._source_rows)
        self._write_data_rows(rows_to_show)

    def refresh(self) -> None:
        self._load_companies()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        try:
            self._refresh_action_access()
            self._load_companies()
        except Exception:
            traceback.print_exc()
