"""ETL: Import Metadata — import scanned table column metadata."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFontMetrics, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.etl.scan_connection.scan_connection import (
    _CONNECTION_COLUMNS,
    _SCAN_LOG_TAB_HEADER_HEIGHT_PX,
    _SCAN_LOG_TAB_HEADER_LAYOUT_MARGINS,
    _SCAN_LOG_TAB_HEADER_LAYOUT_SPACING,
    _SCAN_LOG_TAB_HEADER_STYLESHEET,
    _connection_id,
    _connection_name,
    _extract_table_name,
    _prepare_scan_header_button,
    _value_for_column,
)
from core.api import (
    api_check_import_metadata_fields,
    api_get_all_connections,
    api_get_metadata_table_columns,
    api_get_metadata_tables,
    api_import_metadata_tables,
)
from core.app_preferences import latest_datetime_display
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
    restore_filter_texts,
    saved_filter_texts,
    sync_vertical_header_labels,
)
from ui.form_page_styles import (
    APP_FONT_SIZE_PX,
    FORM_PAGE_FONT_SIZE_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    LIST_PAGE_HEADER_TITLE_FONT_PX,
    placeholder_enter,
)
from ui.theme import Theme

_SCANNED_TABLES_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("TABLE_NAME", ("TABLE_NAME", "tableName", "name")),
    ("LAST_SCAN_DATE", ("LAST_SCAN_DATE", "lastScanDate", "last_scan_date")),
    ("LAST_IMPORT_DATE", ("LAST_IMPORT_DATE", "lastImportDate", "last_import_date")),
    ("IMPORT_STATUS", ("IMPORT_STATUS", "importStatus", "import_status")),
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


def _build_import_table_panel(
    header_title: str,
    table: QTableWidget,
    *,
    filters_btn: QPushButton | None = None,
    search_input: QLineEdit | None = None,
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
    if search_input is not None:
        search_input.setMinimumWidth(160)
        search_input.setMaximumWidth(320)
        hl.addWidget(search_input)
    if filters_btn is not None:
        filters_btn.setCheckable(True)
        filters_btn.setFixedWidth(80)
        filters_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hl.addWidget(filters_btn)
    layout.addWidget(bar)
    layout.addWidget(table, 1)
    return panel


def _build_import_main_panel(
    *,
    header_title: str,
    last_scan_label: QLabel,
    header_buttons: tuple[QPushButton, ...],
    content: QWidget,
) -> QWidget:
    """Import tables card: navy toolbar (title + last scan + actions), no subtitle."""
    panel = QWidget()
    panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    root = QVBoxLayout(panel)
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
    last_scan_label.setStyleSheet(
        f"font-size: {APP_FONT_SIZE_PX}px; color: {Theme.PANEL_TEXT_BRIGHT}; font-weight: 400;"
    )
    hl.addWidget(last_scan_label)
    for btn in header_buttons:
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        hl.addWidget(btn)
    root.addWidget(header)

    content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    root.addWidget(content, 1)
    return panel


def _display_value(value: Any) -> str:
    return "--" if value is None or value == "" else str(value)


def _scanned_row_as_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    name = _extract_table_name(row)
    return {"TABLE_NAME": name} if name else {}


def _scanned_cell_texts(row_data: dict[str, Any]) -> tuple[str, str, str, str]:
    table_name = _extract_table_name(row_data)
    return (
        table_name,
        format_data_table_cell(
            row_data.get("LAST_SCAN_DATE") or row_data.get("lastScanDate"),
            "LAST_SCAN_DATE",
            ("LAST_SCAN_DATE", "lastScanDate", "last_scan_date"),
        ),
        format_data_table_cell(
            row_data.get("LAST_IMPORT_DATE") or row_data.get("lastImportDate"),
            "LAST_IMPORT_DATE",
            ("LAST_IMPORT_DATE", "lastImportDate", "last_import_date"),
        ),
        format_data_table_cell(
            row_data.get("IMPORT_STATUS") or row_data.get("importStatus"),
            "IMPORT_STATUS",
            ("IMPORT_STATUS", "importStatus", "import_status"),
        ),
    )


def _configure_scanned_table_header(table: QTableWidget) -> None:
    hh = table.horizontalHeader()
    hh.setStretchLastSection(False)
    table.setColumnWidth(0, 40)
    for col in range(1, table.columnCount()):
        hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
    hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)


def _resize_scanned_table_columns(table: QTableWidget, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    fm_cell = QFontMetrics(table.font())
    fm_header = QFontMetrics(table.horizontalHeader().font())
    for col_idx, (header, keys) in enumerate(_SCANNED_TABLES_COLUMN_SPEC, start=1):
        width = fm_header.horizontalAdvance(header) + 18
        for row in rows:
            value, key_used = _value_for_column(row, keys)
            text = format_data_table_cell(value, key_used, keys)
            width = max(width, fm_cell.horizontalAdvance(text) + 12)
        table.setColumnWidth(col_idx, max(MIN_DATA_COL_WIDTH_PX, width))


def _row_last_scan_raw(row: Any) -> Any:
    if not isinstance(row, dict):
        return None
    for key in ("LAST_SCAN_DATE", "lastScanDate", "last_scan_date"):
        value = row.get(key)
        if not is_blank_display_value(value):
            return value
    return None


def _latest_last_scan_display(tables: list[Any], *, api_last_scan: str = "") -> str:
    """Latest scan timestamp for the connection (payload field or max table LAST_SCAN_DATE)."""
    candidates: list[Any] = []
    if api_last_scan.strip():
        candidates.append(api_last_scan.strip())
    for row in tables:
        raw = _row_last_scan_raw(row)
        if raw is not None:
            candidates.append(raw)
    return latest_datetime_display(*candidates)


class _ImportFieldMismatchDialog(QDialog):
    """Shows FIELD MISMATCH rows; Yes proceeds with import, No cancels."""

    def __init__(
        self,
        parent: QWidget | None,
        *,
        message: str,
        rows: list[dict[str, Any]],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Field mismatch")
        self.setMinimumSize(480, 320)
        self.setStyleSheet("QDialog { background: #ffffff; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        intro = QLabel(
            message.strip()
            or "Column definitions do not match. Review the details below."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: {Theme.TEXT_PRIMARY};"
        )
        layout.addWidget(intro)

        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Column name", "Table"])
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        apply_data_table_appearance(table, read_only=True, stretch_last_section=True)
        attach_table_copy_shortcut(table)

        for row in rows:
            if not isinstance(row, dict):
                continue
            col_name = str(
                row.get("column_name") or row.get("columnName") or row.get("COLUMN_NAME") or ""
            ).strip()
            table_name = str(
                row.get("msg") or row.get("table") or row.get("tableName") or row.get("TABLE_NAME") or ""
            ).strip()
            r_index = table.rowCount()
            table.insertRow(r_index)
            for c, text in enumerate((col_name, table_name)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(r_index, c, item)

        if table.rowCount() == 0:
            table.setRowCount(1)
            for c, text in enumerate(("--", "--")):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(0, c, item)

        layout.addWidget(table, 1)

        prompt = QLabel("Do you want to import anyway?")
        prompt.setStyleSheet(
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: {Theme.TEXT_SECONDARY};"
        )
        layout.addWidget(prompt)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


def _build_import_tables_widget() -> QTableWidget:
    table = QTableWidget(0, 5)
    table.setHorizontalHeaderLabels(
        ["", "TABLE_NAME", "LAST_SCAN_DATE", "LAST_IMPORT_DATE", "IMPORT_STATUS"]
    )
    table.setColumnWidth(0, 40)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    apply_data_table_appearance(
        table,
        read_only=False,
        stretch_last_section=False,
        hide_vertical_header=False,
    )
    attach_table_copy_shortcut(table)
    _configure_scanned_table_header(table)
    return table


class ImportMetadataPageWidget(QWidget):
    """Import metadata UI (connections | import tables + column details)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        page_header = QFrame()
        page_header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        page_header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        page_hl = QHBoxLayout(page_header)
        page_hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        page_hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        page_title = QLabel("ETL: Import Metadata")
        page_title.setStyleSheet(
            f"font-size: {LIST_PAGE_HEADER_TITLE_FONT_PX}px; font-weight: 600; color: #ffffff;"
        )
        page_hl.addWidget(page_title)
        page_hl.addStretch()
        self.connections_filters_btn = QPushButton("Filters")
        self.connections_filters_btn.setCheckable(True)
        self.connections_filters_btn.setFixedWidth(80)
        self.connections_filters_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setFixedWidth(100)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        page_hl.addWidget(self.connections_filters_btn)
        page_hl.addWidget(self.refresh_btn)
        root.addWidget(page_header)

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
        self.connections_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.connections_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        apply_data_table_appearance(
            self.connections_table,
            read_only=True,
            stretch_last_section=False,
        )
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
        self.empty_hint = QLabel("Select a connection from the list to import metadata.")
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
        card.setObjectName("importMetadataCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card.setStyleSheet(
            "#importMetadataCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 12px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 12)
        card_layout.setSpacing(10)

        self.refresh_tables_btn = QPushButton("Refresh")
        self.import_btn = QPushButton("Import")
        _prepare_scan_header_button(self.refresh_tables_btn, width_px=88)
        _prepare_scan_header_button(self.import_btn, width_px=80)

        self.last_scan_label = QLabel("Last scanned: --")
        self.metadata_search_input = QLineEdit()
        self.metadata_search_input.setPlaceholderText(placeholder_enter("table name to filter"))
        self.metadata_search_input.setFixedHeight(22)
        self.metadata_search_input.setStyleSheet(
            "QLineEdit { background: #ffffff; border: 1px solid #cbd5e1; border-radius: 4px;"
            f" padding: 2px 8px; font-size: {APP_FONT_SIZE_PX}px; color: #0f172a; }}"
        )
        self.select_all_checkbox = QCheckBox("Select all")
        self.select_all_checkbox.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px;")
        self.scanned_tables_filters_btn = QPushButton("Filters")
        self.columns_filters_btn = QPushButton("Filters")

        self.metadata_tables_table = _build_import_tables_widget()
        self.metadata_table_info_table = QTableWidget(0, len(_COLUMN_DETAIL_SPEC))
        self.metadata_table_info_table.setHorizontalHeaderLabels(
            [h for h, _ in _COLUMN_DETAIL_SPEC]
        )
        self.metadata_table_info_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.metadata_table_info_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        apply_data_table_appearance(
            self.metadata_table_info_table,
            read_only=True,
            stretch_last_section=False,
        )
        attach_table_copy_shortcut(self.metadata_table_info_table)

        import_split = QSplitter(Qt.Orientation.Vertical)
        import_split.setChildrenCollapsible(False)
        import_split.setHandleWidth(6)
        import_split.addWidget(
            _build_import_table_panel(
                "Scanned tables",
                self.metadata_tables_table,
                filters_btn=self.scanned_tables_filters_btn,
                search_input=self.metadata_search_input,
            )
        )
        import_split.addWidget(
            _build_import_table_panel(
                "Column details",
                self.metadata_table_info_table,
                filters_btn=self.columns_filters_btn,
            )
        )
        import_split.setStretchFactor(0, 2)
        import_split.setStretchFactor(1, 1)
        import_split.setSizes([320, 200])

        import_content = QWidget()
        import_content_layout = QVBoxLayout(import_content)
        import_content_layout.setContentsMargins(0, 0, 0, 0)
        import_content_layout.setSpacing(8)
        select_row = QHBoxLayout()
        select_row.addWidget(self.select_all_checkbox)
        select_row.addStretch()
        import_content_layout.addLayout(select_row)
        import_content_layout.addWidget(import_split, 1)

        import_panel = _build_import_main_panel(
            header_title="Import tables",
            last_scan_label=self.last_scan_label,
            header_buttons=(self.refresh_tables_btn, self.import_btn),
            content=import_content,
        )
        card_layout.addWidget(import_panel, 1)
        details_outer.addWidget(card, 1)
        self.detail_stack.addWidget(details_page)

        right_layout.addWidget(self.detail_stack, 1)
        self.set_right_panel_enabled(False)

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

    def show_empty_detail(self) -> None:
        self.detail_stack.setCurrentIndex(0)
        self.set_import_controls_enabled(False)

    def show_detail_panel(self) -> None:
        self.detail_stack.setCurrentIndex(1)
        self.set_import_controls_enabled(True)

    def set_right_panel_enabled(self, enabled: bool) -> None:
        if enabled:
            self.show_detail_panel()
        else:
            self.show_empty_detail()

    def set_import_controls_enabled(self, enabled: bool) -> None:
        self.refresh_tables_btn.setEnabled(enabled)
        self.import_btn.setEnabled(enabled)
        self.metadata_search_input.setEnabled(enabled)
        self.select_all_checkbox.setEnabled(enabled)
        self.scanned_tables_filters_btn.setEnabled(enabled)
        self.columns_filters_btn.setEnabled(enabled)
        self.metadata_tables_table.setEnabled(enabled)
        self.metadata_table_info_table.setEnabled(enabled)


class EtlImportMetadataPage(QWidget):
    """Import metadata page with API wiring."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._ui = ImportMetadataPageWidget()
        layout.addWidget(self._ui)

        self._connections: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._restore_connection_name: str | None = None
        self._tables_cache: list[Any] = []
        self._scanned_tables_source: list[dict[str, Any]] = []
        self._selected_tables: set[str] = set()
        self._rendering = False
        self._connections_filter_visible = False
        self._tables_filter_visible = False
        self._columns_filter_visible = False
        self._columns_source: list[dict[str, str]] = []
        self._connections_filter_timer = QTimer(self)
        self._connections_filter_timer.setSingleShot(True)
        self._connections_filter_timer.setInterval(200)
        self._tables_filter_timer = QTimer(self)
        self._tables_filter_timer.setSingleShot(True)
        self._tables_filter_timer.setInterval(200)
        self._columns_filter_timer = QTimer(self)
        self._columns_filter_timer.setSingleShot(True)
        self._columns_filter_timer.setInterval(200)

        self._ui.refresh_btn.clicked.connect(self.refresh)
        self._ui.connections_filters_btn.toggled.connect(self._on_connections_filters_toggled)
        self._connections_filter_timer.timeout.connect(self._refresh_connections_table_view)
        self._ui.connections_table.itemSelectionChanged.connect(self._on_selection_changed)
        self._ui.metadata_search_input.textChanged.connect(self._on_tables_search_changed)
        self._ui.refresh_tables_btn.clicked.connect(self._fetch_tables)
        self._ui.import_btn.clicked.connect(self._import_tables)
        self._ui.select_all_checkbox.stateChanged.connect(self._on_select_all_changed)
        self._ui.metadata_tables_table.itemChanged.connect(self._on_table_item_changed)
        self._ui.metadata_tables_table.cellClicked.connect(self._on_table_cell_clicked)
        self._ui.metadata_tables_table.itemDoubleClicked.connect(self._on_scanned_table_double_clicked)
        self._ui.scanned_tables_filters_btn.toggled.connect(self._on_scanned_tables_filters_toggled)
        self._ui.columns_filters_btn.toggled.connect(self._on_columns_filters_toggled)
        self._tables_filter_timer.timeout.connect(self._refresh_scanned_tables_view)
        self._columns_filter_timer.timeout.connect(self._refresh_columns_view)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh()

    def refresh(self) -> None:
        if self._current:
            self._restore_connection_name = _connection_name(self._current)
        self._load_connections()

    def _token(self) -> str | None:
        profile = get_user_profile() or {}
        return profile.get("token") or profile.get("accessToken")

    def _show_message(self, text: str, *, error: bool = False) -> None:
        show_auto_hiding_message(self, self._ui.message_label, text, error=error)

    def _load_connections(self) -> None:
        result = api_get_all_connections(self._token())
        if not result.get("success"):
            self._connections = []
            self._populate_connections()
            self._show_message(str(result.get("message") or "Failed to load connections."), error=True)
            return
        self._connections = list(result.get("data") or [])
        self._populate_connections()
        show_auto_hiding_message(self, self._ui.message_label, "", error=False)

    def _populate_connections(self) -> None:
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

    def _rebind_current_connection(self) -> None:
        self._current = self._selected_connection()

    def _on_selection_changed(self) -> None:
        self._rebind_current_connection()
        if self._current is None:
            self._reset_right_panel()
            return
        self._apply_connection_selection()

    def _reset_right_panel(self) -> None:
        self._tables_cache = []
        self._scanned_tables_source = []
        self._selected_tables = set()
        self._columns_source = []
        self._tables_filter_visible = False
        self._columns_filter_visible = False
        self._ui.scanned_tables_filters_btn.setChecked(False)
        self._ui.columns_filters_btn.setChecked(False)
        self._ui.metadata_search_input.clear()
        self._ui.metadata_tables_table.setRowCount(0)
        self._ui.metadata_table_info_table.setRowCount(0)
        self._ui.last_scan_label.setText("Last scanned: --")
        self._ui.set_right_panel_enabled(False)

    def _apply_connection_selection(self) -> None:
        if not self._current:
            return
        self._ui.set_right_panel_enabled(True)
        self._tables_cache = []
        self._scanned_tables_source = []
        self._selected_tables = set()
        self._fetch_tables()

    def _fetch_tables(self) -> None:
        conn_id = _connection_id(self._current)
        if conn_id is None:
            self._show_message("Select a connection first.", error=True)
            return
        result = api_get_metadata_tables(conn_id, token=self._token())
        if not result.get("success"):
            self._tables_cache = []
            self._refresh_scanned_tables_view()
            self._show_message(str(result.get("message") or "Failed to load tables."), error=True)
            return
        self._tables_cache = list(result.get("tables") or [])
        self._selected_tables = set()
        last_scanned = _latest_last_scan_display(
            self._tables_cache,
            api_last_scan=str(result.get("lastScanDate") or ""),
        )
        self._ui.last_scan_label.setText(f"Last scanned: {last_scanned}")
        self._ui.metadata_table_info_table.setRowCount(0)
        self._refresh_scanned_tables_view()
        show_auto_hiding_message(self, self._ui.message_label, "", error=False)

    def _tables_data_row_offset(self) -> int:
        return data_row_offset(self._tables_filter_visible)

    def _is_scanned_data_row(self, table_row: int) -> bool:
        return table_row >= self._tables_data_row_offset()

    def _get_scanned_row_at(self, table_row: int) -> dict[str, Any] | None:
        if not self._is_scanned_data_row(table_row):
            return None
        name_item = self._ui.metadata_tables_table.item(table_row, 1)
        if name_item is None:
            return None
        row = name_item.data(Qt.ItemDataRole.UserRole)
        return row if isinstance(row, dict) else None

    def _open_scanned_row_details(self, table_row: int) -> None:
        row = self._get_scanned_row_at(table_row)
        if not row:
            return
        table_name = _extract_table_name(row)
        if table_name:
            self._load_table_info(table_name)

    def _on_scanned_table_double_clicked(self, item: QTableWidgetItem) -> None:
        if not self._is_scanned_data_row(item.row()):
            return
        self._open_scanned_row_details(item.row())

    def _on_tables_search_changed(self, _text: str = "") -> None:
        self._refresh_scanned_tables_view()

    def _scanned_rows_after_search(self) -> list[Any]:
        query = self._ui.metadata_search_input.text().strip().lower()
        if not query:
            return list(self._tables_cache)
        return [
            row
            for row in self._tables_cache
            if query in _extract_table_name(row).lower()
        ]

    def _filter_scanned_rows_by_column_texts(
        self,
        rows: list[Any],
        filter_texts: list[str],
    ) -> list[Any]:
        filtered: list[Any] = []
        for row in rows:
            row_data = _scanned_row_as_dict(row)
            if not _extract_table_name(row_data):
                continue
            cells = _scanned_cell_texts(row_data)
            skip = False
            for col_idx, text in enumerate(cells, start=1):
                q = (
                    filter_texts[col_idx].strip().lower()
                    if col_idx < len(filter_texts)
                    else ""
                )
                if q and q not in text.lower():
                    skip = True
                    break
            if not skip:
                filtered.append(row)
        return filtered

    def _schedule_scanned_column_filter_apply(self) -> None:
        if self._tables_filter_visible:
            self._tables_filter_timer.start()

    def _on_scanned_tables_filters_toggled(self, checked: bool) -> None:
        self._tables_filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self._ui.metadata_tables_table)
        self._refresh_scanned_tables_view()

    def _refresh_scanned_tables_view(self) -> None:
        saved_filters = (
            saved_filter_texts(self._ui.metadata_tables_table)
            if self._tables_filter_visible
            else []
        )
        rows = self._scanned_rows_after_search()
        if self._tables_filter_visible:
            rows = self._filter_scanned_rows_by_column_texts(rows, saved_filters)
        self._render_tables(rows, saved_filter_texts=saved_filters)

    def _render_tables(
        self,
        rows: list[Any],
        *,
        saved_filter_texts: list[str] | None = None,
    ) -> None:
        self._rendering = True
        table = self._ui.metadata_tables_table
        dict_rows = [_scanned_row_as_dict(row) for row in rows]
        dict_rows = [r for r in dict_rows if _extract_table_name(r)]
        self._scanned_tables_source = dict_rows
        offset = self._tables_data_row_offset()
        table.setSortingEnabled(False)
        table.setRowCount(offset + len(dict_rows))
        if offset:
            install_filter_row(
                table,
                table.columnCount(),
                on_text_changed=self._schedule_scanned_column_filter_apply,
            )
            if saved_filter_texts:
                restore_filter_texts(self._ui.metadata_tables_table, saved_filter_texts)
            w0 = table.cellWidget(0, 0)
            if isinstance(w0, QLineEdit):
                w0.setEnabled(False)
                w0.setPlaceholderText("")
        for row_idx, row_data in enumerate(dict_rows):
            table_name, scan_txt, import_txt, status_txt = _scanned_cell_texts(row_data)
            r_index = offset + row_idx
            check_item = QTableWidgetItem()
            check_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            check_item.setCheckState(
                Qt.CheckState.Checked
                if table_name in self._selected_tables
                else Qt.CheckState.Unchecked
            )
            table.setItem(r_index, 0, check_item)
            for col, text in enumerate(
                (table_name, scan_txt, import_txt, status_txt),
                start=1,
            ):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 1:
                    item.setData(Qt.ItemDataRole.UserRole, row_data)
                table.setItem(r_index, col, item)
        sync_vertical_header_labels(
            table, filter_visible=self._tables_filter_visible, data_row_count=len(dict_rows)
        )
        _resize_scanned_table_columns(table, dict_rows)
        table.setSortingEnabled(not self._tables_filter_visible)
        self._rendering = False
        self._sync_select_all()

    def _import_tables(self) -> None:
        conn_id = _connection_id(self._current)
        if conn_id is None:
            QMessageBox.warning(self, "Missing", "Select a connection first.")
            return
        table_names = sorted(self._selected_tables)
        if not table_names:
            QMessageBox.warning(self, "Missing", "Select at least one table.")
            return

        check = api_check_import_metadata_fields(conn_id, table_names, token=self._token())
        if check.get("success"):
            self._run_import_tables(conn_id, table_names)
            return

        if check.get("field_mismatch"):
            dlg = _ImportFieldMismatchDialog(
                self,
                message=str(check.get("message") or "FIELD MISMATCH"),
                rows=list(check.get("data") or []),
            )
            if dlg.exec() != QDialog.DialogCode.Accepted:
                self._show_message(
                    str(check.get("message") or "Import cancelled."),
                    error=True,
                )
                return
            self._run_import_tables(conn_id, table_names)
            return

        self._show_message(str(check.get("message") or "Field check failed."), error=True)

    def _run_import_tables(self, conn_id: int | str, table_names: list[str]) -> None:
        result = api_import_metadata_tables(conn_id, table_names, token=self._token())
        if result.get("success"):
            QMessageBox.information(
                self,
                "Success",
                str(result.get("message") or "Table imported successfully."),
            )
            show_auto_hiding_message(self, self._ui.message_label, "", error=False)
            self._fetch_tables()
        else:
            self._show_message(str(result.get("message") or "Import failed."), error=True)

    def _on_select_all_changed(self, state: int) -> None:
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        table = self._ui.metadata_tables_table
        offset = self._tables_data_row_offset()
        self._rendering = True
        for row in range(offset, table.rowCount()):
            name_item = table.item(row, 1)
            check_item = table.item(row, 0)
            if not name_item or not check_item:
                continue
            table_name = name_item.text()
            check_item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            if checked:
                self._selected_tables.add(table_name)
            else:
                self._selected_tables.discard(table_name)
        self._rendering = False

    def _on_table_item_changed(self, item: QTableWidgetItem) -> None:
        if self._rendering or item.column() != 0:
            return
        if item.row() < self._tables_data_row_offset():
            return
        name_item = self._ui.metadata_tables_table.item(item.row(), 1)
        if not name_item:
            return
        table_name = name_item.text()
        if item.checkState() == Qt.CheckState.Checked:
            self._selected_tables.add(table_name)
        else:
            self._selected_tables.discard(table_name)
        self._sync_select_all()

    def _on_table_cell_clicked(self, row: int, column: int) -> None:
        if row < self._tables_data_row_offset() or column == 0:
            return
        self._open_scanned_row_details(row)

    def _load_table_info(self, table_name: str) -> None:
        conn_id = _connection_id(self._current)
        if conn_id is None:
            QMessageBox.warning(self, "Missing", "Select a connection first.")
            return
        result = api_get_metadata_table_columns(conn_id, table_name, token=self._token())
        if not result.get("success"):
            QMessageBox.warning(
                self, "Failed", str(result.get("message") or "Could not load table info.")
            )
            return
        self._build_columns_source(
            str(result.get("tableName") or table_name),
            list(result.get("columns") or []),
        )
        self._refresh_columns_view()

    def _build_columns_source(self, table_name: str, columns: list[Any]) -> None:
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

    def _schedule_columns_filter_apply(self) -> None:
        if self._columns_filter_visible:
            self._columns_filter_timer.start()

    def _on_columns_filters_toggled(self, checked: bool) -> None:
        self._columns_filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self._ui.metadata_table_info_table)
        self._refresh_columns_view()

    def _columns_filtered_rows(self) -> list[dict[str, str]]:
        rows = list(self._columns_source)
        if not self._columns_filter_visible:
            return rows
        return filter_dict_rows_by_column_edits(
            rows,
            self._ui.metadata_table_info_table,
            list(_COLUMN_DETAIL_SPEC),
            True,
            _value_for_column,
            format_data_table_cell,
        )

    def _refresh_columns_view(self) -> None:
        saved = (
            saved_filter_texts(self._ui.metadata_table_info_table)
            if self._columns_filter_visible
            else None
        )
        render_dict_rows_table(
            self._ui.metadata_table_info_table,
            self._columns_filtered_rows(),
            list(_COLUMN_DETAIL_SPEC),
            filter_visible=self._columns_filter_visible,
            value_for_column=_value_for_column,
            format_cell=format_data_table_cell,
            on_filter_text_changed=self._schedule_columns_filter_apply,
            saved_filter_texts_list=saved,
        )

    def _sync_select_all(self) -> None:
        table = self._ui.metadata_tables_table
        offset = self._tables_data_row_offset()
        self._ui.select_all_checkbox.blockSignals(True)
        data_rows = table.rowCount() - offset
        if data_rows <= 0:
            self._ui.select_all_checkbox.setChecked(False)
        else:
            all_checked = all(
                table.item(row, 0) and table.item(row, 0).checkState() == Qt.CheckState.Checked
                for row in range(offset, table.rowCount())
                if table.item(row, 0)
            )
            self._ui.select_all_checkbox.setChecked(all_checked)
        self._ui.select_all_checkbox.blockSignals(False)
