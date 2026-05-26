"""ETL: Extraction — select imported tables/columns and run extraction jobs."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.api import (
    api_get_all_connections,
    api_get_extracted_fields,
    api_get_imported_tables,
    api_remove_imported_table,
    api_start_etl_job,
    api_update_extracted_fields,
)
from core.user_context import get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.data_table import (
    MIN_DATA_COL_WIDTH_PX,
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    configure_data_table_header,
    data_row_offset,
    filter_dict_rows_by_column_edits,
    format_data_table_cell,
    install_filter_row,
    resize_data_table_columns_to_content,
    restore_filter_texts,
    saved_filter_texts,
    sync_vertical_header_labels,
)
from ui.form_page_styles import (
    FORM_PAGE_FONT_SIZE_PX,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LINEEDIT_PLACEHOLDER_SUBSTYLE,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    LIST_PAGE_HEADER_TITLE_FONT_PX,
)


def _display_value(value: Any) -> str:
    return "--" if value is None or value == "" else str(value)


def _extraction_format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    text = format_data_table_cell(value, key, key_candidates)
    return text if text else "--"


_IMPORT_TABLES_DATA_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("TABLE_NAME", ("TABLE_NAME", "tableName")),
    ("LAST_SCAN_DATE", ("LAST_SCAN_DATE", "lastScanDate", "last_scan_date")),
    ("LAST_IMPORT_DATE", ("LAST_IMPORT_DATE", "lastImportDate", "last_import_date")),
)

_EXTRACTION_COLUMNS_DATA_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("COLUMN_NAME", ("name",)),
    ("DATA_TYPE", ("type",)),
    ("CHAR_MAX_LEN", ("char_max_len",)),
    ("NUM_PRECISION", ("num_precision",)),
    ("NUM_SCALE", ("num_scale",)),
    ("IS_NULLABLE", ("is_nullable_display", "nullable")),
    ("PRIMARY_KEY", ("primary_key",)),
)


def _value_for_extraction_row(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for k in keys:
        if k in row and row.get(k) is not None:
            return row.get(k), k
    return None, keys[0] if keys else ""


def normalize_extraction_columns(columns: list[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    if not isinstance(columns, list):
        return normalized
    for column in columns:
        if not isinstance(column, dict):
            continue
        is_nullable_raw = str(column.get("IS_NULLABLE", column.get("nullable", ""))).strip().upper()
        if is_nullable_raw in ("YES", "Y", "TRUE", "1"):
            nullable = "Y"
        elif is_nullable_raw in ("NO", "N", "FALSE", "0"):
            nullable = "N"
        else:
            nullable = _display_value(column.get("IS_NULLABLE", column.get("nullable")))

        checked_raw = str(column.get("is_checked", column.get("is_extract", "0"))).strip().lower()
        checked = checked_raw in ("1", "true", "yes", "y")

        normalized.append(
            {
                "name": _display_value(column.get("COLUMN_NAME", column.get("column_name"))),
                "type": _display_value(column.get("DATA_TYPE", column.get("data_type"))),
                "nullable": nullable,
                "char_max_len": _display_value(column.get("CHARACTER_MAXIMUM_LENGTH")),
                "num_precision": _display_value(column.get("NUMERIC_PRECISION")),
                "num_scale": _display_value(column.get("NUMERIC_SCALE")),
                "is_nullable_display": _display_value(
                    column.get("IS_NULLABLE", column.get("nullable"))
                ),
                "primary_key": _display_value(column.get("is_primary_key")),
                "checked": checked,
            }
        )
    return normalized


class ExtractionPageWidget(QWidget):
    """Extraction UI: source connections, config, tables, and columns."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        title = QLabel("ETL: Extraction")
        title.setStyleSheet(f"font-size: {LIST_PAGE_HEADER_TITLE_FONT_PX}px; font-weight: 600; color: #ffffff;")
        hl.addWidget(title)
        hl.addStretch()
        root.addWidget(header)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setChildrenCollapsible(False)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 6, 12)
        left_layout.setSpacing(10)

        conn_card = QFrame()
        conn_card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }"
        )
        conn_card_layout = QVBoxLayout(conn_card)
        conn_card_layout.setContentsMargins(12, 10, 12, 10)
        conn_hdr = QLabel("Source connections")
        conn_hdr.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 600;")
        conn_card_layout.addWidget(conn_hdr)
        self.extraction_connections = QListWidget()
        self.extraction_connections.setMinimumWidth(220)
        self.extraction_connections.setMaximumWidth(280)
        self.extraction_connections.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px;")
        conn_card_layout.addWidget(self.extraction_connections, 1)
        left_layout.addWidget(conn_card, 3)

        config_card = QFrame()
        config_card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }"
        )
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(12, 10, 12, 10)
        config_title = QLabel("Extraction config")
        config_title.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 600;")
        config_layout.addWidget(config_title)

        field_style = (
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; min-height: {FORM_SINGLELINE_FIELD_HEIGHT_PX}px;"
            + LINEEDIT_PLACEHOLDER_SUBSTYLE
        )
        form = QFormLayout()
        form.setSpacing(8)
        self.target_connection_dropdown = QComboBox()
        self.target_connection_dropdown.addItem("-- Select target connection --", None)
        self.target_connection_dropdown.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px;")
        self.fetch_size_input = QLineEdit("2000")
        self.fetch_size_input.setStyleSheet(field_style)
        self.commit_size_input = QLineEdit("2000")
        self.commit_size_input.setStyleSheet(field_style)
        form.addRow("Target connection", self.target_connection_dropdown)
        form.addRow("Fetch size", self.fetch_size_input)
        form.addRow("Chunk size", self.commit_size_input)
        config_layout.addLayout(form)

        self.import_tables_btn = QPushButton("Extract")
        self.import_tables_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self.import_tables_btn.setMinimumHeight(34)
        config_layout.addWidget(self.import_tables_btn)
        left_layout.addWidget(config_card, 2)

        body.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(12, 12, 12, 12)
        right_layout.setSpacing(8)

        self.extraction_title = QLabel("No connection selected")
        self.extraction_title.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX + 2}px; font-weight: 600;")
        right_layout.addWidget(self.extraction_title)

        vert = QSplitter(Qt.Orientation.Vertical)
        vert.setChildrenCollapsible(False)

        tables_card = QFrame()
        tables_card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }"
        )
        tables_layout = QVBoxLayout(tables_card)
        tables_layout.setContentsMargins(12, 10, 12, 10)
        tables_hdr_row = QHBoxLayout()
        tables_hdr = QLabel("Tables")
        tables_hdr.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 600;")
        tables_hdr_row.addWidget(tables_hdr)
        tables_hdr_row.addStretch()
        self.tables_filters_btn = QPushButton("Filters")
        self.tables_filters_btn.setCheckable(True)
        self.tables_filters_btn.setFixedWidth(80)
        self.tables_filters_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        tables_hdr_row.addWidget(self.tables_filters_btn)
        tables_layout.addLayout(tables_hdr_row)

        self.import_tables_table = QTableWidget(0, 4)
        self.import_tables_table.setHorizontalHeaderLabels(
            ["", "TABLE_NAME", "LAST_SCAN_DATE", "LAST_IMPORT_DATE"]
        )
        self.import_tables_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.import_tables_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.import_tables_table.setColumnWidth(0, 40)
        apply_data_table_appearance(
            self.import_tables_table,
            read_only=False,
            stretch_last_section=False,
            hide_vertical_header=True,
        )
        attach_table_copy_shortcut(self.import_tables_table)
        self.import_tables_table.setColumnWidth(0, 40)
        configure_data_table_header(self.import_tables_table, stretch_last=False)
        tables_layout.addWidget(self.import_tables_table, 1)

        table_actions = QHBoxLayout()
        table_actions.addStretch()
        self.tables_refresh_btn = QPushButton("Refresh")
        self.tables_refresh_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self.tables_remove_btn = QPushButton("Remove table")
        self.tables_remove_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self.tables_remove_btn.setEnabled(False)
        table_actions.addWidget(self.tables_refresh_btn)
        table_actions.addWidget(self.tables_remove_btn)
        tables_layout.addLayout(table_actions)
        vert.addWidget(tables_card)

        columns_card = QFrame()
        columns_card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }"
        )
        columns_layout = QVBoxLayout(columns_card)
        columns_layout.setContentsMargins(12, 10, 12, 10)
        columns_title_row = QHBoxLayout()
        self.extraction_columns_title = QLabel("Columns")
        self.extraction_columns_title.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 600;")
        columns_title_row.addWidget(self.extraction_columns_title)
        columns_title_row.addStretch()
        self.columns_filters_btn = QPushButton("Filters")
        self.columns_filters_btn.setCheckable(True)
        self.columns_filters_btn.setFixedWidth(80)
        self.columns_filters_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        columns_title_row.addWidget(self.columns_filters_btn)
        columns_layout.addLayout(columns_title_row)

        col_select = QHBoxLayout()
        self.columns_select_all_checkbox = QCheckBox("Select all")
        self.columns_select_all_checkbox.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px;")
        col_select.addWidget(self.columns_select_all_checkbox)
        col_select.addStretch()
        columns_layout.addLayout(col_select)

        self.extraction_columns_table = QTableWidget(0, 8)
        self.extraction_columns_table.setHorizontalHeaderLabels(
            [
                "",
                "COLUMN_NAME",
                "DATA_TYPE",
                "CHAR_MAX_LEN",
                "NUM_PRECISION",
                "NUM_SCALE",
                "IS_NULLABLE",
                "PRIMARY_KEY",
            ]
        )
        self.extraction_columns_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.extraction_columns_table.setColumnWidth(0, 40)
        apply_data_table_appearance(
            self.extraction_columns_table,
            read_only=False,
            stretch_last_section=False,
            hide_vertical_header=True,
        )
        attach_table_copy_shortcut(self.extraction_columns_table)
        self.extraction_columns_table.setColumnWidth(0, 40)
        configure_data_table_header(self.extraction_columns_table, stretch_last=False)
        columns_layout.addWidget(self.extraction_columns_table, 1)

        col_actions = QHBoxLayout()
        col_actions.addStretch()
        self.save_columns_btn = QPushButton("Save")
        self.save_columns_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        col_actions.addWidget(self.save_columns_btn)
        columns_layout.addLayout(col_actions)
        vert.addWidget(columns_card)

        vert.setSizes([400, 220])
        right_layout.addWidget(vert, 1)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        right_layout.addWidget(self._status_label)

        body.addWidget(right)
        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 4)
        root.addWidget(body, 1)


