"""ETL: Scan — connection list with SCAN log summary and detail tabs."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics, QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.api import (
    api_get_all_connections,
    api_get_etl_logs_by_connection_and_operation_type,
    api_get_metadata_tables,
    api_metadata_scan_all,
    api_metadata_scan_by_filter,
    api_post_scan_connection_source_tables,
)
from core.user_context import get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.blank_display import is_blank_display_value
from ui.data_table import (
    MIN_DATA_COL_WIDTH_PX,
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    data_row_offset,
    filter_dict_rows_by_column_edits,
    format_data_table_cell,
    install_filter_row,
    render_dict_rows_table,
    resize_data_table_columns_to_content,
    saved_filter_texts,
    sync_vertical_header_labels,
)
from ui.form_page_styles import (
    APP_FONT_SIZE_PX,
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE,
    FORM_LABEL_STYLE,
    FORM_PAGE_FONT_SIZE_PX,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    LIST_PAGE_HEADER_TITLE_FONT_PX,
    themed_list_page_header_stylesheet,
)

_TAB_SCAN_HISTORY = 1
_TAB_SCAN_DETAIL_LOG = 2
_INNER_TAB_SCANNED_LIST = 0
_INNER_TAB_SCAN_BY_FILTER = 1
from ui.widgets.required_label import field_caption_label, labeled_field_block
from ui.theme import Theme

_CONNECTION_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Connection Name", ("connectionName",)),
    ("Connection ID", ("connectionId", "connectionID", "connection_id", "id")),
)

_SCANNED_LIST_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Table Name", ("TABLE_NAME", "tableName", "table_name", "name")),
    ("Schema", ("schemaName", "schema", "SCHEMA_NAME", "schema_name")),
    ("Last Scan", ("LAST_SCAN_DATE", "lastScanDate", "last_scan_date")),
)

_TAB_STYLESHEET = (
    "QTabWidget::pane { border: 1px solid #e2e8f0; border-radius: 6px; background: #ffffff; }"
    "QTabBar::tab {"
    f" font-size: {FORM_PAGE_FONT_SIZE_PX}px; padding: 8px 16px; margin-right: 4px;"
    " background: #f1f5f9; color: #475569; border: 1px solid #e2e8f0;"
    " border-bottom: none; border-top-left-radius: 6px; border-top-right-radius: 6px;"
    "}"
    "QTabBar::tab:selected { background: #ffffff; color: #0f172a; font-weight: 600; }"
    "QTabBar::tab:hover:!selected { background: #e2e8f0; }"
)

# Summary: one row per scan run (newest first), excluding details[].
_SUMMARY_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Id", ("id",)),
    ("Operation Type", ("operationType", "operation_type")),
    ("Status", ("status",)),
    ("Error Reason", ("errorMessage", "error_message")),
    ("Created By", ("createdBy", "created_by")),
    ("Start Time", ("startTime", "start_time")),
    ("End Time", ("endTime", "end_time")),
    ("Duration (ms)", ("durationMs", "duration_ms")),
    ("Success Count", ("successCount", "success_count")),
    ("Failed Count", ("failedCount", "failed_count")),
    ("Total Tables", ("totalTables", "total_tables")),
    ("Created On", ("createdAt", "created_at", "createdOn", "created_on")),
)

# Scan details: per-table steps (details[]), Id = parent scan run id.
_DETAILS_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Id", ("scan_id",)),
    ("Table", ("table", "tableName")),
    ("Step", ("step", "stepType")),
    ("Status", ("status",)),
    ("Start", ("start", "startTime")),
    ("End", ("end", "endTime")),
    ("Duration (ms)", ("duration", "durationMs")),
    ("No. of Columns", ("columns", "rows", "rowsProcessed")),
    ("Error Reason", ("error", "errorMessage")),
)

_SCAN_HISTORY_SUBTITLE = (
    "One row per scan run for this connection. "
    "Double-click a row to open its per-table steps in Scan Detail Log."
)
_SCAN_DETAIL_LOG_SUBTITLE_ALL = (
    "Per-table steps for all scan runs on this connection. "
    "Double-click a row in Scan History to filter by scan run."
)
_SCAN_TAB_SUBTITLE_SCANNED_LIST = (
    "Tables already scanned for the selected connection. "
    "Use Scan All to scan the full database, or use the Scan by filter tab for a targeted scan."
)
_SCAN_TAB_SUBTITLE_FILTER = (
    "Use schema and table name filters, load and select database tables on the left, "
    "then run a targeted scan. View scanned results on the Scanned tables tab."
)

# Embedded tab toolbars (smaller than full-page LIST_PAGE_HEADER_*).
_SCAN_LOG_TAB_HEADER_HEIGHT_PX = 30
_SCAN_LOG_TAB_HEADER_TITLE_FONT_PX = 11
_SCAN_LOG_TAB_HEADER_LAYOUT_MARGINS = (10, 0, 10, 0)
_SCAN_LOG_TAB_HEADER_LAYOUT_SPACING = 6
_SCAN_LOG_TAB_SUBTITLE_STYLE = (
    f"font-size: {APP_FONT_SIZE_PX}px; color: {Theme.TEXT_SECONDARY}; font-weight: 400;"
)
_SCAN_LOG_TAB_HEADER_STYLESHEET = themed_list_page_header_stylesheet(
    widget_bg=Theme.HEADER_NAV,
    label_color=Theme.PANEL_TEXT_BRIGHT,
    button_bg=Theme.HEADER_ACCENT,
    button_color=Theme.PANEL_TEXT_BRIGHT,
    button_hover=Theme.HEADER_ACCENT_HOVER,
    button_pressed=Theme.HEADER_ACCENT_PRESSED,
    title_font_px=_SCAN_LOG_TAB_HEADER_TITLE_FONT_PX,
    button_font_px=APP_FONT_SIZE_PX,
    button_padding_v_px=2,
    button_padding_h_px=10,
)

def _prepare_scan_header_button(btn: QPushButton, *, width_px: int | None = 88) -> None:
    if width_px is not None:
        btn.setFixedWidth(width_px)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)


def _size_scan_header_button_to_text(btn: QPushButton, *, padding_px: int = 24) -> None:
    """Fit navy header button width to its label (avoids clipped text on HiDPI)."""
    metrics = QFontMetrics(btn.font())
    btn.setFixedWidth(metrics.horizontalAdvance(btn.text()) + padding_px)


def _build_scan_operation_tab(
    *,
    header_title: str,
    subtitle: str,
    header_buttons: tuple[QPushButton, ...],
    content: QWidget,
) -> QWidget:
    """Scan sub-tab: navy toolbar, subtitle, and custom body (same pattern as log tabs)."""
    tab = QWidget()
    tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    root = QVBoxLayout(tab)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    header = QFrame()
    header.setStyleSheet(_SCAN_LOG_TAB_HEADER_STYLESHEET)
    header.setFixedHeight(_SCAN_LOG_TAB_HEADER_HEIGHT_PX)
    hl = QHBoxLayout(header)
    hl.setContentsMargins(*_SCAN_LOG_TAB_HEADER_LAYOUT_MARGINS)
    hl.setSpacing(_SCAN_LOG_TAB_HEADER_LAYOUT_SPACING)
    hl.addWidget(QLabel(header_title))
    hl.addStretch()
    for btn in header_buttons:
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hl.addWidget(btn)
    root.addWidget(header)

    body = QWidget()
    body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(8)
    hint = QLabel(subtitle)
    hint.setWordWrap(True)
    hint.setStyleSheet(_SCAN_LOG_TAB_SUBTITLE_STYLE)
    body_layout.addWidget(hint)
    content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    body_layout.addWidget(content, 1)
    root.addWidget(body, 1)
    return tab


def _build_scan_filter_database_panel(
    *,
    schema_input: QLineEdit,
    name_contains_input: QLineEdit,
    select_all_cb: QCheckBox,
    table: QTableWidget,
    load_btn: QPushButton,
) -> QWidget:
    """Left pane: schema/name filters, Database tables bar, select-all above checkbox column."""
    panel = QWidget()
    panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    root = QVBoxLayout(panel)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(8)

    filters = QVBoxLayout()
    filters.setSpacing(8)
    filters.addWidget(
        labeled_field_block(
            field_caption_label("Schema", FORM_LABEL_STYLE),
            schema_input,
        )
    )
    filters.addWidget(
        labeled_field_block(
            field_caption_label("Table name contains", FORM_LABEL_STYLE),
            name_contains_input,
        )
    )
    root.addLayout(filters)

    bar = QFrame()
    bar.setStyleSheet(_SCAN_LOG_TAB_HEADER_STYLESHEET)
    bar.setFixedHeight(_SCAN_LOG_TAB_HEADER_HEIGHT_PX)
    bar_hl = QHBoxLayout(bar)
    bar_hl.setContentsMargins(*_SCAN_LOG_TAB_HEADER_LAYOUT_MARGINS)
    bar_hl.setSpacing(_SCAN_LOG_TAB_HEADER_LAYOUT_SPACING)
    bar_hl.addWidget(QLabel("Database tables"))
    bar_hl.addStretch()
    load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    bar_hl.addWidget(load_btn)
    root.addWidget(bar)

    select_row = QHBoxLayout()
    select_row.setContentsMargins(0, 0, 0, 0)
    select_row.setSpacing(0)
    col0_slot = QWidget()
    col0_slot.setFixedWidth(40)
    col0_l = QHBoxLayout(col0_slot)
    col0_l.setContentsMargins(0, 0, 0, 0)
    col0_l.addWidget(select_all_cb, 0, Qt.AlignmentFlag.AlignCenter)
    select_row.addWidget(col0_slot)
    select_row.addStretch()
    root.addLayout(select_row)

    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    root.addWidget(table, 1)
    return panel


def _configure_scan_filter_source_table(table: QTableWidget) -> None:
    hh = table.horizontalHeader()
    if table.columnCount() > 0:
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        table.setColumnWidth(0, 40)
    if table.columnCount() > 1:
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)


def _build_scan_tables_widget(
    headers: list[str],
    *,
    read_only: bool,
    checkbox_column: bool = False,
) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    if checkbox_column:
        table.setColumnWidth(0, 40)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    apply_data_table_appearance(
        table,
        read_only=read_only,
        stretch_last_section=not checkbox_column,
        hide_vertical_header=checkbox_column,
    )
    if checkbox_column:
        _configure_scan_filter_source_table(table)
    attach_table_copy_shortcut(table)
    return table


def _build_scan_log_tab(
    *,
    header_title: str,
    subtitle: str,
    column_count: int,
    filters_btn: QPushButton | None = None,
    header_widgets_before_filters: tuple[QWidget, ...] = (),
    filters_in_header: bool = True,
) -> tuple[QWidget, QTableWidget, QLabel]:
    """List-page layout: navy toolbar, muted subtitle, data table."""
    tab = QWidget()
    tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    root = QVBoxLayout(tab)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    header = QFrame()
    header.setStyleSheet(_SCAN_LOG_TAB_HEADER_STYLESHEET)
    header.setFixedHeight(_SCAN_LOG_TAB_HEADER_HEIGHT_PX)
    hl = QHBoxLayout(header)
    hl.setContentsMargins(*_SCAN_LOG_TAB_HEADER_LAYOUT_MARGINS)
    hl.setSpacing(_SCAN_LOG_TAB_HEADER_LAYOUT_SPACING)
    hl.addWidget(QLabel(header_title))
    hl.addStretch()
    for widget in header_widgets_before_filters:
        if isinstance(widget, QPushButton):
            widget.setFixedWidth(80)
            widget.setCursor(Qt.CursorShape.PointingHandCursor)
        hl.addWidget(widget)
    if filters_btn is not None and filters_in_header:
        filters_btn.setCheckable(True)
        filters_btn.setFixedWidth(80)
        filters_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hl.addWidget(filters_btn)
    root.addWidget(header)

    body = QWidget()
    body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    body_layout = QVBoxLayout(body)
    body_layout.setContentsMargins(0, 0, 0, 0)
    body_layout.setSpacing(8)

    hint = QLabel(subtitle)
    hint.setWordWrap(True)
    hint.setStyleSheet(_SCAN_LOG_TAB_SUBTITLE_STYLE)
    body_layout.addWidget(hint)

    table = QTableWidget(0, column_count)
    table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    apply_data_table_appearance(table, read_only=True, stretch_last_section=False)
    attach_table_copy_shortcut(table)
    body_layout.addWidget(table, 1)
    root.addWidget(body, 1)
    return tab, table, hint


def _cell_text(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    return format_data_table_cell(value, key, key_candidates)


def _value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for key in keys:
        if key in row and row.get(key) is not None:
            return (row.get(key), key)
    return (None, keys[0] if keys else "")


def _connection_name(conn: dict[str, Any] | None) -> str:
    if not conn:
        return ""
    return str(conn.get("connectionName") or "").strip()


def _connection_id(conn: dict[str, Any] | None) -> int | str | None:
    """Resolve DB connection id from ``get-all`` rows (API uses ``id``, not ``connectionId``)."""
    if not conn:
        return None
    for key in ("connectionId", "connectionID", "connection_id", "id"):
        value = conn.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _extract_table_name(row: Any) -> str:
    if isinstance(row, dict):
        for key in ("tableName", "TABLE_NAME", "table_name", "name"):
            value = row.get(key)
            if value not in (None, ""):
                return str(value).strip()
    return str(row).strip() if row not in (None, "") else ""


def _extract_table_schema(row: Any) -> str:
    if isinstance(row, dict):
        for key in ("schemaName", "schema", "SCHEMA_NAME", "schema_name"):
            value = row.get(key)
            if value not in (None, ""):
                return str(value).strip()
    return ""


def _value_for_scanned_list_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    """Resolve scanned-table row values for list tab filters and rendering."""
    if not keys:
        return (None, "")
    primary = keys[0]
    if primary in ("TABLE_NAME", "tableName", "table_name", "name"):
        return (_extract_table_name(row), primary)
    if primary in ("schemaName", "schema", "SCHEMA_NAME", "schema_name"):
        return (_extract_table_schema(row), primary)
    if primary in ("LAST_SCAN_DATE", "lastScanDate", "last_scan_date"):
        if isinstance(row, dict):
            for key in keys:
                value = row.get(key)
                if value not in (None, ""):
                    return (value, key)
        return (None, primary)
    return _value_for_column(row, keys)


def _row_dict_from_spec(
    source: dict[str, Any],
    spec: tuple[tuple[str, tuple[str, ...]], ...],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for _header, keys in spec:
        value, key_used = _value_for_column(source, keys)
        out[keys[0]] = _cell_text(value, key_used, keys)
    return out


def _summary_table_rows(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [_row_dict_from_spec(entry, _SUMMARY_COLUMN_SPEC) for entry in entries]


def _log_row_value(row: dict[str, str], keys: tuple[str, ...]) -> tuple[Any, str]:
    key = keys[0]
    return (row.get(key, ""), key)


def _log_format_cell(value: Any, key_used: str, keys: tuple[str, ...]) -> str:
    return _cell_text(value, key_used, keys)


def _flatten_scan_details(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for entry in entries:
        scan_id = _cell_text(entry.get("id"), "id", ("id",))
        details = entry.get("details")
        if not isinstance(details, list):
            continue
        for item in details:
            if not isinstance(item, dict):
                continue
            row = {
                "scan_id": scan_id,
                "table": _cell_text(item.get("tableName"), "tableName", ("tableName", "table")),
                "step": _cell_text(item.get("stepType"), "stepType", ("stepType", "step")),
                "status": _cell_text(item.get("status"), "status", ("status",)),
                "start": _cell_text(item.get("startTime"), "startTime", ("startTime", "start")),
                "end": _cell_text(item.get("endTime"), "endTime", ("endTime", "end")),
                "duration": _cell_text(item.get("durationMs"), "durationMs", ("durationMs", "duration")),
                "columns": _cell_text(
                    item.get("rowsProcessed"), "rowsProcessed", ("rowsProcessed", "columns", "rows")
                ),
                "error": _cell_text(
                    item.get("errorMessage"), "errorMessage", ("errorMessage", "error")
                ),
            }
            rows.append(row)
    rows.sort(key=lambda r: (r.get("start", ""), r.get("scan_id", "")), reverse=True)
    return rows


class ScanConnectionPageWidget(QWidget):
    """Scan UI: connections table · tabbed scan logs / history."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._summary_source_rows: list[dict[str, str]] = []
        self._summary_raw_entries: list[dict[str, Any]] = []
        self._details_source_rows: list[dict[str, str]] = []
        self._summary_filter_visible = False
        self._details_filter_visible = False
        self._detail_scan_id_filter: str | None = None
        self._summary_filter_timer = QTimer(self)
        self._summary_filter_timer.setSingleShot(True)
        self._summary_filter_timer.setInterval(200)
        self._details_filter_timer = QTimer(self)
        self._details_filter_timer.setSingleShot(True)
        self._details_filter_timer.setInterval(200)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        title = QLabel("ETL: Scan")
        title.setStyleSheet(
            f"font-size: {LIST_PAGE_HEADER_TITLE_FONT_PX}px; font-weight: 600; color: #ffffff;"
        )
        hl.addWidget(title)
        hl.addStretch()
        self.connections_filters_btn = QPushButton("Filters")
        self.connections_filters_btn.setCheckable(True)
        self.connections_filters_btn.setFixedWidth(80)
        self.connections_filters_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFixedWidth(100)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hl.addWidget(self.connections_filters_btn)
        hl.addWidget(self.refresh_btn)
        root.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )

        content = QWidget()
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        content.setMinimumHeight(320)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setVisible(False)
        content_layout.addWidget(self.message_label)

        self.connections_table = QTableWidget()
        apply_data_table_appearance(self.connections_table)
        self.connections_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.connections_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.connections_table.setSortingEnabled(True)
        attach_table_copy_shortcut(self.connections_table)

        right_wrap = QWidget()
        right_wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        right_layout = QVBoxLayout(right_wrap)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self.detail_stack = QStackedWidget()
        self.detail_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        empty_page = QWidget()
        empty_layout = QVBoxLayout(empty_page)
        empty_layout.setContentsMargins(24, 48, 24, 48)
        self.empty_hint = QLabel("Select a connection from the list to view scan logs.")
        self.empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; font-size: {FORM_PAGE_FONT_SIZE_PX + 1}px;"
        )
        empty_layout.addStretch()
        empty_layout.addWidget(self.empty_hint)
        empty_layout.addStretch()
        self.detail_stack.addWidget(empty_page)

        details_page = QWidget()
        details_page.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        details_outer = QVBoxLayout(details_page)
        details_outer.setContentsMargins(0, 0, 0, 0)
        details_outer.setSpacing(0)

        card = QWidget()
        card.setObjectName("scanDetailCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card.setStyleSheet(
            "#scanDetailCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 12px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 12)
        card_layout.setSpacing(10)

        self.scan_progress_label = QLabel("")
        self.scan_progress_label.setWordWrap(True)
        self.scan_progress_label.setStyleSheet(
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: {Theme.TEXT_SECONDARY};"
        )
        self.scan_progress_label.setVisible(False)
        card_layout.addWidget(self.scan_progress_label)

        self.scan_progress_bar = QProgressBar()
        self.scan_progress_bar.setRange(0, 0)
        self.scan_progress_bar.setFixedHeight(8)
        self.scan_progress_bar.setVisible(False)
        card_layout.addWidget(self.scan_progress_bar)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(_TAB_STYLESHEET)
        self.tabs.setDocumentMode(True)
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.scan_filter_run_btn = QPushButton("Scan by Filter")
        self.scanned_list_scan_all_btn = QPushButton("Scan All")
        self.scanned_list_filters_btn = QPushButton("Filters")
        self.load_database_tables_btn = QPushButton("Load tables")
        _size_scan_header_button_to_text(self.scan_filter_run_btn)
        _prepare_scan_header_button(self.scanned_list_scan_all_btn, width_px=100)
        self.scanned_list_filters_btn.setCheckable(True)
        self.scanned_list_filters_btn.setFixedWidth(80)
        self.scanned_list_filters_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _prepare_scan_header_button(self.load_database_tables_btn, width_px=100)

        self.scanned_tables_list_table = _build_scan_tables_widget(
            ["Table Name", "Schema", "Last Scan"],
            read_only=True,
        )
        scanned_list_content = QWidget()
        scanned_list_content_layout = QVBoxLayout(scanned_list_content)
        scanned_list_content_layout.setContentsMargins(0, 0, 0, 0)
        scanned_list_content_layout.setSpacing(0)
        scanned_list_content_layout.addWidget(self.scanned_tables_list_table, 1)
        scanned_tables_tab = _build_scan_operation_tab(
            header_title="Scanned tables",
            subtitle=_SCAN_TAB_SUBTITLE_SCANNED_LIST,
            header_buttons=(
                self.scanned_list_filters_btn,
                self.scanned_list_scan_all_btn,
            ),
            content=scanned_list_content,
        )

        self.scan_filter_schema_input = QLineEdit()
        self.scan_filter_schema_input.setStyleSheet(FORM_INPUT_STYLE)
        self.scan_filter_schema_input.setPlaceholderText("e.g. public")
        self.scan_filter_name_contains_input = QLineEdit()
        self.scan_filter_name_contains_input.setStyleSheet(FORM_INPUT_STYLE)
        self.scan_filter_name_contains_input.setPlaceholderText("e.g. masjid")
        self.scan_filter_select_all_cb = QCheckBox("Select all")
        self.scan_filter_select_all_cb.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px;")

        self.scan_filter_source_tables_table = _build_scan_tables_widget(
            ["", "Table Name"],
            read_only=False,
            checkbox_column=True,
        )
        filter_database_panel = _build_scan_filter_database_panel(
            schema_input=self.scan_filter_schema_input,
            name_contains_input=self.scan_filter_name_contains_input,
            select_all_cb=self.scan_filter_select_all_cb,
            table=self.scan_filter_source_tables_table,
            load_btn=self.load_database_tables_btn,
        )

        scan_filter_content = QWidget()
        scan_filter_content_layout = QVBoxLayout(scan_filter_content)
        scan_filter_content_layout.setContentsMargins(0, 0, 0, 0)
        scan_filter_content_layout.setSpacing(0)
        scan_filter_content_layout.addWidget(filter_database_panel, 1)
        scan_filter_tab = _build_scan_operation_tab(
            header_title="Scan by filter",
            subtitle=_SCAN_TAB_SUBTITLE_FILTER,
            header_buttons=(self.scan_filter_run_btn,),
            content=scan_filter_content,
        )

        scan_tab = QWidget()
        scan_tab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        scan_tab_layout = QVBoxLayout(scan_tab)
        scan_tab_layout.setContentsMargins(0, 0, 0, 0)
        scan_tab_layout.setSpacing(0)
        self.scan_inner_tabs = QTabWidget()
        self.scan_inner_tabs.setDocumentMode(True)
        self.scan_inner_tabs.setStyleSheet(_TAB_STYLESHEET)
        self.scan_inner_tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scan_inner_tabs.addTab(scanned_tables_tab, "Scanned tables")
        self.scan_inner_tabs.addTab(scan_filter_tab, "Scan by filter")
        scan_tab_layout.addWidget(self.scan_inner_tabs, 1)
        self.tabs.addTab(scan_tab, "Scan")

        self.summary_filters_btn = QPushButton("Filters")
        summary_tab, self.summary_table, _ = _build_scan_log_tab(
            header_title="Scan History",
            subtitle=_SCAN_HISTORY_SUBTITLE,
            column_count=len(_SUMMARY_COLUMN_SPEC),
            filters_btn=self.summary_filters_btn,
        )
        self.tabs.addTab(summary_tab, "Scan History")

        self.detail_show_all_btn = QPushButton("Show all")
        self.detail_show_all_btn.setVisible(False)
        self.details_filters_btn = QPushButton("Filters")
        details_tab, self.details_table, self.detail_log_hint = _build_scan_log_tab(
            header_title="Scan Detail Log",
            subtitle=_SCAN_DETAIL_LOG_SUBTITLE_ALL,
            column_count=len(_DETAILS_COLUMN_SPEC),
            filters_btn=self.details_filters_btn,
            header_widgets_before_filters=(self.detail_show_all_btn,),
        )
        self.tabs.addTab(details_tab, "Scan Detail Log")

        card_layout.addWidget(self.tabs, 1)
        details_outer.addWidget(card, 1)
        self.detail_stack.addWidget(details_page)

        right_layout.addWidget(self.detail_stack, 1)
        self.set_scan_controls_enabled(False)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(6)
        split.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        split.setMinimumHeight(320)
        split.addWidget(self.connections_table)
        split.addWidget(right_wrap)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 3)
        split.setSizes([250, 750])
        content_layout.addWidget(split, 1)

        self.connections_table.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self._summary_filter_timer.timeout.connect(self._apply_summary_column_filters)
        self._details_filter_timer.timeout.connect(self._apply_details_column_filters)
        self.summary_filters_btn.toggled.connect(self._on_summary_filters_toggled)
        self.details_filters_btn.toggled.connect(self._on_details_filters_toggled)
        self.summary_table.itemDoubleClicked.connect(self._on_summary_row_double_clicked)
        self.detail_show_all_btn.clicked.connect(self._clear_detail_scan_filter)

    def _summary_spec_list(self) -> list[tuple[str, tuple[str, ...]]]:
        return list(_SUMMARY_COLUMN_SPEC)

    def _details_spec_list(self) -> list[tuple[str, tuple[str, ...]]]:
        return list(_DETAILS_COLUMN_SPEC)

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
            self.summary_table,
            self._summary_spec_list(),
            self._summary_filter_visible,
            _log_row_value,
            _log_format_cell,
        )

    def _details_rows_for_display(self) -> list[dict[str, str]]:
        rows = list(self._details_source_rows)
        if self._detail_scan_id_filter:
            sid = str(self._detail_scan_id_filter)
            rows = [r for r in rows if str(r.get("scan_id", "")) == sid]
        return filter_dict_rows_by_column_edits(
            rows,
            self.details_table,
            self._details_spec_list(),
            self._details_filter_visible,
            _log_row_value,
            _log_format_cell,
        )

    def _raw_entry_for_summary_row(self, row: dict[str, str]) -> dict[str, Any] | None:
        rid = str(row.get("id", "")).strip()
        if not rid:
            return None
        for raw in self._summary_raw_entries:
            if _cell_text(raw.get("id")) == rid:
                return raw
        return None

    def _write_summary_table(self, rows: list[dict[str, str]]) -> None:
        spec = self._summary_spec_list()
        headers = [h for h, _ in spec]
        self.summary_table.setColumnCount(len(headers))
        self.summary_table.setHorizontalHeaderLabels(headers)
        off = self._summary_data_row_offset()
        total = off + len(rows)
        if self._summary_filter_visible and total < 1:
            total = 1
        self.summary_table.setSortingEnabled(False)
        self.summary_table.setRowCount(total)
        if self._summary_filter_visible:
            for c in range(self.summary_table.columnCount()):
                self.summary_table.takeItem(0, c)
            install_filter_row(
                self.summary_table,
                self.summary_table.columnCount(),
                on_text_changed=self._schedule_summary_filter_apply,
            )
        for r, row in enumerate(rows):
            tr = off + r
            raw = self._raw_entry_for_summary_row(row)
            for col, (_header, keys) in enumerate(spec):
                text = row.get(keys[0], "")
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0 and isinstance(raw, dict):
                    item.setData(Qt.ItemDataRole.UserRole, raw)
                self.summary_table.setItem(tr, col, item)
        sync_vertical_header_labels(
            self.summary_table,
            filter_visible=self._summary_filter_visible,
            data_row_count=len(rows),
        )
        if self._summary_source_rows:
            resize_data_table_columns_to_content(
                self.summary_table,
                spec,
                self._summary_source_rows,
                _log_row_value,
                _log_format_cell,
            )
        self.summary_table.setSortingEnabled(not self._summary_filter_visible)

    def _write_details_table(self, rows: list[dict[str, str]]) -> None:
        spec = self._details_spec_list()
        headers = [h for h, _ in spec]
        self.details_table.setColumnCount(len(headers))
        self.details_table.setHorizontalHeaderLabels(headers)
        off = self._details_data_row_offset()
        total = off + len(rows)
        if self._details_filter_visible and total < 1:
            total = 1
        self.details_table.setSortingEnabled(False)
        self.details_table.setRowCount(total)
        if self._details_filter_visible:
            for c in range(self.details_table.columnCount()):
                self.details_table.takeItem(0, c)
            install_filter_row(
                self.details_table,
                self.details_table.columnCount(),
                on_text_changed=self._schedule_details_filter_apply,
            )
        for r, row in enumerate(rows):
            tr = off + r
            for col, (_header, keys) in enumerate(spec):
                text = row.get(keys[0], "")
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.details_table.setItem(tr, col, item)
        sync_vertical_header_labels(
            self.details_table,
            filter_visible=self._details_filter_visible,
            data_row_count=len(rows),
        )
        base_rows = self._details_source_rows
        if self._detail_scan_id_filter:
            sid = str(self._detail_scan_id_filter)
            base_rows = [r for r in base_rows if str(r.get("scan_id", "")) == sid]
        if base_rows:
            resize_data_table_columns_to_content(
                self.details_table,
                spec,
                base_rows,
                _log_row_value,
                _log_format_cell,
            )
        self.details_table.setSortingEnabled(not self._details_filter_visible)

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
            clear_filter_row_widgets(self.summary_table)
        rows = self._filtered_summary_rows() if checked else list(self._summary_source_rows)
        self._write_summary_table(rows)

    def _on_details_filters_toggled(self, checked: bool) -> None:
        self._details_filter_visible = checked
        if not checked:
            self._details_filter_timer.stop()
            clear_filter_row_widgets(self.details_table)
        self._write_details_table(self._details_rows_for_display())

    def _on_summary_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if item.row() < self._summary_data_row_offset():
            return
        cell = self.summary_table.item(item.row(), 0)
        if cell is None:
            return
        entry = cell.data(Qt.ItemDataRole.UserRole)
        if not isinstance(entry, dict):
            return
        scan_id = _cell_text(entry.get("id"))
        if not scan_id:
            return
        self._detail_scan_id_filter = scan_id
        self._update_detail_filter_hint()
        self._write_details_table(self._details_rows_for_display())
        self.tabs.setCurrentIndex(_TAB_SCAN_DETAIL_LOG)

    def _clear_detail_scan_filter(self) -> None:
        self._detail_scan_id_filter = None
        self._update_detail_filter_hint()
        self._write_details_table(self._details_rows_for_display())

    def _update_detail_filter_hint(self) -> None:
        if self._detail_scan_id_filter:
            self.detail_log_hint.setText(
                f"Showing table-level details for scan run Id {self._detail_scan_id_filter}. "
                "Use Show all to return to the full log."
            )
            self.detail_show_all_btn.setVisible(True)
        else:
            self.detail_log_hint.setText(_SCAN_DETAIL_LOG_SUBTITLE_ALL)
            self.detail_show_all_btn.setVisible(False)

    def set_scan_log_data(
        self,
        entries: list[dict[str, Any]],
        *,
        clear_detail_filter: bool = True,
    ) -> None:
        if clear_detail_filter:
            self._detail_scan_id_filter = None
            self._update_detail_filter_hint()
        matched = sorted(
            entries,
            key=lambda e: str(e.get("startTime") or e.get("createdAt") or e.get("createdOn") or ""),
            reverse=True,
        )
        self._summary_raw_entries = matched
        self._summary_source_rows = _summary_table_rows(matched)
        self._details_source_rows = _flatten_scan_details(matched)
        summary_display = (
            self._filtered_summary_rows()
            if self._summary_filter_visible
            else list(self._summary_source_rows)
        )
        self._write_summary_table(summary_display)
        self._write_details_table(self._details_rows_for_display())

    def show_empty_detail(self) -> None:
        self.detail_stack.setCurrentIndex(0)
        self.set_scan_controls_enabled(False)

    def show_detail_panel(self, _connection_label: str) -> None:
        self.detail_stack.setCurrentIndex(1)
        self.set_scan_controls_enabled(True)

    def set_scan_controls_enabled(self, enabled: bool) -> None:
        self.scan_filter_run_btn.setEnabled(enabled)
        self.scanned_list_scan_all_btn.setEnabled(enabled)
        self.scanned_list_filters_btn.setEnabled(enabled)
        self.scan_inner_tabs.setEnabled(enabled)
        self.scan_filter_schema_input.setEnabled(enabled)
        self.scan_filter_name_contains_input.setEnabled(enabled)
        self.scan_filter_select_all_cb.setEnabled(enabled)
        self.load_database_tables_btn.setEnabled(enabled)
        self.scanned_tables_list_table.setEnabled(enabled)
        self.scan_filter_source_tables_table.setEnabled(enabled)

    def is_scan_by_filter_mode(self) -> bool:
        return self.scan_inner_tabs.currentIndex() == _INNER_TAB_SCAN_BY_FILTER

    def set_right_panel_enabled(self, enabled: bool, connection_label: str = "") -> None:
        if enabled and connection_label:
            self.show_detail_panel(connection_label)
        else:
            self.show_empty_detail()
            self._summary_source_rows = []
            self._summary_raw_entries = []
            self._details_source_rows = []
            self._detail_scan_id_filter = None
            self._update_detail_filter_hint()
            self.summary_table.setRowCount(0)
            self.details_table.setRowCount(0)
            self.scan_progress_label.clear()
            self.scan_progress_label.setVisible(False)
            self.scan_progress_bar.setVisible(False)


