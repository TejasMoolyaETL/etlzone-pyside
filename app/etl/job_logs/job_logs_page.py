"""ETL: Job Logs — summary, execution timeline, and live monitor tab."""

from __future__ import annotations

import json
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QBrush, QColor, QHideEvent, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.etl.scan_connection.scan_connection import (
    _DETAILS_COLUMN_SPEC,
    _SCAN_LOG_PARENT_ID_KEYS,
    _SUMMARY_COLUMN_SPEC,
    _TAB_STYLESHEET,
    _apply_scan_log_id_item_sort_role,
    _build_scan_log_tab,
    _detail_row_cell_text,
    _finalize_scan_log_table_sort,
    _log_format_cell,
    _log_row_value,
    _parent_run_id,
    _value_for_column,
    _prepare_scan_header_button,
    normalize_etl_log_detail_items,
    prepare_scan_log_detail_table,
    prepare_scan_log_table_data,
)
from core.api import api_get_all_etl_jobs, api_get_etl_log_by_id
from core.etl_monitor_ws_client import EtlMonitorWebSocketClient, monitor_log_id
from core.user_context import get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from core.app_preferences import format_datetime_display
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
    LIST_PAGE_HEADER_BUTTON_FONT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    LIST_PAGE_HEADER_TITLE_FONT_PX,
    Theme,
)

_JOB_LOGS_HEADER_STYLESHEET = (
    LIST_PAGE_HEADER_STYLESHEET
    + f" QCheckBox {{ color: {Theme.PANEL_TEXT_BRIGHT}; font-size: {LIST_PAGE_HEADER_BUTTON_FONT_PX}px; "
    f"font-weight: 500; spacing: 8px; }} "
    f" QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 3px; "
    f"border: 2px solid {Theme.PANEL_TEXT_BRIGHT}; background: transparent; }} "
    f" QCheckBox::indicator:hover {{ background: rgba(255, 255, 255, 0.15); }} "
    f" QCheckBox::indicator:checked {{ background: {Theme.PANEL_TEXT_BRIGHT}; "
    f"border: 2px solid {Theme.PANEL_TEXT_BRIGHT}; }} "
    f" QCheckBox::indicator:checked:hover {{ background: #e2e8f0; "
    f"border-color: #e2e8f0; }} "
)

_TAB_JOB_LOGS = 0
_TAB_JOB_DETAIL_LOG = 1
_TAB_MONITOR = 2
_MONITOR_MAX_ROWS = 500

_JOB_LOGS_SUBTITLE = (
    "One row per job run. Double-click a row to load its step details in Job Detail Log."
)
_JOB_DETAIL_LOG_SUBTITLE_EMPTY = (
    "Double-click a job in Job Logs to load step details from the server."
)

_MONITOR_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Log Id", ("logId", "log_id", "LogId", "id", "ID")),
    ("Operation", ("operation", "operationType", "operation_type", "Operation")),
    ("Table", ("tableName", "table_name", "table", "TableName")),
    ("Step", ("stepType", "step_type", "step", "StepType")),
    ("Status", ("status", "state", "stepStatus", "Status")),
    ("Message", ("message", "msg", "Message")),
    ("Time", ("time", "timestamp", "createdAt", "createdOn", "Time")),
)

_MONITOR_SUBTITLE = (
    "Live ETL events from the WebSocket. One row per log id — status changes update that row "
    "instead of adding duplicates. Newest activity appears at the top."
)

_STATUS_ROW_BG: dict[str, str] = {
    "SUCCESS": "#d4edda",
    "FAILED": "#f8d7da",
    "RUNNING": "#fff3cd",
    "QUEUED": "#d1ecf1",
}


class _JobLogsFetchWorker(QObject):
    finished = Signal(object, str)

    def __init__(self, token: str | None) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        result = api_get_all_etl_jobs(self._token)
        if result.get("success"):
            self.finished.emit(result.get("data"), "")
        else:
            self.finished.emit([], str(result.get("message") or "Failed to load job logs."))


class _JobLogDetailFetchWorker(QObject):
    finished = Signal(str, object, str, int)

    def __init__(self, log_id: str, token: str | None, seq: int) -> None:
        super().__init__()
        self._log_id = log_id
        self._token = token
        self._seq = seq

    @Slot()
    def run(self) -> None:
        result = api_get_etl_log_by_id(self._log_id, token=self._token)
        if result.get("success"):
            self.finished.emit(self._log_id, result.get("data") or [], "", self._seq)
        else:
            self.finished.emit(
                self._log_id,
                [],
                str(result.get("message") or "Failed to load log details."),
                self._seq,
            )


