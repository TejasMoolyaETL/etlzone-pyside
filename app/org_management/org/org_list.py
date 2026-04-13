"""Organization list - fetches api/orgs/get-all-orgs and displays orgs in a table."""

from __future__ import annotations

import json
import traceback
from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QShowEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.api import api_delete_org, api_get_all_orgs
from core.app_preferences import format_datetime_display, is_datetime_field
from ui.blank_display import is_blank_display_value
from core.user_context import get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.form_page_styles import (
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.data_table import (
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    data_row_offset,
    filter_dict_rows_by_column_edits,
    install_filter_row,
    MIN_DATA_COL_WIDTH_PX,
    resize_data_table_columns_to_content,
    sync_vertical_header_labels,
)
from ui.styles import CONTEXT_MENU_STYLESHEET

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})

# Column order: (header, possible API keys)
_ORG_COLUMN_SPEC = (
    ("Org Id", ("orgId", "org_id", "id")),
    ("Org Code", ("orgCode", "org_code")),
    ("Org Name", ("orgName", "org_name")),
    ("Industry", ("industry",)),
    ("Status", ("status",)),
    ("Created By", ("createdBy", "created_by")),
    ("Created On", ("createdOn", "created_on", "createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified On", ("modifiedOn", "modified_on", "modifiedAt", "modified_at", "updatedAt", "updated_at")),
)


def _flatten_org(org: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in org.items() if k not in _HIDDEN_KEYS}


def _value_for_column(org: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    """Return (value, key_used) for the first key that exists in org. key_used for date formatting."""
    flat = _flatten_org(org)
    for key in keys:
        if key in flat:
            return (flat[key], key)
    return (None, keys[0] if keys else "")


def _format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


class OrgListPage(QWidget):
    """Page that fetches and displays all organizations in a table."""

    def __init__(
        self,
        on_create_clicked: Callable[[], None] | None = None,
        on_view_clicked: Callable[[dict[str, Any]], None] | None = None,
        on_edit_org: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_create_clicked = on_create_clicked
        self.on_view_clicked = on_view_clicked
        self.on_edit_org = on_edit_org
        self._source_rows: list[dict[str, Any]] = []
        self._column_spec: list[tuple[str, tuple[str, ...]]] = []
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
        title = QLabel("Organization")
        header_layout.addWidget(title)
        header_layout.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        header_layout.addWidget(refresh_btn)
        self._filter_toggle = QPushButton("Filters")
        self._filter_toggle.setCheckable(True)
        self._filter_toggle.setFixedWidth(100)
        self._filter_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_toggle.toggled.connect(self._on_filter_toggle)
        header_layout.addWidget(self._filter_toggle)
        create_btn = QPushButton("Create")
        create_btn.setFixedWidth(100)
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(self._on_create)
        header_layout.addWidget(create_btn)
        layout.addWidget(header)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._message_label.setVisible(False)
        content_layout.addWidget(self._message_label)

        self.table = QTableWidget()
        apply_data_table_appearance(self.table)
        self.table.setSortingEnabled(False)
        # itemDoubleClicked passes the actual item (correct after sort); cellDoubleClicked row/col are logical indices and mismatch visual order when sorting is on.
        self.table.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        attach_table_copy_shortcut(self.table)
        content_layout.addWidget(self.table, 1)
        layout.addWidget(content)

    def _data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _is_data_table_row(self, table_row: int) -> bool:
        return table_row >= self._data_row_offset()

    def _schedule_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_source_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._source_rows,
            self.table,
            self._column_spec,
            self._filter_visible,
            _value_for_column,
            _format_cell,
        )

    def _write_data_rows(self, data_rows: list[dict[str, Any]]) -> None:
        off = self._data_row_offset()
        self.table.setSortingEnabled(False)
        total = off + len(data_rows)
        if self._filter_visible and total < 1:
            total = 1
        self.table.setRowCount(total)
        if self._filter_visible:
            for c in range(self.table.columnCount()):
                self.table.takeItem(0, c)
            install_filter_row(
                self.table,
                len(self._column_spec),
                on_text_changed=self._schedule_filter_apply,
            )
        for r, row in enumerate(data_rows):
            tr = off + r
            for col, (_, keys) in enumerate(self._column_spec):
                value, key_used = _value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(tr, col, item)
        sync_vertical_header_labels(
            self.table,
            filter_visible=self._filter_visible,
            data_row_count=len(data_rows),
        )
        resize_data_table_columns_to_content(
            self.table,
            self._column_spec,
            self._source_rows,
            _value_for_column,
            _format_cell,
        )
        self.table.setSortingEnabled(not self._filter_visible)

    def _apply_column_filters_refresh(self) -> None:
        if not self._filter_visible or not self._column_spec or not self._source_rows:
            return
        try:
            filtered = self._filtered_source_rows()
            self._write_data_rows(filtered)
        except Exception:
            traceback.print_exc()

    def _on_filter_toggle(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            self._filter_apply_timer.stop()
            clear_filter_row_widgets(self.table)
        if self._column_spec and self._source_rows:
            try:
                to_show = self._filtered_source_rows() if checked else list(self._source_rows)
                self._write_data_rows(to_show)
            except Exception:
                traceback.print_exc()
        elif not self._source_rows:
            self._show_empty_table()

    def _show_empty_table(self) -> None:
        self._source_rows = []
        self._column_spec = []
        self.table.setSortingEnabled(False)
        clear_filter_row_widgets(self.table)
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

    def _populate_table(self, orgs: list[dict[str, Any]]) -> None:
        if not orgs:
            self._show_empty_table()
            return
        try:
            self._source_rows = [dict(r) for r in orgs]
            self._column_spec = list(_ORG_COLUMN_SPEC)
            self.table.setSortingEnabled(False)
            headers = [spec[0] for spec in self._column_spec]
            self.table.setColumnCount(len(self._column_spec))
            self.table.setHorizontalHeaderLabels(headers)
            hh = self.table.horizontalHeader()
            hh.setStretchLastSection(False)
            for col in range(self.table.columnCount()):
                hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
            filtered = self._filtered_source_rows() if self._filter_visible else list(self._source_rows)
            self._write_data_rows(filtered)
        except Exception:
            traceback.print_exc()
            show_auto_hiding_message(
                self, self._message_label, "Failed to display organizations.", error=True
            )
            self._show_empty_table()

    def _load_orgs(self) -> None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_orgs(token=token)
        if not result.get("success"):
            show_auto_hiding_message(
                self,
                self._message_label,
                result.get("message", "Failed to load organizations."),
                error=True,
            )
            self._show_empty_table()
            return
        show_auto_hiding_message(self, self._message_label, "")
        data = result.get("data") or []
        self._populate_table(data)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._load_orgs()

    def refresh(self) -> None:
        self._load_orgs()

    def _on_create(self) -> None:
        """Navigate to create-organization page if callback set."""
        if self.on_create_clicked:
            self.on_create_clicked()

    def _on_item_double_clicked(self, item: QTableWidgetItem) -> None:
        """Open view page for the org on the clicked cell (works correctly when table is sorted)."""
        if not self.on_view_clicked or not item:
            return
        if not self._is_data_table_row(item.row()):
            return
        row_item = self.table.item(item.row(), 0)
        if row_item is None:
            return
        org = row_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(org, dict):
            self.on_view_clicked(org)

    def _has_data_row_selection(self) -> bool:
        for it in self.table.selectedItems():
            if self._is_data_table_row(it.row()):
                return True
        return False

    def _selected_org_row(self) -> dict[str, Any] | None:
        items = self.table.selectedItems()
        if not items:
            return None
        r = items[0].row()
        if not self._is_data_table_row(r):
            return None
        item = self.table.item(r, 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _org_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        """Resolve org under right-click. No selection fallback — avoids wrong org when another row is selected.

        Qt may pass `pos` in viewport coordinates OR in QTableWidget coordinates; try both for indexAt/itemAt.
        """
        vp = self.table.viewport()

        def _org_from_viewport_point(vp_point: QPoint) -> dict[str, Any] | None:
            idx = self.table.indexAt(vp_point)
            if idx.isValid():
                if not self._is_data_table_row(idx.row()):
                    return None
                item = self.table.itemFromIndex(idx)
                if item:
                    org = item.data(Qt.ItemDataRole.UserRole)
                    if isinstance(org, dict):
                        return org
            item = self.table.itemAt(vp_point)
            if item:
                if not self._is_data_table_row(item.row()):
                    return None
                org = item.data(Qt.ItemDataRole.UserRole)
                if isinstance(org, dict):
                    return org
            return None

        # 1) pos already in viewport coordinates (common for QAbstractItemView context menu)
        org = _org_from_viewport_point(pos)
        if org is not None:
            return org
        # 2) pos in QTableWidget coordinates — convert to viewport
        vp_pos = vp.mapFrom(self.table, pos)
        return _org_from_viewport_point(vp_pos)

    def _get_org_id(self, org: dict[str, Any]) -> int | str | None:
        for k in ("orgId", "org_id", "id"):
            v = org.get(k)
            if v is not None:
                return v
        return None

    def _on_context_menu(self, pos: QPoint) -> None:
        clicked_item = self.table.itemAt(pos)
        if clicked_item is not None and self._is_data_table_row(clicked_item.row()):
            self.table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self.table.selectRow(clicked_item.row())
        org = self._org_at_pos(pos)
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Add Organization")
        display_action = menu.addAction("Display Organization")
        edit_action = menu.addAction("Edit Organization")
        delete_action = menu.addAction("Delete Organization")
        has_data = self._has_data_row_selection() or (
            clicked_item is not None and self._is_data_table_row(clicked_item.row())
        )
        display_action.setEnabled(has_data)
        edit_action.setEnabled(has_data and self.on_edit_org is not None)
        delete_action.setEnabled(has_data)
        # Show menu at cursor — avoids wrong global position if pos coordinate space differs by platform
        action = menu.exec(QCursor.pos())
        target = self._selected_org_row() or org
        if action == add_action and self.on_create_clicked:
            self.on_create_clicked()
        elif action == display_action and target and self.on_view_clicked:
            self.on_view_clicked(target)
        elif action == edit_action and target and self.on_edit_org:
            self.on_edit_org(target)
        elif action == delete_action and target:
            self._handle_delete_org(target)

    def _handle_delete_org(self, org: dict[str, Any]) -> None:
        org_id = self._get_org_id(org)
        if org_id is None:
            show_auto_hiding_message(
                self, self._message_label, "Cannot delete: Organization ID is missing.", error=True
            )
            return
        name = (
            org.get("orgName")
            or org.get("org_name")
            or org.get("orgCode")
            or org.get("org_code")
            or str(org_id)
        )
        reply = QMessageBox.question(
            self,
            "Delete Organization",
            f"Are you sure you want to delete organization '{name}'?",
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
        result = api_delete_org(org_id, token=token)
        if result.get("success"):
            show_auto_hiding_message(
                self,
                self._message_label,
                result.get("message", "Organization deleted."),
                error=False,
            )
            self.refresh()
        else:
            show_auto_hiding_message(
                self,
                self._message_label,
                result.get("message", "Failed to delete organization."),
                error=True,
            )
