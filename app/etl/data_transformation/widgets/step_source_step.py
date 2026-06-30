"""Wizard step 1: multiple source tables per flow."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.etl.data_transformation.constants import CARD_STYLE, PANEL_HINT_STYLE, PANEL_TITLE_STYLE
from app.etl.data_transformation.data_service import TransformationDataService
from app.etl.data_transformation.metadata_helpers import (
    connection_id,
    connection_label,
    extraction_table_name,
    transformation_connection_id,
    transformation_record_id,
    transformation_table_name,
)
from ui.data_table import apply_data_table_appearance, attach_table_copy_shortcut
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
)


def _source_field(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


class StepSourceStepWidget(QWidget):
    def __init__(self, service: TransformationDataService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._connections: list[dict[str, Any]] = []
        self._extracted_tables: list[dict[str, Any]] = []
        self._connection_labels: dict[str, str] = {}
        self._flow_id: int | str | None = None
        self._sources: list[dict[str, Any]] = []
        self._source_record_id: int | str | None = None
        self._pending_table_name: str | None = None
        self._edit_mode = False
        self._loading_selection = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        card = QFrame()
        card.setObjectName("dtCard")
        card.setStyleSheet(CARD_STYLE)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(10)

        title = QLabel("Source tables")
        title.setStyleSheet(PANEL_TITLE_STYLE)
        card_layout.addWidget(title)

        hint = QLabel(
            "Add one or more source tables for the selected flow. Each row needs a connection, "
            "extracted table, alias, and sequence number."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(PANEL_HINT_STYLE)
        card_layout.addWidget(hint)

        list_lbl = QLabel("Configured source tables")
        list_lbl.setStyleSheet(PANEL_TITLE_STYLE)
        card_layout.addWidget(list_lbl)

        self.sources_table = QTableWidget(0, 5)
        self.sources_table.setHorizontalHeaderLabels(
            ["Connection", "Table name", "Alias", "Sequence", "Status"]
        )
        apply_data_table_appearance(self.sources_table, read_only=True, hide_vertical_header=True)
        self.sources_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.sources_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.sources_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.sources_table.setMinimumHeight(140)
        attach_table_copy_shortcut(self.sources_table)
        card_layout.addWidget(self.sources_table)

        form = QFormLayout()
        form.setSpacing(10)

        self.connection_combo = QComboBox()
        self.connection_combo.setMinimumWidth(280)
        form.addRow("Connection", self.connection_combo)

        self._table_cell = QWidget()
        table_cell_layout = QHBoxLayout(self._table_cell)
        table_cell_layout.setContentsMargins(0, 0, 0, 0)
        table_cell_layout.setSpacing(0)
        self.table_view_label = QLabel("—")
        self.table_view_label.setMinimumWidth(280)
        self.table_view_label.setStyleSheet("color: #0f172a;")
        self.table_combo = QComboBox()
        self.table_combo.setMinimumWidth(280)
        self.table_combo.setPlaceholderText("Select a table")
        table_cell_layout.addWidget(self.table_view_label)
        table_cell_layout.addWidget(self.table_combo, 1)
        form.addRow("Table name", self._table_cell)

        self.alias_input = QLineEdit()
        self.alias_input.setPlaceholderText("e.g. E")
        self.alias_input.setMinimumWidth(280)
        form.addRow("Alias name", self.alias_input)

        self.sequence_input = QLineEdit("1")
        form.addRow("Sequence no.", self.sequence_input)

        self.status_input = QLineEdit("ACTIVE")
        form.addRow("Status", self.status_input)

        card_layout.addLayout(form)

        action_row = QHBoxLayout()
        action_row.addStretch()
        self.new_btn = QPushButton("New")
        self.delete_btn = QPushButton("Delete")
        self.save_btn = QPushButton("Save")
        self.edit_btn = QPushButton("Edit")
        for btn in (self.new_btn, self.delete_btn, self.edit_btn):
            btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self.save_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self.edit_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        action_row.addWidget(self.new_btn)
        action_row.addWidget(self.delete_btn)
        action_row.addWidget(self.save_btn)
        action_row.addWidget(self.edit_btn)
        card_layout.addLayout(action_row)

        self._success_label = QLabel("")
        self._success_label.setWordWrap(True)
        self._success_label.setStyleSheet("color: #15803d;")
        self._success_label.setVisible(False)
        card_layout.addWidget(self._success_label)

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setVisible(False)
        card_layout.addWidget(self._error_label)

        root.addWidget(card, 1)

        self.connection_combo.currentIndexChanged.connect(self._on_connection_changed)
        self.sources_table.itemSelectionChanged.connect(self._on_row_selected)
        self.new_btn.clicked.connect(self._on_new)
        self.delete_btn.clicked.connect(self._on_delete)
        self.save_btn.clicked.connect(self._on_save)
        self.edit_btn.clicked.connect(self._on_edit)

    def set_flow_id(self, flow_id: int | str | None) -> None:
        self._flow_id = flow_id

    def source_record_id(self) -> int | str | None:
        return self._source_record_id

    def reset(self) -> None:
        self._flow_id = None
        self._sources = []
        self._source_record_id = None
        self._pending_table_name = None
        self._edit_mode = False
        self._extracted_tables = []
        self._clear_form()
        self._refresh_table()
        self._clear_messages()
        self._refresh_form_mode()

    def load_connections(self) -> tuple[bool, str]:
        ok, rows, msg = self._service.load_connections()
        if not ok:
            return False, msg
        self._connections = rows
        self._connection_labels = {}
        for conn in rows:
            cid = connection_id(conn)
            if cid is None:
                continue
            label = connection_label(conn) or str(cid)
            self._connection_labels[str(cid).strip()] = label
        self.connection_combo.blockSignals(True)
        self.connection_combo.clear()
        for conn in rows:
            label = connection_label(conn) or str(connection_id(conn) or "")
            if label:
                self.connection_combo.addItem(label, conn)
        self.connection_combo.blockSignals(False)
        return True, ""

    def setup_status(self) -> tuple[str, bool]:
        count = len(self._sources)
        if count == 0:
            return "No source tables yet — click New, fill the form, then Save.", False
        suffix = "s" if count != 1 else ""
        return f"{count} source table{suffix} configured.", True

    def load_sources(self, flow_id: int | str) -> tuple[bool, str]:
        ok, rows, msg = self._service.load_transformation_sources_by_flow(flow_id)
        if not ok:
            return False, msg
        self._sources = rows
        self._refresh_table()
        self._on_new()
        return True, ""

    def load_existing_source(self, flow_id: int | str) -> tuple[bool, str]:
        return self.load_sources(flow_id)

    def _connection_display(self, record: dict[str, Any]) -> str:
        cid = transformation_connection_id(record)
        if cid is not None:
            label = self._connection_labels.get(str(cid).strip())
            if label:
                return label
        nested = record.get("connection")
        if isinstance(nested, dict):
            label = connection_label(nested)
            if label:
                return label
        return str(cid).strip() if cid is not None else ""

    def _refresh_table(self) -> None:
        self._loading_selection = True
        self.sources_table.setRowCount(len(self._sources))
        for row_index, record in enumerate(self._sources):
            values = (
                self._connection_display(record),
                transformation_table_name(record)
                or _source_field(record, "tableName", "table_name", "TABLE_NAME"),
                _source_field(record, "aliasName", "alias_name", "ALIAS_NAME"),
                _source_field(record, "sequenceNo", "sequence_no", "SEQUENCE_NO") or "1",
                _source_field(record, "status", "STATUS") or "ACTIVE",
            )
            for col_index, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, record)
                self.sources_table.setItem(row_index, col_index, item)
        self.sources_table.clearSelection()
        self._loading_selection = False

    def _clear_form(self) -> None:
        if self.connection_combo.count() > 0:
            self.connection_combo.setCurrentIndex(0)
        self.table_combo.clear()
        self.table_view_label.setText("—")
        self.alias_input.clear()
        self.sequence_input.setText("1")
        self.status_input.setText("ACTIVE")
        self._extracted_tables = []

    def _set_connection_combo(self, connection_value: int | str | None) -> None:
        if connection_value is None:
            if self.connection_combo.count() > 0:
                self.connection_combo.setCurrentIndex(0)
            return
        target = str(connection_value).strip()
        for index in range(self.connection_combo.count()):
            conn = self.connection_combo.itemData(index)
            if isinstance(conn, dict) and str(connection_id(conn) or "").strip() == target:
                self.connection_combo.setCurrentIndex(index)
                return

    def _apply_record(self, record: dict[str, Any]) -> None:
        self._source_record_id = transformation_record_id(
            record, "id", "sourceId", "source_id", "ID"
        )
        self._edit_mode = False
        self._set_connection_combo(transformation_connection_id(record))
        table_name = transformation_table_name(record) or _source_field(
            record, "tableName", "table_name", "TABLE_NAME"
        )
        self._pending_table_name = table_name or None
        self._on_connection_changed()
        self.alias_input.setText(_source_field(record, "aliasName", "alias_name", "ALIAS_NAME"))
        self.sequence_input.setText(
            _source_field(record, "sequenceNo", "sequence_no", "SEQUENCE_NO") or "1"
        )
        self.status_input.setText(_source_field(record, "status", "STATUS") or "ACTIVE")
        self._clear_messages()
        self._refresh_form_mode()

    def _refresh_form_mode(self) -> None:
        has_record = self._source_record_id is not None
        view_only = has_record and not self._edit_mode

        self.connection_combo.setEnabled(not view_only)
        self.alias_input.setReadOnly(view_only)
        self.sequence_input.setReadOnly(view_only)
        self.status_input.setReadOnly(view_only)
        self.sources_table.setEnabled(not self._edit_mode)

        if view_only:
            self.table_view_label.setText(self._pending_table_name or "—")
            self.table_view_label.setVisible(True)
            self.table_combo.setVisible(False)
        else:
            self.table_view_label.setVisible(False)
            self.table_combo.setVisible(True)

        self.save_btn.setEnabled((not has_record) or self._edit_mode)
        self.edit_btn.setEnabled(has_record and not self._edit_mode)
        self.new_btn.setEnabled(True)
        self.delete_btn.setEnabled(has_record and not self._edit_mode)

    def build_payload(
        self, flow_id: int | str | None, *, for_create: bool
    ) -> tuple[dict[str, Any] | None, str]:
        conn = self.connection_combo.currentData()
        if not isinstance(conn, dict):
            return None, "Connection is required."
        cid = connection_id(conn)
        if cid is None:
            return None, "Connection ID is missing."

        table_row = self.table_combo.currentData()
        table_name = extraction_table_name(table_row) if isinstance(table_row, dict) else ""
        if not table_name:
            table_name = self.table_combo.currentText().strip()
        if not table_name and self._pending_table_name:
            table_name = self._pending_table_name.strip()
        if not table_name:
            return None, "Table name is required."

        alias_name = self.alias_input.text().strip()
        if not alias_name:
            return None, "Alias name is required."

        sequence_text = self.sequence_input.text().strip() or "1"
        if not sequence_text.isdigit():
            return None, "Sequence no. must be a number."

        payload: dict[str, Any] = {
            "connectionId": int(cid) if str(cid).isdigit() else cid,
            "tableName": table_name,
            "aliasName": alias_name,
            "sequenceNo": int(sequence_text),
            "status": self.status_input.text().strip() or "ACTIVE",
        }
        if for_create:
            if flow_id is None:
                return None, "Select a flow using Switch Flow first."
            payload["flowId"] = int(flow_id) if str(flow_id).isdigit() else flow_id
        return payload, ""

    def create_source(self) -> tuple[bool, str]:
        if self._flow_id is None:
            return False, "Select a flow using Switch Flow first."
        payload, err = self.build_payload(self._flow_id, for_create=True)
        if payload is None:
            return False, err or "Source configuration is incomplete."
        result = self._service.save_transformation_source(payload)
        if not result.get("success"):
            return False, str(result.get("message") or "Failed to save source configuration.")
        if self._flow_id is not None:
            ok, msg = self.load_sources(self._flow_id)
            if not ok:
                return False, msg
        self._show_success(str(result.get("message") or "Source configuration saved."))
        return True, ""

    def update_source(self) -> tuple[bool, str]:
        if self._source_record_id is None:
            return False, "Source configuration is incomplete."
        payload, err = self.build_payload(self._flow_id, for_create=False)
        if payload is None:
            return False, err or "Source configuration is incomplete."
        result = self._service.update_transformation_source(self._source_record_id, payload)
        if not result.get("success"):
            return False, str(result.get("message") or "Failed to update source configuration.")
        if self._flow_id is not None:
            ok, msg = self.load_sources(self._flow_id)
            if not ok:
                return False, msg
            self._select_row_by_id(self._source_record_id)
        self._edit_mode = False
        self._refresh_form_mode()
        self._show_success(str(result.get("message") or "Source configuration updated."))
        return True, ""

    def save_source(self) -> tuple[bool, str]:
        if self._source_record_id is not None and self._edit_mode:
            return self.update_source()
        if self._source_record_id is not None and not self._edit_mode:
            return True, ""
        return self.create_source()

    def _select_row_by_id(self, record_id: int | str | None) -> None:
        if record_id is None:
            return
        target = str(record_id).strip()
        for row in range(self.sources_table.rowCount()):
            item = self.sources_table.item(row, 0)
            if item is None:
                continue
            record = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(record, dict):
                continue
            row_id = transformation_record_id(record, "id", "sourceId", "source_id", "ID")
            if row_id is not None and str(row_id).strip() == target:
                self.sources_table.selectRow(row)
                self._apply_record(record)
                break

    def _on_row_selected(self) -> None:
        if self._loading_selection or self._edit_mode:
            return
        rows = self.sources_table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.sources_table.item(rows[0].row(), 0)
        if item is None:
            return
        record = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(record, dict):
            self._apply_record(record)

    def _on_new(self) -> None:
        self._source_record_id = None
        self._edit_mode = True
        self._pending_table_name = None
        self._loading_selection = True
        self.sources_table.clearSelection()
        self._loading_selection = False
        self._clear_form()
        self._clear_messages()
        if self.connection_combo.count() > 0:
            self._on_connection_changed()
        self._refresh_form_mode()

    def _on_edit(self) -> None:
        if self._source_record_id is None:
            return
        self._edit_mode = True
        self._pending_table_name = (
            transformation_table_name(
                next(
                    (
                        r
                        for r in self._sources
                        if transformation_record_id(r, "id", "sourceId", "source_id", "ID")
                        == self._source_record_id
                    ),
                    {},
                )
            )
            or self.table_view_label.text().strip()
            or None
        )
        if self._pending_table_name == "—":
            self._pending_table_name = None
        self._clear_messages()
        self._refresh_form_mode()
        self._on_connection_changed()

    def _on_save(self) -> None:
        ok, msg = self.save_source()
        if not ok:
            self._show_error(msg)

    def _on_delete(self) -> None:
        if self._source_record_id is None:
            return
        reply = QMessageBox.question(
            self,
            "Delete source table",
            "Delete the selected source table configuration?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = self._service.delete_transformation_source(self._source_record_id)
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Failed to delete source configuration."))
            return
        if self._flow_id is not None:
            ok, msg = self.load_sources(self._flow_id)
            if not ok:
                self._show_error(msg)
                return
        self._show_success(str(result.get("message") or "Source configuration deleted."))

    def _on_connection_changed(self) -> None:
        if self._source_record_id is not None and not self._edit_mode:
            return
        self.table_combo.clear()
        self._extracted_tables = []
        conn = self.connection_combo.currentData()
        if not isinstance(conn, dict):
            return
        cid = connection_id(conn)
        ok, rows, msg = self._service.load_extracted_metadata_tables(cid)
        if not ok:
            self._show_error(msg)
            if self._pending_table_name:
                pending = self._pending_table_name
                self.table_combo.addItem(pending, {"tableName": pending})
                self.table_combo.setCurrentIndex(0)
                self._pending_table_name = None
            return
        self._clear_messages()
        self._extracted_tables = rows
        select_index = -1
        combo_index = 0
        pending = self._pending_table_name
        for row in rows:
            name = extraction_table_name(row)
            if name:
                self.table_combo.addItem(name, row)
                if pending and name == pending:
                    select_index = combo_index
                combo_index += 1
        if pending and select_index < 0:
            existing = self.table_combo.findText(pending)
            if existing < 0:
                self.table_combo.addItem(pending, {"tableName": pending})
                select_index = self.table_combo.count() - 1
            else:
                select_index = existing
        if select_index >= 0:
            self.table_combo.setCurrentIndex(select_index)
            self._pending_table_name = None

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(bool(message))
        if message:
            self._success_label.clear()
            self._success_label.setVisible(False)

    def _show_success(self, message: str) -> None:
        self._success_label.setText(message)
        self._success_label.setVisible(bool(message))
        if message:
            self._error_label.clear()
            self._error_label.setVisible(False)

    def _clear_messages(self) -> None:
        self._error_label.clear()
        self._error_label.setVisible(False)
        self._success_label.clear()
        self._success_label.setVisible(False)
