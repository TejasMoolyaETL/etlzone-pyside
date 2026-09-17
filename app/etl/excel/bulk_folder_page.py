"""ETL: Excel — bulk import all files from a folder path."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QShowEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.etl.excel.upload_file_page import _enrich_analyze_sheets_unicode
from app.etl.widgets.etl_connection_picker import EtlConnectionHeaderPicker
from core.api import (
    api_analyze_import_file,
    api_create_import,
    api_execute_import_sheet,
    api_save_import_mapping,
    api_upload_import_file,
    import_target_data_type_to_java,
)
from core.etl_connection_context import etl_connection_id, get_etl_connection_context
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.data_table import apply_data_table_appearance, attach_table_copy_shortcut
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE,
    FORM_LABEL_STYLE,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
)
from ui.theme import Theme
from ui.widgets.required_label import field_caption_label, labeled_field_block

_SUPPORTED_SUFFIXES = {".xlsx", ".xls", ".csv", ".json"}

_HEADER_BTN_STYLESHEET = (
    f"QPushButton {{ background: {Theme.HEADER_ACCENT}; color: {Theme.PANEL_TEXT_BRIGHT}; border: none; "
    "border-radius: 6px; padding: 5px 16px; font-size: 12px; font-weight: 500; }"
    f"QPushButton:hover:!disabled {{ background: {Theme.HEADER_ACCENT_HOVER}; }}"
    f"QPushButton:pressed:!disabled {{ background: {Theme.HEADER_ACCENT_PRESSED}; }}"
    f"QPushButton:disabled {{ background: #1e293b; color: {Theme.TEXT_SECONDARY}; }}"
)

_CARD_STYLE = f"""
    QFrame#bulkCard {{
        background: {Theme.BG_WHITE};
        border: 1px solid {Theme.BORDER_DEFAULT};
        border-radius: 10px;
    }}
    QLabel#bulkCardTitle {{
        color: {Theme.TEXT_PRIMARY};
        font-size: 15px;
        font-weight: 700;
        background: transparent;
        border: none;
    }}
    QLabel#bulkCardHint {{
        color: {Theme.TEXT_SECONDARY};
        font-size: 11px;
        background: transparent;
        border: none;
    }}
