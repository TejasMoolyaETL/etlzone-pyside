"""ETL: Scan — connection list with SCAN log summary and detail tabs."""

from __future__ import annotations

import json
import re
from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QFontMetrics, QShowEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
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

from app.etl.widgets.import_field_mismatch_dialog import ImportFieldMismatchDialog
from core.api import (
    api_check_scan_connection_fields,
    api_get_etl_log_by_id,
    api_get_etl_logs_by_connection_and_operation_type,
    api_get_metadata_table_columns,
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
    FORM_PLAIN_TEXT_STYLE,
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
from app.etl.widgets.etl_connection_picker import EtlConnectionHeaderPicker
from core.etl_connection_context import get_etl_connection_context
from ui.form_combobox_style import apply_form_combobox_field
from ui.spreadsheet_export import write_xlsx

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

_COLUMN_DETAIL_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("TABLE_NAME", ("TABLE_NAME", "tableName")),
    ("COLUMN_NAME", ("COLUMN_NAME",)),
    ("DATA_TYPE", ("DATA_TYPE",)),
    ("CHARACTER_MAXIMUM_LENGTH", ("CHARACTER_MAXIMUM_LENGTH",)),
    ("NUMERIC_PRECISION", ("NUMERIC_PRECISION",)),
    ("NUMERIC_SCALE", ("NUMERIC_SCALE",)),
    ("IS_NULLABLE", ("IS_NULLABLE",)),
    ("is_primary_key", ("is_primary_key",)),
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

# Fallback columns when the API returns no rows yet.
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

_DETAILS_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Scan Id", ("scan_id",)),
    ("Id", ("id",)),
    ("Table", ("tableName", "table", "table_name")),
    ("Step", ("stepType", "step", "step_type")),
    ("Status", ("status",)),
    ("Start", ("startTime", "start", "start_time")),
    ("End", ("endTime", "end", "end_time")),
    ("Duration (ms)", ("durationMs", "duration", "duration_ms")),
    ("Rows Read", ("rowsRead", "rows_read")),
    ("Rows Written", ("rowsWritten", "rows_written")),
    ("Rows Skipped", ("rowsSkipped", "rows_skipped")),
    ("No. Of Columns", ("total_column_count", "totalColumnCount", "rowsProcessed", "columns")),
    ("Error Reason", ("errorMessage", "error", "error_message")),
    ("Created By", ("createdBy", "created_by")),
    ("Created On", ("createdAt", "created_at", "createdOn", "created_on")),
)

_ETL_LOG_COUNT_KEYS: frozenset[str] = frozenset(
    {
        "rowsRead",
        "rows_read",
        "rowsWritten",
        "rows_written",
        "rowsSkipped",
        "rows_skipped",
        "rowsProcessed",
        "rows_processed",
        "total_column_count",
        "totalColumnCount",
        "successCount",
        "success_count",
        "failedCount",
        "failed_count",
        "totalTables",
        "total_tables",
        "table_success_count",
        "table_failed_count",
        "total_table_count",
    }
)

_SCAN_LOG_CHILD_DETAIL_KEYS: tuple[str, ...] = (
    "details",
    "detail",
    "steps",
    "children",
    "tableDetails",
    "table_details",
    "logs",
)

_SCAN_LOG_PARENT_ID_KEYS: tuple[str, ...] = ("id", "logId", "log_id")

_SUMMARY_PREFERRED_FIELD_ORDER: tuple[str, ...] = (
    "id",
    "logId",
    "operationType",
    "status",
    "connectionName",
    "errorMessage",
    "createdBy",
    "startTime",
    "endTime",
    "durationMs",
    "rowsRead",
    "rowsWritten",
    "rowsSkipped",
    "table_success_count",
    "table_failed_count",
    "total_table_count",
    "successCount",
    "failedCount",
    "totalTables",
    "createdAt",
    "createdOn",
)

_DETAILS_PREFERRED_FIELD_ORDER: tuple[str, ...] = (
    "scan_id",
    "id",
    "tableName",
    "table",
    "stepType",
    "step",
    "status",
    "startTime",
    "endTime",
    "durationMs",
    "rowsRead",
    "rowsWritten",
    "rowsSkipped",
    "total_column_count",
    "totalColumnCount",
    "rowsProcessed",
    "errorMessage",
    "createdBy",
    "createdAt",
    "createdOn",
)

_SCAN_HISTORY_SUBTITLE = (
    "One row per scan run for this connection. "
    "Double-click a row to load its per-table steps in Scan Detail Log."
)
_SCAN_DETAIL_LOG_SUBTITLE_EMPTY = (
    "Double-click a scan run in Scan History to load step details from the server."
)
_SCAN_TAB_SUBTITLE_SCANNED_LIST = (
    "Tables already scanned for the selected connection. "
    "Click a table row to view its column details below. "
    "Use Scan All to scan the full database, or use the Scan by filter tab for a targeted scan."
)
_SCAN_TAB_SUBTITLE_FILTER = (
    "Choose a schema, paste table names to narrow the list, load database tables, "
    "select rows, then run a targeted scan. View scanned results on the Scanned tables tab."
)

