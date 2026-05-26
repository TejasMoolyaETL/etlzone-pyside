"""Object List Tracker list page for DMT Tracker."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QCursor, QGuiApplication, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.dmt.dmt_object_tracker.dmt_object_tracker_comment_panel import ObjectTrackerCommentPanel
from core.api import api_delete_object_tracker, api_get_all_object_trackers
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
    DATA_TABLE_HEADER_FONT_SIZE_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.styles import CONTEXT_MENU_STYLESHEET
from ui.theme import Theme

_TRACKER_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Tracker Id", ("objectTrackerId", "trackerId", "id")),
    ("Module", ("moduleName",)),
    ("Object Name", ("objectName",)),
    ("TCode", ("tcode",)),
    (
        "Status",
        ("statusName", "statusLabel", "status", "dmt_object_list_tracker_status", "statusSeq", "status_seq"),
    ),
    (
        "Business Object Type",
        ("businessObjectTypeName", "businessObjectType", "dmt_business_object_type", "businessObjectTypeSeq"),
    ),
    ("Scope", ("scopeName", "scope", "dmt_scope", "scopeSeq")),
    ("Load Approach", ("loadApproachName", "loadApproach", "dmt_load_approach", "loadApproachSeq")),
    ("Upload Tool", ("uploadToolName", "uploadTool", "dmt_upload_tool", "uploadToolSeq")),
    (
        "Customization Status",
        ("customizationStatusName", "customizationStatus", "dmt_customization_status", "customizationStatusSeq"),
    ),
    ("Build Status", ("buildStatusName", "buildStatus", "dmt_buildStatus", "buildStatusSeq")),
    ("Build Completion Date", ("buildCompletionDate",)),
    (
        "Functional Unit Testing Status",
        (
            "functionalUnitTestingStatusName",
            "functionalUnitTestingStatus",
            "dmt_functionalUnitTestingStatus",
            "functionalUnitTestingStatusSeq",
        ),
    ),
    ("Functional Unit Testing Completion Date", ("functionalUnitTestingCompletionDate",)),
    (
        "Business Unit Testing Status",
        (
            "businessUnitTestingStatusName",
            "businessUnitTestingStatus",
            "dmt_businessUnitTestingStatus",
            "businessUnitTestingStatusSeq",
        ),
    ),
    ("Business Unit Testing Completion Date", ("businessUnitTestingCompletionDate",)),
    ("Estimated Prod Count", ("estimatedProdCount",)),
    ("Functional SPOC", ("functionalSPOC",)),
    ("DMC Program Name", ("dmcProgramName",)),
    ("Comments", ("comments",)),
    ("SharePoint", ("uploadedToSharePoint",)),
    ("Created By", ("createdBy",)),
    ("Created At", ("createdAt",)),
    ("Modified By", ("modifiedBy",)),
    ("Modified At", ("modifiedAt",)),
)


def _tracker_value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key), key
    return None, keys[0]


def _format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if isinstance(value, dict):
        for k in ("keyValue", "key_value", "name", "label", "displayName"):
            t = str(value.get(k) or "").strip()
            if t:
                return t
        return ""
    if isinstance(value, (list, tuple)):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                for k in ("keyValue", "key_value", "name", "label", "displayName"):
                    t = str(item.get(k) or "").strip()
                    if t:
                        parts.append(t)
                        break
            else:
                t = str(item).strip()
                if t:
                    parts.append(t)
        return "\n".join(parts)
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _tracker_id(row: dict[str, Any]) -> int | str | None:
    for key in ("objectTrackerId", "trackerId", "id"):
        value = row.get(key)
        if value is not None:
            return value
    return None


class DmtObjectTrackerListPage(QWidget):
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
        self._comment_context_listeners: list[Callable[[], None]] = []
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
        hl.addWidget(QLabel("DMT - Object List Tracker"))
        hl.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._load_trackers)
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
        self._more_btn = QToolButton()
        self._more_btn.setText("☰")
        self._more_btn.setFixedWidth(34)
        self._more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._more_btn.setStyleSheet(
            "QToolButton {"
            f" color: {Theme.PANEL_TEXT_BRIGHT};"
            " font-size: 16px; font-weight: 700; padding-bottom: 2px;"
            " border: none; background: transparent; }"
            f"QToolButton:hover {{ background: {Theme.HEADER_ACCENT_HOVER}; }}"
            f"QToolButton:pressed {{ background: {Theme.HEADER_ACCENT_PRESSED}; }}"
        )
        more_menu = QMenu(self._more_btn)
        more_menu.setStyleSheet(
            "QMenu {"
            " background: #f8fafc; color: #475569;"
            " border: 1px solid #cbd5e1;"
            " border-radius: 0px; padding: 0px; }"
            "QMenu::item {"
            " background: #f8fafc; color: #475569;"
            f" font-size: {DATA_TABLE_HEADER_FONT_SIZE_PX}px; font-weight: 600;"
            " padding: 3px 6px; margin: 0px; border: none;"
            " border-bottom: 2px solid #e2e8f0; border-right: 1px solid #cbd5e1; }"
            "QMenu::item:selected { background: #f8fafc; color: #475569; }"
            "QMenu::item:pressed { background: #f8fafc; color: #475569; }"
        )
        copy_action = QAction("Copy", self._more_btn)
        copy_action.triggered.connect(self._copy_selection_to_clipboard)
        more_menu.addAction(copy_action)
        self._more_btn.setMenu(more_menu)
        hl.addWidget(self._more_btn)
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
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.itemDoubleClicked.connect(self._on_row_double_clicked)
        self.table.itemSelectionChanged.connect(self._on_tracker_selection_changed)
        attach_table_copy_shortcut(self.table)
        ll.addWidget(self.table, 1)
        split.addWidget(left_panel)

        self._comment_panel = ObjectTrackerCommentPanel(self)
        split.addWidget(self._comment_panel)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([700, 300])
        cl.addWidget(split, 1)
        layout.addWidget(content, 1)

    def get_selected_row(self) -> dict[str, Any] | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self._get_tracker_at_row(row)

    def register_comment_context_listener(self, listener: Callable[[], None]) -> None:
        if listener not in self._comment_context_listeners:
            self._comment_context_listeners.append(listener)

    def _notify_comment_context_changed(self) -> None:
        for listener in self._comment_context_listeners:
            try:
                listener()
            except Exception:
                continue

    def _on_tracker_selection_changed(self) -> None:
        self._notify_comment_context_changed()

    def _data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _schedule_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_source_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._source_rows,
            self.table,
            list(_TRACKER_COLUMN_SPEC),
            self._filter_visible,
            _tracker_value_for_column,
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
            for col, (_, keys) in enumerate(_TRACKER_COLUMN_SPEC):
                value, key_used = _tracker_value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(tr, col, item)
        sync_vertical_header_labels(self.table, filter_visible=self._filter_visible, data_row_count=len(rows))
        resize_data_table_columns_to_content(
            self.table,
            list(_TRACKER_COLUMN_SPEC),
            self._source_rows,
            _tracker_value_for_column,
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

    def _get_tracker_at_row(self, row: int) -> dict[str, Any] | None:
        if row < self._data_row_offset() or row >= self.table.rowCount():
            return None
        item = self.table.item(row, 0)
        data = item.data(Qt.ItemDataRole.UserRole) if item else None
        return data if isinstance(data, dict) else None

    def _tracker_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        idx = self.table.indexAt(pos)
        if idx.isValid():
            return self._get_tracker_at_row(idx.row())
        item = self.table.itemAt(pos)
        if item:
            return self._get_tracker_at_row(item.row())
        return None

    def _on_context_menu(self, pos: QPoint) -> None:
        clicked_item = self.table.itemAt(pos)
        if clicked_item is not None and clicked_item.row() >= self._data_row_offset():
            self.table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self.table.selectRow(clicked_item.row())
        rec = self._tracker_at_pos(pos)
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Add Object Tracker")
        display_action = menu.addAction("Display Object Tracker")
        edit_action = menu.addAction("Edit Object Tracker")
        delete_action = menu.addAction("Delete Object Tracker")
        display_action.setEnabled(rec is not None and self.on_edit_clicked is not None)
        edit_action.setEnabled(rec is not None and self.on_edit_clicked is not None)
        delete_action.setEnabled(rec is not None)
        action = menu.exec(QCursor.pos())
        if action == add_action and self.on_create_clicked:
            self.on_create_clicked()
        elif action == display_action and rec is not None and self.on_edit_clicked:
            self.on_edit_clicked(rec, False)
        elif action == edit_action and rec is not None and self.on_edit_clicked:
            self.on_edit_clicked(rec, True)
        elif action == delete_action and rec is not None:
            self._handle_delete_tracker(rec)

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if item.row() < self._data_row_offset():
            return
        rec = self._get_tracker_at_row(item.row())
        if rec is not None and self.on_edit_clicked:
            self.on_edit_clicked(rec, False)

    def _handle_delete_tracker(self, rec: dict[str, Any]) -> None:
        tracker_id = _tracker_id(rec)
        if tracker_id is None:
            show_auto_hiding_message(self, self._message_label, "Cannot delete: Tracker ID is missing.", error=True)
            return
        reply = QMessageBox.question(
            self,
            "Delete Object Tracker",
            "Are you sure you want to delete this tracker record?",
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
        result = api_delete_object_tracker(tracker_id, token=token)
        if result.get("success"):
            show_auto_hiding_message(
                self,
                self._message_label,
                str(result.get("message") or "Object tracker record deleted."),
                error=False,
            )
            QTimer.singleShot(700, self._load_trackers)
        else:
            show_auto_hiding_message(
                self,
                self._message_label,
                str(result.get("message") or "Failed to delete object tracker record."),
                error=True,
            )

    def _copy_selection_to_clipboard(self) -> None:
        selected = self.table.selectedIndexes()
        if not selected:
            show_auto_hiding_message(self, self._message_label, "Select rows/cells to copy.", error=True)
            return
        selected_cells = {(idx.row(), idx.column()) for idx in selected}
        min_row = min(idx.row() for idx in selected)
        max_row = max(idx.row() for idx in selected)
        min_col = min(idx.column() for idx in selected)
        max_col = max(idx.column() for idx in selected)
        lines: list[str] = []
        for r in range(min_row, max_row + 1):
            row_cells: list[str] = []
            for c in range(min_col, max_col + 1):
                if (r, c) in selected_cells:
                    item = self.table.item(r, c)
                    row_cells.append(item.text() if item else "")
                else:
                    row_cells.append("")
            lines.append("\t".join(row_cells))
        QGuiApplication.clipboard().setText("\n".join(lines))
        show_auto_hiding_message(self, self._message_label, "Copied.", error=False)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._load_trackers()

    def refresh(self) -> None:
        self._load_trackers()

    def _load_trackers(self) -> None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_object_trackers(token=token)
        if not result.get("success"):
            show_auto_hiding_message(
                self,
                self._message_label,
                str(result.get("message") or "Failed to load object tracker records."),
                error=True,
            )
            self._show_empty_table()
            return
        rows = result.get("data") or []
        valid_rows = [dict(r) for r in rows if isinstance(r, dict)]
        self._source_rows = valid_rows
        self.table.setColumnCount(len(_TRACKER_COLUMN_SPEC))
        self.table.setHorizontalHeaderLabels([h for h, _ in _TRACKER_COLUMN_SPEC])
        rows_to_show = self._filtered_source_rows() if self._filter_visible else valid_rows
        self._write_data_rows(rows_to_show)
        show_auto_hiding_message(self, self._message_label, "", error=False)
