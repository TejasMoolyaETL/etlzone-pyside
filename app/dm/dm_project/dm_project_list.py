"""DM: Project list page."""

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

from app.dm.dm_project.dm_project_fields import auth_token, format_master_display
from core.api import api_delete_dm_project, api_get_all_dm_projects
from core.app_preferences import (
    format_date_display,
    format_datetime_display,
    is_date_only_field,
    is_datetime_field,
)
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

_LOOKUP_STYLE_COLUMN_KEYS: frozenset[str] = frozenset(
    {
        "srcLandscape",
        "tgtLandscape",
        "migrationType",
        "status",
        "deliveryModel",
        "leadSource",
        "laptopOwnership",
        "accomadationOwnership",
        "accommodationOwnership",
        "travelExpenseOwnership",
        "perDiemOwnership",
        "extractionOwnership",
        "transformationOwnership",
        "loadingOwnership",
    }
)

# Column order mirrors the create/edit form: identity → migration → clients →
# commercial ownership → scope/ownership pairs → notes.
_PROJECT_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Project Id", ("id", "projectId")),
    ("Project Name", ("projectName",)),
    ("Status", ("status",)),
    ("Client Company", ("clientCompanyName", "clientCompanyId")),
    ("Region", ("region",)),
    ("Delivery Model", ("deliveryModel", "delivery_model")),
    ("Source Landscape", ("srcLandscape", "src_landscape")),
    ("Target Landscape", ("tgtLandscape", "tgt_landscape")),
    ("Migration Type", ("migrationType", "migration_type")),
    ("Start Date", ("startDate", "start_date")),
    ("Go-Live Date", ("goLiveDate", "go_live_date")),
    ("Implementation Partner", ("implementationPartnerName", "implementationPartnerId")),
    ("End Client", ("endClientName", "endClientId")),
    ("Intermediate Client 1", ("intermediateClient1Name", "intermediateClient1Id")),
    ("Intermediate Client 2", ("intermediateClient2Name", "intermediateClient2Id")),
    ("Intermediate Client 3", ("intermediateClient3Name", "intermediateClient3Id")),
    ("Intermediate Client 4", ("intermediateClient4Name", "intermediateClient4Id")),
    ("Lead Source", ("leadSource", "lead_source")),
    ("Laptop Ownership", ("laptopOwnership",)),
    ("Accommodation Ownership", ("accomadationOwnership", "accommodationOwnership")),
    ("Travel Expense Ownership", ("travelExpenseOwnership",)),
    ("Per Diem Ownership", ("perDiemOwnership",)),
    ("Extraction Scope", ("extractionScope",)),
    ("Extraction Ownership", ("extractionOwnership",)),
    ("Transformation Scope", ("transformationScope",)),
    ("Transformation Ownership", ("transformationOwnership",)),
    ("Load Scope", ("loadScope",)),
    ("Loading Ownership", ("loadingOwnership",)),
    ("Comment At ETLZone", ("commentAtEtlzone",)),
)


def _is_master_lookup_shaped(val: Any) -> bool:
    if not isinstance(val, dict):
        return False
    if val.get("keyValue") is not None or val.get("key_value") is not None:
        return True
    inner = val.get("data") if isinstance(val.get("data"), dict) else None
    if inner is not None and (
        inner.get("keyValue") is not None or inner.get("key_value") is not None
    ):
        return True
    return False


def _value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    first_scalar: tuple[Any, str] | None = None
    for key in keys:
        if key not in row:
            continue
        val = row.get(key)
        if val is None:
            continue
        if _is_master_lookup_shaped(val):
            return val, key
        if first_scalar is None:
            first_scalar = (val, key)
    if first_scalar is not None:
        return first_scalar
    return None, keys[0]


def _unwrap_master_value(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if _is_master_lookup_shaped(value):
            inner = value.get("data")
            return inner if isinstance(inner, dict) else value
        return None
    if isinstance(value, list) and len(value) == 1:
        return _unwrap_master_value(value[0])
    if isinstance(value, str):
        s = value.strip()
        if len(s) < 2:
            return None
        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
            try:
                parsed = ast.literal_eval(s)
            except (ValueError, SyntaxError):
                try:
                    parsed = json.loads(s)
                except (ValueError, TypeError):
                    parsed = None
            if parsed is not None:
                return _unwrap_master_value(parsed)
    return None


def _format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if is_date_only_field(key, key_candidates):
        return format_date_display(value)
    lookup_keys = _LOOKUP_STYLE_COLUMN_KEYS.intersection(key_candidates or (key,))
    if lookup_keys:
        row = _unwrap_master_value(value)
        if row is not None:
            text = format_master_display(row)
            if text:
                return text
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, dict):
        if key in _LOOKUP_STYLE_COLUMN_KEYS:
            text = format_master_display(value)
            return text if text else ""
        for k in ("keyValue", "key_value", "name", "label"):
            t = str(value.get(k) or "").strip()
            if t:
                return t
        return ""
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
                text = format_master_display(parsed)
                return text if text else ""
        m = re.search(r"""['"]keyValue['"]\s*:\s*['"]([^'"]+)['"]""", s)
        if m:
            return m.group(1)
    return str(value)