_SCHEMA_FILTER_ALL_LABEL = "-- All schemas --"
_TABLE_NAMES_FILTER_PLACEHOLDER = (
    "Paste table names (one per line, or comma / semicolon separated)"
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


def _display_value(value: Any) -> str:
    return "--" if value is None or value == "" else str(value)


def _build_scanned_sub_table_panel(
    header_title: str,
    table: QTableWidget,
    *,
    filters_btn: QPushButton | None = None,
) -> QWidget:
    panel = QWidget()
    panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    bar = QFrame()
    bar.setStyleSheet(_SCAN_LOG_TAB_HEADER_STYLESHEET)
    bar.setFixedHeight(_SCAN_LOG_TAB_HEADER_HEIGHT_PX)
    hl = QHBoxLayout(bar)
    hl.setContentsMargins(*_SCAN_LOG_TAB_HEADER_LAYOUT_MARGINS)
    hl.setSpacing(_SCAN_LOG_TAB_HEADER_LAYOUT_SPACING)
    hl.addWidget(QLabel(header_title))
    hl.addStretch()
    if filters_btn is not None:
        filters_btn.setCheckable(True)
        filters_btn.setFixedWidth(80)
        filters_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hl.addWidget(filters_btn)
    layout.addWidget(bar)
    layout.addWidget(table, 1)
    return panel


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
    schema_combo: QComboBox,
    table_names_input: QPlainTextEdit,
    select_all_cb: QCheckBox,
    table: QTableWidget,
    download_btn: QPushButton,
    load_btn: QPushButton,
) -> QWidget:
    """Left pane: schema/table filters, Database tables bar, select-all above checkbox column."""
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
            schema_combo,
        )
    )
    filters.addWidget(
        labeled_field_block(
            field_caption_label("Table names", FORM_LABEL_STYLE),
            table_names_input,
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
    download_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    load_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    bar_hl.addWidget(download_btn)
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
    selectable: bool = False,
) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    if checkbox_column:
        table.setColumnWidth(0, 40)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(
        QTableWidget.SelectionMode.SingleSelection
        if selectable
        else QTableWidget.SelectionMode.NoSelection
    )
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


def _value_for_log_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    """Like :func:`_value_for_column` but also matches keys case-insensitively."""
    value, key_used = _value_for_column(row, keys)
    if value is not None:
        return value, key_used
    lower_map = {str(k).lower(): k for k in row}
    for key in keys:
        actual = lower_map.get(key.lower())
        if actual is not None and row.get(actual) is not None:
            return row.get(actual), actual
    return None, keys[0] if keys else ""


def normalize_etl_log_detail_items(payload: Any) -> list[dict[str, Any]]:
    """Normalize ``GET api/etl/logs/{id}`` payload to plain dict rows."""
    from core.api import _extract_etl_log_detail_rows

    if isinstance(payload, list):
        raw = payload
    elif isinstance(payload, dict):
        raw = _extract_etl_log_detail_rows(payload)
    else:
        return []
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            clean = json.loads(json.dumps(item, default=str))
        except (TypeError, ValueError):
            clean = dict(item)
        if isinstance(clean, dict):
            out.append(clean)
    return out


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


def _sort_rows_by_table_name(rows: list[Any]) -> list[Any]:
    return sorted(rows, key=lambda r: _extract_table_name(r).lower())


def _unique_schemas_from_rows(rows: list[Any]) -> list[str]:
    schemas: set[str] = set()
    for row in rows:
        schema = _extract_table_schema(row).strip()
        if schema:
            schemas.add(schema)
    return sorted(schemas, key=str.lower)


def _parse_table_name_filter_tokens(text: str) -> list[str]:
    if not text.strip():
        return []
    parts = re.split(r"[\s,;\t]+", text.strip())
    return [part.strip().lower() for part in parts if part.strip()]


def _table_matches_name_tokens(table_name: str, schema: str, tokens: list[str]) -> bool:
    name_l = table_name.lower()
    qualified_l = f"{schema}.{table_name}".lower() if schema else name_l
    for token in tokens:
        if token == name_l or token == qualified_l:
            return True
        if "." in token and token.split(".")[-1] == name_l:
            return True
    return False


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
    spec: tuple[tuple[str, tuple[str, ...]], ...] | list[tuple[str, tuple[str, ...]]],
) -> dict[str, str]:
    out: dict[str, str] = {}
    for _header, keys in spec:
        value, key_used = _value_for_column(source, keys)
        out[keys[0]] = _cell_text(value, key_used, keys)
    return out


def _log_row_dict_from_spec(
    source: dict[str, Any],
    spec: tuple[tuple[str, tuple[str, ...]], ...] | list[tuple[str, tuple[str, ...]]],
) -> dict[str, str]:
    """Build a log table row; count fields keep ``0`` and show ``--`` for null."""
    out: dict[str, str] = {}
    for _header, keys in spec:
        value, key_used = _value_for_log_column(source, keys)
        out[keys[0]] = _format_log_field_value(value, key_used)
    return out


def _detail_spec_known_keys_lower(
    spec: list[tuple[str, tuple[str, ...]]],
) -> set[str]:
    known: set[str] = set()
    for _, variants in spec:
        for variant in variants:
            known.add(variant.lower())
    return known


def _detail_column_spec_from_sources(
    sources: list[dict[str, Any]],
) -> list[tuple[str, tuple[str, ...]]]:
    """Always include count columns, then append any extra scalar API fields."""
    spec: list[tuple[str, tuple[str, ...]]] = list(_DETAILS_COLUMN_SPEC)
    known = _detail_spec_known_keys_lower(spec)
    extra = _collect_scalar_field_names(sources, exclude=frozenset({"scan_id"}))
    extra = _order_field_names(extra, _DETAILS_PREFERRED_FIELD_ORDER)
    for key in extra:
        variants = _field_key_variants(key)
        if any(variant.lower() in known for variant in variants):
            continue
        spec.append((_humanize_field_name(key), variants))
        known.update(variant.lower() for variant in variants)
    return spec


def _humanize_field_name(key: str) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", str(key or "").strip())
    text = text.replace("_", " ").strip()
    return text.title() if text else ""


def _field_key_variants(field: str) -> tuple[str, ...]:
    name = str(field or "").strip()
    if not name:
        return ()
    variants = [name]
    snake = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()
    if snake not in variants:
        variants.append(snake)
    upper = name.upper()
    if upper not in variants:
        variants.append(upper)
    return tuple(dict.fromkeys(variants))


def _is_scalar_log_value(value: Any) -> bool:
    return not isinstance(value, (dict, list))


def _is_etl_log_count_key(key: str) -> bool:
    name = str(key or "").strip()
    if not name:
        return False
    if name in _ETL_LOG_COUNT_KEYS:
        return True
    lowered = name.lower()
    return lowered in {k.lower() for k in _ETL_LOG_COUNT_KEYS}


def _format_log_field_value(value: Any, key: str) -> str:
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, default=str, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(value)
    if _is_etl_log_count_key(key):
        if value is None:
            return "--"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            number = float(value)
            return str(int(number)) if number == int(number) else str(number)
    return _cell_text(value, key, _field_key_variants(key))


def _nested_detail_list(entry: dict[str, Any]) -> list[dict[str, Any]]:
    for key in _SCAN_LOG_CHILD_DETAIL_KEYS:
        value = entry.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _parent_run_id(entry: dict[str, Any]) -> str:
    for key in _SCAN_LOG_PARENT_ID_KEYS:
        if key in entry and entry.get(key) not in (None, ""):
            return _cell_text(entry.get(key), key, (key,))
    return ""


def _order_field_names(keys: list[str], preferred: tuple[str, ...]) -> list[str]:
    preferred_set = set(preferred)
    ordered = [k for k in preferred if k in keys]
    ordered.extend(k for k in keys if k not in preferred_set)
    return ordered


