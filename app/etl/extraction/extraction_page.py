"""ETL: Extraction — select imported tables/columns and run extraction jobs."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QPoint, Qt, QTimer
from PySide6.QtGui import QCursor, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QDialog,
    QInputDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.etl.scan_connection.scan_connection import (
    _TAB_STYLESHEET,
    _build_scan_operation_tab,
    _build_scanned_sub_table_panel,
    _connection_id,
    _connection_name,
    _prepare_scan_header_button,
    _value_for_column,
)

from app.etl.extraction.extraction_add_table_dialog import ExtractionAddTableDialog
from app.etl.extraction.group_table_where_clause_dialog import GroupTableWhereClauseDialog
from app.etl.extraction.extract_group_add_tables_dialog import (
    ExtractGroupAddTablesDialog,
    group_table_names,
)
from app.etl.extraction.extract_group_dialog import ExtractGroupDialog
from app.etl.extraction.extract_target_dialog import ExtractTargetDialog
from app.etl.widgets.etl_connection_picker import EtlConnectionHeaderPicker
from core.api import (
    api_add_extract_group_tables,
    api_add_group_table_where_clause,
    api_create_extract_group,
    api_delete_extract_group,
    api_delete_extract_group_table,
    api_create_extraction_table,
    api_delete_extraction_table,
    api_get_extracted_fields,
    api_get_extraction_by_id,
    api_get_extraction_tables_by_connection,
    api_get_extract_groups,
    api_get_imported_tables,
    api_start_etl_job,
    api_start_group_extraction_job,
    api_update_extract_group,
    api_update_extracted_fields,
    api_update_group_tgt_table_name,
    api_update_extraction_target_table,
    api_update_extraction_where_clause,
)
from core.etl_connection_context import get_etl_connection_context
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
    render_dict_rows_table,
    restore_filter_texts,
    saved_filter_texts,
    sync_vertical_header_labels,
)
from ui.styles import CONTEXT_MENU_STYLESHEET
from ui.form_page_styles import (
    FORM_PAGE_FONT_SIZE_PX,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
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
    ("ID", ("id", "ID")),
    ("TABLE_NAME", ("tableName", "TABLE_NAME", "table_name", "name")),
    ("CONNECTION_ID", ("connectionName", "connectionId", "connection_id")),
    ("IMPORT_STATUS", ("importStatus", "import_status", "IMPORT_STATUS")),
    ("CREATED_AT", ("createdAt", "created_at", "CREATED_AT")),
    ("TGT_TABLE_NAME", ("targetTableName", "TGT_TABLE_NAME", "tgtTableName", "tgt_table_name")),
    ("WHERE_CLAUSE", ("whereClause", "where_clause", "WHERE_CLAUSE")),
)

_TGT_NAME_KEYS: tuple[str, ...] = (
    "TGT_TABLE_NAME",
    "tgtTableName",
    "tgt_table_name",
    "newTableName",
    "targetTableName",
    "target_table_name",
)

_TABLES_TAB_SUBTITLE = (
    "Extraction tables for the selected connection. Right-click to add tables from import metadata. "
    "Click a row to view and edit extraction columns."
)
_TAB_TABLES = 0
_TAB_EXTRACT_GROUP = 1

_EXTRACT_GROUP_TAB_SUBTITLE = (
    "Named groups of tables for batch extraction. Assign tables to a group from the Tables tab."
)

_EXTRACT_GROUP_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Id", ("id", "groupId", "group_id")),
    ("Group Name", ("groupName",)),
    ("Fetch Size", ("fetchSize", "fetch_size")),
    ("Chunk Size", ("chunkSize", "chunk_size", "chunkSIze")),
    ("Description", ("description",)),
    ("Source Connection ID", ("sourceConnectionId", "source_connection_id")),
    ("Target Connection ID", ("targetConnectionId", "target_connection_id")),
)

_GROUP_TABLES_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("TABLE_NAME", ("TABLE_NAME", "tableName", "table_name", "name")),
    ("TGT_TABLE_NAME", ("TGT_TABLE_NAME", "newTableName", "tgtTableName", "tgt_table_name")),
    ("WHERE_CLAUSE", ("whereClause", "where_clause", "WHERE_CLAUSE")),
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


def _value_for_extraction_table_row(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    """Resolve extraction table cells, including ``config.targetTableName`` / ``config.whereClause``."""
    if "targetTableName" in keys or "TGT_TABLE_NAME" in keys:
        tgt = _imported_tgt_table_name(row)
        return (tgt if tgt else None), "targetTableName"
    if "whereClause" in keys or "where_clause" in keys or "WHERE_CLAUSE" in keys:
        clause = _imported_where_clause(row)
        return (clause if clause else None), "whereClause"
    return _value_for_extraction_row(row, keys)


def _extract_group_id(row: dict[str, Any] | None) -> int | str | None:
    if not row:
        return None
    for key in ("id", "groupId", "group_id"):
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _imported_table_name(row: dict[str, Any]) -> str:
    value, key_used = _value_for_extraction_row(row, _IMPORT_TABLES_DATA_SPEC[1][1])
    text = _extraction_format_cell(value, key_used, _IMPORT_TABLES_DATA_SPEC[1][1])
    return text if text and text != "--" else ""


def _extraction_record_id(row: dict[str, Any] | None) -> int | str | None:
    if not row:
        return None
    for key in ("id", "ID", "extractionId", "extraction_id"):
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _import_metadata_table_id(row: dict[str, Any] | None) -> int | str | None:
    if not row:
        return None
    for key in ("importTableId", "import_table_id", "IMPORT_TABLE_ID"):
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _imported_tgt_table_name(row: dict[str, Any]) -> str:
    for key in _TGT_NAME_KEYS:
        value = row.get(key)
        if value is not None and str(value).strip() and str(value).strip() != "--":
            return str(value).strip()
    config = row.get("config")
    if isinstance(config, dict):
        for key in _TGT_NAME_KEYS:
            value = config.get(key)
            if value is not None and str(value).strip() and str(value).strip() != "--":
                return str(value).strip()
    return ""


def _imported_where_clause(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    return _where_clause_from_table_item(row)


def build_etl_job_table_entry(row: dict[str, Any]) -> dict[str, str]:
    """One ``etl/jobs/start`` table item: source name + target name from imported metadata."""
    return {
        "tableName": _imported_table_name(row),
        "newTableName": _imported_tgt_table_name(row),
        "whereClause": _imported_where_clause(row),
    }


def build_etl_job_table_entries(
    table_names: list[str],
    tables_source: list[dict[str, Any]],
) -> list[dict[str, str]]:
    by_name = {
        _imported_table_name(row): row
        for row in tables_source
        if isinstance(row, dict) and _imported_table_name(row)
    }
    entries: list[dict[str, str]] = []
    for name in table_names:
        row = by_name.get(name)
        if isinstance(row, dict):
            entries.append(build_etl_job_table_entry(row))
        else:
            entries.append({"tableName": name, "newTableName": "", "whereClause": ""})
    return entries


def normalize_group_job_table_entries(
    raw_tables: Any,
    tables_source: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Normalize extract-group table list to job ``tableName`` objects."""
    if not isinstance(raw_tables, list):
        return []
    by_name = {
        _imported_table_name(row): row
        for row in tables_source
        if isinstance(row, dict) and _imported_table_name(row)
    }
    entries: list[dict[str, str]] = []
    for item in raw_tables:
        if isinstance(item, dict):
            src = str(
                item.get("tableName")
                or item.get("TABLE_NAME")
                or item.get("table_name")
                or item.get("name")
                or ""
            ).strip()
            if not src:
                continue
            tgt = str(
                item.get("newTableName")
                or item.get("TGT_TABLE_NAME")
                or item.get("tgtTableName")
                or item.get("tgt_table_name")
                or ""
            ).strip()
            if not tgt:
                source_row = by_name.get(src)
                if isinstance(source_row, dict):
                    tgt = _imported_tgt_table_name(source_row)
            entries.append({"tableName": src, "newTableName": tgt, "whereClause": ""})
        elif isinstance(item, str) and item.strip():
            src = item.strip()
            source_row = by_name.get(src)
            if isinstance(source_row, dict):
                entries.append(build_etl_job_table_entry(source_row))
            else:
                entries.append({"tableName": src, "newTableName": "", "whereClause": ""})
    return entries