def _normalize_job_log_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("data", "jobs", "logs", "content"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def _monitor_pick_field(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) not in (None, ""):
            return row.get(key)
    lower_map = {str(k).lower(): k for k in row}
    for key in keys:
        actual = lower_map.get(key.lower())
        if actual is not None:
            value = row.get(actual)
            if value not in (None, ""):
                return value
    return None


def _monitor_value_to_text(value: Any, *, time_field: bool = False) -> str:
    """Monitor cells must show ``0`` and other falsy values (not blank like list tables)."""
    if value is None:
        return "--"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    if time_field:
        text = format_datetime_display(value)
        if text:
            return text
        if value is not None:
            return str(value).strip() or "--"
    text = str(value).strip()
    return text if text else "--"


def _monitor_format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    time_field = key.lower() in ("time", "timestamp", "createdat", "createdon") or (
        bool(key_candidates)
        and key_candidates[0].lower() in ("time", "timestamp", "createdat", "createdon")
    )
    return _monitor_value_to_text(value, time_field=time_field)


def _monitor_rows_from_buffer(buffer: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Buffer is newest-first; keep the first (latest) row per log id."""
    merged: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for payload in buffer:
        if not isinstance(payload, dict):
            continue
        entry = dict(payload)
        log_id = monitor_log_id(entry)
        if log_id:
            if log_id in seen_ids:
                continue
            seen_ids.add(log_id)
        merged.append(entry)
        if len(merged) >= _MONITOR_MAX_ROWS:
            break
    return merged


def _upsert_monitor_row(
    rows: list[dict[str, Any]],
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    """Insert or replace by log id; updated rows move to the top."""
    entry = dict(payload)
    log_id = monitor_log_id(entry)
    updated = [row for row in rows if not log_id or monitor_log_id(row) != log_id]
    updated.insert(0, entry)
    return updated[:_MONITOR_MAX_ROWS]


def _cells_for_monitor_payload(payload: dict[str, Any]) -> list[str]:
    """Build display cells from raw WS JSON (same fields as the HTML monitor)."""
    return [
        _monitor_value_to_text(_monitor_pick_field(payload, "logId", "log_id", "LogId", "id")),
        _monitor_value_to_text(_monitor_pick_field(payload, "operation", "operationType")),
        _monitor_value_to_text(_monitor_pick_field(payload, "tableName", "table_name", "table")),
        _monitor_value_to_text(_monitor_pick_field(payload, "stepType", "step_type", "step")),
        _monitor_value_to_text(_monitor_pick_field(payload, "status", "state", "stepStatus")),
        _monitor_value_to_text(_monitor_pick_field(payload, "message", "msg")),
        _monitor_value_to_text(
            _monitor_pick_field(payload, "time", "timestamp", "createdAt", "createdOn"),
            time_field=True,
        ),
    ]


def _monitor_table_item(text: str, *, status: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    item.setForeground(QBrush(QColor("#0f172a")))
    bg = _STATUS_ROW_BG.get(status.upper(), _STATUS_ROW_BG["QUEUED"])
    item.setBackground(QBrush(QColor(bg)))
    return item


class JobLogsPageWidget(QWidget):
    """Job logs parent/child tables and live monitor tab."""

    job_detail_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._summary_source_rows: list[dict[str, str]] = []
        self._summary_raw_entries: list[dict[str, Any]] = []
        self._details_source_rows: list[dict[str, str]] = []
        self._summary_column_spec: list[tuple[str, tuple[str, ...]]] = list(_SUMMARY_COLUMN_SPEC)
        self._details_column_spec: list[tuple[str, tuple[str, ...]]] = list(_DETAILS_COLUMN_SPEC)
        self._summary_filter_visible = False
        self._details_filter_visible = False
        self._detail_job_id_filter: str | None = None
        self._summary_filter_timer = QTimer(self)
        self._summary_filter_timer.setSingleShot(True)
        self._summary_filter_timer.setInterval(200)
        self._summary_filter_timer.timeout.connect(self._apply_summary_column_filters)
        self._details_filter_timer = QTimer(self)
        self._details_filter_timer.setSingleShot(True)
        self._details_filter_timer.setInterval(200)
        self._details_filter_timer.timeout.connect(self._apply_details_column_filters)
        self._monitor_rows: list[dict[str, Any]] = []
        self._monitor_filter_visible = False
        self._monitor_connected = False
        self._monitor_event_count = 0
        self._monitor_last_error = ""
        self._monitor_filter_timer = QTimer(self)
        self._monitor_filter_timer.setSingleShot(True)
        self._monitor_filter_timer.setInterval(200)
        self._monitor_filter_timer.timeout.connect(self._refresh_monitor_table)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(_JOB_LOGS_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        title = QLabel("ETL: Job Logs")
        title.setStyleSheet(
            f"font-size: {LIST_PAGE_HEADER_TITLE_FONT_PX}px; font-weight: 600; color: #ffffff;"
        )
        hl.addWidget(title)
        hl.addStretch()
        self.auto_refresh_checkbox = QCheckBox("Auto refresh (3s)")
        self.auto_refresh_checkbox.setChecked(True)
        self.auto_refresh_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn = QPushButton("Refresh")
        _prepare_scan_header_button(self.refresh_btn, width_px=100)
        hl.addWidget(self.auto_refresh_checkbox)
        hl.addWidget(self.refresh_btn)
        root.addWidget(header)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setStyleSheet(_TAB_STYLESHEET)
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        job_logs_tab = QWidget()
        content_layout = QVBoxLayout(job_logs_tab)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(10)

        self.job_summary_filters_btn = QPushButton("Filters")
        job_summary_tab, self.job_summary_table, _ = _build_scan_log_tab(
            header_title="Job Logs",
            subtitle=_JOB_LOGS_SUBTITLE,
            column_count=len(_SUMMARY_COLUMN_SPEC),
            filters_btn=self.job_summary_filters_btn,
            filters_in_header=True,
        )
        content_layout.addWidget(job_summary_tab, 1)

        self.page_status_label = QLabel("")
        self.page_status_label.setWordWrap(True)
        content_layout.addWidget(self.page_status_label)

        self.tabs.addTab(job_logs_tab, "Job Logs")

        self.job_detail_show_all_btn = QPushButton("Clear")
        self.job_detail_show_all_btn.setVisible(False)
        self.job_detail_filters_btn = QPushButton("Filters")
        job_detail_tab, self.job_detail_table, self.job_detail_hint = _build_scan_log_tab(
            header_title="Job Detail Log",
            subtitle=_JOB_DETAIL_LOG_SUBTITLE_EMPTY,
            column_count=len(_DETAILS_COLUMN_SPEC),
            filters_btn=self.job_detail_filters_btn,
            header_widgets_before_filters=(self.job_detail_show_all_btn,),
        )
        self.job_detail_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.tabs.addTab(job_detail_tab, "Job Detail Log")

        self.monitor_clear_btn = QPushButton("Clear")
        self.monitor_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.monitor_filters_btn = QPushButton("Filters")
        monitor_tab, self.monitor_table, self.monitor_hint = _build_scan_log_tab(
            header_title="Live Monitor",
            subtitle=_MONITOR_SUBTITLE,
            column_count=len(_MONITOR_COLUMN_SPEC),
            filters_btn=self.monitor_filters_btn,
            header_widgets_before_filters=(self.monitor_clear_btn,),
        )
        self.monitor_filters_btn.toggled.connect(self._on_monitor_filters_toggled)
        self.monitor_table.setSortingEnabled(False)
        self.tabs.addTab(monitor_tab, "Monitor")

        root.addWidget(self.tabs, 1)
        self._write_monitor_table([])
        self._update_monitor_hint()

        self.job_summary_filters_btn.toggled.connect(self._on_summary_filters_toggled)
        self.job_detail_filters_btn.toggled.connect(self._on_details_filters_toggled)
        self.job_summary_table.itemDoubleClicked.connect(self._on_summary_row_double_clicked)
        self.job_detail_show_all_btn.clicked.connect(self._clear_detail_job_filter)

    def current_tab_index(self) -> int:
        return self.tabs.currentIndex()

    def set_monitor_connection_connected(self, connected: bool) -> None:
        self._monitor_connected = connected
        if connected:
            self._monitor_last_error = ""
        self._update_monitor_hint()

    def set_monitor_connection_error(self, message: str) -> None:
        self._monitor_last_error = (message or "").strip()
        self._monitor_connected = False
        self._update_monitor_hint()

    def load_monitor_buffer(self, buffer: list[dict[str, Any]]) -> None:
        """Load buffered WebSocket events (one row per log id, newest state)."""
        self._monitor_rows = _monitor_rows_from_buffer(buffer)
        self._write_monitor_table(self._monitor_rows)
        self._update_monitor_hint()

    def clear_monitor_logs(self) -> None:
        self._monitor_rows = []
        self._monitor_event_count = 0
        if self._monitor_filter_visible:
            clear_filter_row_widgets(self.monitor_table)
        self._write_monitor_table([])
        self._update_monitor_hint()

    def append_monitor_log(self, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            return
        self._monitor_event_count += 1
        self._monitor_rows = _upsert_monitor_row(self._monitor_rows, payload)
        if self._monitor_filter_visible:
            self._refresh_monitor_table()
        else:
            self._write_monitor_table(self._monitor_rows)
        self._update_monitor_hint()

    def _update_monitor_hint(self) -> None:
        conn = "CONNECTED" if self._monitor_connected else "DISCONNECTED"
        text = (
            f"{_MONITOR_SUBTITLE} Connection: {conn}. "
            f"Jobs: {len(self._monitor_rows)}. Updates received: {self._monitor_event_count}."
        )
        if self._monitor_last_error and not self._monitor_connected:
            text += f" Error: {self._monitor_last_error}"
        self.monitor_hint.setText(text)

    def _on_monitor_filters_toggled(self, checked: bool) -> None:
        self._monitor_filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self.monitor_table)
        self._refresh_monitor_table()

    def _schedule_monitor_filter_apply(self) -> None:
        if self._monitor_filter_visible:
            self._monitor_filter_timer.start()

    def _refresh_monitor_table(self) -> None:
        table = self.monitor_table
        rows = list(self._monitor_rows)
        saved = saved_filter_texts(table) if self._monitor_filter_visible else None
        if self._monitor_filter_visible:
            filtered: list[dict[str, Any]] = []
            for payload in rows:
                if not isinstance(payload, dict):
                    continue
                cells = _cells_for_monitor_payload(payload)
                match = True
                for col, (_, keys) in enumerate(_MONITOR_COLUMN_SPEC):
                    w = table.cellWidget(0, col)
                    if not isinstance(w, QLineEdit):
                        continue
                    q = w.text().strip().lower()
                    if q and q not in cells[col].lower():
                        match = False
                        break
                if match:
                    filtered.append(payload)
            rows = filtered
        self._write_monitor_table(rows, saved_filter_texts_list=saved)

    def _write_monitor_table(
        self,
        rows: list[dict[str, Any]],
        *,
        saved_filter_texts_list: list[str] | None = None,
    ) -> None:
        table = self.monitor_table
        spec = list(_MONITOR_COLUMN_SPEC)
        headers = [h for h, _ in spec]
        off = data_row_offset(self._monitor_filter_visible)
        table.setSortingEnabled(False)
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        total = off + len(rows)
        if self._monitor_filter_visible and total < 1:
            total = 1
        table.setRowCount(total)
        if self._monitor_filter_visible:
            for c in range(len(headers)):
                table.takeItem(0, c)
            install_filter_row(
                table,
                len(headers),
                on_text_changed=self._schedule_monitor_filter_apply,
            )
            if saved_filter_texts_list:
                restore_filter_texts(table, saved_filter_texts_list)
        for r_index, payload in enumerate(rows):
            if not isinstance(payload, dict):
                continue
            tr = off + r_index
            cells = _cells_for_monitor_payload(payload)
            status = str(_monitor_pick_field(payload, "status", "state", "stepStatus") or "")
            for col, text in enumerate(cells):
                table.setItem(tr, col, _monitor_table_item(text, status=status))
        sync_vertical_header_labels(
            table,
            filter_visible=self._monitor_filter_visible,
            data_row_count=len(rows),
        )
        if rows:
            self._resize_monitor_columns(table)

    def _resize_monitor_columns(self, table: QTableWidget) -> None:
        spec = list(_MONITOR_COLUMN_SPEC)
        fm = table.fontMetrics()
        fm_h = table.horizontalHeader().fontMetrics()
        for col, (header, _) in enumerate(spec):
            width = fm_h.horizontalAdvance(header) + 18
            for row in range(table.rowCount()):
                item = table.item(row, col)
                if item is not None:
                    width = max(width, fm.horizontalAdvance(item.text()) + 12)
            table.setColumnWidth(col, max(48, width))

    def render_all_reports(self, payload: Any) -> None:
        entries = _normalize_job_log_entries(payload)
        self.set_job_log_data(entries, clear_detail=self._detail_job_id_filter is None)

    def _summary_spec_list(self) -> list[tuple[str, tuple[str, ...]]]:
        return list(self._summary_column_spec)

    def _details_spec_list(self) -> list[tuple[str, tuple[str, ...]]]:
        return list(self._details_column_spec)

    def _summary_data_row_offset(self) -> int:
        return data_row_offset(self._summary_filter_visible)

    def _details_data_row_offset(self) -> int:
        return data_row_offset(self._details_filter_visible)

    def _schedule_summary_filter_apply(self) -> None:
        if self._summary_filter_visible:
            self._summary_filter_timer.start()

    def _schedule_details_filter_apply(self) -> None:
        if self._details_filter_visible:
            self._details_filter_timer.start()

    def _filtered_summary_rows(self) -> list[dict[str, str]]:
        return filter_dict_rows_by_column_edits(
            self._summary_source_rows,
            self.job_summary_table,
            self._summary_spec_list(),
            self._summary_filter_visible,
            _log_row_value,
            _log_format_cell,
        )

    def _details_rows_for_display(self) -> list[dict[str, str]]:
        if not self._detail_job_id_filter:
            return []
        return filter_dict_rows_by_column_edits(
            list(self._details_source_rows),
            self.job_detail_table,
            self._details_spec_list(),
            self._details_filter_visible,
            _log_row_value,
            _log_format_cell,
        )

    def _raw_entry_for_summary_row(self, row: dict[str, str]) -> dict[str, Any] | None:
        rid = ""
        for _, keys in self._summary_column_spec:
            if keys[0] in _SCAN_LOG_PARENT_ID_KEYS:
                rid = str(row.get(keys[0], "")).strip()
                if rid and rid != "--":
                    break
        if not rid:
            rid = str(row.get("id", "")).strip()
        if not rid or rid == "--":
            return None
        for raw in self._summary_raw_entries:
            if _parent_run_id(raw) == rid:
                return raw
        return None

    def _write_summary_table(self, rows: list[dict[str, str]]) -> None:
        spec = self._summary_spec_list()
        headers = [h for h, _ in spec]
        table = self.job_summary_table
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        off = self._summary_data_row_offset()
        total = off + len(rows)
        if self._summary_filter_visible and total < 1:
            total = 1
        table.setSortingEnabled(False)
        table.setRowCount(total)
        if self._summary_filter_visible:
            for c in range(table.columnCount()):
                table.takeItem(0, c)
            install_filter_row(
                table,
                table.columnCount(),
                on_text_changed=self._schedule_summary_filter_apply,
            )
        for r, row in enumerate(rows):
            tr = off + r
            raw = self._raw_entry_for_summary_row(row)
            for col, (_header, keys) in enumerate(spec):
                text = row.get(keys[0], "")
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    raw_id = raw.get("id") if isinstance(raw, dict) else row.get(keys[0])
                    _apply_scan_log_id_item_sort_role(item, raw_id)
                    if isinstance(raw, dict):
                        item.setData(Qt.ItemDataRole.UserRole, raw)
                table.setItem(tr, col, item)
        sync_vertical_header_labels(
            table,
            filter_visible=self._summary_filter_visible,
            data_row_count=len(rows),
        )
        if self._summary_source_rows:
            resize_data_table_columns_to_content(
                table,
                spec,
                self._summary_source_rows,
                _log_row_value,
                _log_format_cell,
            )
        _finalize_scan_log_table_sort(table, filter_visible=self._summary_filter_visible)

    def _write_details_table(self, rows: list[dict[str, str]]) -> None:
        spec = self._details_spec_list()
        headers = [h for h, _ in spec]
        table = self.job_detail_table
        table.clearContents()
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        off = self._details_data_row_offset()
        total = off + len(rows)
        if self._details_filter_visible and total < 1:
            total = 1
        table.setSortingEnabled(False)
        table.setRowCount(total)
        if self._details_filter_visible:
            for c in range(table.columnCount()):
                table.takeItem(0, c)
            install_filter_row(
                table,
                table.columnCount(),
                on_text_changed=self._schedule_details_filter_apply,
            )
        for r, row in enumerate(rows):
            tr = off + r
            for col, (_header, keys) in enumerate(spec):
                text = _detail_row_cell_text(row, keys)
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    value, _ = _value_for_column(row, keys)
                    _apply_scan_log_id_item_sort_role(item, value)
                table.setItem(tr, col, item)
        sync_vertical_header_labels(
            table,
            filter_visible=self._details_filter_visible,
            data_row_count=len(rows),
        )
        if self._details_source_rows:
            resize_data_table_columns_to_content(
                table,
                spec,
                self._details_source_rows,
                _log_row_value,
                _log_format_cell,
            )
        _finalize_scan_log_table_sort(table, filter_visible=self._details_filter_visible)

    def _apply_summary_column_filters(self) -> None:
        if not self._summary_filter_visible:
            return
        self._write_summary_table(self._filtered_summary_rows())

    def _apply_details_column_filters(self) -> None:
        if not self._details_filter_visible:
            return
        self._write_details_table(self._details_rows_for_display())

    def _on_summary_filters_toggled(self, checked: bool) -> None:
        self._summary_filter_visible = checked
        if not checked:
            self._summary_filter_timer.stop()
            clear_filter_row_widgets(self.job_summary_table)
        rows = self._filtered_summary_rows() if checked else list(self._summary_source_rows)
        self._write_summary_table(rows)

    def _on_details_filters_toggled(self, checked: bool) -> None:
        self._details_filter_visible = checked
        if not checked:
            self._details_filter_timer.stop()
            clear_filter_row_widgets(self.job_detail_table)
        self._write_details_table(self._details_rows_for_display())

    def request_job_log_details(self, job_id: str) -> None:
        """Called by page controller to load ``GET api/etl/logs/{id}``."""
        self._detail_job_id_filter = job_id
        self._details_source_rows = []
        self._details_column_spec = list(_DETAILS_COLUMN_SPEC)
        self._update_detail_filter_hint(loading=True)
        self._write_details_table([])
        self.tabs.setCurrentIndex(_TAB_JOB_DETAIL_LOG)

    def apply_job_log_details(
        self,
        job_id: str,
        detail_items: list[dict[str, Any]],
        *,
        error_message: str = "",
    ) -> None:
        self._detail_job_id_filter = job_id
        if error_message:
            self._details_source_rows = []
            self._details_column_spec = list(_DETAILS_COLUMN_SPEC)
            self._update_detail_filter_hint(error=error_message)
            self._write_details_table([])
            return
        self._details_column_spec, self._details_source_rows = prepare_scan_log_detail_table(
            job_id, detail_items
        )
        self._update_detail_filter_hint()
        self._write_details_table(self._details_rows_for_display())

    def _on_summary_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if item.row() < self._summary_data_row_offset():
            return
        cell = self.job_summary_table.item(item.row(), 0)
        if cell is None:
            return
        entry = cell.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, dict):
            return
        job_id = _parent_run_id(entry)
        if not job_id:
            return
        self.job_detail_requested.emit(job_id)

    def _clear_detail_job_filter(self) -> None:
        self._detail_job_id_filter = None
        self._details_source_rows = []
        self._details_column_spec = list(_DETAILS_COLUMN_SPEC)
        self._update_detail_filter_hint()
        self._write_details_table([])

    def _update_detail_filter_hint(
        self,
        *,
        loading: bool = False,
        error: str = "",
    ) -> None:
        if loading and self._detail_job_id_filter:
            self.job_detail_hint.setText(
                f"Loading step details for job Id {self._detail_job_id_filter}…"
            )
            self.job_detail_show_all_btn.setVisible(True)
        elif error and self._detail_job_id_filter:
            self.job_detail_hint.setText(
                f"Job Id {self._detail_job_id_filter}: {error}"
            )
            self.job_detail_show_all_btn.setVisible(True)
        elif self._detail_job_id_filter:
            count = len(self._details_source_rows)
            self.job_detail_hint.setText(
                f"Step details for job Id {self._detail_job_id_filter} ({count} row(s)). "
                "Use Clear to close."
            )
            self.job_detail_show_all_btn.setVisible(True)
        else:
            self.job_detail_hint.setText(_JOB_DETAIL_LOG_SUBTITLE_EMPTY)
            self.job_detail_show_all_btn.setVisible(False)

    def set_job_log_data(
        self,
        entries: list[dict[str, Any]],
        *,
        clear_detail: bool = True,
    ) -> None:
        if clear_detail:
            self._detail_job_id_filter = None
            self._details_source_rows = []
            self._details_column_spec = list(_DETAILS_COLUMN_SPEC)
            self._update_detail_filter_hint()
        (
            matched,
            self._summary_column_spec,
            _details_spec_unused,
            self._summary_source_rows,
            _detail_rows_unused,
        ) = prepare_scan_log_table_data(entries)
        self._summary_raw_entries = matched
        if clear_detail:
            self._write_details_table([])
        summary_display = (
            self._filtered_summary_rows()
            if self._summary_filter_visible
            else list(self._summary_source_rows)
        )
        self._write_summary_table(summary_display)
        if not clear_detail and self._detail_job_id_filter:
            self._write_details_table(self._details_rows_for_display())


class EtlJobLogsPage(QWidget):
    """Job logs page with background fetch and optional polling."""

    _POLL_MS = 3000

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        monitor_ws: EtlMonitorWebSocketClient | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._ui = JobLogsPageWidget()
        layout.addWidget(self._ui)

        self._auto_refresh = True
        self._fetch_in_flight = False
        self._last_payload: dict[str, Any] = {}
        self._fetch_thread: QThread | None = None
        self._fetch_worker: _JobLogsFetchWorker | None = None
        self._detail_fetch_in_flight = False
        self._detail_fetch_seq = 0
        self._detail_fetch_pending_id: str | None = None
        self._detail_fetch_thread: QThread | None = None
        self._detail_fetch_worker: _JobLogDetailFetchWorker | None = None
        self._visible = False
        self._owns_monitor_ws = monitor_ws is None
        self._monitor_ws = monitor_ws or EtlMonitorWebSocketClient(self)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(self._POLL_MS)
        self._poll_timer.timeout.connect(self.refresh)

        self._ui.refresh_btn.clicked.connect(self.refresh)
        self._ui.auto_refresh_checkbox.stateChanged.connect(self._on_auto_refresh_toggled)
        self._ui.monitor_clear_btn.clicked.connect(self._clear_monitor_logs)
        self._ui.job_detail_requested.connect(self._load_job_log_details)
        self._ui.tabs.currentChanged.connect(self._on_main_tab_changed)
        self._monitor_ws.log_received.connect(self._on_monitor_log)
        self._monitor_ws.connection_changed.connect(self._ui.set_monitor_connection_connected)
        self._monitor_ws.connection_error.connect(self._ui.set_monitor_connection_error)
        if self._owns_monitor_ws:
            self._monitor_ws.start()

    def _clear_monitor_logs(self) -> None:
        self._monitor_ws.clear_buffer()
        self._ui.clear_monitor_logs()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._visible = True
        self.refresh()
        if self._auto_refresh:
            self._poll_timer.start()
        self._sync_monitor_from_buffer()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self._visible = False
        self._poll_timer.stop()
        if self._owns_monitor_ws:
            self._monitor_ws.stop()

    def _sync_monitor_from_buffer(self) -> None:
        self._ui.set_monitor_connection_connected(self._monitor_ws.is_connected())
        self._ui.load_monitor_buffer(self._monitor_ws.buffered_logs())

    def _on_main_tab_changed(self, index: int) -> None:
        if index == _TAB_MONITOR:
            self._sync_monitor_from_buffer()

    def _schedule_job_log_details(self, job_id: str) -> None:
        job_id = str(job_id or "").strip()
        if not job_id:
            return
        self._detail_fetch_pending_id = job_id
        if not self._detail_fetch_in_flight:
            self._start_job_log_detail_fetch()

    def _start_job_log_detail_fetch(self) -> None:
        if self._detail_fetch_in_flight:
            return
        job_id = str(self._detail_fetch_pending_id or "").strip()
        if not job_id:
            return
        self._detail_fetch_seq += 1
        seq = self._detail_fetch_seq
        self._detail_fetch_in_flight = True
        self._ui.request_job_log_details(job_id)
        self._detail_fetch_thread = QThread(self)
        self._detail_fetch_worker = _JobLogDetailFetchWorker(job_id, self._token(), seq)
        self._detail_fetch_worker.moveToThread(self._detail_fetch_thread)
        self._detail_fetch_thread.started.connect(self._detail_fetch_worker.run)
        self._detail_fetch_worker.finished.connect(self._on_detail_fetch_finished)
        self._detail_fetch_worker.finished.connect(self._detail_fetch_thread.quit)
        self._detail_fetch_thread.finished.connect(self._cleanup_detail_fetch_thread)
        self._detail_fetch_thread.start()

    def _load_job_log_details(self, job_id: str) -> None:
        self._schedule_job_log_details(job_id)

    @Slot(str, object, str, int)
    def _on_detail_fetch_finished(
        self,
        job_id: str,
        payload: object,
        error_message: str,
        seq: int,
    ) -> None:
        if seq != self._detail_fetch_seq:
            return
        self._detail_fetch_in_flight = False
        current = str(self._ui._detail_job_id_filter or "").strip()
        if str(job_id) != current:
            if current:
                self._detail_fetch_pending_id = current
                self._start_job_log_detail_fetch()
            return
        detail_rows = normalize_etl_log_detail_items(payload)
        self._ui.apply_job_log_details(
            job_id,
            detail_rows,
            error_message=str(error_message or ""),
        )
        pending = str(self._detail_fetch_pending_id or "").strip()
        if pending and pending != str(job_id):
            self._start_job_log_detail_fetch()

    @Slot()
    def _cleanup_detail_fetch_thread(self) -> None:
        if self._detail_fetch_worker is not None:
            self._detail_fetch_worker.deleteLater()
            self._detail_fetch_worker = None
        if self._detail_fetch_thread is not None:
            self._detail_fetch_thread.deleteLater()
            self._detail_fetch_thread = None

    @Slot(dict)
    def _on_monitor_log(self, payload: dict[str, Any]) -> None:
        self._ui.append_monitor_log(payload)

    def refresh(self) -> None:
        if self._fetch_in_flight:
            return
        self._fetch_in_flight = True
        self._ui.page_status_label.setText("Loading job logs…")
        self._fetch_thread = QThread(self)
        self._fetch_worker = _JobLogsFetchWorker(self._token())
        self._fetch_worker.moveToThread(self._fetch_thread)
        self._fetch_thread.started.connect(self._fetch_worker.run)
        self._fetch_worker.finished.connect(self._on_fetch_finished)
        self._fetch_worker.finished.connect(self._fetch_thread.quit)
        self._fetch_thread.finished.connect(self._cleanup_fetch_thread)
        self._fetch_thread.start()

    def _token(self) -> str | None:
        profile = get_user_profile() or {}
        return profile.get("token") or profile.get("accessToken")

    def _on_auto_refresh_toggled(self, state: int) -> None:
        self._auto_refresh = Qt.CheckState(state) == Qt.CheckState.Checked
        if self._visible and self._auto_refresh:
            self._poll_timer.start()
        else:
            self._poll_timer.stop()

    @Slot(object, str)
    def _on_fetch_finished(self, payload: object, error_message: str) -> None:
        self._fetch_in_flight = False
        if error_message:
            self._ui.page_status_label.setText("Failed to load job logs.")
            show_auto_hiding_message(
                self,
                self._ui.page_status_label,
                str(error_message),
                error=True,
            )
            return

        try:
            self._last_payload = payload
            self._ui.render_all_reports(payload)
            show_auto_hiding_message(self, self._ui.page_status_label, "", error=False)
            active_detail_id = self._ui._detail_job_id_filter
            if active_detail_id:
                self._schedule_job_log_details(str(active_detail_id))

            jobs = _normalize_job_log_entries(payload)
            any_running = any(
                str((job or {}).get("status", "")).upper() in ("QUEUED", "RUNNING") for job in jobs
            )
            if not any_running:
                self._poll_timer.stop()
            elif self._visible and self._auto_refresh:
                self._poll_timer.start()
        except Exception:
            self._ui.page_status_label.setText("Failed to load job logs.")
            show_auto_hiding_message(
                self,
                self._ui.page_status_label,
                "Failed to load job logs.",
                error=True,
            )

    def _cleanup_fetch_thread(self) -> None:
        if self._fetch_worker is not None:
            self._fetch_worker.deleteLater()
            self._fetch_worker = None
        if self._fetch_thread is not None:
            self._fetch_thread.deleteLater()
            self._fetch_thread = None