"""


def _source_type_for_path(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".xlsx", ".xls"}:
        return "EXCEL"
    if ext == ".csv":
        return "CSV"
    if ext == ".json":
        return "JSON"
    return ""


def _sanitize_table_name(name: str) -> str:
    cleaned = re.sub(r"[^\w]+", "_", (name or "").strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("_")
    if not cleaned:
        return "imported_table"
    if cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned[:120]


def _table_name_for_file(path: Path) -> str:
    return _sanitize_table_name(path.stem)


def _session_id_from_create(result: dict[str, Any]) -> str:
    data = result.get("data")
    candidates: list[Any] = []
    if isinstance(data, dict):
        candidates.append(data)
        nested = data.get("data")
        if isinstance(nested, dict):
            candidates.append(nested)
    candidates.append(result)
    keys = (
        "sessionId",
        "sessionID",
        "session_id",
        "importSessionId",
        "importId",
        "id",
        "uuid",
    )
    for obj in candidates:
        if not isinstance(obj, dict):
            continue
        for key in keys:
            value = obj.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def _first_id(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    raw = row.get("_raw")
    if isinstance(raw, dict):
        for key in keys:
            if key in raw and raw.get(key) is not None:
                return raw.get(key)
    return None


def _list_folder_files(folder: str) -> list[Path]:
    root = Path(folder)
    if not root.is_dir():
        return []
    files = [
        p
        for p in sorted(root.iterdir(), key=lambda x: x.name.lower())
        if p.is_file() and p.suffix.lower() in _SUPPORTED_SUFFIXES
    ]
    return files


class BulkFolderImportPage(QWidget):
    """Choose a folder and import every spreadsheet/CSV/JSON into DB (table = file name)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._running = False
        self._folder = ""
        self._files: list[Path] = []
        self._ctx = get_etl_connection_context()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("Excel: Bulk via folder path"))
        hl.addStretch()
        self.connection_picker = EtlConnectionHeaderPicker()
        hl.addWidget(self.connection_picker)
        self.submit_btn = QPushButton("Import all")
        self.submit_btn.setFixedWidth(120)
        self.submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_btn.setStyleSheet(_HEADER_BTN_STYLESHEET)
        self.submit_btn.clicked.connect(self._handle_submit)
        hl.addWidget(self.submit_btn)
        root.addWidget(header)

        body = QWidget()
        body.setStyleSheet(f"background: {Theme.BG_PAGE_ALT};")
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(24, 18, 24, 18)
        body_l.setSpacing(14)

        card = QFrame()
        card.setObjectName("bulkCard")
        card.setStyleSheet(_CARD_STYLE)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(20, 16, 20, 18)
        card_l.setSpacing(10)

        title = QLabel("Bulk import from folder")
        title.setObjectName("bulkCardTitle")
        card_l.addWidget(title)
        hint = QLabel(
            "Pick a folder containing Excel / CSV / JSON files. Each file is uploaded, "
            "mapped, and imported. Target table name = file name (without extension)."
        )
        hint.setObjectName("bulkCardHint")
        hint.setWordWrap(True)
        card_l.addWidget(hint)

        folder_lbl = field_caption_label("Folder path*", FORM_LABEL_STYLE)
        folder_row = QWidget()
        folder_row_l = QHBoxLayout(folder_row)
        folder_row_l.setContentsMargins(0, 0, 0, 0)
        folder_row_l.setSpacing(8)
        self.folder_edit = QLineEdit()
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setPlaceholderText("No folder selected")
        self.folder_edit.setStyleSheet(FORM_INPUT_STYLE)
        self.folder_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
        browse_btn = QPushButton("Browse…")
        browse_btn.setFixedWidth(100)
        browse_btn.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.setStyleSheet(
            "QPushButton { background: #f8fafc; color: #334155; border: 1px solid #cbd5e1; "
            "border-radius: 4px; padding: 4px 12px; font-size: 11px; font-weight: 600; }"
            "QPushButton:hover { background: #eef2f7; border-color: #94a3b8; }"
        )
        browse_btn.clicked.connect(self._browse_folder)
        folder_row_l.addWidget(self.folder_edit, 1)
        folder_row_l.addWidget(browse_btn)
        card_l.addWidget(labeled_field_block(folder_lbl, folder_row))

        self.multi_language_check = QCheckBox("Enable multi-language (Unicode)")
        self.multi_language_check.setChecked(True)
        self.multi_language_check.setCursor(Qt.CursorShape.PointingHandCursor)
        self.multi_language_check.setStyleSheet(
            "QCheckBox { color: #334155; font-size: 11px; font-weight: 600; }"
        )
        card_l.addWidget(self.multi_language_check)

        op_lbl = field_caption_label("Import operation*", FORM_LABEL_STYLE)
        op_row = QWidget()
        op_row_l = QHBoxLayout(op_row)
        op_row_l.setContentsMargins(0, 0, 0, 0)
        op_row_l.setSpacing(16)
        self.op_group = QButtonGroup(self)
        self.radio_drop_create = QRadioButton("Drop and Create")
        self.radio_delete = QRadioButton("Delete (then load)")
        self.radio_drop_create.setChecked(True)
        self.op_group.addButton(self.radio_drop_create)
        self.op_group.addButton(self.radio_delete)
        op_row_l.addWidget(self.radio_drop_create)
        op_row_l.addWidget(self.radio_delete)
        op_row_l.addStretch()
        card_l.addWidget(labeled_field_block(op_lbl, op_row))

        self.file_count_label = QLabel("Files found: 0")
        self.file_count_label.setStyleSheet(
            "color: #475569; font-size: 11px; font-weight: 600; background: transparent;"
        )
        card_l.addWidget(self.file_count_label)

        self.message_label = QLabel()
        self.message_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.message_label.setWordWrap(True)
        self.message_label.setVisible(False)
        card_l.addWidget(self.message_label)

        body_l.addWidget(card, 0, Qt.AlignmentFlag.AlignTop)

        self.log_table = QTableWidget()
        self.log_table.setColumnCount(4)
        self.log_table.setHorizontalHeaderLabels(["File", "Table", "Status", "Message"])
        apply_data_table_appearance(
            self.log_table,
            read_only=True,
            stretch_last_section=True,
            hide_vertical_header=True,
            sort_indicator_shown=False,
            alternating_row_colors=True,
        )
        self.log_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.log_table.setMinimumHeight(280)
        hh = self.log_table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        hh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.log_table.setColumnWidth(0, 220)
        self.log_table.setColumnWidth(1, 180)
        attach_table_copy_shortcut(self.log_table)
        body_l.addWidget(self.log_table, 1)

        root.addWidget(body, 1)

    def go_to_nav_item(self, _nav_item: str) -> None:
        self._refresh_connections()

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._refresh_connections()

    def _token(self) -> str | None:
        profile = get_user_profile() or {}
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _refresh_connections(self) -> None:
        self._ctx.refresh_connections(self._token())

    def _selected_connection_id(self) -> int | None:
        conn = self._ctx.current_connection()
        conn_id = etl_connection_id(conn) if conn else None
        if conn_id is None or str(conn_id).strip() == "":
            return None
        try:
            return int(conn_id)
        except (TypeError, ValueError):
            return None

    def _selected_operation(self) -> str:
        return "DELETE" if self.radio_delete.isChecked() else "DROP_CREATE"

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self.message_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self.message_label, message, error=False)

    def _clear_message(self) -> None:
        cancel_auto_hide_message(self, self.message_label)
        self.message_label.clear()
        self.message_label.setVisible(False)

    def _browse_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select folder with files to import")
        if not folder:
            return
        self._folder = folder
        self.folder_edit.setText(folder)
        self._files = _list_folder_files(folder)
        self.file_count_label.setText(f"Files found: {len(self._files)}")
        self._reset_log_preview()
        self._clear_message()
        if not self._files:
            self._show_error("No .xlsx / .xls / .csv / .json files found in that folder.")

    def _reset_log_preview(self) -> None:
        self.log_table.setRowCount(0)
        self.log_table.setRowCount(len(self._files))
        for row, path in enumerate(self._files):
            table = _table_name_for_file(path)
            self.log_table.setItem(row, 0, QTableWidgetItem(path.name))
            self.log_table.setItem(row, 1, QTableWidgetItem(table))
            self.log_table.setItem(row, 2, QTableWidgetItem("Pending"))
            self.log_table.setItem(row, 3, QTableWidgetItem(""))

    def _set_log_row(self, row: int, status: str, message: str, *, ok: bool | None = None) -> None:
        status_item = QTableWidgetItem(status)
        msg_item = QTableWidgetItem(message)
        if ok is True:
            status_item.setForeground(QColor("#15803d"))
        elif ok is False:
            status_item.setForeground(QColor("#dc2626"))
        self.log_table.setItem(row, 2, status_item)
        self.log_table.setItem(row, 3, msg_item)
        self.log_table.scrollToItem(status_item)
        QApplication.processEvents()

    def _build_mapping_body(
        self,
        sheet: dict[str, Any],
        *,
        target_table: str,
        target_connection_id: int,
    ) -> tuple[dict[str, Any] | None, str | None]:
        sheet_id = _first_id(sheet, "sheetId", "sheet_id", "sheetID", "id")
        try:
            sheet_id_int = int(sheet_id) if sheet_id is not None and str(sheet_id).strip() else None
        except (TypeError, ValueError):
            sheet_id_int = None
        if sheet_id_int is None:
            return None, "Sheet ID missing from analyze result."

        columns = sheet.get("columns") if isinstance(sheet.get("columns"), list) else []
        if not columns:
            return None, "No columns found in workbook."

        mappings: list[dict[str, Any]] = []
        for col in columns:
            if not isinstance(col, dict):
                continue
            source_column_id = _first_id(
                col,
                "sourceColumnId",
                "source_column_id",
                "columnId",
                "column_id",
                "fieldId",
                "id",
            )
            try:
                source_id_int = (
                    int(source_column_id)
                    if source_column_id is not None and str(source_column_id).strip()
                    else None
                )
            except (TypeError, ValueError):
                source_id_int = None
            if source_id_int is None:
                return None, "A column is missing sourceColumnId."
            target_column_name = str(col.get("tgtColumnName") or col.get("name") or "").strip()
            if not target_column_name:
                return None, "A column is missing target column name."
            java_type = import_target_data_type_to_java(
                col.get("tgtDatatype") or col.get("datatype")
            )
            nullable = True
            if col.get("nullable") in ("FALSE", "false", "0", False):
                nullable = False
            mapping: dict[str, Any] = {
                "sourceColumnId": source_id_int,
                "targetColumnName": target_column_name,
                "targetDataType": java_type,
                "nullable": nullable,
                "primaryKey": bool(col.get("primaryKey", False)),
                "selected": bool(col.get("selected", True)),
            }
            length_raw = str(col.get("length") or "").strip()
            if length_raw and java_type in ("STRING", "DECIMAL"):
                try:
                    mapping["length"] = int(length_raw)
                except ValueError:
                    pass
            mappings.append(mapping)

        if not mappings:
            return None, "No column mappings to save."
        return (
            {
                "sheetId": sheet_id_int,
                "targetTableName": target_table,
                "targetConnectionId": target_connection_id,
                "mappings": mappings,
            },
            None,
        )

    def _import_one_file(
        self,
        path: Path,
        *,
        connection_id: int,
        operation: str,
        multi_language: bool,
        token: str | None,
    ) -> tuple[bool, str, str]:
        table_name = _table_name_for_file(path)
        source_type = _source_type_for_path(path)
        if not source_type:
            return False, table_name, "Unsupported file type."

        create = api_create_import(table_name, source_type, token=token)
        if not create.get("success"):
            return False, table_name, str(create.get("message") or "Failed to create import session.")
        session_id = _session_id_from_create(create)
        if not session_id:
            # Fallback: some backends only expose session after create via name echo.
            data = create.get("data") if isinstance(create.get("data"), dict) else {}
            session_id = str(data.get("name") or table_name).strip()
        if not session_id:
            return False, table_name, "Import created but session ID was not returned."

        upload = api_upload_import_file(
            session_id,
            str(path),
            token=token,
            codepage="65001" if multi_language else None,
            multi_language=multi_language,
        )
        if not upload.get("success"):
            return False, table_name, str(upload.get("message") or "Upload failed.")

        analyze = api_analyze_import_file(
            session_id,
            token=token,
            codepage="65001" if multi_language else None,
            multi_language=multi_language,
        )
        if not analyze.get("success"):
            return False, table_name, str(analyze.get("message") or "Analyze failed.")
        sheets = analyze.get("data") if isinstance(analyze.get("data"), list) else []
        sheets = _enrich_analyze_sheets_unicode(
            sheets,
            file_path=str(path),
            multi_language=multi_language,
        )
        if not sheets:
            return False, table_name, "Analyze returned no sheets."

        # One table per file: use first sheet (matches "table = file name").
        sheet = sheets[0] if isinstance(sheets[0], dict) else {}
        body, err = self._build_mapping_body(
            sheet,
            target_table=table_name,
            target_connection_id=connection_id,
        )
        if err or body is None:
            return False, table_name, err or "Could not build mapping."

        save = api_save_import_mapping(session_id, body, token=token)
        if not save.get("success"):
            return False, table_name, str(save.get("message") or "Failed to save mapping.")

        sheet_id = body.get("sheetId")
        execute = api_execute_import_sheet(
            session_id,
            sheet_id,
            operation=operation,
            token=token,
        )
        if not execute.get("success"):
            return False, table_name, str(execute.get("message") or "Execute/import failed.")
        return True, table_name, str(execute.get("message") or "Imported successfully.")

    def _handle_submit(self) -> None:
        if self._running:
            return
        self._clear_message()
        if not self._folder or not self._files:
            self._show_error("Select a folder that contains importable files.")
            return
        connection_id = self._selected_connection_id()
        if connection_id is None:
            self._show_error("Select a connection in the header before importing.")
            return
        token = self._token()
        if not token:
            self._show_error("Session expired. Please log in again.")
            return

        operation = self._selected_operation()
        multi_language = bool(self.multi_language_check.isChecked())
        self._running = True
        self.submit_btn.setEnabled(False)
        ok_count = 0
        fail_count = 0
        try:
            for row, path in enumerate(self._files):
                self._set_log_row(row, "Running…", "Create → upload → map → execute")
                try:
                    ok, table, message = self._import_one_file(
                        path,
                        connection_id=connection_id,
                        operation=operation,
                        multi_language=multi_language,
                        token=token,
                    )
                except Exception as exc:  # noqa: BLE001 — keep batch going
                    ok, table, message = False, _table_name_for_file(path), str(exc)
                if self.log_table.item(row, 1) is not None:
                    self.log_table.item(row, 1).setText(table)
                if ok:
                    ok_count += 1
                    self._set_log_row(row, "Success", message, ok=True)
                else:
                    fail_count += 1
                    self._set_log_row(row, "Failed", message, ok=False)
        finally:
            self._running = False
            self.submit_btn.setEnabled(True)

        if fail_count == 0:
            self._show_success(f"Imported {ok_count} file(s) successfully.")
        else:
            self._show_error(f"Finished with {ok_count} success, {fail_count} failed.")
