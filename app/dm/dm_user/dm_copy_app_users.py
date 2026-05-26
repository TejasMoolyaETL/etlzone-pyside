"""Copy app_users staging — left: GET api/get-all-user; right: drop queue (same UX as API Replicate)."""

from __future__ import annotations

import json
import traceback
from typing import Any, Callable

from PySide6.QtCore import QMimeData, QObject, QPoint, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QDrag, QMouseEvent, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.api_dev.api_details.api_details_copy_to_api_mgmt import _make_replicate_section_header

from app.user_management.users.user_list import (
    _COLUMN_SPEC as _APP_USER_COLUMN_SPEC,
    _format_cell as _format_app_user_cell,
    _value_for_user_column as _app_user_value_for_column,
)
from core.api import api_get_all_users, api_users_copy_from_app_user
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
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
from ui.form_page_styles import (
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    MODAL_FIELD_LABEL_STYLE,
)
from ui.post_save_navigation import schedule_after_success
from ui.styles import CONTEXT_MENU_STYLESHEET

_MIME_APP_USER_ROW = "application/x-etlzone-app-user-row"


def _app_user_row_id(row: dict[str, Any]) -> Any:
    return row.get("id") or row.get("userId") or row.get("user_id")


class _UsersLoadWorker(QObject):
    finished = Signal(bool, object, str)

    def __init__(self, token: str | None) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        result = api_get_all_users(token=self._token)
        if not result.get("success"):
            self.finished.emit(False, [], str(result.get("message", "Failed to load users.")))
            return
        raw = result.get("data") or []
        rows = [r for r in raw if isinstance(r, dict)]
        self.finished.emit(True, rows, "")


class _ReplicateWorker(QObject):
    finished = Signal(bool, str)

    def __init__(self, token: str | None, user_ids: list[int]) -> None:
        super().__init__()
        self._token = token
        self._user_ids = user_ids

    @Slot()
    def run(self) -> None:
        result = api_users_copy_from_app_user(self._user_ids, token=self._token)
        if not result.get("success"):
            self.finished.emit(False, str(result.get("message") or "Replication failed."))
            return
        self.finished.emit(
            True,
            str(result.get("message") or "Users replicated successfully."),
        )


