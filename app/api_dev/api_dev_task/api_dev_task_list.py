"""API Dev Task list page."""

from __future__ import annotations

import json
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

from core.api import api_delete_api_task_by_id, api_get_all_api_tasks
from core.app_preferences import format_datetime_display, is_datetime_field
from core.user_context import get_user_profile
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

_COL_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Task Id", ("taskId", "id")),
    ("API Id", ("apiId", "api_id")),
    ("Summary", ("summary",)),
    ("Description", ("desc", "description")),
    ("Status", ("status",)),
    ("Created By", ("createdBy", "created_by")),
    ("Created At", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified At", ("modifiedAt", "modified_at", "updatedAt", "updated_at")),
)


def _value_for_col(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for key in keys:
        if key in row:
            return row.get(key), key
    return None, keys[0]


def _format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


class APIDevTaskPage(QWidget):
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
        hl.addWidget(QLabel("API: Dev Tasks"))
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
        create_btn.clicked.connect(lambda: self.on_create_clicked() if self.on_create_clicked else None)
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

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = profile.get("token") or profile.get("accessToken") or profile.get("access_token") or profile.get("jwt")
        return str(token) if token else None

    def _data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _schedule_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._source_rows,
            self.table,
            list(_COL_SPEC),
            self._filter_visible,
            _value_for_col,
            _format_cell,
        )

    def _write_rows(self, rows: list[dict[str, Any]]) -> None:
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
            for c, (_, keys) in enumerate(_COL_SPEC):
                v, k = _value_for_col(row, keys)
                it = QTableWidgetItem(_format_cell(v, k, keys))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if c == 0:
                    it.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(tr, c, it)
        sync_vertical_header_labels(self.table, filter_visible=self._filter_visible, data_row_count=len(rows))
        resize_data_table_columns_to_content(self.table, list(_COL_SPEC), self._source_rows, _value_for_col, _format_cell)
        self.table.setSortingEnabled(not self._filter_visible)

    def _apply_column_filters_refresh(self) -> None:
        if not self._filter_visible or not self._source_rows:
            return
        self._write_rows(self._filtered_rows())

    def _on_filter_toggle(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            self._filter_apply_timer.stop()
            clear_filter_row_widgets(self.table)
        if self._source_rows:
            self._write_rows(self._filtered_rows() if checked else list(self._source_rows))
        else:
            self._show_empty()

    def _show_empty(self) -> None:
        self._source_rows = []
        self.table.setSortingEnabled(False)
        clear_filter_row_widgets(self.table)
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

    def _get_row(self, table_row: int) -> dict[str, Any] | None:
        if table_row < self._data_row_offset() or table_row >= self.table.rowCount():
            return None
        it = self.table.item(table_row, 0)
        rec = it.data(Qt.ItemDataRole.UserRole) if it else None
        return rec if isinstance(rec, dict) else None

    def _selected_row(self) -> dict[str, Any] | None:
        items = self.table.selectedItems()
        if not items:
            return None
        return self._get_row(items[0].row())

    def _on_context_menu(self, _pos: QPoint) -> None:
        row = self._selected_row()
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Add API Task")
        display_action = menu.addAction("Display API Task")
        edit_action = menu.addAction("Edit API Task")
        delete_action = menu.addAction("Delete API Task")
        display_action.setEnabled(row is not None and self.on_edit_clicked is not None)
        edit_action.setEnabled(row is not None and self.on_edit_clicked is not None)
        delete_action.setEnabled(row is not None)
        action = menu.exec(QCursor.pos())
        if action == add_action and self.on_create_clicked:
            self.on_create_clicked()
        elif action == display_action and row and self.on_edit_clicked:
            self.on_edit_clicked(row, False)
        elif action == edit_action and row and self.on_edit_clicked:
            self.on_edit_clicked(row, True)
        elif action == delete_action and row:
            self._remove_row(row)

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if item.row() < self._data_row_offset():
            return
        row = self._get_row(item.row())
        if row is not None and self.on_edit_clicked:
            self.on_edit_clicked(row, False)

    def _remove_row(self, row: dict[str, Any]) -> None:
        tid = row.get("taskId") or row.get("id")
        if tid is None:
            show_auto_hiding_message(self, self._message_label, "Cannot delete: task id missing.", error=True)
            return
        reply = QMessageBox.question(
            self,
            "Delete API Task",
            f"Delete task '{row.get('summary') or tid}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = api_delete_api_task_by_id(tid, token=self._token())
        show_auto_hiding_message(
            self,
            self._message_label,
            str(result.get("message") or ("Deleted." if result.get("success") else "Delete failed.")),
            error=not bool(result.get("success")),
        )
        if result.get("success"):
            self.refresh()

    def _load_rows(self) -> None:
        result = api_get_all_api_tasks(token=self._token())
        if not result.get("success"):
            self._show_empty()
            show_auto_hiding_message(
                self, self._message_label, str(result.get("message") or "Failed to load API tasks."), error=True
            )
            return
        rows = result.get("data") or []
        self._source_rows = [r for r in rows if isinstance(r, dict)]
        self.table.clear()
        self.table.setColumnCount(len(_COL_SPEC))
        self.table.setHorizontalHeaderLabels([h for h, _ in _COL_SPEC])
        rows_to_show = self._filtered_rows() if self._filter_visible else list(self._source_rows)
        self._write_rows(rows_to_show)

    def refresh(self) -> None:
        self._load_rows()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._load_rows()
