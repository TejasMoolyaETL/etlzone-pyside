"""DMT - Category list page for DMT Tracker."""

from __future__ import annotations

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

from core.api import api_delete_category, api_get_all_categories
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

_CATEGORY_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Category Id", ("categoryId", "id")),
    ("Category Name", ("categoryName", "name")),
    ("Created At", ("createdAt", "created_at")),
    ("Created By", ("createdBy", "created_by")),
    ("Modified At", ("modifiedAt", "modified_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
)


def _category_value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key), key
    return None, keys[0]


def _format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    return str(value)


class CategoryListPage(QWidget):
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
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        header_layout.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        header_layout.addWidget(QLabel("DMT - Category"))
        header_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._load_categories)
        header_layout.addWidget(refresh_btn)

        self._filter_btn = QPushButton("Filters")
        self._filter_btn.setCheckable(True)
        self._filter_btn.setChecked(False)
        self._filter_btn.setFixedWidth(100)
        self._filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_btn.toggled.connect(self._on_filter_toggle)
        header_layout.addWidget(self._filter_btn)

        create_btn = QPushButton("Create")
        create_btn.setFixedWidth(100)
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(lambda: self.on_create_clicked() if self.on_create_clicked else None)
        header_layout.addWidget(create_btn)
        layout.addWidget(header)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        self._message_label = QLabel()
        self._message_label.setVisible(False)
        content_layout.addWidget(self._message_label)

        self.table = QTableWidget()
        apply_data_table_appearance(self.table)
        self.table.setSortingEnabled(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        attach_table_copy_shortcut(self.table)
        content_layout.addWidget(self.table, 1)
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
            list(_CATEGORY_COLUMN_SPEC),
            self._filter_visible,
            _category_value_for_column,
            _format_cell,
        )

    def _write_data_rows(self, rows: list[dict[str, Any]]) -> None:
        off = self._data_row_offset()
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
            for col, (_, keys) in enumerate(_CATEGORY_COLUMN_SPEC):
                value, key_used = _category_value_for_column(row, keys)
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
            list(_CATEGORY_COLUMN_SPEC),
            self._source_rows,
            _category_value_for_column,
            _format_cell,
        )
        self.table.setSortingEnabled(not self._filter_visible)

    def _apply_column_filters_refresh(self) -> None:
        if not self._filter_visible:
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

    def _get_category_at_row(self, row: int) -> dict[str, Any] | None:
        if row < self._data_row_offset() or row >= self.table.rowCount():
            return None
        item = self.table.item(row, 0)
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        return data if isinstance(data, dict) else None

    def _category_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        idx = self.table.indexAt(pos)
        if idx.isValid():
            return self._get_category_at_row(idx.row())
        item = self.table.itemAt(pos)
        if item:
            return self._get_category_at_row(item.row())
        return None

    def _on_context_menu(self, pos: QPoint) -> None:
        category = self._category_at_pos(pos)
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Add Category")
        display_action = menu.addAction("Display Category")
        edit_action = menu.addAction("Edit Category")
        delete_action = menu.addAction("Delete Category")
        display_action.setEnabled(category is not None and self.on_edit_clicked is not None)
        edit_action.setEnabled(category is not None and self.on_edit_clicked is not None)
        delete_action.setEnabled(category is not None)
        action = menu.exec(QCursor.pos())
        if action == add_action and self.on_create_clicked:
            self.on_create_clicked()
        elif action == display_action and category is not None and self.on_edit_clicked:
            self.on_edit_clicked(category, False)
        elif action == edit_action and category is not None and self.on_edit_clicked:
            self.on_edit_clicked(category, True)
        elif action == delete_action and category is not None:
            self._handle_delete_category(category)

    def _handle_delete_category(self, category: dict[str, Any]) -> None:
        category_id = category.get("categoryId") or category.get("id")
        if category_id is None:
            show_auto_hiding_message(self, self._message_label, "Cannot delete: Category ID is missing.", error=True)
            return
        name = category.get("categoryName") or "this category"
        reply = QMessageBox.question(
            self,
            "Delete Category",
            f"Are you sure you want to delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_delete_category(category_id, token=token)
        if result.get("success"):
            show_auto_hiding_message(self, self._message_label, str(result.get("message") or "Category deleted."), error=False)
            QTimer.singleShot(700, self._load_categories)
        else:
            show_auto_hiding_message(self, self._message_label, str(result.get("message") or "Failed to delete category."), error=True)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._load_categories()

    def refresh(self) -> None:
        self._load_categories()

    def _load_categories(self) -> None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_categories(token=token)
        if not result.get("success"):
            show_auto_hiding_message(self, self._message_label, str(result.get("message") or "Failed to load categories."), error=True)
            self._show_empty_table()
            return
        rows = result.get("data") or []
        valid_rows = [dict(r) for r in rows if isinstance(r, dict)]
        self._source_rows = valid_rows
        self.table.setColumnCount(len(_CATEGORY_COLUMN_SPEC))
        self.table.setHorizontalHeaderLabels([h for h, _ in _CATEGORY_COLUMN_SPEC])
        rows_to_show = self._filtered_source_rows() if self._filter_visible else valid_rows
        self._write_data_rows(rows_to_show)
        show_auto_hiding_message(self, self._message_label, "", error=False)

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if item.row() < self._data_row_offset():
            return
        category = self._get_category_at_row(item.row())
        if category is not None and self.on_edit_clicked:
            self.on_edit_clicked(category, False)