def _group_table_row_id(row: dict[str, Any] | None) -> int | str | None:
    if not row:
        return None
    for key in ("id", "ID", "groupTableId", "group_table_id"):
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def _ids_equal(left: int | str | None, right: int | str | None) -> bool:
    if left is None or right is None:
        return False
    return str(left).strip() == str(right).strip()


def _group_table_tgt_name(row_data: dict[str, Any] | None) -> str:
    if not row_data:
        return ""
    value = str(
        row_data.get("newTableName")
        or row_data.get("TGT_TABLE_NAME")
        or row_data.get("tgtTableName")
        or row_data.get("tgt_table_name")
        or ""
    ).strip()
    return "" if value == "--" else value


def _where_clause_from_table_item(item: dict[str, Any]) -> str:
    for key in ("whereClause", "where_clause", "WHERE_CLAUSE"):
        value = item.get(key)
        if value is not None and str(value).strip() and str(value).strip() != "--":
            return str(value).strip()
    for nested_key in ("extractionConfig", "extraction_config", "config"):
        nested = item.get(nested_key)
        if isinstance(nested, dict):
            for key in ("whereClause", "where_clause", "WHERE_CLAUSE"):
                value = nested.get(key)
                if value is not None and str(value).strip() and str(value).strip() != "--":
                    return str(value).strip()
    return ""


def _group_table_where_clause(row_data: dict[str, Any] | None) -> str:
    if not row_data:
        return ""
    return _where_clause_from_table_item(row_data)


def group_table_display_rows(group: dict[str, Any]) -> list[dict[str, Any]]:
    """Rows for the group-tables detail panel from a GET extract-group record."""
    raw = group.get("tableName") or group.get("tables") or group.get("tableList")
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, dict):
            table_name = str(
                item.get("tableName")
                or item.get("TABLE_NAME")
                or item.get("table_name")
                or item.get("name")
                or ""
            ).strip()
            if not table_name:
                continue
            tgt_name = str(
                item.get("newTableName")
                or item.get("TGT_TABLE_NAME")
                or item.get("tgtTableName")
                or item.get("tgt_table_name")
                or ""
            ).strip()
            where_clause = _where_clause_from_table_item(item)
            row_id = _group_table_row_id(item)
            extraction_config = item.get("extractionConfig") or item.get("extraction_config")
            rows.append(
                {
                    "TABLE_NAME": table_name,
                    "TGT_TABLE_NAME": tgt_name or "--",
                    "WHERE_CLAUSE": where_clause or "--",
                    "id": row_id,
                    "ID": row_id,
                    "tableName": table_name,
                    "newTableName": tgt_name,
                    "whereClause": where_clause,
                    "extractionConfig": extraction_config,
                }
            )
        elif isinstance(item, str) and item.strip():
            table_name = item.strip()
            rows.append(
                {
                    "TABLE_NAME": table_name,
                    "TGT_TABLE_NAME": "--",
                    "tableName": table_name,
                    "newTableName": "",
                }
            )
    return rows


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


def _connection_fetch_size(conn: dict[str, Any] | None) -> str:
    if not conn:
        return ""
    for key in ("fetchSize", "fetch_size", "src_fetch_size"):
        value = conn.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def _connection_chunk_size(conn: dict[str, Any] | None) -> str:
    if not conn:
        return ""
    for key in ("chunkSize", "chunk_size", "chunkSIze", "tgt_commit_size"):
        value = conn.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