class _UserDragTable(QTableWidget):
    """Left table: drag full row JSON into staging."""

    def __init__(self, *, data_row_offset_fn: Callable[[], int]) -> None:
        super().__init__()
        self._data_row_offset_fn = data_row_offset_fn
        self._press_row = -1
        self._press_pos: QPoint | None = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            idx = self.indexAt(self._press_pos)
            self._press_row = idx.row() if idx.isValid() else -1
        else:
            self._press_row = -1
            self._press_pos = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            event.buttons() & Qt.MouseButton.LeftButton
            and self._press_row >= 0
            and self._press_pos is not None
        ):
            if (
                event.position().toPoint() - self._press_pos
            ).manhattanLength() >= QApplication.startDragDistance():
                off = self._data_row_offset_fn()
                tr = self._press_row
                self._press_row = -1
                self._press_pos = None
                if tr >= off:
                    self._start_drag_for_row(tr)
        super().mouseMoveEvent(event)

    def _start_drag_for_row(self, table_row: int) -> None:
        item = self.item(table_row, 0)
        if item is None:
            return
        raw = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(raw, dict):
            return
        mime = QMimeData()
        mime.setData(_MIME_APP_USER_ROW, json.dumps(raw, default=str).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class _StagingDropTable(QTableWidget):
    row_dropped = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(_MIME_APP_USER_ROW):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(_MIME_APP_USER_ROW):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(_MIME_APP_USER_ROW):
            event.ignore()
            return
        try:
            raw = event.mimeData().data(_MIME_APP_USER_ROW).data().decode("utf-8")
            row = json.loads(raw)
        except Exception:
            event.ignore()
            return
        if isinstance(row, dict):
            self.row_dropped.emit(row)
        event.acceptProposedAction()


class DmCopyAppUsersPage(QWidget):
    """Copy app_users: left = api/get-all-user catalog; right = staging; Replicate → POST api/dm-project/user/copy-from-app-user."""

    def __init__(self, on_back: Callable[[], None] | None = None) -> None:
        super().__init__()
        self.on_back = on_back
        self._loading = False
        self._pending_refresh = False
        self._load_thread: QThread | None = None
        self._load_worker: _UsersLoadWorker | None = None
        self._replicate_thread: QThread | None = None
        self._replicate_worker: _ReplicateWorker | None = None
        self._source_rows: list[dict[str, Any]] = []
        self._column_spec: list[tuple[str, tuple[str, ...]]] = []
        self._staging_rows: list[dict[str, Any]] = []
        self._filter_visible = False
        self._queue_filter_visible = False
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.setInterval(200)
        self._filter_apply_timer.timeout.connect(self._apply_column_filters_refresh)
        self._queue_filter_timer = QTimer(self)
        self._queue_filter_timer.setSingleShot(True)
        self._queue_filter_timer.setInterval(200)
        self._queue_filter_timer.timeout.connect(self._apply_queue_filter_refresh)
        self._build_ui()

    def _data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _queue_data_row_offset(self) -> int:
        return data_row_offset(self._queue_filter_visible)

    def _update_section_titles(self) -> None:
        app_n = len(self._source_rows)
        queue_n = len(self._staging_rows)
        self._left_title_label.setText(f"App users ({app_n})")
        self._queue_title_label.setText(f"Queue for copy ({queue_n})")

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
        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self._handle_back)
        hl.addWidget(self._back_btn)
        hl.addWidget(QLabel("DM: Copy App users"))
        hl.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        hl.addWidget(refresh_btn)
        layout.addWidget(header)

        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._message_label.setVisible(False)
        msg_wrap = QHBoxLayout()
        msg_wrap.setContentsMargins(12, 4, 12, 0)
        msg_wrap.addWidget(self._message_label)
        layout.addLayout(msg_wrap)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        left_wrap = QWidget()
        left_l = QVBoxLayout(left_wrap)
        left_l.setContentsMargins(8, 0, 4, 8)
        left_l.setSpacing(4)
        left_bar, self._left_title_label, self._left_filter_btn = _make_replicate_section_header(
            "App users (0)",
            "dmCopyAppUsersSectionTitleApp",
            bar_tool_tip="Application users (same list as User Management)",
        )
        self._left_filter_btn.toggled.connect(self._on_filter_toggle)
        left_l.addWidget(left_bar)
        self._left_table = _UserDragTable(data_row_offset_fn=self._data_row_offset)
        self._left_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._left_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        apply_data_table_appearance(self._left_table)
        self._left_table.setSortingEnabled(False)
        attach_table_copy_shortcut(self._left_table)
        left_l.addWidget(self._left_table, 1)

        mid = QWidget()
        mid.setFixedWidth(40)
        mid_l = QVBoxLayout(mid)
        mid_l.setContentsMargins(4, 0, 4, 0)
        mid_l.addStretch(1)
        self._btn_to_staging = QPushButton("\u003e")
        self._btn_to_staging.setFixedSize(30, 26)
        self._btn_to_staging.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_to_staging.setToolTip("Move selected app users to the queue")
        self._btn_to_staging.clicked.connect(self._move_selected_to_staging)
        mid_l.addWidget(self._btn_to_staging, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._btn_from_staging = QPushButton("\u003c")
        self._btn_from_staging.setFixedSize(30, 26)
        self._btn_from_staging.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_from_staging.setToolTip("Remove selected rows from the queue")
        self._btn_from_staging.clicked.connect(self._remove_selected_from_staging)
        mid_l.addWidget(self._btn_from_staging, alignment=Qt.AlignmentFlag.AlignHCenter)
        mid_l.addStretch(1)

        right_wrap = QWidget()
        right_l = QVBoxLayout(right_wrap)
        right_l.setContentsMargins(4, 0, 8, 8)
        right_l.setSpacing(4)
        queue_bar, self._queue_title_label, self._queue_filter_btn = _make_replicate_section_header(
            "Queue for copy (0)",
            "dmCopyAppUsersSectionTitleQueue",
            bar_tool_tip="Users to copy into DM (drag rows here or use \u003e)",
        )
        self._queue_filter_btn.toggled.connect(self._on_queue_filter_toggle)
        right_l.addWidget(queue_bar)
        self._right_table = _StagingDropTable()
        self._right_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._right_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        apply_data_table_appearance(self._right_table)
        self._right_table.setSortingEnabled(False)
        self._right_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._right_table.customContextMenuRequested.connect(self._on_staging_context_menu)
        attach_table_copy_shortcut(self._right_table)
        self._right_table.row_dropped.connect(self._on_row_dropped)
        right_l.addWidget(self._right_table, 1)

        splitter.addWidget(left_wrap)
        splitter.addWidget(mid)
        splitter.addWidget(right_wrap)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)
        layout.addWidget(splitter, 1)

        bottom = QWidget()
        bottom_l = QHBoxLayout(bottom)
        bottom_l.setContentsMargins(12, 8, 12, 12)
        bottom_l.setSpacing(12)
        hint = QLabel("Select app users on the left, move them to the queue, then replicate into DM.")
        hint.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        hint.setWordWrap(True)
        hint.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bottom_l.addWidget(hint, 1)
        self._replicate_btn = QPushButton("Replicate")
        self._replicate_btn.setFixedWidth(120)
        self._replicate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._replicate_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._replicate_btn.setEnabled(False)
        self._replicate_btn.clicked.connect(self._on_replicate_clicked)
        bottom_l.addWidget(self._replicate_btn)
        layout.addWidget(bottom)

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _show_message(self, text: str, *, error: bool) -> None:
        show_auto_hiding_message(self, self._message_label, text, error=error)

    def _clear_message(self) -> None:
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.setText("")
        self._message_label.setVisible(False)

    def _schedule_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_source_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._source_rows,
            self._left_table,
            self._column_spec,
            self._filter_visible,
            _app_user_value_for_column,
            _format_app_user_cell,
        )

    def _write_left_data_rows(self, data_rows: list[dict[str, Any]]) -> None:
        off = self._data_row_offset()
        self._left_table.setSortingEnabled(False)
        total = off + len(data_rows)
        if self._filter_visible and total < 1:
            total = 1
        self._left_table.setRowCount(total)
        if self._filter_visible:
            for c in range(self._left_table.columnCount()):
                self._left_table.takeItem(0, c)
            install_filter_row(
                self._left_table,
                len(self._column_spec),
                on_text_changed=self._schedule_filter_apply,
            )
        for r, row in enumerate(data_rows):
            tr = off + r
            for col, (_, keys) in enumerate(self._column_spec):
                value, key_used = _app_user_value_for_column(row, keys)
                item = QTableWidgetItem(_format_app_user_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self._left_table.setItem(tr, col, item)
        sync_vertical_header_labels(
            self._left_table,
            filter_visible=self._filter_visible,
            data_row_count=len(data_rows),
        )
        resize_data_table_columns_to_content(
            self._left_table,
            self._column_spec,
            self._source_rows,
            _app_user_value_for_column,
            _format_app_user_cell,
        )
        self._left_table.setSortingEnabled(not self._filter_visible)

    def _apply_column_filters_refresh(self) -> None:
        if not self._filter_visible or not self._column_spec or not self._source_rows:
            return
        try:
            filtered = self._filtered_source_rows()
            self._write_left_data_rows(filtered)
        except Exception:
            traceback.print_exc()

    def _filtered_staging_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._staging_rows,
            self._right_table,
            self._column_spec,
            self._queue_filter_visible,
            _app_user_value_for_column,
            _format_app_user_cell,
        )

    def _apply_queue_filter_refresh(self) -> None:
        if not self._queue_filter_visible or not self._column_spec:
            return
        try:
            self._write_staging_table(self._filtered_staging_rows())
        except Exception:
            traceback.print_exc()

    def _on_queue_filter_toggle(self, checked: bool) -> None:
        self._queue_filter_visible = checked
        if not checked:
            self._queue_filter_timer.stop()
            clear_filter_row_widgets(self._right_table)
        if self._staging_rows:
            try:
                rows = self._filtered_staging_rows() if checked else list(self._staging_rows)
                self._write_staging_table(rows)
            except Exception:
                traceback.print_exc()
        else:
            self._write_staging_table()

    def _on_filter_toggle(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            self._filter_apply_timer.stop()
            clear_filter_row_widgets(self._left_table)
        if self._column_spec and self._source_rows:
            try:
                to_show = self._filtered_source_rows() if checked else list(self._source_rows)
                self._write_left_data_rows(to_show)
            except Exception:
                traceback.print_exc()
        elif not self._source_rows:
            self._show_empty_left_table()

    def _show_empty_left_table(self) -> None:
        self._source_rows = []
        self._column_spec = []
        self._left_table.setSortingEnabled(False)
        clear_filter_row_widgets(self._left_table)
        self._left_table.setRowCount(0)
        self._left_table.setColumnCount(0)
        self._update_section_titles()

    def _populate_left(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            self._show_empty_left_table()
            return
        try:
            self._source_rows = [dict(r) for r in rows if isinstance(r, dict)]
            self._column_spec = list(_APP_USER_COLUMN_SPEC)
            self._left_table.setSortingEnabled(False)
            self._left_table.setColumnCount(len(self._column_spec))
            self._left_table.setHorizontalHeaderLabels([s[0] for s in self._column_spec])
            hh = self._left_table.horizontalHeader()
            hh.setStretchLastSection(False)
            for col in range(self._left_table.columnCount()):
                hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
            filtered = self._filtered_source_rows() if self._filter_visible else list(self._source_rows)
            self._write_left_data_rows(filtered)
            self._update_section_titles()
        except Exception:
            traceback.print_exc()
            self._show_empty_left_table()

    def _write_staging_table(self, display_rows: list[dict[str, Any]] | None = None) -> None:
        rows = display_rows if display_rows is not None else self._staging_rows
        off = self._queue_data_row_offset()
        self._right_table.setSortingEnabled(False)
        total = off + len(rows)
        if self._queue_filter_visible and total < 1:
            total = 1
        self._right_table.setRowCount(total)
        if not rows:
            if self._queue_filter_visible:
                spec_empty = self._column_spec or list(_APP_USER_COLUMN_SPEC)
                self._right_table.setColumnCount(len(spec_empty))
                self._right_table.setHorizontalHeaderLabels([s[0] for s in spec_empty])
                for c in range(self._right_table.columnCount()):
                    self._right_table.takeItem(0, c)
                install_filter_row(
                    self._right_table,
                    len(spec_empty),
                    on_text_changed=lambda: self._queue_filter_timer.start(),
                )
            else:
                self._right_table.setColumnCount(0)
            self._replicate_btn.setEnabled(False)
            self._update_section_titles()
            return
        spec = self._column_spec or list(_APP_USER_COLUMN_SPEC)
        self._right_table.setColumnCount(len(spec))
        self._right_table.setHorizontalHeaderLabels([s[0] for s in spec])
        hh = self._right_table.horizontalHeader()
        for col in range(self._right_table.columnCount()):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        if self._queue_filter_visible:
            for c in range(self._right_table.columnCount()):
                self._right_table.takeItem(0, c)
            install_filter_row(
                self._right_table,
                len(spec),
                on_text_changed=lambda: self._queue_filter_timer.start(),
            )
        for r, row in enumerate(rows):
            tr = off + r
            for col, (_, keys) in enumerate(spec):
                value, key_used = _app_user_value_for_column(row, keys)
                item = QTableWidgetItem(_format_app_user_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self._right_table.setItem(tr, col, item)
        sync_vertical_header_labels(
            self._right_table,
            filter_visible=self._queue_filter_visible,
            data_row_count=len(rows),
        )
        resize_data_table_columns_to_content(
            self._right_table,
            spec,
            self._staging_rows,
            _app_user_value_for_column,
            _format_app_user_cell,
        )
        self._replicate_btn.setEnabled(len(self._staging_rows) > 0)
        self._update_section_titles()

    def _append_to_staging(self, row: dict[str, Any], *, refresh: bool = True) -> bool:
        uid = _app_user_row_id(row)
        if uid is None:
            self._show_message("Row has no user id; skipped.", error=True)
            return False
        for existing in self._staging_rows:
            if _app_user_row_id(existing) == uid:
                return False
        self._staging_rows.append(dict(row))
        if refresh:
            rows = self._filtered_staging_rows() if self._queue_filter_visible else list(self._staging_rows)
            self._write_staging_table(rows)
        return True

    def _on_row_dropped(self, row: dict[str, Any]) -> None:
        if self._append_to_staging(row):
            return
        if _app_user_row_id(row) is not None:
            self._show_message("That user is already in the queue.", error=False)

    def _move_selected_to_staging(self) -> None:
        off = self._data_row_offset()
        selected = self._left_table.selectionModel().selectedRows()
        if not selected:
            self._show_message("Select one or more app users on the left, then click \u003e.", error=False)
            return
        moved = 0
        for idx in selected:
            tr = idx.row()
            if tr < off:
                continue
            item = self._left_table.item(tr, 0)
            raw = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if isinstance(raw, dict) and self._append_to_staging(dict(raw), refresh=False):
                moved += 1
        if moved:
            rows = self._filtered_staging_rows() if self._queue_filter_visible else list(self._staging_rows)
            self._write_staging_table(rows)
        elif selected:
            self._show_message("No new rows moved (already queued or missing user id).", error=False)

    def _user_ids_from_queue_table_rows(self, table_rows: list[int]) -> set[Any]:
        off = self._queue_data_row_offset()
        uids: set[Any] = set()
        for tr in table_rows:
            if tr < off:
                continue
            item = self._right_table.item(tr, 0)
            raw = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
            if isinstance(raw, dict):
                uid = _app_user_row_id(raw)
                if uid is not None:
                    uids.add(uid)
        return uids

    def _remove_staging_by_user_ids(self, uids: set[Any]) -> int:
        if not uids:
            return 0
        before = len(self._staging_rows)
        self._staging_rows = [r for r in self._staging_rows if _app_user_row_id(r) not in uids]
        return before - len(self._staging_rows)

    def _remove_selected_from_staging(self) -> None:
        if not self._staging_rows:
            return
        off = self._queue_data_row_offset()
        table_rows = sorted(
            {idx.row() for idx in self._right_table.selectionModel().selectedRows() if idx.row() >= off},
            reverse=True,
        )
        if not table_rows:
            self._show_message("Select one or more rows in the queue, then click \u003c.", error=False)
            return
        removed = self._remove_staging_by_user_ids(self._user_ids_from_queue_table_rows(table_rows))
        if removed:
            rows = self._filtered_staging_rows() if self._queue_filter_visible else list(self._staging_rows)
            self._write_staging_table(rows)

    def _on_staging_context_menu(self, pos: QPoint) -> None:
        item = self._right_table.itemAt(pos)
        if item is not None:
            self._right_table.selectRow(item.row())
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        remove_action = menu.addAction("Remove selected")
        remove_action.setEnabled(self._right_table.currentRow() >= 0)
        clear_action = menu.addAction("Clear all")
        clear_action.setEnabled(bool(self._staging_rows))
        chosen = menu.exec(self._right_table.mapToGlobal(pos))
        if chosen == remove_action:
            r = self._right_table.currentRow()
            if self._remove_staging_by_user_ids(self._user_ids_from_queue_table_rows([r])):
                rows = (
                    self._filtered_staging_rows()
                    if self._queue_filter_visible
                    else list(self._staging_rows)
                )
                self._write_staging_table(rows)
        elif chosen == clear_action:
            self._staging_rows.clear()
            self._write_staging_table()

    def _token(self) -> str | None:
        profile = get_user_profile()
        t = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(t) if t else None

    def refresh(self) -> None:
        if self._loading:
            self._pending_refresh = True
            return
        tok = self._token()
        self._loading = True
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self._message_label.setText("Loading users...")
        self._message_label.setVisible(True)
        self._load_thread = QThread(self)
        self._load_worker = _UsersLoadWorker(tok)
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.finished.connect(self._on_users_loaded)
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._cleanup_load_thread)
        self._load_thread.start()

    @Slot()
    def _on_users_loaded(self, success: bool, rows: object, message: str) -> None:
        self._loading = False
        if not success:
            self._show_message(message or "Failed to load users.", error=True)
            self._show_empty_left_table()
        else:
            show_auto_hiding_message(self, self._message_label, "")
            data = list(rows) if isinstance(rows, list) else []
            self._populate_left([r for r in data if isinstance(r, dict)])
        if self._pending_refresh:
            self._pending_refresh = False
            self.refresh()

    def _cleanup_load_thread(self) -> None:
        if self._load_worker is not None:
            self._load_worker.deleteLater()
            self._load_worker = None
        if self._load_thread is not None:
            self._load_thread.deleteLater()
            self._load_thread = None

    def _cleanup_replicate_thread(self) -> None:
        if self._replicate_worker is not None:
            self._replicate_worker.deleteLater()
            self._replicate_worker = None
        if self._replicate_thread is not None:
            self._replicate_thread.deleteLater()
            self._replicate_thread = None

    def _staging_numeric_user_ids(self) -> list[int]:
        """Stable unique list of int IDs from staging rows (same order as staging)."""
        out: list[int] = []
        seen: set[int] = set()
        for r in self._staging_rows:
            rid = _app_user_row_id(r)
            if rid is None or isinstance(rid, bool):
                continue
            try:
                n = int(rid)
            except (TypeError, ValueError):
                continue
            if n not in seen:
                seen.add(n)
                out.append(n)
        return out

    def _on_replicate_clicked(self) -> None:
        if not self._staging_rows:
            return
        if self._replicate_thread is not None and self._replicate_thread.isRunning():
            return
        ids = self._staging_numeric_user_ids()
        if not ids:
            self._show_message("No numeric user IDs in the replication list.", error=True)
            return
        tok = self._token()
        if not tok:
            self._show_message("Session expired. Please log in again.", error=True)
            return
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self._message_label.setText("Replicating…")
        self._message_label.setVisible(True)
        self._replicate_btn.setEnabled(False)
        self._replicate_thread = QThread(self)
        self._replicate_worker = _ReplicateWorker(tok, ids)
        self._replicate_worker.moveToThread(self._replicate_thread)
        self._replicate_thread.started.connect(self._replicate_worker.run)
        self._replicate_worker.finished.connect(self._on_replicate_finished)
        self._replicate_worker.finished.connect(self._replicate_thread.quit)
        self._replicate_thread.finished.connect(self._cleanup_replicate_thread)
        self._replicate_thread.start()

    @Slot()
    def _on_replicate_finished(self, success: bool, message: str) -> None:
        if success:
            self._staging_rows.clear()
            self._write_staging_table()
            self._replicate_btn.setEnabled(False)
            self._show_message(message or "Users replicated successfully.", error=False)
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_message,
                on_back=self.on_back,
            )
        else:
            self._show_message(message or "Replication failed.", error=True)
            self._replicate_btn.setEnabled(len(self._staging_rows) > 0)

    def _reset_copy_page_for_reload(self) -> None:
        """Clear queue and filters when the page is opened (same as API Replicate)."""
        self._pending_refresh = False
        self._filter_apply_timer.stop()
        self._queue_filter_timer.stop()
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.clear()
        self._message_label.setVisible(False)
        self._left_filter_btn.blockSignals(True)
        self._left_filter_btn.setChecked(False)
        self._left_filter_btn.blockSignals(False)
        self._on_filter_toggle(False)
        self._queue_filter_btn.blockSignals(True)
        self._queue_filter_btn.setChecked(False)
        self._queue_filter_btn.blockSignals(False)
        self._on_queue_filter_toggle(False)
        self._staging_rows.clear()
        self._write_staging_table()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._reset_copy_page_for_reload()
        self.refresh()
