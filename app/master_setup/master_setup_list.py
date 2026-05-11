"""Master Setup list page."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
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

from core.api import api_delete_master_key_value, api_get_all_master_key_values
from core.app_preferences import format_datetime_display, is_datetime_field
from core.user_context import get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.blank_display import is_blank_display_value
from ui.data_table import (
    FILTER_ROW_HEIGHT_PX,
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    data_row_offset,
    filter_dict_rows_by_column_edits,
    install_filter_row,
    resize_data_table_columns_to_content,
    sync_vertical_header_labels,
)
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.styles import CONTEXT_MENU_STYLESHEET

_MASTER_SETUP_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Id", ("id", "masterKeyValueId", "master_key_value_id")),
    # Flat list from get-by-category/ALL: prefer categoryName; legacy rows use nested ``category``.
    ("Category", ("categoryName", "category_name", "category")),
    ("Seq", ("seq",)),
    ("Key Value", ("keyValue", "key_value")),
    ("Description", ("description", "desc")),
    ("Created At", ("createdAt", "created_at")),
    ("Created By", ("createdBy", "createBy", "created_by", "create_by")),
    ("Modified At", ("modifiedAt", "modified_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
)


def _master_setup_value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key), key
    return None, keys[0]


def _format_category_cell(value: Any) -> str:
    """Show nested ``category.category`` when API returns ``category`` as an object; else plain text."""
    if is_blank_display_value(value):
        return ""
    if isinstance(value, dict):
        inner = value.get("category")
        if isinstance(inner, dict):
            leaf = inner.get("category")
            if leaf is not None:
                return str(leaf).strip()
            return ""
        if inner is not None:
            return str(inner).strip()
        for alt in ("categoryName", "category_name", "name"):
            v = value.get(alt)
            if v is not None and not isinstance(v, (dict, list)):
                return str(v).strip()
        return ""
    return str(value).strip()


def _format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, dict) and key in ("category", "categoryName", "category_name"):
        return _format_category_cell(value)
    return str(value)


class MasterSetupListPage(QWidget):
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
        hl.addWidget(QLabel("Master Setup Value"))
        hl.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._load_master_keys)
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

    def _data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _schedule_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_source_rows(self) -> list[dict[str, Any]]:
        rows = filter_dict_rows_by_column_edits(
            self._source_rows,
            self.table,
            list(_MASTER_SETUP_COLUMN_SPEC),
            self._filter_visible,
            _master_setup_value_for_column,
            _format_cell,
        )
        if not self._filter_visible:
            return rows
        category_col = 1  # "Category"
        cat_keys = _MASTER_SETUP_COLUMN_SPEC[category_col][1]
        w = self.table.cellWidget(0, category_col)
        if isinstance(w, QComboBox):
            selected = w.currentText().strip()
            if selected and selected != "All":
                rows = [
                    r
                    for r in rows
                    if _format_cell(*_master_setup_value_for_column(r, cat_keys), cat_keys).strip() == selected
                ]
        return rows

    def _install_category_filter_combo(self) -> None:
        if not self._filter_visible or self.table.columnCount() <= 1:
            return
        category_col = 1
        cat_keys = _MASTER_SETUP_COLUMN_SPEC[category_col][1]
        existing = self.table.cellWidget(0, category_col)
        if existing is not None:
            self.table.removeCellWidget(0, category_col)
        combo = QComboBox()
        combo.setEditable(False)
        combo.addItem("All")
        categories = sorted(
            {
                _format_cell(*_master_setup_value_for_column(r, cat_keys), cat_keys).strip()
                for r in self._source_rows
                if isinstance(r, dict)
            }
        )
        for c in categories:
            if c:
                combo.addItem(c)
        apply_form_combobox_field(combo, height_px=FILTER_ROW_HEIGHT_PX)
        combo.currentTextChanged.connect(lambda _t="", cb=self._schedule_filter_apply: cb())
        self.table.setCellWidget(0, category_col, combo)

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
            self._install_category_filter_combo()
        for r, row in enumerate(rows):
            tr = off + r
            for col, (_, keys) in enumerate(_MASTER_SETUP_COLUMN_SPEC):
                value, key_used = _master_setup_value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(tr, col, item)
        sync_vertical_header_labels(self.table, filter_visible=self._filter_visible, data_row_count=len(rows))
        resize_data_table_columns_to_content(
            self.table,
            list(_MASTER_SETUP_COLUMN_SPEC),
            self._source_rows,
            _master_setup_value_for_column,
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

    def _get_master_key_at_row(self, row: int) -> dict[str, Any] | None:
        if row < self._data_row_offset() or row >= self.table.rowCount():
            return None
        item = self.table.item(row, 0)
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        return data if isinstance(data, dict) else None

    def _master_key_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        idx = self.table.indexAt(pos)
        if idx.isValid():
            return self._get_master_key_at_row(idx.row())
        item = self.table.itemAt(pos)
        if item:
            return self._get_master_key_at_row(item.row())
        return None

    def _on_context_menu(self, pos: QPoint) -> None:
        row_data = self._master_key_at_pos(pos)
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Add Master Setup Value")
        display_action = menu.addAction("Display Master Setup Value")
        edit_action = menu.addAction("Edit Master Setup Value")
        delete_action = menu.addAction("Delete Master Setup Value")
        display_action.setEnabled(row_data is not None and self.on_edit_clicked is not None)
        edit_action.setEnabled(row_data is not None and self.on_edit_clicked is not None)
        delete_action.setEnabled(row_data is not None)
        action = menu.exec(QCursor.pos())
        if action == add_action and self.on_create_clicked:
            self.on_create_clicked()
        elif action == display_action and row_data is not None and self.on_edit_clicked:
            self.on_edit_clicked(row_data, False)
        elif action == edit_action and row_data is not None and self.on_edit_clicked:
            self.on_edit_clicked(row_data, True)
        elif action == delete_action and row_data is not None:
            self._handle_delete_master_key(row_data)

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if item.row() < self._data_row_offset():
            return
        row_data = self._get_master_key_at_row(item.row())
        if row_data is not None and self.on_edit_clicked:
            self.on_edit_clicked(row_data, False)

    def _handle_delete_master_key(self, row_data: dict[str, Any]) -> None:
        key_id = row_data.get("id") or row_data.get("masterKeyValueId") or row_data.get("master_key_value_id")
        if key_id is None:
            show_auto_hiding_message(self, self._message_label, "Cannot delete: ID is missing.", error=True)
            return
        name = row_data.get("keyValue") or "this entry"
        reply = QMessageBox.question(
            self,
            "Delete Master Setup Value",
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
        result = api_delete_master_key_value(key_id, token=token)
        if result.get("success"):
            show_auto_hiding_message(
                self,
                self._message_label,
                str(result.get("message") or "Master setup entry deleted."),
                error=False,
            )
            QTimer.singleShot(700, self._load_master_keys)
        else:
            show_auto_hiding_message(
                self,
                self._message_label,
                str(result.get("message") or "Failed to delete master setup entry."),
                error=True,
            )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._load_master_keys()

    def refresh(self) -> None:
        self._load_master_keys()

    def _load_master_keys(self) -> None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_master_key_values(token=token)
        if not result.get("success"):
            show_auto_hiding_message(
                self,
                self._message_label,
                str(result.get("message") or "Failed to load master setup entries."),
                error=True,
            )
            self._show_empty_table()
            return
        rows = result.get("data") or []
        valid_rows = [dict(r) for r in rows if isinstance(r, dict)]
        self._source_rows = valid_rows
        self.table.setColumnCount(len(_MASTER_SETUP_COLUMN_SPEC))
        self.table.setHorizontalHeaderLabels([h for h, _ in _MASTER_SETUP_COLUMN_SPEC])
        rows_to_show = self._filtered_source_rows() if self._filter_visible else valid_rows
        self._write_data_rows(rows_to_show)
        show_auto_hiding_message(self, self._message_label, "", error=False)