class ExtractionPageWidget(QWidget):
    """Extraction UI: source connections, optional config, tables, and optional columns."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        page_title: str = "ETL: Extraction",
        show_columns: bool = True,
    ) -> None:
        super().__init__(parent)
        self.show_columns = show_columns
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        title = QLabel(page_title)
        title.setStyleSheet(f"font-size: {LIST_PAGE_HEADER_TITLE_FONT_PX}px; font-weight: 600; color: #ffffff;")
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
        right_layout.setSpacing(8)

        self.extraction_title = QLabel("No connection selected")
        self.extraction_title.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX + 2}px; font-weight: 600;")
        right_layout.addWidget(self.extraction_title)

        self.tables_filters_btn = QPushButton("Filters")
        self.tables_refresh_btn = QPushButton("Refresh")
        self.tables_extract_btn = QPushButton("Extract")
        self.tables_remove_btn = QPushButton("Remove table")
        _prepare_scan_header_button(self.tables_filters_btn, width_px=80)
        _prepare_scan_header_button(self.tables_refresh_btn, width_px=100)
        _prepare_scan_header_button(self.tables_extract_btn, width_px=88)
        _prepare_scan_header_button(self.tables_remove_btn, width_px=110)
        self.tables_remove_btn.setEnabled(False)

        self.import_tables_table = QTableWidget(0, len(_IMPORT_TABLES_DATA_SPEC) + 1)
        self.import_tables_table.setHorizontalHeaderLabels(
            [""] + [label for label, _ in _IMPORT_TABLES_DATA_SPEC]
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
        configure_data_table_header(self.import_tables_table, stretch_last=False)

        self.extraction_columns_title = QLabel("Columns")
        self.columns_filters_btn = QPushButton("Filters")
        self.columns_select_all_checkbox = QCheckBox("Select all")
        self.extraction_columns_table = QTableWidget(0, 8)
        self.save_columns_btn = QPushButton("Save")
        _prepare_scan_header_button(self.save_columns_btn, width_px=100)
        self.save_columns_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)

        tables_tab_buttons: list[QPushButton] = [
            self.tables_filters_btn,
            self.tables_refresh_btn,
            self.tables_extract_btn,
        ]
        if show_columns:
            tables_tab_buttons.append(self.tables_remove_btn)

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
            apply_data_table_appearance(
                self.extraction_columns_table,
                read_only=False,
                stretch_last_section=False,
                hide_vertical_header=True,
            )
            attach_table_copy_shortcut(self.extraction_columns_table)
            configure_data_table_header(self.extraction_columns_table, stretch_last=False)

            columns_panel = QWidget()
            columns_panel_layout = QVBoxLayout(columns_panel)
            columns_panel_layout.setContentsMargins(0, 0, 0, 0)
            columns_panel_layout.setSpacing(6)
            columns_title_row = QHBoxLayout()
            self.extraction_columns_title.setStyleSheet(
                f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 600;"
            )
            columns_title_row.addWidget(self.extraction_columns_title)
            columns_title_row.addStretch()
            col_select = QHBoxLayout()
            self.columns_select_all_checkbox.setStyleSheet(
                f"font-size: {FORM_PAGE_FONT_SIZE_PX}px;"
            )
            col_select.addWidget(self.columns_select_all_checkbox)
            col_select.addStretch()
            col_actions = QHBoxLayout()
            col_actions.addStretch()
            col_actions.addWidget(self.save_columns_btn)
            columns_panel_layout.addLayout(columns_title_row)
            columns_panel_layout.addLayout(col_select)
            columns_panel_layout.addWidget(
                _build_scanned_sub_table_panel(
                    "Column details",
                    self.extraction_columns_table,
                    filters_btn=self.columns_filters_btn,
                ),
                1,
            )
            columns_panel_layout.addLayout(col_actions)

            tables_split = QSplitter(Qt.Orientation.Vertical)
            tables_split.setChildrenCollapsible(False)
            tables_split.setHandleWidth(6)
            tables_split.addWidget(self.import_tables_table)
            tables_split.addWidget(columns_panel)
            tables_split.setStretchFactor(0, 2)
            tables_split.setStretchFactor(1, 1)
            tables_split.setSizes([320, 220])
            tables_content = tables_split
        else:
            tables_content = self.import_tables_table

        tables_tab = _build_scan_operation_tab(
            header_title="Tables",
            subtitle=_TABLES_TAB_SUBTITLE,
            header_buttons=tuple(tables_tab_buttons),
            content=tables_content,
        )

        self.extract_group_create_btn = QPushButton("Create")
        self.extract_group_refresh_btn = QPushButton("Refresh")
        self.extract_group_extract_btn = QPushButton("Extract")
        self.extract_group_filters_btn = QPushButton("Filters")
        for btn in (
            self.extract_group_create_btn,
            self.extract_group_refresh_btn,
            self.extract_group_extract_btn,
            self.extract_group_filters_btn,
        ):
            _prepare_scan_header_button(btn, width_px=88)
        _prepare_scan_header_button(self.extract_group_filters_btn, width_px=80)
        self.extract_groups_table = QTableWidget()
        self.extract_groups_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.extract_groups_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        apply_data_table_appearance(
            self.extract_groups_table,
            read_only=True,
            stretch_last_section=False,
        )
        attach_table_copy_shortcut(self.extract_groups_table)

        self.extract_group_tables_title = QLabel("Group tables — select a group")
        self.extract_group_tables_title.setStyleSheet(
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 600;"
        )
        self.extract_group_tables_table = QTableWidget()
        apply_data_table_appearance(
            self.extract_group_tables_table,
            read_only=True,
            stretch_last_section=True,
        )
        attach_table_copy_shortcut(self.extract_group_tables_table)

        group_tables_panel = QWidget()
        group_tables_layout = QVBoxLayout(group_tables_panel)
        group_tables_layout.setContentsMargins(0, 0, 0, 0)
        group_tables_layout.setSpacing(6)
        group_tables_layout.addWidget(self.extract_group_tables_title)
        group_tables_layout.addWidget(
            _build_scanned_sub_table_panel(
                "Tables in group",
                self.extract_group_tables_table,
            ),
            1,
        )

        extract_group_split = QSplitter(Qt.Orientation.Vertical)
        extract_group_split.setChildrenCollapsible(False)
        extract_group_split.setHandleWidth(6)
        extract_group_split.addWidget(self.extract_groups_table)
        extract_group_split.addWidget(group_tables_panel)
        extract_group_split.setStretchFactor(0, 2)
        extract_group_split.setStretchFactor(1, 1)
        extract_group_split.setSizes([280, 200])

        extract_group_tab = _build_scan_operation_tab(
            header_title="Extract Group",
            subtitle=_EXTRACT_GROUP_TAB_SUBTITLE,
            header_buttons=(
                self.extract_group_create_btn,
                self.extract_group_refresh_btn,
                self.extract_group_extract_btn,
                self.extract_group_filters_btn,
            ),
            content=extract_group_split,
        )

        details_card = QWidget()
        details_card.setObjectName("extractionCard")
        details_card.setStyleSheet(
            "#extractionCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 8px; }"
        )
        details_layout = QVBoxLayout(details_card)
        details_layout.setContentsMargins(8, 8, 8, 8)
        details_layout.setSpacing(0)

        self.extraction_inner_tabs = QTabWidget()
        self.extraction_inner_tabs.setDocumentMode(True)
        self.extraction_inner_tabs.setStyleSheet(_TAB_STYLESHEET)
        self.extraction_inner_tabs.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.extraction_inner_tabs.addTab(tables_tab, "Tables")
        self.extraction_inner_tabs.addTab(extract_group_tab, "Extract Group")
        details_layout.addWidget(self.extraction_inner_tabs, 1)
        right_layout.addWidget(details_card, 1)

        self._status_label = QLabel("")
        self._status_label.setWordWrap(True)
        right_layout.addWidget(self._status_label)

        right_wrap.setMinimumHeight(320)
        content_layout.addWidget(right_wrap, 1)

        scroll.setWidget(content)
        root.addWidget(scroll, 1)
        self.set_extraction_workspace_enabled(False)

    def set_extraction_workspace_enabled(self, enabled: bool) -> None:
        self.extraction_inner_tabs.setEnabled(enabled)
        self.import_tables_table.setEnabled(enabled)
        self.extraction_columns_table.setEnabled(enabled)
        self.extract_groups_table.setEnabled(enabled)
        self.extract_group_tables_table.setEnabled(enabled)
        self.tables_filters_btn.setEnabled(enabled)
        self.tables_refresh_btn.setEnabled(enabled)
        self.tables_extract_btn.setEnabled(enabled)
        if not enabled:
            self.tables_remove_btn.setEnabled(False)
        self.columns_filters_btn.setEnabled(enabled)
        self.columns_select_all_checkbox.setEnabled(enabled)
        self.extract_group_filters_btn.setEnabled(enabled)
        self.extract_group_create_btn.setEnabled(enabled)
        self.extract_group_refresh_btn.setEnabled(enabled)
        self.extract_group_extract_btn.setEnabled(enabled)
        self.save_columns_btn.setEnabled(enabled)


class EtlExtractionPage(QWidget):
    """Extraction workspace with table/column selection and job run controls."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._show_columns = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._ui = ExtractionPageWidget(
            page_title="ETL: Extraction",
            show_columns=True,
        )
        layout.addWidget(self._ui)

        self._ctx = get_etl_connection_context()
        self._active_table_name: str | None = None
        self._active_extraction_id: int | str | None = None
        self._columns_by_table: dict[str, list[dict[str, Any]]] = {}
        self._columns_baseline: dict[str, dict[str, bool]] = {}
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
        self._extract_groups_source: list[dict[str, Any]] = []
        self._extract_group_filter_visible = False
        self._extract_group_filter_timer = QTimer(self)
        self._extract_group_filter_timer.setSingleShot(True)
        self._extract_group_filter_timer.setInterval(200)
        self._active_extract_group: dict[str, Any] | None = None
        self._columns_dirty = False
        self._applied_connection: dict[str, Any] | None = None
        self._inner_tab_index = _TAB_TABLES
        self._suppress_inner_tab_change = False

        self._ui.refresh_btn.clicked.connect(self.refresh)
        self._ui.extraction_inner_tabs.currentChanged.connect(self._on_inner_tab_changed)
        self._ctx.connection_selected.connect(self._on_connection_selected)
        self._ui.tables_filters_btn.toggled.connect(self._on_tables_filters_toggled)
        self._tables_filter_timer.timeout.connect(self._refresh_tables_view)
        self._ui.tables_refresh_btn.clicked.connect(self._refresh_tables)
        self._ui.extract_group_filters_btn.toggled.connect(self._on_extract_group_filters_toggled)
        self._extract_group_filter_timer.timeout.connect(self._refresh_extract_groups_view)
        self._ui.extract_group_create_btn.clicked.connect(self._on_create_extract_group)
        self._ui.extract_group_refresh_btn.clicked.connect(self._load_extract_groups)
        self._ui.extract_group_extract_btn.clicked.connect(self._on_extract_group_extract_btn_clicked)
        self._ui.extract_groups_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._ui.extract_groups_table.customContextMenuRequested.connect(
            self._on_extract_groups_context_menu
        )
        self._ui.extract_groups_table.cellClicked.connect(self._on_extract_group_row_clicked)
        self._ui.extract_group_tables_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._ui.extract_group_tables_table.customContextMenuRequested.connect(
            self._on_group_tables_context_menu
        )
        self._ui.import_tables_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._ui.import_tables_table.customContextMenuRequested.connect(
            self._on_import_tables_context_menu
        )
        self._ui.extract_groups_table.itemDoubleClicked.connect(
            lambda _row, _col: self._on_edit_extract_group()
        )
        if self._show_columns:
            self._ui.columns_filters_btn.toggled.connect(self._on_columns_filters_toggled)
            self._columns_filter_timer.timeout.connect(self._refresh_columns_view)
            self._ui.import_tables_table.cellClicked.connect(self._on_table_clicked)
            self._ui.tables_remove_btn.clicked.connect(self._remove_table)
            self._ui.save_columns_btn.clicked.connect(self._save_columns)
            self._ui.columns_select_all_checkbox.stateChanged.connect(self._on_columns_select_all)
            self._ui.extraction_columns_table.itemChanged.connect(self._on_column_item_changed)
        self._ui.tables_extract_btn.clicked.connect(self._on_extract_clicked)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._columns_dirty:
            self.refresh()

    def confirm_leave_unsaved_columns(self) -> bool:
        """Return True when navigation away from this page may proceed."""
        return self._require_columns_saved("leave this page")

    def refresh(self) -> None:
        if not self._require_columns_saved("refresh"):
            return
        result = self._ctx.refresh_connections(self._token())
        if not result.get("success"):
            self._show_page_message(
                str(result.get("message") or "Failed to load connections."), error=True
            )
            return
        show_auto_hiding_message(self, self._ui.message_label, "", error=False)
        self._on_connection_selected(self._ctx.current_connection())

    def _token(self) -> str | None:
        profile = get_user_profile() or {}
        return profile.get("token") or profile.get("accessToken")

    def _show_status(self, text: str, *, error: bool = False) -> None:
        if not text:
            self._ui._status_label.clear()
            return
        show_auto_hiding_message(self, self._ui._status_label, text, error=error)

    def _show_page_message(self, text: str, *, error: bool) -> None:
        show_auto_hiding_message(self, self._ui.message_label, text, error=error)

    def _current_connection(self) -> dict[str, Any] | None:
        return self._ctx.current_connection()

    def _on_connection_selected(self, conn: object) -> None:
        if not isinstance(conn, dict):
            if self._columns_dirty:
                QMessageBox.warning(
                    self,
                    "Unsaved changes",
                    "Save column selection changes before changing connection.",
                )
                if self._applied_connection is not None:
                    self._ctx.select_connection(self._applied_connection)
                return
            self._reset_workspace()
            self._applied_connection = None
            return
        if self._columns_dirty:
            new_id = _connection_id(conn)
            applied_id = _connection_id(self._applied_connection)
            if new_id != applied_id:
                QMessageBox.warning(
                    self,
                    "Unsaved changes",
                    "Save column selection changes before switching connection.",
                )
                if self._applied_connection is not None:
                    self._ctx.select_connection(self._applied_connection)
                return
        self._apply_connection_selection()

    def _mark_columns_dirty(self) -> None:
        self._sync_columns_dirty_state()

    def _clear_columns_workspace(self) -> None:
        self._columns_by_table = {}
        self._columns_baseline = {}
        self._columns_dirty = False

    def _snapshot_column_checks(self, columns: list[dict[str, Any]]) -> dict[str, bool]:
        return {
            str(col.get("name")): bool(col.get("checked"))
            for col in columns
            if col.get("name") is not None and str(col.get("name")).strip()
        }

    def _set_columns_baseline(self, table_name: str, columns: list[dict[str, Any]]) -> None:
        self._columns_baseline[table_name] = self._snapshot_column_checks(columns)

    def _sync_columns_dirty_state(self) -> None:
        self._columns_dirty = self._has_unsaved_column_changes()

    def _has_unsaved_column_changes(self) -> bool:
        for table_name, columns in self._columns_by_table.items():
            baseline = self._columns_baseline.get(table_name)
            if baseline is None:
                continue
            if self._snapshot_column_checks(columns) != baseline:
                return True
        return False

    def _require_columns_saved(self, action: str) -> bool:
        if not self._columns_dirty:
            return True
        QMessageBox.warning(
            self,
            "Unsaved changes",
            f"Save column selection changes using Save before you {action}.",
        )
        return False

    def _on_inner_tab_changed(self, index: int) -> None:
        if self._suppress_inner_tab_change:
            self._suppress_inner_tab_change = False
            return
        if (
            self._columns_dirty
            and self._inner_tab_index == _TAB_TABLES
            and index != _TAB_TABLES
        ):
            if not self._require_columns_saved("switch tabs"):
                self._suppress_inner_tab_change = True
                self._ui.extraction_inner_tabs.setCurrentIndex(self._inner_tab_index)
                return
        self._inner_tab_index = index

    def _apply_connection_selection(self) -> None:
        conn = self._current_connection()
        if not conn:
            return
        self._active_table_name = None
        self._active_extraction_id = None
        self._clear_columns_workspace()
        if self._show_columns:
            self._ui.tables_remove_btn.setEnabled(False)
        self._ui.import_tables_table.setRowCount(0)
        self._ui.extraction_columns_table.setRowCount(0)
        self._ui.extraction_columns_title.setText("Columns")
        if self._show_columns:
            self._sync_columns_select_all()
        self._ui.extraction_title.setText(str(conn.get("connectionName") or ""))
        self._ui.set_extraction_workspace_enabled(True)
        self._show_status("")
        self._load_tables()
        self._load_extract_groups()
        applied = self._current_connection()
        self._applied_connection = dict(applied) if applied else None

    def _reset_workspace(self) -> None:
        self._active_table_name = None
        self._active_extraction_id = None
        self._clear_columns_workspace()
        self._extract_groups_source = []
        self._active_extract_group = None
        self._refresh_group_tables_view(None)
        self._ui.extraction_title.setText("No connection selected")
        self._ui.import_tables_table.setRowCount(0)
        self._ui.extraction_columns_table.setRowCount(0)
        self._ui.extraction_columns_title.setText("Columns")
        self._refresh_extract_groups_view()
        self._ui.set_extraction_workspace_enabled(False)
        if self._show_columns:
            self._ui.tables_remove_btn.setEnabled(False)
            self._sync_columns_select_all()

    def _connection_name(self) -> str:
        return _connection_name(self._current_connection())

    def _connection_id(self) -> int | str | None:
        return _connection_id(self._current_connection())

    def _group_source_connection_id(self) -> int | str | None:
        group = self._active_extract_group
        if isinstance(group, dict):
            src_id = group.get("sourceConnectionId") or group.get("source_connection_id")
            if src_id is not None and str(src_id).strip() != "":
                return src_id
        return self._connection_id()

    def _load_extract_groups(self) -> None:
        active_id = _extract_group_id(self._active_extract_group)
        result = api_get_extract_groups(token=self._token())
        if not result.get("success"):
            self._extract_groups_source = []
            self._active_extract_group = None
            self._refresh_extract_groups_view()
            self._refresh_group_tables_view(None)
            self._show_status(str(result.get("message") or "Failed to load extract groups."), error=True)
            return
        self._extract_groups_source = list(result.get("data") or [])
        self._refresh_extract_groups_view()
        if active_id is not None:
            for group in self._extract_groups_source:
                if _extract_group_id(group) == active_id:
                    self._active_extract_group = group
                    self._refresh_group_tables_view(group)
                    self._show_status("")
                    return
        self._active_extract_group = None
        self._refresh_group_tables_view(None)
        self._show_status("")

    def _extract_groups_data_row_offset(self) -> int:
        return data_row_offset(self._extract_group_filter_visible)

    def _extract_group_row_data_at(self, table_row: int) -> dict[str, Any] | None:
        if table_row < self._extract_groups_data_row_offset():
            return None
        item = self._ui.extract_groups_table.item(table_row, 0)
        if item is None:
            return None
        row_data = item.data(Qt.ItemDataRole.UserRole)
        return row_data if isinstance(row_data, dict) else None

    def _on_extract_group_row_clicked(self, row: int, column: int) -> None:
        if row < self._extract_groups_data_row_offset():
            return
        group = self._extract_group_row_data_at(row)
        if not group:
            return
        self._active_extract_group = group
        self._refresh_group_tables_view(group)

    def _refresh_group_tables_view(self, group: dict[str, Any] | None = None) -> None:
        selected = group if group is not None else self._active_extract_group
        if not selected:
            self._ui.extract_group_tables_title.setText("Group tables — select a group")
            self._ui.extract_group_tables_table.setRowCount(0)
            return
        group_name = str(selected.get("groupName") or "Extract group").strip()
        self._ui.extract_group_tables_title.setText(f"Group tables — {group_name}")
        rows = group_table_display_rows(selected)
        render_dict_rows_table(
            self._ui.extract_group_tables_table,
            rows,
            list(_GROUP_TABLES_COLUMN_SPEC),
            filter_visible=False,
            value_for_column=_value_for_extraction_row,
            format_cell=_extraction_format_cell,
            enable_sorting=True,
        )

    def _group_table_row_data_at(self, table_row: int) -> dict[str, Any] | None:
        item = self._ui.extract_group_tables_table.item(table_row, 0)
        if item is None:
            return None
        row_data = item.data(Qt.ItemDataRole.UserRole)
        return row_data if isinstance(row_data, dict) else None

    def _on_group_tables_context_menu(self, pos: QPoint) -> None:
        table = self._ui.extract_group_tables_table
        clicked_item = table.itemAt(pos)
        if clicked_item is None:
            return
        row = clicked_item.row()
        table.setCurrentCell(row, clicked_item.column())
        table.selectRow(row)
        row_data = self._group_table_row_data_at(row)
        table_name = ""
        if isinstance(row_data, dict):
            table_name = str(row_data.get("TABLE_NAME") or row_data.get("tableName") or "").strip()
        workspace_enabled = self._ui.extraction_inner_tabs.isEnabled()
        has_table = bool(table_name)
        can_remove = has_table and _group_table_row_id(row_data) is not None
        can_update_tgt = can_remove
        can_where_clause = can_remove
        current_where = _group_table_where_clause(row_data) if isinstance(row_data, dict) else ""
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        update_tgt_action = menu.addAction("Update TGT Table Name")
        where_clause_action = menu.addAction(
            "Edit Where Clause" if current_where else "Add Where Clause"
        )
        remove_action = menu.addAction("Remove table")
        update_tgt_action.setEnabled(workspace_enabled and can_update_tgt)
        where_clause_action.setEnabled(workspace_enabled and can_where_clause)
        remove_action.setEnabled(workspace_enabled and can_remove)
        action = menu.exec(QCursor.pos())
        if action == update_tgt_action and can_update_tgt and isinstance(row_data, dict):
            self._on_update_group_tgt_table_name(row_data, table_name)
        elif action == where_clause_action and can_where_clause and isinstance(row_data, dict):
            self._on_add_group_table_where_clause(row_data, table_name)
        elif action == remove_action and can_remove and isinstance(row_data, dict):
            self._on_remove_group_table(row_data, table_name)

    def _on_add_group_table_where_clause(
        self,
        row_data: dict[str, Any],
        table_name: str,
    ) -> None:
        if not self._require_columns_saved("add a where clause"):
            return
        group_table_id = _group_table_row_id(row_data)
        if group_table_id is None:
            QMessageBox.warning(
                self,
                "Missing",
                "Group table ID is missing. Refresh the group list and try again.",
            )
            return
        connection_id = self._group_source_connection_id()
        if connection_id is None:
            QMessageBox.warning(self, "Missing", "Group source connection is required.")
            return
        dlg = GroupTableWhereClauseDialog(
            self,
            table_name=table_name,
            connection_id=connection_id,
            token=self._token(),
            initial=_group_table_where_clause(row_data),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        where_clause = dlg.where_clause()
        if not where_clause:
            QMessageBox.warning(self, "Missing", "Where clause cannot be empty.")
            return
        result = api_add_group_table_where_clause(
            group_table_id,
            where_clause,
            token=self._token(),
        )
        if not result.get("success"):
            QMessageBox.warning(
                self,
                "Failed",
                str(result.get("message") or "Failed to save where clause."),
            )
            return
        msg = str(result.get("message") or "Where clause saved.")
        self._patch_group_table_where_clause(group_table_id, where_clause)
        self._load_extract_groups()
        self._show_status(msg, error=False)

    def _patch_group_table_where_clause(
        self,
        group_table_id: int | str,
        where_clause: str,
    ) -> None:
        for group in self._extract_groups_source:
            raw = group.get("tableName") or group.get("tables") or group.get("tableList")
            if not isinstance(raw, list):
                continue
            for item in raw:
                if isinstance(item, dict) and _ids_equal(_group_table_row_id(item), group_table_id):
                    extraction_config = item.get("extractionConfig") or item.get("extraction_config")
                    if isinstance(extraction_config, dict):
                        extraction_config["whereClause"] = where_clause
                    else:
                        item["extractionConfig"] = {"whereClause": where_clause}
                    item["whereClause"] = where_clause
                    return

    def _on_update_group_tgt_table_name(
        self,
        row_data: dict[str, Any],
        table_name: str,
    ) -> None:
        if not self._require_columns_saved("update target table name"):
            return
        group_table_id = _group_table_row_id(row_data)
        if group_table_id is None:
            QMessageBox.warning(
                self,
                "Missing",
                "Group table ID is missing. Refresh the group list and try again.",
            )
            return
        current_tgt = _group_table_tgt_name(row_data)
        new_name, ok = QInputDialog.getText(
            self,
            "Update TGT Table Name",
            f"New target table name for \"{table_name}\":",
            text=current_tgt,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Missing", "Target table name cannot be empty.")
            return
        if new_name == current_tgt:
            return
        result = api_update_group_tgt_table_name(
            group_table_id,
            new_name,
            token=self._token(),
        )
        if not result.get("success"):
            msg = str(result.get("message") or "Failed to update target table name.")
            self._show_status(msg, error=True)
            QMessageBox.warning(self, "Failed", msg)
            return
        msg = str(result.get("message") or "Target table name updated.")
        self._patch_group_table_tgt_name(group_table_id, new_name)
        self._load_extract_groups()
        self._show_status(msg, error=False)

    def _patch_group_table_tgt_name(
        self,
        group_table_id: int | str,
        new_name: str,
    ) -> None:
        """Update cached group table target names before the GET refresh returns."""
        for group in self._extract_groups_source:
            raw = group.get("tableName") or group.get("tables") or group.get("tableList")
            if not isinstance(raw, list):
                continue
            for item in raw:
                if isinstance(item, dict) and _ids_equal(_group_table_row_id(item), group_table_id):
                    item["newTableName"] = new_name
                    item["TGT_TABLE_NAME"] = new_name
                    item["tgtTableName"] = new_name
                    item["tgt_table_name"] = new_name
                    return

    def _on_remove_group_table(self, row_data: dict[str, Any], table_name: str) -> None:
        if not self._require_columns_saved("remove a table from an extract group"):
            return
        group_table_id = _group_table_row_id(row_data)
        if group_table_id is None:
            QMessageBox.warning(
                self,
                "Missing",
                "Group table ID is missing. Refresh the group list and try again.",
            )
            return
        answer = QMessageBox.question(
            self,
            "Remove table",
            f"Remove table \"{table_name}\" from this extract group?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = api_delete_extract_group_table(group_table_id, token=self._token())
        if not result.get("success"):
            QMessageBox.warning(
                self,
                "Remove failed",
                str(result.get("message") or "Failed to remove table from extract group."),
            )
            return
        self._show_status(
            str(result.get("message") or "Table removed from extract group."),
            error=False,
        )
        self._load_extract_groups()

    def _selected_extract_group(self) -> dict[str, Any] | None:
        items = self._ui.extract_groups_table.selectedItems()
        if not items:
            return None
        row = items[0].data(Qt.ItemDataRole.UserRole)
        return row if isinstance(row, dict) else None

    def _on_extract_groups_context_menu(self, pos: QPoint) -> None:
        table = self._ui.extract_groups_table
        clicked_item = table.itemAt(pos)
        if clicked_item is not None:
            table.setCurrentCell(clicked_item.row(), clicked_item.column())
            table.selectRow(clicked_item.row())
        group = self._selected_extract_group()
        has_group = _extract_group_id(group) is not None
        workspace_enabled = self._ui.extraction_inner_tabs.isEnabled()
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        edit_action = menu.addAction("Edit")
        add_tables_action = menu.addAction("Add table")
        delete_action = menu.addAction("Delete")
        run_action = menu.addAction("Run extraction")
        edit_action.setEnabled(workspace_enabled and has_group)
        add_tables_action.setEnabled(workspace_enabled and has_group)
        delete_action.setEnabled(workspace_enabled and has_group)
        run_action.setEnabled(workspace_enabled and has_group)
        action = menu.exec(QCursor.pos())
        if action == edit_action and has_group:
            self._on_edit_extract_group()
        elif action == add_tables_action and has_group:
            self._on_add_group_tables(group)
        elif action == delete_action and has_group:
            self._on_delete_extract_group()
        elif action == run_action and has_group:
            self._start_group_extraction(group)

    def _table_row_data_at(self, table_row: int) -> dict[str, Any] | None:
        if table_row < self._tables_data_row_offset():
            return None
        name_item = self._ui.import_tables_table.item(table_row, 2)
        if name_item is None:
            return None
        row_data = name_item.data(Qt.ItemDataRole.UserRole)
        return row_data if isinstance(row_data, dict) else None

    def _on_import_tables_context_menu(self, pos: QPoint) -> None:
        table = self._ui.import_tables_table
        clicked_item = table.itemAt(pos)
        row_data: dict[str, Any] | None = None
        table_name = ""
        if clicked_item is not None:
            row = clicked_item.row()
            if row >= self._tables_data_row_offset():
                table.setCurrentCell(row, clicked_item.column())
                table.selectRow(row)
                row_data = self._table_row_data_at(row)
                table_name = _imported_table_name(row_data) if row_data else self._table_name_at_row(row)
        workspace_enabled = self._ui.extraction_inner_tabs.isEnabled()
        has_table = bool(table_name)
        extraction_id = _extraction_record_id(row_data)
        can_where_clause = has_table and extraction_id is not None
        current_where = _imported_where_clause(row_data) if row_data else ""
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_table_action = menu.addAction("Add table")
        add_table_action.setEnabled(workspace_enabled and self._connection_id() is not None)
        delete_action = None
        update_tgt_action = None
        where_clause_action = None
        if has_table:
            delete_action = menu.addAction("Delete table")
            update_tgt_action = menu.addAction("Edit TGT Table Name")
            where_clause_action = menu.addAction(
                "Edit Where Clause" if current_where else "Add Where Clause"
            )
            delete_action.setEnabled(workspace_enabled and extraction_id is not None)
            update_tgt_action.setEnabled(workspace_enabled and has_table and extraction_id is not None)
            where_clause_action.setEnabled(workspace_enabled and can_where_clause)
        action = menu.exec(QCursor.pos())
        if action == add_table_action:
            self._on_add_extraction_tables()
        elif action == delete_action and has_table and extraction_id is not None:
            self._delete_extraction_table(extraction_id, table_name)
        elif action == update_tgt_action and has_table and isinstance(row_data, dict):
            self._on_update_tgt_table_name(row_data, table_name)
        elif action == where_clause_action and can_where_clause and isinstance(row_data, dict):
            self._on_import_table_where_clause(row_data, table_name)

    def _on_import_table_where_clause(
        self,
        row_data: dict[str, Any],
        table_name: str,
    ) -> None:
        if not self._require_columns_saved("add a where clause"):
            return
        extraction_id = _extraction_record_id(row_data)
        if extraction_id is None:
            QMessageBox.warning(
                self,
                "Missing",
                "Extraction ID is missing. Refresh the table list and try again.",
            )
            return
        connection_id = self._connection_id()
        if connection_id is None:
            QMessageBox.warning(self, "Missing", "Please select a source connection.")
            return
        dlg = GroupTableWhereClauseDialog(
            self,
            table_name=table_name,
            connection_id=connection_id,
            token=self._token(),
            initial=_imported_where_clause(row_data),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        where_clause = dlg.where_clause()
        if not where_clause:
            QMessageBox.warning(self, "Missing", "Where clause cannot be empty.")
            return
        result = api_update_extraction_where_clause(
            extraction_id,
            where_clause,
            token=self._token(),
        )
        if not result.get("success"):
            QMessageBox.warning(
                self,
                "Failed",
                str(result.get("message") or "Failed to save where clause."),
            )
            return
        msg = str(result.get("message") or "Where clause saved.")
        self._patch_extraction_where_clause(row_data, extraction_id, where_clause)
        self._refresh_tables_view()
        self._show_status(msg, error=False)

    def _patch_extraction_where_clause(
        self,
        row_data: dict[str, Any],
        extraction_id: int | str,
        where_clause: str,
    ) -> None:
        row_data["whereClause"] = where_clause
        row_data["where_clause"] = where_clause
        row_data["WHERE_CLAUSE"] = where_clause
        config = row_data.get("config")
        if not isinstance(config, dict):
            config = {}
            row_data["config"] = config
        config["whereClause"] = where_clause
        for source_row in self._tables_source:
            if _extraction_record_id(source_row) is not None and _ids_equal(
                _extraction_record_id(source_row), extraction_id
            ):
                source_row["whereClause"] = where_clause
                source_row["where_clause"] = where_clause
                source_row["WHERE_CLAUSE"] = where_clause
                config = source_row.get("config")
                if not isinstance(config, dict):
                    config = {}
                    source_row["config"] = config
                config["whereClause"] = where_clause
                break

    def _on_update_tgt_table_name(
        self,
        row_data: dict[str, Any] | None,
        table_name: str,
    ) -> None:
        if not self._require_columns_saved("update target table name"):
            return
        extraction_id = _extraction_record_id(row_data)
        if extraction_id is None:
            QMessageBox.warning(
                self,
                "Missing",
                "Extraction ID is missing. Refresh the table list and try again.",
            )
            return
        current_tgt = _imported_tgt_table_name(row_data) if row_data else ""
        new_name, ok = QInputDialog.getText(
            self,
            "Edit TGT Table Name",
            f"New target table name for \"{table_name}\":",
            text=current_tgt,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Missing", "Target table name cannot be empty.")
            return
        if new_name == current_tgt:
            return
        result = api_update_extraction_target_table(
            extraction_id,
            new_name,
            token=self._token(),
        )
        if not result.get("success"):
            msg = str(result.get("message") or "Failed to update target table name.")
            self._show_status(msg, error=True)
            QMessageBox.warning(self, "Failed", msg)
            return
        msg = str(result.get("message") or "Target table name updated.")
        self._show_status(msg, error=False)
        if row_data is not None:
            config = row_data.get("config")
            if not isinstance(config, dict):
                config = {}
                row_data["config"] = config
            config["targetTableName"] = new_name
            row_data["targetTableName"] = new_name
            row_data["TGT_TABLE_NAME"] = new_name
            row_data["tgtTableName"] = new_name
            row_data["newTableName"] = new_name
        for source_row in self._tables_source:
            if _extraction_record_id(source_row) is not None and _ids_equal(
                _extraction_record_id(source_row), extraction_id
            ):
                config = source_row.get("config")
                if not isinstance(config, dict):
                    config = {}
                    source_row["config"] = config
                config["targetTableName"] = new_name
                source_row["targetTableName"] = new_name
                source_row["TGT_TABLE_NAME"] = new_name
                source_row["tgtTableName"] = new_name
                source_row["newTableName"] = new_name
                break
        self._refresh_tables_view()

    def _on_create_extract_group(self) -> None:
        if not self._require_columns_saved("create an extract group"):
            return
        dlg = ExtractGroupDialog(
            self,
            connections=self._ctx.connections(),
            default_source_connection_id=self._connection_id(),
            title="Create Extract Group",
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dlg.payload()
        src_conn = self._connection_by_id(payload.get("sourceConnectionId"))
        tgt_conn = self._connection_by_id(payload.get("targetConnectionId"))
        sizes = self._job_fetch_and_chunk_sizes(src_conn, tgt_conn)
        if sizes is None:
            return
        fetch_size, chunk_size = sizes
        payload["fetchSize"] = int(fetch_size)
        payload["chunkSize"] = int(chunk_size)
        table_entries = self._extract_group_table_payload()
        if table_entries:
            payload["tableName"] = table_entries
        result = api_create_extract_group(payload, token=self._token())
        if not result.get("success"):
            QMessageBox.warning(
                self,
                "Create failed",
                str(result.get("message") or "Failed to create extract group."),
            )
            return
        self._show_status(str(result.get("message") or "Extract group created."), error=False)
        self._load_extract_groups()

    def _on_add_group_tables(self, group: dict[str, Any]) -> None:
        if not self._require_columns_saved("add tables to an extract group"):
            return
        group_id = _extract_group_id(group)
        src_conn_id = group.get("sourceConnectionId")
        if group_id is None:
            QMessageBox.warning(self, "Missing", "Select a valid extract group.")
            return
        if src_conn_id is None:
            QMessageBox.warning(self, "Missing", "Group source connection is required.")
            return
        result = api_get_imported_tables(str(src_conn_id), token=self._token())
        if not result.get("success"):
            QMessageBox.warning(
                self,
                "Failed",
                str(result.get("message") or "Failed to load imported tables."),
            )
            return
        tables = list(result.get("tables") or [])
        if not tables:
            QMessageBox.information(self, "No tables", "No imported tables found for this connection.")
            return
        dlg = ExtractGroupAddTablesDialog(
            self,
            group_name=str(group.get("groupName") or ""),
            tables=tables,
            checked_table_names=group_table_names(group),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_tables = dlg.newly_checked_table_entries()
        if not new_tables:
            QMessageBox.information(self, "No changes", "Select at least one new table to add.")
            return
        add_result = api_add_extract_group_tables(group_id, new_tables, token=self._token())
        if not add_result.get("success"):
            QMessageBox.warning(
                self,
                "Add failed",
                str(add_result.get("message") or "Failed to add tables to extract group."),
            )
            return
        self._show_status(str(add_result.get("message") or "Tables added to extract group."), error=False)
        self._load_extract_groups()

    def _on_add_extraction_tables(self) -> None:
        if not self._require_columns_saved("add tables to extraction"):
            return
        conn = self._current_connection()
        conn_id = self._connection_id()
        conn_name = _connection_name(conn)
        if conn_id is None:
            QMessageBox.warning(self, "Missing", "Please select a source connection.")
            return
        result = api_get_imported_tables(conn_id, token=self._token())
        if not result.get("success"):
            QMessageBox.warning(
                self,
                "Failed",
                str(result.get("message") or "Failed to load imported tables."),
            )
            return
        tables = list(result.get("tables") or [])
        if not tables:
            QMessageBox.information(self, "No tables", "No imported tables found for this connection.")
            return
        existing = {
            _imported_table_name(row)
            for row in self._tables_source
            if isinstance(row, dict) and _imported_table_name(row)
        }
        dlg = ExtractionAddTableDialog(
            self,
            connection_name=conn_name,
            tables=tables,
            existing_table_names=existing,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_names = dlg.newly_checked_table_names()
        if not new_names:
            QMessageBox.information(self, "No changes", "Select at least one new table to add.")
            return
        failures: list[str] = []
        for table_name in new_names:
            add_result = api_create_extraction_table(
                table_name,
                conn_id,
                token=self._token(),
            )
            if not add_result.get("success"):
                failures.append(f"{table_name}: {add_result.get('message') or 'Failed'}")
        if failures:
            QMessageBox.warning(
                self,
                "Add failed",
                "Some tables could not be added:\n" + "\n".join(failures),
            )
        else:
            self._show_status(
                f"Added {len(new_names)} table(s) to extraction.",
                error=False,
            )
        self._load_tables()

    def _delete_extraction_table(
        self,
        extraction_id: int | str,
        table_name: str,
    ) -> None:
        if not self._require_columns_saved("delete a table"):
            return
        result = api_delete_extraction_table(extraction_id, token=self._token())
        if result.get("success"):
            msg = str(result.get("message") or "Table removed from extraction.")
            self._show_status(msg, error=False)
            QMessageBox.information(self, "Success", msg)
            self._columns_by_table.pop(table_name, None)
            self._columns_baseline.pop(table_name, None)
            self._sync_columns_dirty_state()
            if self._active_table_name == table_name:
                self._active_table_name = None
                self._active_extraction_id = None
                self._ui.tables_remove_btn.setEnabled(False)
                self._ui.extraction_columns_table.setRowCount(0)
                self._ui.extraction_columns_title.setText("Columns")
                self._sync_columns_select_all()
            self._load_tables()
        else:
            msg = str(result.get("message") or "Failed to remove table.")
            self._show_status(msg, error=True)
            QMessageBox.warning(self, "Failed", msg)

    def _on_edit_extract_group(self) -> None:
        if not self._require_columns_saved("edit an extract group"):
            return
        group = self._selected_extract_group()
        group_id = _extract_group_id(group)
        if not group or group_id is None:
            QMessageBox.warning(self, "Missing", "Select an extract group to edit.")
            return
        dlg = ExtractGroupDialog(
            self,
            connections=self._ctx.connections(),
            initial=group,
            title="Edit Extract Group",
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dlg.payload()
        table_entries = self._extract_group_table_payload(group)
        if table_entries:
            payload["tableName"] = table_entries
        result = api_update_extract_group(group_id, payload, token=self._token())
        if not result.get("success"):
            QMessageBox.warning(
                self,
                "Update failed",
                str(result.get("message") or "Failed to update extract group."),
            )
            return
        self._show_status(str(result.get("message") or "Extract group updated."), error=False)
        self._load_extract_groups()

    def _on_delete_extract_group(self) -> None:
        if not self._require_columns_saved("delete an extract group"):
            return
        group = self._selected_extract_group()
        group_id = _extract_group_id(group)
        if not group or group_id is None:
            QMessageBox.warning(self, "Missing", "Select an extract group to delete.")
            return
        name = str(group.get("groupName") or group_id)
        answer = QMessageBox.question(
            self,
            "Delete extract group",
            f"Delete extract group \"{name}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = api_delete_extract_group(group_id, token=self._token())
        if not result.get("success"):
            QMessageBox.warning(
                self,
                "Delete failed",
                str(result.get("message") or "Failed to delete extract group."),
            )
            return
        self._show_status(str(result.get("message") or "Extract group deleted."), error=False)
        self._load_extract_groups()

    def _connection_name_by_id(self, connection_id: int | str | None) -> str:
        if connection_id is None:
            return ""
        target = str(connection_id).strip()
        for conn in self._ctx.connections():
            cid = conn.get("connectionId") or conn.get("connectionID") or conn.get("id")
            if cid is not None and str(cid).strip() == target:
                return str(conn.get("connectionName") or "").strip()
        return ""

    def _connection_by_id(self, connection_id: int | str | None) -> dict[str, Any] | None:
        if connection_id is None:
            return None
        target = str(connection_id).strip()
        for conn in self._ctx.connections():
            cid = conn.get("connectionId") or conn.get("connectionID") or conn.get("id")
            if cid is not None and str(cid).strip() == target:
                return conn
        return None

    def _job_fetch_and_chunk_sizes(
        self,
        src_conn: dict[str, Any] | None,
        tgt_conn: dict[str, Any] | None,
    ) -> tuple[str, str] | None:
        fetch_size = _connection_fetch_size(src_conn)
        chunk_size = _connection_chunk_size(tgt_conn)
        if not fetch_size:
            QMessageBox.warning(
                self,
                "Missing",
                "Source connection fetch size is not configured. Set it on the Connections page.",
            )
            return None
        if not chunk_size:
            QMessageBox.warning(
                self,
                "Missing",
                "Target connection chunk size is not configured. Set it on the Connections page.",
            )
            return None
        return fetch_size, chunk_size

    def _extract_group_table_payload(self, group: dict[str, Any] | None = None) -> list[dict[str, str]]:
        checked = self._checked_tables()
        if checked:
            return build_etl_job_table_entries(checked, self._tables_source)
        if group:
            return normalize_group_job_table_entries(
                group.get("tableName") or group.get("tables") or group.get("tableList"),
                self._tables_source,
            )
        return []

    def _start_group_extraction(self, group: dict[str, Any] | None) -> None:
        if not self._require_columns_saved("run extraction"):
            return
        if not group:
            return
        group_id = _extract_group_id(group)
        if group_id is None:
            QMessageBox.warning(self, "Missing", "Select a valid extract group.")
            return
        result = api_start_group_extraction_job(group_id, token=self._token())
        if result.get("success"):
            QMessageBox.information(self, "Success", str(result.get("message") or "Job queued."))
            self._show_status(str(result.get("message") or ""), error=False)
        else:
            QMessageBox.warning(
                self,
                "Failed",
                str(result.get("message") or "Failed to start extraction job."),
            )

    def _on_extract_group_extract_btn_clicked(self) -> None:
        group = self._selected_extract_group() or self._active_extract_group
        if group is None:
            QMessageBox.warning(self, "Missing", "Select an extract group to run.")
            return
        self._start_group_extraction(group)

    def _on_extract_group_filters_toggled(self, checked: bool) -> None:
        self._extract_group_filter_visible = checked
        if not checked:
            clear_filter_row_widgets(self._ui.extract_groups_table)
        self._refresh_extract_groups_view()

    def _schedule_extract_group_filter_apply(self) -> None:
        if self._extract_group_filter_visible:
            self._extract_group_filter_timer.start()

    def _extract_groups_filtered_rows(self) -> list[dict[str, Any]]:
        rows = list(self._extract_groups_source)
        if not self._extract_group_filter_visible:
            return rows
        return filter_dict_rows_by_column_edits(
            rows,
            self._ui.extract_groups_table,
            list(_EXTRACT_GROUP_COLUMN_SPEC),
            True,
            _value_for_extraction_row,
            _extraction_format_cell,
        )

    def _refresh_extract_groups_view(self) -> None:
        saved = (
            saved_filter_texts(self._ui.extract_groups_table)
            if self._extract_group_filter_visible
            else None
        )
        render_dict_rows_table(
            self._ui.extract_groups_table,
            self._extract_groups_filtered_rows(),
            list(_EXTRACT_GROUP_COLUMN_SPEC),
            filter_visible=self._extract_group_filter_visible,
            value_for_column=_value_for_extraction_row,
            format_cell=_extraction_format_cell,
            on_filter_text_changed=self._schedule_extract_group_filter_apply,
            saved_filter_texts_list=saved,
            enable_sorting=False,
        )

    def _load_tables(self) -> None:
        conn_id = self._connection_id()
        if conn_id is None:
            return
        result = api_get_extraction_tables_by_connection(conn_id, token=self._token())
        if result.get("success"):
            tables = list(result.get("tables") or [])
            self._render_tables(tables)
            if not tables:
                self._show_status("No extraction tables found.")
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
            _value_for_extraction_table_row,
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
                value, key_used = _value_for_extraction_table_row(row, keys)
                item = QTableWidgetItem(_extraction_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx == 2:
                    item.setData(Qt.ItemDataRole.UserRole, row)
                table.setItem(r_index, col_idx, item)
        sync_vertical_header_labels(
            table, filter_visible=self._tables_filter_visible, data_row_count=len(rows)
        )
        resize_data_table_columns_to_content(
            table,
            list(_IMPORT_TABLES_DATA_SPEC),
            rows,
            _value_for_extraction_table_row,
            _extraction_format_cell,
            column_start_index=1,
        )
        table.setColumnWidth(0, 40)
        table.setSortingEnabled(not self._tables_filter_visible)

    def _refresh_tables(self) -> None:
        if not self._require_columns_saved("refresh the table list"):
            return
        if self._connection_id() is None:
            QMessageBox.warning(self, "Missing", "Please select a source connection.")
            return
        self._active_table_name = None
        self._active_extraction_id = None
        self._clear_columns_workspace()
        if self._show_columns:
            self._ui.tables_remove_btn.setEnabled(False)
        self._ui.extraction_columns_table.setRowCount(0)
        self._ui.extraction_columns_title.setText("Columns")
        if self._show_columns:
            self._sync_columns_select_all()
        self._load_tables()

    def _table_name_at_row(self, table_row: int) -> str:
        name_item = self._ui.import_tables_table.item(table_row, 2)
        if name_item is None:
            return ""
        row_data = name_item.data(Qt.ItemDataRole.UserRole)
        if isinstance(row_data, dict):
            name = _imported_table_name(row_data)
            if name:
                return name
        text = name_item.text().strip()
        return text if text and text != "--" else ""

    def _on_table_clicked(self, row: int, column: int) -> None:
        if row < self._tables_data_row_offset() or column == 0:
            return
        if not self._require_columns_saved("open another table"):
            return
        table_name = self._table_name_at_row(row)
        if not table_name:
            return
        row_data = self._table_row_data_at(row)
        extraction_id = _extraction_record_id(row_data)
        if extraction_id is not None:
            detail = api_get_extraction_by_id(extraction_id, token=self._token())
            if detail.get("success") and isinstance(detail.get("data"), dict):
                row_data = detail["data"]
                self._patch_tables_source_row(extraction_id, row_data)
        self._active_table_name = table_name
        self._active_extraction_id = _extraction_record_id(row_data)
        self._ui.tables_remove_btn.setEnabled(self._active_extraction_id is not None)
        self._load_columns(table_name)

    def _patch_tables_source_row(
        self,
        extraction_id: int | str,
        row_data: dict[str, Any],
    ) -> None:
        for idx, row in enumerate(self._tables_source):
            if _extraction_record_id(row) is not None and _ids_equal(
                _extraction_record_id(row), extraction_id
            ):
                self._tables_source[idx] = dict(row_data)
                self._refresh_tables_view()
                break

    def _remove_table(self) -> None:
        if not self._require_columns_saved("remove a table"):
            return
        table_name = self._active_table_name
        extraction_id = self._active_extraction_id
        if not table_name:
            QMessageBox.warning(self, "Missing", "Please click a table to remove.")
            return
        if extraction_id is None:
            QMessageBox.warning(
                self,
                "Missing",
                "Extraction ID is missing. Refresh the table list and try again.",
            )
            return
        self._delete_extraction_table(extraction_id, table_name)

    def _load_columns(self, table_name: str) -> None:
        conn_id = self._connection_id()
        if conn_id is None:
            return
        self._show_status("")
        result = api_get_extracted_fields(str(conn_id), table_name, token=self._token())
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
        self._set_columns_baseline(table_name, columns)
        self._sync_columns_dirty_state()
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
        self._mark_columns_dirty()
        self._sync_columns_select_all()

    def _on_column_item_changed(self, item: QTableWidgetItem) -> None:
        if self._columns_rendering or item.column() != 0:
            return
        if item.row() < self._columns_data_row_offset():
            return
        self._update_columns_cache_from_table()
        self._mark_columns_dirty()
        self._sync_columns_select_all()

    def _save_columns(self) -> None:
        conn_id = self._connection_id()
        table_name = self._current_columns_table_name()
        if conn_id is None:
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
            str(conn_id),
            table_name,
            checked_columns,
            unchecked_columns,
            token=self._token(),
        )
        if result.get("success"):
            msg = str(result.get("message") or "Columns updated.")
            self._show_status(msg, error=False)
            if table_name in self._columns_by_table:
                self._set_columns_baseline(table_name, self._columns_by_table[table_name])
            self._sync_columns_dirty_state()
            QMessageBox.information(self, "Success", msg)
        else:
            msg = str(result.get("message") or "Failed to update columns.")
            self._show_status(msg, error=True)
            QMessageBox.warning(self, "Failed", msg)

    def _checked_tables(self) -> list[str]:
        table = self._ui.import_tables_table
        selected: list[str] = []
        offset = self._tables_data_row_offset()
        for row in range(offset, table.rowCount()):
            check_item = table.item(row, 0)
            if not check_item:
                continue
            if check_item.checkState() == Qt.CheckState.Checked:
                table_name = self._table_name_at_row(row)
                if table_name:
                    selected.append(table_name)
        return selected

    def _on_extract_clicked(self) -> None:
        if not self._require_columns_saved("run extraction"):
            return
        if not self._current_connection():
            QMessageBox.warning(self, "Missing", "Please select a source connection.")
            return
        dlg = ExtractTargetDialog(
            self,
            connections=self._ctx.connections(),
            source_connection_name=self._connection_name(),
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        target_conn = dlg.selected_connection()
        if not isinstance(target_conn, dict):
            QMessageBox.warning(self, "Missing", "Please select a target connection.")
            return
        self._start_extraction(target_conn)

    def _start_extraction(self, target_conn: dict[str, Any]) -> None:
        src_conn = self._current_connection()
        if not src_conn:
            QMessageBox.warning(self, "Missing", "Please select a source connection.")
            return

        checked_tables = self._checked_tables()
        if not checked_tables:
            QMessageBox.warning(self, "Missing", "Please select at least one table to extract.")
            return

        sizes = self._job_fetch_and_chunk_sizes(src_conn, target_conn)
        if sizes is None:
            return
        fetch_size, commit_size = sizes

        src_conn_id = self._connection_id()
        src_name = self._connection_name()
        tgt_name = str(target_conn.get("connectionName") or "").strip()
        if src_conn_id is None:
            QMessageBox.warning(self, "Missing", "Please select a source connection.")
            return

        for table_name in checked_tables:
            normalized = self._columns_by_table.get(table_name)
            if not normalized:
                result = api_get_extracted_fields(str(src_conn_id), table_name, token=self._token())
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
            "tableName": build_etl_job_table_entries(checked_tables, self._tables_source),
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