def _collect_scalar_field_names(
    rows: list[dict[str, Any]],
    *,
    exclude: frozenset[str],
) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in row:
            if key in exclude or key in seen:
                continue
            if not _is_scalar_log_value(row.get(key)):
                continue
            seen.add(key)
            ordered.append(key)
    return ordered


def derive_scan_summary_column_spec(
    entries: list[dict[str, Any]],
) -> list[tuple[str, tuple[str, ...]]]:
    """Build Scan History columns from parent log fields (excludes nested ``details``)."""
    if not entries:
        return list(_SUMMARY_COLUMN_SPEC)
    keys = _collect_scalar_field_names(
        entries,
        exclude=frozenset(_SCAN_LOG_CHILD_DETAIL_KEYS),
    )
    keys = _order_field_names(keys, _SUMMARY_PREFERRED_FIELD_ORDER)
    if not keys:
        return list(_SUMMARY_COLUMN_SPEC)
    return [(_humanize_field_name(key), _field_key_variants(key)) for key in keys]


def derive_scan_details_column_spec(
    entries: list[dict[str, Any]],
) -> list[tuple[str, tuple[str, ...]]]:
    """Build Scan Detail Log columns from flattened child rows."""
    flat = _flatten_scan_details(entries)
    if not flat:
        return list(_DETAILS_COLUMN_SPEC)
    keys = _collect_scalar_field_names(
        [{key: value for key, value in row.items()} for row in flat],
        exclude=frozenset(),
    )
    keys = _order_field_names(keys, _DETAILS_PREFERRED_FIELD_ORDER)
    if not keys:
        return list(_DETAILS_COLUMN_SPEC)
    spec: list[tuple[str, tuple[str, ...]]] = []
    for key in keys:
        if key == "scan_id":
            spec.append((_humanize_field_name(key), ("scan_id",)))
        else:
            spec.append((_humanize_field_name(key), _field_key_variants(key)))
    return spec


def _summary_table_rows(
    entries: list[dict[str, Any]],
    spec: list[tuple[str, tuple[str, ...]]] | None = None,
) -> list[dict[str, str]]:
    column_spec = spec or derive_scan_summary_column_spec(entries)
    return [_log_row_dict_from_spec(entry, column_spec) for entry in entries]


def _scan_log_id_sort_key(value: Any) -> tuple[int, int | str]:
    text = str(value or "").strip()
    if not text or text == "--":
        return (2, 0)
    try:
        return (0, int(text))
    except (ValueError, TypeError):
        return (1, text.lower())


def _sort_scan_log_rows_by_id(rows: list[dict[str, str]], id_key: str) -> list[dict[str, str]]:
    return sorted(rows, key=lambda r: _scan_log_id_sort_key(r.get(id_key)))


def _apply_scan_log_id_item_sort_role(item: QTableWidgetItem, raw_id: Any) -> None:
    """Use numeric Qt sort role so Id columns order as 1, 2, 10 rather than 1, 10, 2."""
    key = _scan_log_id_sort_key(raw_id)
    if key[0] == 0:
        item.setData(Qt.ItemDataRole.EditRole, key[1])
    elif key[0] == 1:
        item.setData(Qt.ItemDataRole.EditRole, key[1])


def _finalize_scan_log_table_sort(table: QTableWidget, *, filter_visible: bool) -> None:
    if filter_visible:
        table.setSortingEnabled(False)
        return
    table.setSortingEnabled(True)
    header = table.horizontalHeader()
    header.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
    table.sortItems(0, Qt.SortOrder.AscendingOrder)


def _finalize_scanned_list_table_sort(table: QTableWidget, *, filter_visible: bool) -> None:
    """Keep Scanned tables in Table Name A–Z order (case-insensitive); lock header sort."""
    offset = data_row_offset(filter_visible)
    table.setSortingEnabled(False)
    for row in range(offset, table.rowCount()):
        item = table.item(row, 0)
        if item is not None:
            item.setData(Qt.ItemDataRole.EditRole, item.text().casefold())
    table.setSortingEnabled(True)
    header = table.horizontalHeader()
    header.setSortIndicator(0, Qt.SortOrder.AscendingOrder)
    table.sortItems(0, Qt.SortOrder.AscendingOrder)
    table.setSortingEnabled(False)
    header.setSortIndicatorShown(False)
    header.setSectionsClickable(False)


def _log_row_value(row: dict[str, str], keys: tuple[str, ...]) -> tuple[Any, str]:
    return _value_for_log_column(row, keys)


def _log_format_cell(value: Any, key_used: str, keys: tuple[str, ...]) -> str:
    return _cell_text(value, key_used, keys)


def _detail_row_cell_text(row: dict[str, str], keys: tuple[str, ...]) -> str:
    """Resolve a detail-table cell using all key aliases (camelCase / snake_case)."""
    value, key_used = _value_for_log_column(row, keys)
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return _log_format_cell(value, key_used, keys)