def _is_valid_project_row(row: dict[str, Any]) -> bool:
    pid = row.get("id")
    if pid is None:
        pid = row.get("projectId")
    if pid is None:
        return False
    if str(pid).strip() == "":
        return False
    return True


class DmProjectListPage(QWidget):
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
        hl.addWidget(QLabel("DM: Project"))
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

        create_btn = QPushButton("Create")
        create_btn.setFixedWidth(100)
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(
            lambda: self.on_create_clicked() if self.on_create_clicked else None
        )
        hl.addWidget(create_btn)
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

    def _data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _schedule_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_source_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._source_rows,
            self.table,
            list(_PROJECT_COLUMNS),
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
            install_filter_row(
                self.table,
                self.table.columnCount(),
                on_text_changed=self._schedule_filter_apply,
            )
        for r, row in enumerate(rows):
            tr = off + r
            for col, (_, keys) in enumerate(_PROJECT_COLUMNS):
                value, key_used = _value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(tr, col, item)
        sync_vertical_header_labels(
            self.table,
            filter_visible=self._filter_visible,
            data_row_count=len(rows),
        )
        resize_data_table_columns_to_content(
            self.table,
            list(_PROJECT_COLUMNS),
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

    def _get_project_at_row(self, row: int) -> dict[str, Any] | None:
        if row < self._data_row_offset() or row >= self.table.rowCount():
            return None
        item = self.table.item(row, 0)
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        return data if isinstance(data, dict) else None

    def _project_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        idx = self.table.indexAt(pos)
        if idx.isValid():
            return self._get_project_at_row(idx.row())
        item = self.table.itemAt(pos)
        if item:
            return self._get_project_at_row(item.row())
        return None

    def _on_context_menu(self, pos: QPoint) -> None:
        clicked_item = self.table.itemAt(pos)
        if clicked_item is not None and clicked_item.row() >= self._data_row_offset():
            self.table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self.table.selectRow(clicked_item.row())
        project = self._project_at_pos(pos)
        if project is None and clicked_item is not None and clicked_item.row() >= self._data_row_offset():
            project = self._get_project_at_row(clicked_item.row())
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Add Project")
        display_action = menu.addAction("Display Project")
        edit_action = menu.addAction("Edit Project")
        delete_action = menu.addAction("Delete Project")
        display_action.setEnabled(project is not None and self.on_edit_clicked is not None)
        edit_action.setEnabled(project is not None and self.on_edit_clicked is not None)
        delete_action.setEnabled(project is not None)
        action = menu.exec(QCursor.pos())
        if action == add_action and self.on_create_clicked:
            self.on_create_clicked()
        elif action == display_action and project is not None and self.on_edit_clicked:
            self.on_edit_clicked(project, False)
        elif action == edit_action and project is not None and self.on_edit_clicked:
            self.on_edit_clicked(project, True)
        elif action == delete_action and project is not None:
            self._handle_delete(project)

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if item.row() < self._data_row_offset():
            return
        project = self._get_project_at_row(item.row())
        if project is not None and self.on_edit_clicked:
            self.on_edit_clicked(project, False)

    def _handle_delete(self, project: dict[str, Any]) -> None:
        pid = project.get("id") or project.get("projectId")
        if pid is None:
            show_auto_hiding_message(
                self, self._message_label, "Cannot delete: Project ID is missing.", error=True
            )
            return
        name = str(project.get("projectName") or "this project")
        reply = QMessageBox.question(
            self,
            "Delete Project",
            f"Are you sure you want to delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = api_delete_dm_project(pid, token=auth_token())
        show_auto_hiding_message(
            self,
            self._message_label,
            str(result.get("message") or ("Deleted." if result.get("success") else "Delete failed.")),
            error=not bool(result.get("success")),
        )
        if result.get("success"):
            self.refresh()

    def _load_projects(self) -> None:
        result = api_get_all_dm_projects(token=auth_token())
        if not result.get("success"):
            self._show_empty_table()
            show_auto_hiding_message(
                self,
                self._message_label,
                str(result.get("message") or "Failed to load projects."),
                error=True,
            )
            return
        rows = result.get("data") or []
        self._source_rows = [
            r for r in rows if isinstance(r, dict) and _is_valid_project_row(r)
        ]
        show_auto_hiding_message(self, self._message_label, "", error=False)
        self.table.clear()
        self.table.setColumnCount(len(_PROJECT_COLUMNS))
        self.table.setHorizontalHeaderLabels([h for h, _ in _PROJECT_COLUMNS])
        rows_to_show = self._filtered_source_rows() if self._filter_visible else list(self._source_rows)
        self._write_data_rows(rows_to_show)

    def refresh(self) -> None:
        self._load_projects()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        try:
            self._load_projects()
        except Exception:
            traceback.print_exc()