class EtlScanConnectionPage(QWidget):
    """Scan page: pick a connection, view SCAN log summary and per-table details."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._ui = ScanConnectionPageWidget()
        layout.addWidget(self._ui)

        self._connections: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._restore_connection_name: str | None = None
        self._connection_scan_logs: list[dict[str, Any]] = []
        self._source_tables_cache: list[Any] = []
        self._scanned_tables_cache: list[Any] = []
        self._selected_filter_tables: set[str] = set()
        self._rendering_filter_tables = False
        self._scan_in_progress = False
        self._connections_filter_visible = False
        self._scanned_list_filter_visible = False
        self._connections_filter_timer = QTimer(self)
        self._connections_filter_timer.setSingleShot(True)
        self._connections_filter_timer.setInterval(200)
        self._scanned_list_filter_timer = QTimer(self)
        self._scanned_list_filter_timer.setSingleShot(True)
        self._scanned_list_filter_timer.setInterval(200)

        self._ui.refresh_btn.clicked.connect(self.refresh)
        self._ui.connections_filters_btn.toggled.connect(self._on_connections_filters_toggled)
        self._connections_filter_timer.timeout.connect(self._refresh_connections_table_view)
        self._ui.scanned_list_filters_btn.toggled.connect(self._on_scanned_list_filters_toggled)
        self._scanned_list_filter_timer.timeout.connect(self._refresh_scanned_list_table_view)
        self._ui.scanned_list_scan_all_btn.clicked.connect(self._run_scan_all)
        self._ui.scan_filter_run_btn.clicked.connect(self._run_scan_by_filter)
        self._ui.load_database_tables_btn.clicked.connect(self._load_source_database_tables)
        self._ui.scan_filter_schema_input.textChanged.connect(self._apply_filter_table_view)
        self._ui.scan_filter_name_contains_input.textChanged.connect(self._apply_filter_table_view)
        self._ui.scan_filter_select_all_cb.stateChanged.connect(self._on_filter_select_all_changed)
        self._ui.scan_filter_source_tables_table.itemChanged.connect(self._on_filter_table_item_changed)
        self._ui.connections_table.itemSelectionChanged.connect(self._on_selection_changed)
        self._ui.set_right_panel_enabled(False)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh()

    def _token(self) -> str | None:
        profile = get_user_profile() or {}
        return profile.get("token") or profile.get("accessToken")

    def _show_page_message(self, text: str, *, error: bool) -> None:
        show_auto_hiding_message(self, self._ui.message_label, text, error=error)

    def refresh(self) -> None:
        if self._current:
            self._restore_connection_name = _connection_name(self._current)
        result = api_get_all_connections(self._token())
        if not result.get("success"):
            self._connections = []
            self._populate_connections_table()
            self._show_page_message(str(result.get("message") or "Failed to load connections."), error=True)
            return
        self._connections = list(result.get("data") or [])
        self._populate_connections_table()
        show_auto_hiding_message(self, self._ui.message_label, "", error=False)

    def _schedule_connections_filter_apply(self) -> None:
        if self._connections_filter_visible:
            self._connections_filter_timer.start()

    def _on_connections_filters_toggled(self, checked: bool) -> None:
        self._connections_filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self._ui.connections_table)
        self._refresh_connections_table_view()

    def _connections_filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._connections)
        if not self._connections_filter_visible:
            return rows
        return filter_dict_rows_by_column_edits(
            rows,
            self._ui.connections_table,
            list(_CONNECTION_COLUMNS),
            True,
            _value_for_column,
            format_data_table_cell,
        )

    def _refresh_connections_table_view(self) -> None:
        saved = (
            saved_filter_texts(self._ui.connections_table)
            if self._connections_filter_visible
            else None
        )
        render_dict_rows_table(
            self._ui.connections_table,
            self._connections_filtered_rows(),
            list(_CONNECTION_COLUMNS),
            filter_visible=self._connections_filter_visible,
            value_for_column=_value_for_column,
            format_cell=format_data_table_cell,
            on_filter_text_changed=self._schedule_connections_filter_apply,
            saved_filter_texts_list=saved,
        )

    def _schedule_scanned_list_filter_apply(self) -> None:
        if self._scanned_list_filter_visible:
            self._scanned_list_filter_timer.start()

    def _on_scanned_list_filters_toggled(self, checked: bool) -> None:
        self._scanned_list_filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self._ui.scanned_tables_list_table)
        self._refresh_scanned_list_table_view()

    def _scanned_list_cache_rows(self) -> list[dict[str, Any]]:
        return [r for r in self._scanned_tables_cache if isinstance(r, dict)]

    def _scanned_list_filtered_rows(self) -> list[dict[str, Any]]:
        rows = self._scanned_list_cache_rows()
        if not self._scanned_list_filter_visible:
            return rows
        return filter_dict_rows_by_column_edits(
            rows,
            self._ui.scanned_tables_list_table,
            list(_SCANNED_LIST_COLUMN_SPEC),
            True,
            _value_for_scanned_list_column,
            format_data_table_cell,
        )

    def _refresh_scanned_list_table_view(self) -> None:
        saved = (
            saved_filter_texts(self._ui.scanned_tables_list_table)
            if self._scanned_list_filter_visible
            else None
        )
        render_dict_rows_table(
            self._ui.scanned_tables_list_table,
            self._scanned_list_filtered_rows(),
            list(_SCANNED_LIST_COLUMN_SPEC),
            filter_visible=self._scanned_list_filter_visible,
            value_for_column=_value_for_scanned_list_column,
            format_cell=format_data_table_cell,
            on_filter_text_changed=self._schedule_scanned_list_filter_apply,
            saved_filter_texts_list=saved,
        )

    def _populate_connections_table(self) -> None:
        self._refresh_connections_table_view()
        table = self._ui.connections_table

        sm = table.selectionModel()
        table.blockSignals(True)
        if sm is not None:
            sm.blockSignals(True)
        try:
            restored = False
            if self._restore_connection_name:
                restored = self._select_connection_by_name(self._restore_connection_name)
                self._restore_connection_name = None

            if not restored:
                table.clearSelection()
                self._current = None
                self._ui.set_right_panel_enabled(False)
            else:
                self._rebind_current_connection()
        finally:
            table.blockSignals(False)
            if sm is not None:
                sm.blockSignals(False)

        if self._current:
            self._apply_connection_selection()

    def _apply_connection_selection(self) -> None:
        """Load filter tables + scan logs once for the selected connection."""
        conn = self._current
        if not conn:
            return
        name = _connection_name(conn)
        self._ui.set_right_panel_enabled(True, name)
        self._load_filter_tables()
        self._refresh_scan_data()

    def _rebind_current_connection(self) -> None:
        """After ``get-all`` reload, replace stale ``_current`` dict with the selected row payload."""
        conn = self._selected_connection()
        self._current = conn

    def _select_connection_by_name(self, name: str) -> bool:
        target = (name or "").strip().lower()
        if not target:
            return False
        table = self._ui.connections_table
        offset = data_row_offset(self._connections_filter_visible)
        for row in range(offset, table.rowCount()):
            item = table.item(row, 0)
            if item is None:
                continue
            conn = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(conn, dict):
                continue
            if str(conn.get("connectionName") or "").strip().lower() == target:
                table.selectRow(row)
                return True
        return False

    def _selected_connection(self) -> dict[str, Any] | None:
        sm = self._ui.connections_table.selectionModel()
        if sm is None:
            return None
        rows = sm.selectedRows()
        if not rows:
            return None
        item = self._ui.connections_table.item(int(rows[0].row()), 0)
        if item is None:
            return None
        conn = item.data(Qt.ItemDataRole.UserRole)
        return conn if isinstance(conn, dict) else None

    def _on_selection_changed(self) -> None:
        self._rebind_current_connection()
        if self._current is None:
            self._ui.set_right_panel_enabled(False)
            self._connection_scan_logs = []
            self._render_scan_logs()
            return
        self._apply_connection_selection()

    def _begin_scan_ui(self, message: str) -> None:
        self._scan_in_progress = True
        self._ui.scan_progress_label.setText(message)
        self._ui.scan_progress_label.setStyleSheet(
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: {Theme.TEXT_SECONDARY};"
        )
        self._ui.scan_progress_label.setVisible(True)
        self._ui.scan_progress_bar.setVisible(True)
        self._ui.set_scan_controls_enabled(False)
        self._ui.set_scan_log_data([], clear_detail_filter=False)

    def _end_scan_ui(
        self,
        completion_msg: str | None = None,
        *,
        completion_error: bool = False,
        after_filter_scan: bool = False,
    ) -> None:
        self._scan_in_progress = False
        self._ui.scan_progress_bar.setVisible(False)
        if self._current:
            self._ui.set_scan_controls_enabled(True)
            if not completion_error:
                if after_filter_scan:
                    self._refresh_scan_section()
                else:
                    self._load_filter_tables()
        self._refresh_scan_data(preserve_page_message=bool(completion_msg))
        if completion_msg:
            self._show_page_message(completion_msg, error=completion_error)
            if not completion_error:
                if after_filter_scan:
                    self._ui.tabs.setCurrentIndex(0)
                    self._ui.scan_inner_tabs.setCurrentIndex(_INNER_TAB_SCAN_BY_FILTER)
                else:
                    self._ui.tabs.setCurrentIndex(_TAB_SCAN_HISTORY)

    def _run_scan_all(self) -> None:
        name = _connection_name(self._current)
        if not name:
            self._show_page_message("Select a connection first.", error=True)
            return
        reply = QMessageBox.question(
            self,
            "Scan all",
            "You are going to scan the entire database. This could take some time to complete. "
            "Do you want to proceed?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._begin_scan_ui(f"Scanning all tables for {name}…")
        completion_msg: str | None = None
        completion_error = False
        try:
            result = api_metadata_scan_all(name, token=self._token())
            completion_error = not bool(result.get("success"))
            completion_msg = str(
                result.get("message")
                or ("Scan failed." if completion_error else "Scan completed.")
            )
        finally:
            self._end_scan_ui(completion_msg, completion_error=completion_error)

    def _run_scan_by_filter(self) -> None:
        name = _connection_name(self._current)
        conn_id = _connection_id(self._current)
        if not name or conn_id is None:
            self._show_page_message("Select a connection first.", error=True)
            return
        table_names = sorted(self._selected_filter_tables)
        if not table_names:
            QMessageBox.warning(self, "Scan by filter", "Select at least one table to scan.")
            return
        self._begin_scan_ui(f"Scanning {len(table_names)} table(s) for {name}…")
        completion_msg: str | None = None
        completion_error = False
        try:
            result = api_metadata_scan_by_filter(
                conn_id,
                table_names,
                token=self._token(),
            )
            completion_error = not bool(result.get("success"))
            completion_msg = str(
                result.get("message")
                or ("Scan by filter failed." if completion_error else "Scan completed.")
            )
        finally:
            self._end_scan_ui(
                completion_msg,
                completion_error=completion_error,
                after_filter_scan=True,
            )

    def _load_scanned_tables(self) -> None:
        """GET get-scanned-table-by-id — Scanned tables tab and Scan by filter right panel."""
        conn_id = _connection_id(self._current)
        if conn_id is None:
            self._scanned_tables_cache = []
            return
        scanned_result = api_get_metadata_tables(conn_id, token=self._token())
        if scanned_result.get("success"):
            self._scanned_tables_cache = list(scanned_result.get("tables") or [])
        else:
            self._scanned_tables_cache = []
            self._show_page_message(
                str(scanned_result.get("message") or "Failed to load scanned tables."),
                error=True,
            )

    def _refresh_scan_section(self) -> None:
        """After successful scan-by-filter: reload scanned tables and logs; keep left database list."""
        self._load_scanned_tables()
        self._apply_filter_table_view()

    def _load_filter_tables(self) -> None:
        """On connection select / refresh: clear database list and load scanned tables."""
        self._source_tables_cache = []
        self._selected_filter_tables = set()
        self._load_scanned_tables()
        self._apply_filter_table_view()

    def _load_source_database_tables(self) -> None:
        """POST scan-connection/table/{id} — user-triggered from Scan by filter left panel."""
        conn_id = _connection_id(self._current)
        if conn_id is None:
            self._show_page_message("Select a connection first.", error=True)
            return
        self._ui.load_database_tables_btn.setEnabled(False)
        try:
            result = api_post_scan_connection_source_tables(conn_id, token=self._token())
            if result.get("success"):
                self._source_tables_cache = list(result.get("tables") or [])
                self._selected_filter_tables = set()
                self._apply_filter_table_view()
                msg = str(result.get("message") or "").strip()
                if msg:
                    self._show_page_message(msg, error=False)
            else:
                self._source_tables_cache = []
                self._selected_filter_tables = set()
                self._render_source_tables([])
                self._show_page_message(
                    str(result.get("message") or "Failed to load database tables."),
                    error=True,
                )
        finally:
            if self._current and not self._scan_in_progress:
                self._ui.load_database_tables_btn.setEnabled(True)

    def _filtered_rows(self, cache: list[Any], *, include_schema_filter: bool) -> list[Any]:
        schema_q = self._ui.scan_filter_schema_input.text().strip().lower()
        name_q = self._ui.scan_filter_name_contains_input.text().strip().lower()
        rows: list[Any] = []
        for row in cache:
            table_name = _extract_table_name(row)
            if not table_name:
                continue
            if include_schema_filter:
                row_data = row if isinstance(row, dict) else {}
                schema = _extract_table_schema(row_data).lower()
                if schema_q and schema_q not in schema:
                    continue
            if name_q and name_q not in table_name.lower():
                continue
            rows.append(row)
        return rows

    def _apply_filter_table_view(self) -> None:
        self._render_source_tables(
            self._filtered_rows(self._source_tables_cache, include_schema_filter=True)
        )
        self._refresh_scanned_list_table_view()

    def _render_source_tables(self, rows: list[Any]) -> None:
        self._rendering_filter_tables = True
        table = self._ui.scan_filter_source_tables_table
        if table.cellWidget(0, 0) is not None:
            table.removeCellWidget(0, 0)
        table.setRowCount(0)
        for row in rows:
            table_name = _extract_table_name(row)
            if not table_name:
                continue
            r_index = table.rowCount()
            table.insertRow(r_index)
            check_item = QTableWidgetItem()
            check_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            check_item.setCheckState(
                Qt.CheckState.Checked
                if table_name in self._selected_filter_tables
                else Qt.CheckState.Unchecked
            )
            table.setItem(r_index, 0, check_item)
            name_item = QTableWidgetItem(table_name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            name_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            table.setItem(r_index, 1, name_item)
        self._rendering_filter_tables = False
        self._sync_filter_select_all()

    def _sync_filter_select_all(self) -> None:
        table = self._ui.scan_filter_source_tables_table
        total = table.rowCount()
        if total == 0:
            self._ui.scan_filter_select_all_cb.blockSignals(True)
            self._ui.scan_filter_select_all_cb.setCheckState(Qt.CheckState.Unchecked)
            self._ui.scan_filter_select_all_cb.blockSignals(False)
            return
        checked = 0
        for row in range(total):
            item = table.item(row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                checked += 1
        self._ui.scan_filter_select_all_cb.blockSignals(True)
        if checked == 0:
            self._ui.scan_filter_select_all_cb.setCheckState(Qt.CheckState.Unchecked)
        elif checked == total:
            self._ui.scan_filter_select_all_cb.setCheckState(Qt.CheckState.Checked)
        else:
            self._ui.scan_filter_select_all_cb.setCheckState(Qt.CheckState.PartiallyChecked)
        self._ui.scan_filter_select_all_cb.blockSignals(False)

    def _on_filter_select_all_changed(self, state: int) -> None:
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        table = self._ui.scan_filter_source_tables_table
        self._rendering_filter_tables = True
        for row in range(table.rowCount()):
            check_item = table.item(row, 0)
            name_item = table.item(row, 1)
            if not check_item or not name_item:
                continue
            table_name = name_item.text()
            check_item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            if checked:
                self._selected_filter_tables.add(table_name)
            else:
                self._selected_filter_tables.discard(table_name)
        self._rendering_filter_tables = False

    def _on_filter_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._rendering_filter_tables or item.column() != 0:
            return
        name_item = self._ui.scan_filter_source_tables_table.item(item.row(), 1)
        if not name_item:
            return
        table_name = name_item.text()
        if item.checkState() == Qt.CheckState.Checked:
            self._selected_filter_tables.add(table_name)
        else:
            self._selected_filter_tables.discard(table_name)
        self._sync_filter_select_all()

    def _refresh_scan_data(self, *, preserve_page_message: bool = False) -> None:
        if not self._current:
            self._connection_scan_logs = []
            self._render_scan_logs()
            return
        conn_id = _connection_id(self._current)
        if conn_id is None:
            self._connection_scan_logs = []
            if not self._scan_in_progress:
                self._show_page_message("Cannot load scan logs: connection ID is missing.", error=True)
            self._render_scan_logs()
            return
        result = api_get_etl_logs_by_connection_and_operation_type(
            conn_id,
            "SCAN",
            token=self._token(),
        )
        if not result.get("success"):
            if not self._scan_in_progress:
                self._show_page_message(
                    str(result.get("message") or "Failed to load scan logs."),
                    error=True,
                )
            self._connection_scan_logs = []
        else:
            rows = result.get("data") or []
            self._connection_scan_logs = [r for r in rows if isinstance(r, dict)]
            if not preserve_page_message:
                show_auto_hiding_message(self, self._ui.message_label, "", error=False)
        self._render_scan_logs()

    def _render_scan_logs(self) -> None:
        if self._scan_in_progress:
            self._ui.set_scan_log_data([], clear_detail_filter=False)
            return
        logs = self._connection_scan_logs
        self._ui.set_scan_log_data(logs)
        matched = sorted(
            logs,
            key=lambda e: str(e.get("startTime") or e.get("createdAt") or e.get("createdOn") or ""),
            reverse=True,
        )
        if matched:
            latest = matched[0]
            status = _cell_text(latest.get("status")) or "--"
            started = _cell_text(
                latest.get("startTime") or latest.get("createdAt") or latest.get("createdOn")
            ) or "--"
            self._ui.scan_progress_label.setText(f"Last scan: {status} · started {started}")
            self._ui.scan_progress_label.setStyleSheet(
                f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: {Theme.TEXT_SECONDARY};"
            )
            self._ui.scan_progress_label.setVisible(True)
        elif self._current and not self._scan_in_progress:
            self._ui.scan_progress_label.setText("No scan history for this connection.")
            self._ui.scan_progress_label.setStyleSheet(
                f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: {Theme.TEXT_SECONDARY};"
            )
            self._ui.scan_progress_label.setVisible(True)
        elif not (self._ui.scan_progress_label.text() or "").strip():
            self._ui.scan_progress_label.setVisible(False)
