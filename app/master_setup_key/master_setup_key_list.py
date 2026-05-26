"""Master Setup Key list page (api/master-setup/master-key)."""

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

from core.api import api_delete_master_setup_key_entry, api_get_all_master_setup_key_entries
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
    render_dict_rows_table,
    saved_filter_texts,
)
from ui.form_page_styles import (
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.styles import CONTEXT_MENU_STYLESHEET

_COL_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Id", ("id",)),
    ("Category", ("category",)),
    ("Created At", ("createdAt", "created_at")),
    ("Created By", ("createdBy", "created_by")),
    ("Modified At", ("modifiedAt", "modified_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
)


def _value_for_col(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for k in keys:
        if k in row and row.get(k) is not None:
            return row.get(k), k
    return None, keys[0]


def _fmt(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if isinstance(value, (list, dict)):
        try:
            return json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    return str(value)


class MasterSetupKeyListPage(QWidget):
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
        self._filter_apply_timer.timeout.connect(self._refresh_table_view)
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
        hl.addWidget(QLabel("Master Setup Key"))
        hl.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._load_rows)
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

    def _is_data_row(self, row: int) -> bool:
        return row >= self._data_row_offset()

    def _row_data(self, row: int) -> dict[str, Any] | None:
        if row < 0 or row >= self.table.rowCount() or not self._is_data_row(row):
            return None
        it = self.table.item(row, 0)
        d = it.data(Qt.ItemDataRole.UserRole) if it else None
        return d if isinstance(d, dict) else None

    def _on_context_menu(self, pos: QPoint) -> None:
        idx = self.table.indexAt(pos)
        row_data = self._row_data(idx.row()) if idx.isValid() else None
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Add Master Setup Key")
        display_action = menu.addAction("Display Master Setup Key")
        edit_action = menu.addAction("Edit Master Setup Key")
        delete_action = menu.addAction("Delete Master Setup Key")
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
            self._handle_delete(row_data)

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        row_data = self._row_data(item.row())
        if row_data is not None and self.on_edit_clicked:
            self.on_edit_clicked(row_data, False)

    def _handle_delete(self, row_data: dict[str, Any]) -> None:
        rid = row_data.get("id")
        if rid is None:
            show_auto_hiding_message(self, self._message_label, "Cannot delete: ID is missing.", error=True)
            return
        cat_val, cat_key = _value_for_col(row_data, _COL_SPEC[1][1])
        label = _fmt(cat_val, cat_key, _COL_SPEC[1][1]) or "this entry"
        reply = QMessageBox.question(
            self,
            "Delete Master Setup Key",
            f"Are you sure you want to delete '{label}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = api_delete_master_setup_key_entry(rid, token=self._token())
        if result.get("success"):
            show_auto_hiding_message(
                self, self._message_label, str(result.get("message") or "Deleted."), error=False
            )
            QTimer.singleShot(700, self._load_rows)
        else:
            show_auto_hiding_message(
                self, self._message_label, str(result.get("message") or "Delete failed."), error=True
            )

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._load_rows()

    def refresh(self) -> None:
        self._load_rows()

    def _schedule_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _on_filter_toggle(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self.table)
        self._refresh_table_view()

    def _filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._source_rows)
        if not self._filter_visible:
            return rows
        return filter_dict_rows_by_column_edits(
            rows,
            self.table,
            list(_COL_SPEC),
            True,
            _value_for_col,
            _fmt,
        )

    def _refresh_table_view(self) -> None:
        saved = saved_filter_texts(self.table) if self._filter_visible else None
        render_dict_rows_table(
            self.table,
            self._filtered_rows(),
            list(_COL_SPEC),
            filter_visible=self._filter_visible,
            value_for_column=_value_for_col,
            format_cell=_fmt,
            on_filter_text_changed=self._schedule_filter_apply,
            saved_filter_texts_list=saved,
        )

    def _load_rows(self) -> None:
        result = api_get_all_master_setup_key_entries(token=self._token())
        if not result.get("success"):
            show_auto_hiding_message(
                self, self._message_label, str(result.get("message") or "Failed to load."), error=True
            )
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return
        rows = [dict(r) for r in (result.get("data") or []) if isinstance(r, dict)]
        self._source_rows = rows
        self._refresh_table_view()
        show_auto_hiding_message(self, self._message_label, "", error=False)