def _flatten_scan_details(entries: list[dict[str, Any]]) -> list[dict[str, str]]:
    """One row per child in ``details`` (or equivalent), with all scalar child fields."""
    rows: list[dict[str, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        scan_id = _parent_run_id(entry)
        for item in _nested_detail_list(entry):
            row: dict[str, str] = {"scan_id": scan_id}
            for key, value in item.items():
                if key in _SCAN_LOG_CHILD_DETAIL_KEYS and isinstance(value, list):
                    continue
                row[key] = _format_log_field_value(value, key)
            rows.append(row)
    return _sort_scan_log_rows_by_id(rows, "scan_id")


def prepare_scan_log_table_data(
    entries: list[dict[str, Any]],
) -> tuple[
    list[dict[str, Any]],
    list[tuple[str, tuple[str, ...]]],
    list[tuple[str, tuple[str, ...]]],
    list[dict[str, str]],
    list[dict[str, str]],
]:
    """Sort entries and derive parent/child column specs plus display rows."""
    matched = sorted(
        [e for e in entries if isinstance(e, dict)],
        key=lambda e: _scan_log_id_sort_key(e.get("id") or e.get("logId")),
    )
    summary_spec = derive_scan_summary_column_spec(matched)
    details_spec = derive_scan_details_column_spec(matched)
    summary_rows = _summary_table_rows(matched, summary_spec)
    detail_rows = _flatten_scan_details(matched)
    return matched, summary_spec, details_spec, summary_rows, detail_rows


def prepare_scan_log_detail_table(
    parent_id: str,
    detail_items: list[dict[str, Any]],
) -> tuple[list[tuple[str, tuple[str, ...]]], list[dict[str, str]]]:
    """Build detail columns/rows from ``GET api/etl/logs/{id}`` response."""
    sources: list[dict[str, Any]] = []
    for item in detail_items:
        if not isinstance(item, dict):
            continue
        source = dict(item)
        source["scan_id"] = str(parent_id)
        sources.append(source)
    if not sources:
        return list(_DETAILS_COLUMN_SPEC), []
    spec = _detail_column_spec_from_sources(sources)
    rows = [_log_row_dict_from_spec(source, spec) for source in sources]
    return spec, rows


class ScanConnectionPageWidget(QWidget):
    """Scan UI: connections table · tabbed scan logs / history."""

    scan_detail_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._summary_source_rows: list[dict[str, str]] = []
        self._summary_raw_entries: list[dict[str, Any]] = []
        self._details_source_rows: list[dict[str, str]] = []
        self._summary_column_spec: list[tuple[str, tuple[str, ...]]] = list(_SUMMARY_COLUMN_SPEC)
        self._details_column_spec: list[tuple[str, tuple[str, ...]]] = list(_DETAILS_COLUMN_SPEC)
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
        self.connection_picker = EtlConnectionHeaderPicker()
        hl.addWidget(self.connection_picker)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFixedWidth(100)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        self.empty_hint = QLabel("Select a connection to view scan logs.")
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

        self.scan_filter_run_btn = QPushButton("Scan")
        self.scanned_list_scan_all_btn = QPushButton("Scan All")
        self.scanned_list_filters_btn = QPushButton("Filters")
        self.scanned_fields_filters_btn = QPushButton("Filters")
        self.load_database_tables_btn = QPushButton("Load tables")
        self.download_database_tables_btn = QPushButton("Download")
        _size_scan_header_button_to_text(self.scan_filter_run_btn)
        _prepare_scan_header_button(self.scanned_list_scan_all_btn, width_px=100)
        self.scanned_list_filters_btn.setCheckable(True)
        self.scanned_list_filters_btn.setFixedWidth(80)
        self.scanned_list_filters_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        _prepare_scan_header_button(self.scanned_fields_filters_btn, width_px=80)
        _prepare_scan_header_button(self.load_database_tables_btn, width_px=100)
        _prepare_scan_header_button(self.download_database_tables_btn, width_px=100)

        self.scanned_tables_list_table = _build_scan_tables_widget(
            ["Table Name", "Schema", "Last Scan"],
            read_only=True,
            selectable=True,
        )
        self.scanned_table_fields_table = QTableWidget(0, len(_COLUMN_DETAIL_SPEC))
        self.scanned_table_fields_table.setHorizontalHeaderLabels(
            [h for h, _ in _COLUMN_DETAIL_SPEC]
        )
        self.scanned_table_fields_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.scanned_table_fields_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        apply_data_table_appearance(
            self.scanned_table_fields_table,
            read_only=True,
            stretch_last_section=False,
        )
        attach_table_copy_shortcut(self.scanned_table_fields_table)

        scanned_list_split = QSplitter(Qt.Orientation.Vertical)
        scanned_list_split.setChildrenCollapsible(False)
        scanned_list_split.setHandleWidth(6)
        scanned_list_split.addWidget(self.scanned_tables_list_table)
        scanned_list_split.addWidget(
            _build_scanned_sub_table_panel(
                "Column details",
                self.scanned_table_fields_table,
                filters_btn=self.scanned_fields_filters_btn,
            )
        )
        scanned_list_split.setStretchFactor(0, 2)
        scanned_list_split.setStretchFactor(1, 1)
        scanned_list_split.setSizes([320, 200])

        scanned_list_content = QWidget()
        scanned_list_content_layout = QVBoxLayout(scanned_list_content)
        scanned_list_content_layout.setContentsMargins(0, 0, 0, 0)
        scanned_list_content_layout.setSpacing(0)
        scanned_list_content_layout.addWidget(scanned_list_split, 1)
        scanned_tables_tab = _build_scan_operation_tab(
            header_title="Scanned tables",
            subtitle=_SCAN_TAB_SUBTITLE_SCANNED_LIST,
            header_buttons=(
                self.scanned_list_filters_btn,
                self.scanned_list_scan_all_btn,
            ),
            content=scanned_list_content,
        )

        self.scan_filter_schema_combo = QComboBox()
        self.scan_filter_schema_combo.addItem(_SCHEMA_FILTER_ALL_LABEL, "")
        apply_form_combobox_field(self.scan_filter_schema_combo, height_px=28)
        self.scan_filter_table_names_input = QPlainTextEdit()
        self.scan_filter_table_names_input.setPlaceholderText(_TABLE_NAMES_FILTER_PLACEHOLDER)
        self.scan_filter_table_names_input.setMaximumHeight(72)
        self.scan_filter_table_names_input.setStyleSheet(FORM_PLAIN_TEXT_STYLE)
        self.scan_filter_select_all_cb = QCheckBox("Select all")
        self.scan_filter_select_all_cb.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px;")

        self.scan_filter_source_tables_table = _build_scan_tables_widget(
            ["", "Table Name"],
            read_only=False,
            checkbox_column=True,
        )
        filter_database_panel = _build_scan_filter_database_panel(
            schema_combo=self.scan_filter_schema_combo,
            table_names_input=self.scan_filter_table_names_input,
            select_all_cb=self.scan_filter_select_all_cb,
            table=self.scan_filter_source_tables_table,
            download_btn=self.download_database_tables_btn,
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

        self.detail_show_all_btn = QPushButton("Clear")
        self.detail_show_all_btn.setVisible(False)
        self.details_filters_btn = QPushButton("Filters")
        details_tab, self.details_table, self.detail_log_hint = _build_scan_log_tab(
            header_title="Scan Detail Log",
            subtitle=_SCAN_DETAIL_LOG_SUBTITLE_EMPTY,
            column_count=len(_DETAILS_COLUMN_SPEC),
            filters_btn=self.details_filters_btn,
            header_widgets_before_filters=(self.detail_show_all_btn,),
        )
        self.details_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.tabs.addTab(details_tab, "Scan Detail Log")

        card_layout.addWidget(self.tabs, 1)
        details_outer.addWidget(card, 1)
        self.detail_stack.addWidget(details_page)

        right_layout.addWidget(self.detail_stack, 1)
        self.set_scan_controls_enabled(False)

        right_wrap.setMinimumHeight(320)
        content_layout.addWidget(right_wrap, 1)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        self._summary_filter_timer.timeout.connect(self._apply_summary_column_filters)
        self._details_filter_timer.timeout.connect(self._apply_details_column_filters)
        self.summary_filters_btn.toggled.connect(self._on_summary_filters_toggled)
        self.details_filters_btn.toggled.connect(self._on_details_filters_toggled)
        self.summary_table.itemDoubleClicked.connect(self._on_summary_row_double_clicked)
        self.detail_show_all_btn.clicked.connect(self._clear_detail_scan_filter)

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
            self.summary_table,
            self._summary_spec_list(),
            self._summary_filter_visible,
            _log_row_value,
            _log_format_cell,
        )

    def _details_rows_for_display(self) -> list[dict[str, str]]:
        if not self._detail_scan_id_filter:
            return []
        return filter_dict_rows_by_column_edits(
            list(self._details_source_rows),
            self.details_table,
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
                if col == 0:
                    raw_id = raw.get("id") if isinstance(raw, dict) else row.get(keys[0])
                    _apply_scan_log_id_item_sort_role(item, raw_id)
                    if isinstance(raw, dict):
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
        _finalize_scan_log_table_sort(
            self.summary_table,
            filter_visible=self._summary_filter_visible,
        )

    def _write_details_table(self, rows: list[dict[str, str]]) -> None:
        spec = self._details_spec_list()
        headers = [h for h, _ in spec]
        self.details_table.clearContents()
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
                text = _detail_row_cell_text(row, keys)
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    value, _ = _value_for_column(row, keys)
                    _apply_scan_log_id_item_sort_role(item, value)
                self.details_table.setItem(tr, col, item)
        sync_vertical_header_labels(
            self.details_table,
            filter_visible=self._details_filter_visible,
            data_row_count=len(rows),
        )
        if self._details_source_rows:
            resize_data_table_columns_to_content(
                self.details_table,
                spec,
                self._details_source_rows,
                _log_row_value,
                _log_format_cell,
            )
        _finalize_scan_log_table_sort(
            self.details_table,
            filter_visible=self._details_filter_visible,
        )

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
        scan_id = _parent_run_id(entry)
        if not scan_id:
            return
        self.scan_detail_requested.emit(scan_id)

    def request_scan_log_details(self, scan_id: str) -> None:
        self._detail_scan_id_filter = scan_id
        self._details_source_rows = []
        self._details_column_spec = list(_DETAILS_COLUMN_SPEC)
        self._update_detail_filter_hint(loading=True)
        self._write_details_table([])
        self.tabs.setCurrentIndex(_TAB_SCAN_DETAIL_LOG)

    def apply_scan_log_details(
        self,
        scan_id: str,
        detail_items: list[dict[str, Any]],
        *,
        error_message: str = "",
    ) -> None:
        self._detail_scan_id_filter = scan_id
        if error_message:
            self._details_source_rows = []
            self._details_column_spec = list(_DETAILS_COLUMN_SPEC)
            self._update_detail_filter_hint(error=error_message)
            self._write_details_table([])
            return
        self._details_column_spec, self._details_source_rows = prepare_scan_log_detail_table(
            scan_id, detail_items
        )
        self._update_detail_filter_hint()
        self._write_details_table(self._details_rows_for_display())

    def _clear_detail_scan_filter(self) -> None:
        self._detail_scan_id_filter = None
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
        if loading and self._detail_scan_id_filter:
            self.detail_log_hint.setText(
                f"Loading step details for scan run Id {self._detail_scan_id_filter}…"
            )
            self.detail_show_all_btn.setVisible(True)
        elif error and self._detail_scan_id_filter:
            self.detail_log_hint.setText(
                f"Scan run Id {self._detail_scan_id_filter}: {error}"
            )
            self.detail_show_all_btn.setVisible(True)
        elif self._detail_scan_id_filter:
            count = len(self._details_source_rows)
            self.detail_log_hint.setText(
                f"Step details for scan run Id {self._detail_scan_id_filter} ({count} row(s)). "
                "Use Clear to close."
            )
            self.detail_show_all_btn.setVisible(True)
        else:
            self.detail_log_hint.setText(_SCAN_DETAIL_LOG_SUBTITLE_EMPTY)
            self.detail_show_all_btn.setVisible(False)

    def set_scan_log_data(
        self,
        entries: list[dict[str, Any]],
        *,
        clear_detail: bool = True,
    ) -> None:
        if clear_detail:
            self._detail_scan_id_filter = None
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
        if not clear_detail and self._detail_scan_id_filter:
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
        self.scanned_fields_filters_btn.setEnabled(enabled)
        self.scan_inner_tabs.setEnabled(enabled)
        self.scan_filter_schema_combo.setEnabled(enabled)
        self.scan_filter_table_names_input.setEnabled(enabled)
        self.scan_filter_select_all_cb.setEnabled(enabled)
        self.load_database_tables_btn.setEnabled(enabled)
        self.download_database_tables_btn.setEnabled(enabled)
        self.scanned_tables_list_table.setEnabled(enabled)
        self.scanned_table_fields_table.setEnabled(enabled)
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
            self._summary_column_spec = list(_SUMMARY_COLUMN_SPEC)
            self._details_column_spec = list(_DETAILS_COLUMN_SPEC)
            self._detail_scan_id_filter = None
            self._update_detail_filter_hint()
            self.summary_table.setRowCount(0)
            self.details_table.setRowCount(0)
            self.scan_progress_label.clear()
            self.scan_progress_label.setVisible(False)
            self.scan_progress_bar.setVisible(False)


class _ScanLogDetailFetchWorker(QObject):
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


class EtlScanConnectionPage(QWidget):
    """Scan page: pick a connection, view SCAN log summary and per-table details."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._ui = ScanConnectionPageWidget()
        layout.addWidget(self._ui)

        self._ctx = get_etl_connection_context()
        self._connection_scan_logs: list[dict[str, Any]] = []
        self._source_tables_cache: list[Any] = []
        self._scanned_tables_cache: list[Any] = []
        self._selected_filter_tables: set[str] = set()
        self._rendering_filter_tables = False
        self._scan_in_progress = False
        self._scanned_list_filter_visible = False
        self._scanned_fields_filter_visible = False
        self._columns_source: list[dict[str, str]] = []
        self._scanned_list_filter_timer = QTimer(self)
        self._scanned_list_filter_timer.setSingleShot(True)
        self._scanned_list_filter_timer.setInterval(200)
        self._scanned_fields_filter_timer = QTimer(self)
        self._scanned_fields_filter_timer.setSingleShot(True)
        self._scanned_fields_filter_timer.setInterval(200)
        self._detail_fetch_in_flight = False
        self._detail_fetch_seq = 0
        self._detail_fetch_pending_id: str | None = None
        self._detail_fetch_thread: QThread | None = None
        self._detail_fetch_worker: _ScanLogDetailFetchWorker | None = None

        self._ui.refresh_btn.clicked.connect(self.refresh)
        self._ui.scan_detail_requested.connect(self._load_scan_log_details)
        self._ctx.connection_selected.connect(self._on_connection_selected)
        self._ui.scanned_list_filters_btn.toggled.connect(self._on_scanned_list_filters_toggled)
        self._scanned_list_filter_timer.timeout.connect(self._refresh_scanned_list_table_view)
        self._ui.scanned_fields_filters_btn.toggled.connect(self._on_scanned_fields_filters_toggled)
        self._scanned_fields_filter_timer.timeout.connect(self._refresh_scanned_fields_view)
        self._ui.scanned_tables_list_table.cellClicked.connect(self._on_scanned_table_cell_clicked)
        self._ui.scanned_list_scan_all_btn.clicked.connect(self._run_scan_all)
        self._ui.scan_filter_run_btn.clicked.connect(self._run_scan_by_filter)
        self._ui.load_database_tables_btn.clicked.connect(self._load_source_database_tables)
        self._ui.download_database_tables_btn.clicked.connect(self._download_database_tables)
        self._ui.scan_filter_schema_combo.currentIndexChanged.connect(self._apply_filter_table_view)
        self._ui.scan_filter_table_names_input.textChanged.connect(self._apply_filter_table_view)
        self._ui.scan_filter_select_all_cb.stateChanged.connect(self._on_filter_select_all_changed)
        self._ui.scan_filter_source_tables_table.itemChanged.connect(self._on_filter_table_item_changed)
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
        result = self._ctx.refresh_connections(self._token())
        if not result.get("success"):
            self._show_page_message(
                str(result.get("message") or "Failed to load connections."), error=True
            )
            return
        show_auto_hiding_message(self, self._ui.message_label, "", error=False)
        self._on_connection_selected(self._ctx.current_connection())

    def _current_connection(self) -> dict[str, Any] | None:
        return self._ctx.current_connection()

    def _schedule_scanned_list_filter_apply(self) -> None:
        if self._scanned_list_filter_visible:
            self._scanned_list_filter_timer.start()

    def _on_scanned_list_filters_toggled(self, checked: bool) -> None:
        self._scanned_list_filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self._ui.scanned_tables_list_table)
        self._refresh_scanned_list_table_view()

    def _scanned_list_cache_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for row in self._scanned_tables_cache:
            if isinstance(row, dict):
                rows.append(row)
            elif isinstance(row, str) and row.strip():
                rows.append({"tableName": row.strip()})
        return _sort_rows_by_table_name(rows)

    def _scanned_list_filtered_rows(self) -> list[dict[str, Any]]:
        rows = self._scanned_list_cache_rows()
        if not self._scanned_list_filter_visible:
            return rows
        filtered = filter_dict_rows_by_column_edits(
            rows,
            self._ui.scanned_tables_list_table,
            list(_SCANNED_LIST_COLUMN_SPEC),
            True,
            _value_for_scanned_list_column,
            format_data_table_cell,
        )
        return _sort_rows_by_table_name(filtered)

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
            enable_sorting=False,
        )
        _finalize_scanned_list_table_sort(
            self._ui.scanned_tables_list_table,
            filter_visible=self._scanned_list_filter_visible,
        )

    def _scanned_list_data_row_offset(self) -> int:
        return data_row_offset(self._scanned_list_filter_visible)

    def _get_scanned_list_row_at(self, table_row: int) -> dict[str, Any] | None:
        if table_row < self._scanned_list_data_row_offset():
            return None
        item = self._ui.scanned_tables_list_table.item(table_row, 0)
        if item is None:
            return None
        row = item.data(Qt.ItemDataRole.UserRole)
        return row if isinstance(row, dict) else None

    def _on_scanned_table_cell_clicked(self, row: int, _column: int) -> None:
        scanned_row = self._get_scanned_list_row_at(row)
        if not scanned_row:
            return
        table_name = _extract_table_name(scanned_row)
        if table_name:
            self._load_scanned_table_fields(table_name)

    def _clear_scanned_table_fields(self) -> None:
        self._columns_source = []
        self._refresh_scanned_fields_view()

    def _load_scanned_table_fields(self, table_name: str) -> None:
        conn_id = _connection_id(self._current_connection())
        if conn_id is None:
            QMessageBox.warning(self, "Missing", "Select a connection first.")
            return
        result = api_get_metadata_table_columns(conn_id, table_name, token=self._token())
        if not result.get("success"):
            QMessageBox.warning(
                self, "Failed", str(result.get("message") or "Could not load table info.")
            )
            return
        self._build_scanned_fields_source(
            str(result.get("tableName") or table_name),
            list(result.get("columns") or []),
        )
        self._refresh_scanned_fields_view()

    def _build_scanned_fields_source(self, table_name: str, columns: list[Any]) -> None:
        rows: list[dict[str, str]] = []
        for col in columns:
            c = col if isinstance(col, dict) else {}
            rows.append(
                {
                    "TABLE_NAME": table_name,
                    "COLUMN_NAME": _display_value(c.get("COLUMN_NAME")),
                    "DATA_TYPE": _display_value(c.get("DATA_TYPE")),
                    "CHARACTER_MAXIMUM_LENGTH": _display_value(
                        c.get("CHARACTER_MAXIMUM_LENGTH")
                    ),
                    "NUMERIC_PRECISION": _display_value(c.get("NUMERIC_PRECISION")),
                    "NUMERIC_SCALE": _display_value(c.get("NUMERIC_SCALE")),
                    "IS_NULLABLE": _display_value(c.get("IS_NULLABLE")),
                    "is_primary_key": _display_value(c.get("is_primary_key")),
                }
            )
        self._columns_source = rows

    def _schedule_scanned_fields_filter_apply(self) -> None:
        if self._scanned_fields_filter_visible:
            self._scanned_fields_filter_timer.start()

    def _on_scanned_fields_filters_toggled(self, checked: bool) -> None:
        self._scanned_fields_filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self._ui.scanned_table_fields_table)
        self._refresh_scanned_fields_view()

    def _scanned_fields_filtered_rows(self) -> list[dict[str, str]]:
        rows = list(self._columns_source)
        if not self._scanned_fields_filter_visible:
            return rows
        return filter_dict_rows_by_column_edits(
            rows,
            self._ui.scanned_table_fields_table,
            list(_COLUMN_DETAIL_SPEC),
            True,
            _value_for_column,
            format_data_table_cell,
        )

    def _refresh_scanned_fields_view(self) -> None:
        saved = (
            saved_filter_texts(self._ui.scanned_table_fields_table)
            if self._scanned_fields_filter_visible
            else None
        )
        render_dict_rows_table(
            self._ui.scanned_table_fields_table,
            self._scanned_fields_filtered_rows(),
            list(_COLUMN_DETAIL_SPEC),
            filter_visible=self._scanned_fields_filter_visible,
            value_for_column=_value_for_column,
            format_cell=format_data_table_cell,
            on_filter_text_changed=self._schedule_scanned_fields_filter_apply,
            saved_filter_texts_list=saved,
        )

    def _on_connection_selected(self, conn: object) -> None:
        if not isinstance(conn, dict):
            self._ui.set_right_panel_enabled(False)
            self._connection_scan_logs = []
            self._render_scan_logs()
            self._clear_scanned_table_fields()
            return
        name = _connection_name(conn)
        self._ui.set_right_panel_enabled(True, name)
        self._load_filter_tables()
        self._refresh_scan_data()

    def _begin_scan_ui(self, message: str) -> None:
        self._scan_in_progress = True
        self._ui.scan_progress_label.setText(message)
        self._ui.scan_progress_label.setStyleSheet(
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: {Theme.TEXT_SECONDARY};"
        )
        self._ui.scan_progress_label.setVisible(True)
        self._ui.scan_progress_bar.setVisible(True)
        self._ui.set_scan_controls_enabled(False)
        self._ui.set_scan_log_data([], clear_detail=False)

    def _end_scan_ui(
        self,
        completion_msg: str | None = None,
        *,
        completion_error: bool = False,
        after_filter_scan: bool = False,
    ) -> None:
        self._scan_in_progress = False
        self._ui.scan_progress_bar.setVisible(False)
        if self._current_connection():
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
        name = _connection_name(self._current_connection())
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
        if not completion_error:
            self._run_field_check_after_scan(self._scanned_table_names_from_cache())

    def _run_scan_by_filter(self) -> None:
        name = _connection_name(self._current_connection())
        conn_id = _connection_id(self._current_connection())
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
        if not completion_error:
            self._run_field_check_after_scan(table_names)

    def _scanned_table_names_from_cache(self) -> list[str]:
        names: list[str] = []
        for row in self._scanned_tables_cache:
            name = _extract_table_name(row)
            if name:
                names.append(name)
        return sorted(set(names))

    def _run_field_check_after_scan(self, table_names: list[str]) -> None:
        conn_id = _connection_id(self._current_connection())
        if conn_id is None:
            return
        names = sorted({str(name).strip() for name in table_names if str(name).strip()})
        if not names:
            return
        check = api_check_scan_connection_fields(conn_id, names, token=self._token())
        if check.get("success"):
            return
        if check.get("field_mismatch"):
            dlg = ImportFieldMismatchDialog(
                self,
                message=str(check.get("message") or "FIELD MISMATCH"),
                rows=list(check.get("data") or []),
                warning_only=True,
            )
            dlg.exec()
            return
        self._show_page_message(str(check.get("message") or "Field check failed."), error=True)

    def _load_scanned_tables(self) -> None:
        """GET get-scanned-table-by-id — Scanned tables tab and Scan by filter right panel."""
        conn_id = _connection_id(self._current_connection())
        if conn_id is None:
            self._scanned_tables_cache = []
            self._clear_scanned_table_fields()
            return
        scanned_result = api_get_metadata_tables(conn_id, token=self._token())
        if scanned_result.get("success"):
            self._scanned_tables_cache = _sort_rows_by_table_name(
                list(scanned_result.get("tables") or [])
            )
        else:
            self._scanned_tables_cache = []
            self._show_page_message(
                str(scanned_result.get("message") or "Failed to load scanned tables."),
                error=True,
            )
        self._clear_scanned_table_fields()

    def _refresh_scan_section(self) -> None:
        """After successful scan-by-filter: reload scanned tables and logs; keep left database list."""
        self._load_scanned_tables()
        self._apply_filter_table_view()

    def _load_filter_tables(self) -> None:
        """On connection select / refresh: clear database list and load scanned tables."""
        self._source_tables_cache = []
        self._selected_filter_tables = set()
        self._populate_schema_filter_combo()
        self._load_scanned_tables()
        self._apply_filter_table_view()

    def _visible_database_table_names(self) -> list[str]:
        table = self._ui.scan_filter_source_tables_table
        names: list[str] = []
        for row in range(table.rowCount()):
            item = table.item(row, 1)
            if item is None:
                continue
            name = item.text().strip()
            if name:
                names.append(name)
        return names

    def _download_database_tables(self) -> None:
        table_names = self._visible_database_table_names()
        if not table_names:
            QMessageBox.information(
                self,
                "Download",
                "No tables to download. Load tables first or adjust filters.",
            )
            return

        connection_label = (_connection_name(self._current_connection()) or "connection").strip()
        safe_label = re.sub(r'[<>:"/\\|?*]+', "_", connection_label) or "connection"
        default_name = f"database_tables_{safe_label}.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save database tables",
            default_name,
            "Excel workbook (*.xlsx)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path = f"{path}.xlsx"

        try:
            write_xlsx(
                path,
                ["Table Name"],
                [[name] for name in table_names],
                sheet_title="Database tables",
            )
        except RuntimeError as exc:
            QMessageBox.warning(self, "Download failed", str(exc))
            return
        except OSError as exc:
            QMessageBox.warning(self, "Download failed", f"Could not save file: {exc}")
            return

        self._show_page_message(f"Saved {len(table_names)} table(s) to {path}", error=False)

    def _load_source_database_tables(self) -> None:
        """POST scan-connection/table/{id} — user-triggered from Scan by filter left panel."""
        conn_id = _connection_id(self._current_connection())
        if conn_id is None:
            self._show_page_message("Select a connection first.", error=True)
            return
        self._ui.load_database_tables_btn.setEnabled(False)
        try:
            result = api_post_scan_connection_source_tables(conn_id, token=self._token())
            if result.get("success"):
                self._source_tables_cache = list(result.get("tables") or [])
                self._selected_filter_tables = set()
                self._populate_schema_filter_combo()
                self._apply_filter_table_view()
                msg = str(result.get("message") or "").strip()
                if msg:
                    self._show_page_message(msg, error=False)
            else:
                self._source_tables_cache = []
                self._selected_filter_tables = set()
                self._populate_schema_filter_combo()
                self._render_source_tables([])
                self._show_page_message(
                    str(result.get("message") or "Failed to load database tables."),
                    error=True,
                )
        finally:
            if self._current_connection() and not self._scan_in_progress:
                self._ui.load_database_tables_btn.setEnabled(True)

    def _populate_schema_filter_combo(self) -> None:
        combo = self._ui.scan_filter_schema_combo
        previous = str(combo.currentData() or "")
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(_SCHEMA_FILTER_ALL_LABEL, "")
        for schema in _unique_schemas_from_rows(self._source_tables_cache):
            combo.addItem(schema, schema)
        restore_index = combo.findData(previous)
        combo.setCurrentIndex(restore_index if restore_index >= 0 else 0)
        combo.blockSignals(False)

    def _filtered_rows(self, cache: list[Any], *, include_schema_filter: bool) -> list[Any]:
        schema_sel = str(self._ui.scan_filter_schema_combo.currentData() or "").strip().lower()
        name_tokens = _parse_table_name_filter_tokens(
            self._ui.scan_filter_table_names_input.toPlainText()
        )
        rows: list[Any] = []
        for row in cache:
            table_name = _extract_table_name(row)
            if not table_name:
                continue
            row_data = row if isinstance(row, dict) else {}
            schema = _extract_table_schema(row_data)
            if include_schema_filter and schema_sel:
                if schema.lower() != schema_sel:
                    continue
            if name_tokens and not _table_matches_name_tokens(table_name, schema, name_tokens):
                continue
            rows.append(row)
        return _sort_rows_by_table_name(rows)

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
        if not self._current_connection():
            self._connection_scan_logs = []
            self._render_scan_logs()
            return
        conn_id = _connection_id(self._current_connection())
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

    def _schedule_scan_log_details(self, scan_id: str) -> None:
        scan_id = str(scan_id or "").strip()
        if not scan_id:
            return
        self._detail_fetch_pending_id = scan_id
        if not self._detail_fetch_in_flight:
            self._start_scan_log_detail_fetch()

    def _start_scan_log_detail_fetch(self) -> None:
        if self._detail_fetch_in_flight:
            return
        scan_id = str(self._detail_fetch_pending_id or "").strip()
        if not scan_id:
            return
        self._detail_fetch_seq += 1
        seq = self._detail_fetch_seq
        self._detail_fetch_in_flight = True
        self._ui.request_scan_log_details(scan_id)
        self._detail_fetch_thread = QThread(self)
        self._detail_fetch_worker = _ScanLogDetailFetchWorker(scan_id, self._token(), seq)
        self._detail_fetch_worker.moveToThread(self._detail_fetch_thread)
        self._detail_fetch_thread.started.connect(self._detail_fetch_worker.run)
        self._detail_fetch_worker.finished.connect(self._on_detail_fetch_finished)
        self._detail_fetch_worker.finished.connect(self._detail_fetch_thread.quit)
        self._detail_fetch_thread.finished.connect(self._cleanup_detail_fetch_thread)
        self._detail_fetch_thread.start()

    def _load_scan_log_details(self, scan_id: str) -> None:
        self._schedule_scan_log_details(scan_id)

    @Slot(str, object, str, int)
    def _on_detail_fetch_finished(
        self,
        scan_id: str,
        payload: object,
        error_message: str,
        seq: int,
    ) -> None:
        if seq != self._detail_fetch_seq:
            return
        self._detail_fetch_in_flight = False
        current = str(self._ui._detail_scan_id_filter or "").strip()
        if str(scan_id) != current:
            if current:
                self._detail_fetch_pending_id = current
                self._start_scan_log_detail_fetch()
            return
        detail_rows = normalize_etl_log_detail_items(payload)
        self._ui.apply_scan_log_details(
            scan_id,
            detail_rows,
            error_message=str(error_message or ""),
        )
        pending = str(self._detail_fetch_pending_id or "").strip()
        if pending and pending != str(scan_id):
            self._start_scan_log_detail_fetch()

    @Slot()
    def _cleanup_detail_fetch_thread(self) -> None:
        if self._detail_fetch_worker is not None:
            self._detail_fetch_worker.deleteLater()
            self._detail_fetch_worker = None
        if self._detail_fetch_thread is not None:
            self._detail_fetch_thread.deleteLater()
            self._detail_fetch_thread = None

    def _render_scan_logs(self) -> None:
        if self._scan_in_progress:
            self._ui.set_scan_log_data([], clear_detail=False)
            return
        logs = self._connection_scan_logs
        active_detail_id = self._ui._detail_scan_id_filter
        self._ui.set_scan_log_data(logs, clear_detail=active_detail_id is None)
        if active_detail_id:
            self._schedule_scan_log_details(active_detail_id)
        matched = sorted(
            logs,
            key=lambda e: str(
                e.get("startTime")
                or e.get("start_time")
                or e.get("createdAt")
                or e.get("createdOn")
                or ""
            ),
            reverse=True,
        )
        if matched:
            latest = matched[0]
            status = _cell_text(latest.get("status")) or "--"
            started = _cell_text(
                latest.get("startTime")
                or latest.get("start_time")
                or latest.get("createdAt")
                or latest.get("createdOn")
            ) or "--"
            self._ui.scan_progress_label.setText(f"Last scan: {status} · started {started}")
            self._ui.scan_progress_label.setStyleSheet(
                f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: {Theme.TEXT_SECONDARY};"
            )
            self._ui.scan_progress_label.setVisible(True)
        elif self._current_connection() and not self._scan_in_progress:
            self._ui.scan_progress_label.setText("No scan history for this connection.")
            self._ui.scan_progress_label.setStyleSheet(
                f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: {Theme.TEXT_SECONDARY};"
            )
            self._ui.scan_progress_label.setVisible(True)
        elif not (self._ui.scan_progress_label.text() or "").strip():
            self._ui.scan_progress_label.setVisible(False)