class EtlExtractionPage(QWidget):
    """Extraction page with API wiring."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._ui = ExtractionPageWidget()
        layout.addWidget(self._ui)

        self._connections: list[dict[str, Any]] = []
        self._current_connection: dict[str, Any] | None = None
        self._active_table_name: str | None = None
        self._columns_by_table: dict[str, list[dict[str, Any]]] = {}
        self._columns_rendering = False
        self._tables_source: list[dict[str, Any]] = []
        self._tables_filter_visible = False
        self._columns_filter_visible = False
        self._tables_filter_timer = QTimer(self)
        self._tables_filter_timer.setSingleShot(True)
        self._tables_filter_timer.setInterval(200)
        self._columns_filter_timer = QTimer(self)
        self._columns_filter_timer.setSingleShot(True)
        self._columns_filter_timer.setInterval(200)

        self._ui.extraction_connections.currentRowChanged.connect(self._on_connection_selected)
        self._ui.tables_filters_btn.toggled.connect(self._on_tables_filters_toggled)
        self._ui.columns_filters_btn.toggled.connect(self._on_columns_filters_toggled)
        self._tables_filter_timer.timeout.connect(self._refresh_tables_view)
        self._columns_filter_timer.timeout.connect(self._refresh_columns_view)
        self._ui.import_tables_table.cellClicked.connect(self._on_table_clicked)
        self._ui.tables_refresh_btn.clicked.connect(self._refresh_tables)
        self._ui.tables_remove_btn.clicked.connect(self._remove_table)
        self._ui.save_columns_btn.clicked.connect(self._save_columns)
        self._ui.columns_select_all_checkbox.stateChanged.connect(self._on_columns_select_all)
        self._ui.extraction_columns_table.itemChanged.connect(self._on_column_item_changed)
        self._ui.import_tables_btn.clicked.connect(self._start_extraction)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh()

    def refresh(self) -> None:
        self._load_connections()

    def _token(self) -> str | None:
        profile = get_user_profile() or {}
        return profile.get("token") or profile.get("accessToken")

    def _show_status(self, text: str, *, error: bool = False) -> None:
        if not text:
            self._ui._status_label.clear()
            return
        show_auto_hiding_message(self, self._ui._status_label, text, error=error)

    def _load_connections(self) -> None:
        result = api_get_all_connections(self._token())
        if not result.get("success"):
            self._connections = []
            self._populate_connections()
            self._show_status(str(result.get("message") or "Failed to load connections."), error=True)
            return
        self._connections = list(result.get("data") or [])
        self._populate_connections()

    def _populate_connections(self) -> None:
        ui = self._ui
        ui.extraction_connections.blockSignals(True)
        ui.extraction_connections.clear()
        ui.target_connection_dropdown.blockSignals(True)
        ui.target_connection_dropdown.clear()
        ui.target_connection_dropdown.addItem("-- Select target connection --", None)
        for conn in self._connections:
            name = (conn.get("connectionName") or "").strip() or "Unnamed connection"
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, conn)
            ui.extraction_connections.addItem(item)
            ui.target_connection_dropdown.addItem(name, conn)
        ui.extraction_connections.blockSignals(False)
        ui.target_connection_dropdown.blockSignals(False)
        if ui.extraction_connections.count() == 0:
            self._reset_workspace()

    def _reset_workspace(self) -> None:
        self._current_connection = None
        self._active_table_name = None
        self._columns_by_table = {}
        self._ui.extraction_title.setText("No connection selected")
        self._ui.import_tables_table.setRowCount(0)
        self._ui.extraction_columns_table.setRowCount(0)
        self._ui.extraction_columns_title.setText("Columns")
        self._ui.tables_remove_btn.setEnabled(False)
        self._sync_columns_select_all()

    def _connection_name(self) -> str:
        if not self._current_connection:
            return ""
        return str(self._current_connection.get("connectionName") or "").strip()

    def _connection_id(self) -> int | str | None:
        if not self._current_connection:
            return None
        for key in ("connectionId", "connectionID", "connection_id", "id"):
            value = self._current_connection.get(key)
            if value is not None and str(value).strip() != "":
                return value
        return None

    def _on_connection_selected(self, row: int) -> None:
        if row < 0:
            self._reset_workspace()
            return
        item = self._ui.extraction_connections.item(row)
        if item is None:
            return
        conn = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(conn, dict):
            return
        self._current_connection = conn
        self._active_table_name = None
        self._columns_by_table = {}
        self._ui.tables_remove_btn.setEnabled(False)
        self._ui.import_tables_table.setRowCount(0)
        self._ui.extraction_columns_table.setRowCount(0)
        self._ui.extraction_columns_title.setText("Columns")
        self._sync_columns_select_all()
        self._ui.extraction_title.setText(str(conn.get("connectionName") or ""))
        self._show_status("")
        self._load_tables()

    def _load_tables(self) -> None:
        conn_id = self._connection_id()
        if conn_id is None:
            return
        result = api_get_imported_tables(conn_id, token=self._token())
        if result.get("success"):
            self._render_tables(list(result.get("tables") or []))
            if self._ui.import_tables_table.rowCount() == 0:
                self._show_status("No tables found.")
            else:
                self._show_status("")
        else:
            self._render_tables([])
            self._show_status(str(result.get("message") or "Failed to load tables."), error=True)

    def _tables_data_row_offset(self) -> int:
        return data_row_offset(self._tables_filter_visible)

    def _columns_data_row_offset(self) -> int:
        return data_row_offset(self._columns_filter_visible)

    def _on_tables_filters_toggled(self, checked: bool) -> None:
        self._tables_filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self._ui.import_tables_table)
        self._refresh_tables_view()

    def _on_columns_filters_toggled(self, checked: bool) -> None:
        self._columns_filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self._ui.extraction_columns_table)
        self._refresh_columns_view()

    def _schedule_tables_filter_apply(self) -> None:
        if self._tables_filter_visible:
            self._tables_filter_timer.start()

    def _schedule_columns_filter_apply(self) -> None:
        if self._columns_filter_visible:
            self._columns_filter_timer.start()

    def _tables_filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._tables_source)
        if not self._tables_filter_visible:
            return rows
        return filter_dict_rows_by_column_edits(
            rows,
            self._ui.import_tables_table,
            list(_IMPORT_TABLES_DATA_SPEC),
            True,
            _value_for_extraction_row,
            _extraction_format_cell,
            filter_column_offset=1,
        )

    def _render_tables(self, rows: list[Any]) -> None:
        self._tables_source = [dict(r) for r in rows if isinstance(r, dict)]
        self._refresh_tables_view()

    def _refresh_tables_view(self) -> None:
        table = self._ui.import_tables_table
        saved = saved_filter_texts(table) if self._tables_filter_visible else None
        rows = self._tables_filtered_rows()
        offset = self._tables_data_row_offset()
        table.setSortingEnabled(False)
        table.setRowCount(offset + len(rows))
        if offset:
            install_filter_row(
                table,
                table.columnCount(),
                on_text_changed=self._schedule_tables_filter_apply,
            )
            if saved:
                restore_filter_texts(table, saved)
            w0 = table.cellWidget(0, 0)
            if isinstance(w0, QLineEdit):
                    w0.setEnabled(False)
                    w0.setPlaceholderText("")
        for row_idx, row in enumerate(rows):
            r_index = offset + row_idx
            check_item = QTableWidgetItem()
            check_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
            )
            check_item.setCheckState(Qt.CheckState.Unchecked)
            table.setItem(r_index, 0, check_item)
            for col_idx, (_, keys) in enumerate(_IMPORT_TABLES_DATA_SPEC, start=1):
                value, key_used = _value_for_extraction_row(row, keys)
                item = QTableWidgetItem(_extraction_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 1:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                table.setItem(r_index, col_idx, item)
        sync_vertical_header_labels(
            table, filter_visible=self._tables_filter_visible, data_row_count=len(rows)
        )
        resize_data_table_columns_to_content(
            table,
            list(_IMPORT_TABLES_DATA_SPEC),
            rows,
            _value_for_extraction_row,
            _extraction_format_cell,
            column_start_index=1,
        )
        table.setColumnWidth(0, 40)
        table.setSortingEnabled(not self._tables_filter_visible)

    def _refresh_tables(self) -> None:
        if self._connection_id() is None:
            QMessageBox.warning(self, "Missing", "Please select a source connection.")
            return
        self._active_table_name = None
        self._columns_by_table = {}
        self._ui.tables_remove_btn.setEnabled(False)
        self._ui.extraction_columns_table.setRowCount(0)
        self._ui.extraction_columns_title.setText("Columns")
        self._sync_columns_select_all()
        self._load_tables()

    def _on_table_clicked(self, row: int, column: int) -> None:
        if row < self._tables_data_row_offset() or column == 0:
            return
        name_item = self._ui.import_tables_table.item(row, 1)
        if not name_item:
            return
        table_name = name_item.text().strip()
        if not table_name or table_name == "--":
            return
        self._active_table_name = table_name
        self._ui.tables_remove_btn.setEnabled(True)
        self._load_columns(table_name)

    def _remove_table(self) -> None:
        name = self._connection_name()
        table_name = self._active_table_name
        if not name:
            QMessageBox.warning(self, "Missing", "Please select a source connection.")
            return
        if not table_name:
            QMessageBox.warning(self, "Missing", "Please click a table to remove.")
            return
        result = api_remove_imported_table(name, table_name, token=self._token())
        if result.get("success"):
            msg = str(result.get("message") or "Table removed.")
            self._show_status(msg, error=False)
            QMessageBox.information(self, "Success", msg)
            self._columns_by_table.pop(table_name, None)
            self._active_table_name = None
            self._ui.tables_remove_btn.setEnabled(False)
            self._ui.extraction_columns_table.setRowCount(0)
            self._ui.extraction_columns_title.setText("Columns")
            self._sync_columns_select_all()
            self._load_tables()
        else:
            msg = str(result.get("message") or "Failed to remove table.")
            self._show_status(msg, error=True)
            QMessageBox.warning(self, "Failed", msg)

    def _load_columns(self, table_name: str) -> None:
        name = self._connection_name()
        if not name:
            return
        self._show_status("")
        result = api_get_extracted_fields(name, table_name, token=self._token())
        if not result.get("success"):
            self._ui.extraction_columns_table.setRowCount(0)
            self._ui.extraction_columns_title.setText("Columns")
            self._sync_columns_select_all()
            self._show_status(str(result.get("message") or "Failed to load columns."), error=True)
            return
        self._render_columns(
            str(result.get("tableName") or table_name),
            normalize_extraction_columns(list(result.get("columns") or [])),
        )

    def _columns_filtered_rows(self) -> list[dict[str, Any]]:
        table_name = self._current_columns_table_name()
        rows = list(self._columns_by_table.get(table_name or "", []))
        if not self._columns_filter_visible:
            return rows
        return filter_dict_rows_by_column_edits(
            rows,
            self._ui.extraction_columns_table,
            list(_EXTRACTION_COLUMNS_DATA_SPEC),
            True,
            _value_for_extraction_row,
            _extraction_format_cell,
            filter_column_offset=1,
        )

    def _render_columns(self, table_name: str, columns: list[dict[str, Any]]) -> None:
        self._ui.extraction_columns_title.setText(f"Columns — {table_name}")
        self._columns_by_table[table_name] = columns
        self._refresh_columns_view()

    def _refresh_columns_view(self) -> None:
        table = self._ui.extraction_columns_table
        saved = saved_filter_texts(table) if self._columns_filter_visible else None
        rows = self._columns_filtered_rows()
        offset = self._columns_data_row_offset()
        self._columns_rendering = True
        table.setSortingEnabled(False)
        table.setRowCount(offset + len(rows))
        if offset:
            install_filter_row(
                table,
                table.columnCount(),
                on_text_changed=self._schedule_columns_filter_apply,
            )
            if saved:
                restore_filter_texts(table, saved)
            w0 = table.cellWidget(0, 0)
            if isinstance(w0, QLineEdit):
                w0.setEnabled(False)
                w0.setPlaceholderText("")
        for row_idx, column in enumerate(rows):
            r_index = offset + row_idx
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check_item.setCheckState(
                Qt.CheckState.Checked if column.get("checked") else Qt.CheckState.Unchecked
            )
            table.setItem(r_index, 0, check_item)
            for col_idx, (_, keys) in enumerate(_EXTRACTION_COLUMNS_DATA_SPEC, start=1):
                value, key_used = _value_for_extraction_row(column, keys)
                item = QTableWidgetItem(_extraction_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(r_index, col_idx, item)
        sync_vertical_header_labels(
            table, filter_visible=self._columns_filter_visible, data_row_count=len(rows)
        )
        resize_data_table_columns_to_content(
            table,
            list(_EXTRACTION_COLUMNS_DATA_SPEC),
            rows,
            _value_for_extraction_row,
            _extraction_format_cell,
            column_start_index=1,
        )
        table.setColumnWidth(0, 40)
        table.setSortingEnabled(not self._columns_filter_visible)
        self._columns_rendering = False
        self._sync_columns_select_all()

    def _current_columns_table_name(self) -> str | None:
        title = self._ui.extraction_columns_title.text().strip()
        prefix = "Columns — "
        if not title.startswith(prefix):
            return None
        name = title[len(prefix) :].strip()
        return name or None

    def _update_columns_cache_from_table(self) -> None:
        table_name = self._current_columns_table_name()
        if not table_name:
            return
        cached = self._columns_by_table.get(table_name, [])
        if not cached:
            return
        table = self._ui.extraction_columns_table
        offset = self._columns_data_row_offset()
        by_name: dict[str, bool] = {}
        for row in range(offset, table.rowCount()):
            check_item = table.item(row, 0)
            name_item = table.item(row, 1)
            if check_item and name_item:
                by_name[name_item.text().strip()] = check_item.checkState() == Qt.CheckState.Checked
        for col in cached:
            col_name = col.get("name")
            if col_name in by_name:
                col["checked"] = by_name[col_name]

    def _sync_columns_select_all(self) -> None:
        table = self._ui.extraction_columns_table
        self._ui.columns_select_all_checkbox.blockSignals(True)
        offset = self._columns_data_row_offset()
        if table.rowCount() <= offset:
            self._ui.columns_select_all_checkbox.setChecked(False)
        else:
            all_checked = all(
                table.item(row, 0) and table.item(row, 0).checkState() == Qt.CheckState.Checked
                for row in range(offset, table.rowCount())
                if table.item(row, 0)
            )
            self._ui.columns_select_all_checkbox.setChecked(all_checked)
        self._ui.columns_select_all_checkbox.blockSignals(False)

    def _on_columns_select_all(self, state: int) -> None:
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        table = self._ui.extraction_columns_table
        offset = self._columns_data_row_offset()
        self._columns_rendering = True
        for row in range(offset, table.rowCount()):
            check_item = table.item(row, 0)
            if check_item:
                check_item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._columns_rendering = False
        self._update_columns_cache_from_table()

    def _on_column_item_changed(self, item: QTableWidgetItem) -> None:
        if self._columns_rendering or item.column() != 0:
            return
        if item.row() < self._columns_data_row_offset():
            return
        self._update_columns_cache_from_table()
        self._sync_columns_select_all()

    def _save_columns(self) -> None:
        name = self._connection_name()
        table_name = self._current_columns_table_name()
        if not name:
            QMessageBox.warning(self, "Missing", "Please select a source connection.")
            return
        if not table_name:
            QMessageBox.warning(self, "Missing", "Please click a table first.")
            return

        self._update_columns_cache_from_table()
        table = self._ui.extraction_columns_table
        checked_columns: list[str] = []
        unchecked_columns: list[str] = []
        offset = self._columns_data_row_offset()
        for row in range(offset, table.rowCount()):
            check_item = table.item(row, 0)
            name_item = table.item(row, 1)
            if not check_item or not name_item:
                continue
            col_name = name_item.text().strip()
            if not col_name or col_name == "--":
                continue
            if check_item.checkState() == Qt.CheckState.Checked:
                checked_columns.append(col_name)
            else:
                unchecked_columns.append(col_name)

        result = api_update_extracted_fields(
            name,
            table_name,
            checked_columns,
            unchecked_columns,
            token=self._token(),
        )
        if result.get("success"):
            msg = str(result.get("message") or "Columns updated.")
            self._show_status(msg, error=False)
            QMessageBox.information(self, "Success", msg)
        else:
            msg = str(result.get("message") or "Failed to update columns.")
            self._show_status(msg, error=True)
            QMessageBox.warning(self, "Failed", msg)

    def _checked_tables(self) -> list[str]:
        table = self._ui.import_tables_table
        selected: list[str] = []
        for row in range(table.rowCount()):
            check_item = table.item(row, 0)
            name_item = table.item(row, 1)
            if not check_item or not name_item:
                continue
            if check_item.checkState() == Qt.CheckState.Checked:
                table_name = name_item.text().strip()
                if table_name and table_name != "--":
                    selected.append(table_name)
        return selected

    def _start_extraction(self) -> None:
        if not self._current_connection:
            QMessageBox.warning(self, "Missing", "Please select a source connection.")
            return
        target_conn = self._ui.target_connection_dropdown.currentData()
        if not isinstance(target_conn, dict):
            QMessageBox.warning(self, "Missing", "Please select a target connection.")
            return

        checked_tables = self._checked_tables()
        if not checked_tables:
            QMessageBox.warning(self, "Missing", "Please select at least one table to extract.")
            return

        fetch_size = self._ui.fetch_size_input.text().strip()
        commit_size = self._ui.commit_size_input.text().strip()
        if not fetch_size or not commit_size:
            QMessageBox.warning(self, "Missing", "Please enter fetch and chunk size.")
            return

        self._update_columns_cache_from_table()
        src_name = self._connection_name()
        tgt_name = str(target_conn.get("connectionName") or "").strip()

        for table_name in checked_tables:
            normalized = self._columns_by_table.get(table_name)
            if not normalized:
                result = api_get_extracted_fields(src_name, table_name, token=self._token())
                if not result.get("success"):
                    QMessageBox.warning(
                        self,
                        "Failed",
                        f"Could not load columns for table '{table_name}'.",
                    )
                    return
                normalized = normalize_extraction_columns(list(result.get("columns") or []))
                self._columns_by_table[table_name] = normalized

            selected_cols = [
                col
                for col in normalized
                if isinstance(col, dict) and col.get("checked")
            ]
            if not selected_cols:
                QMessageBox.warning(
                    self,
                    "Missing",
                    f"No columns selected for table '{table_name}'.",
                )
                return

        job_payload = {
            "connection_name_src": src_name,
            "connection_name_tgt": tgt_name,
            "src_fetch_size": fetch_size,
            "tgt_commit_size": commit_size,
            "tableName": list(checked_tables),
        }
        result = api_start_etl_job(job_payload, token=self._token())
        if result.get("success"):
            QMessageBox.information(self, "Success", str(result.get("message") or "Job queued."))
            self._show_status(str(result.get("message") or ""), error=False)
        else:
            QMessageBox.warning(
                self,
                "Failed",
                str(result.get("message") or "Failed to start extraction job."),
            )
