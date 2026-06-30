"""Wizard step 3: source-to-target column mappings."""

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
    transformation_record_id,
    transformation_source_alias,
)
from ui.data_table import apply_data_table_appearance, attach_table_copy_shortcut
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
)


def _column_field(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _column_option_name(record: dict[str, Any]) -> str:
    return _column_field(
        record, "columnName", "column_name", "COLUMN_NAME", "fieldName", "name"
    )


def _column_option_type(record: dict[str, Any]) -> str:
    return _column_field(record, "dataType", "data_type", "DATA_TYPE", "type")


def _normalize_data_type(value: str) -> str:
    text = value.strip()
    return text.upper() if text else ""


class StepColumnStepWidget(QWidget):
    def __init__(self, service: TransformationDataService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._flow_id: int | str | None = None
        self._columns: list[dict[str, Any]] = []
        self._alias_entries: list[dict[str, Any]] = []
        self._alias_entry_by_alias: dict[str, dict[str, Any]] = {}
        self._columns_by_alias: dict[str, list[dict[str, Any]]] = {}
        self._column_option_rows: dict[str, dict[str, Any]] = {}
        self._column_record_id: int | str | None = None
        self._edit_mode = False
        self._loading_selection = False
        self._pending_source_column: str | None = None
        self._target_linked_to_source = True

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        card = QFrame()
        card.setObjectName("dtCard")
        card.setStyleSheet(CARD_STYLE)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(10)

        title = QLabel("Column mapping")
        title.setStyleSheet(PANEL_TITLE_STYLE)
        card_layout.addWidget(title)

        hint = QLabel(
            "Select a source alias and column. Target column and data type are filled "
            "automatically from the source column; rename the target if needed."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(PANEL_HINT_STYLE)
        card_layout.addWidget(hint)

        list_lbl = QLabel("Mapped columns")
        list_lbl.setStyleSheet(PANEL_TITLE_STYLE)
        card_layout.addWidget(list_lbl)

        self.columns_table = QTableWidget(0, 5)
        self.columns_table.setHorizontalHeaderLabels(
            ["Source alias", "Source column", "Target column", "Data type", "Status"]
        )
        apply_data_table_appearance(self.columns_table, read_only=True, hide_vertical_header=True)
        self.columns_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.columns_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.columns_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.columns_table.setMinimumHeight(140)
        attach_table_copy_shortcut(self.columns_table)
        card_layout.addWidget(self.columns_table)

        form = QFormLayout()
        form.setSpacing(10)

        self._alias_cell = QWidget()
        alias_cell_layout = QHBoxLayout(self._alias_cell)
        alias_cell_layout.setContentsMargins(0, 0, 0, 0)
        alias_cell_layout.setSpacing(0)
        self.source_alias_view_label = QLabel("—")
        self.source_alias_view_label.setMinimumWidth(280)
        self.source_alias_view_label.setStyleSheet("color: #0f172a;")
        self.source_alias_combo = QComboBox()
        self.source_alias_combo.setMinimumWidth(280)
        alias_cell_layout.addWidget(self.source_alias_view_label)
        alias_cell_layout.addWidget(self.source_alias_combo, 1)
        form.addRow("Source alias", self._alias_cell)

        self._source_column_cell = QWidget()
        source_column_cell_layout = QHBoxLayout(self._source_column_cell)
        source_column_cell_layout.setContentsMargins(0, 0, 0, 0)
        source_column_cell_layout.setSpacing(0)
        self.source_column_view_label = QLabel("—")
        self.source_column_view_label.setMinimumWidth(280)
        self.source_column_view_label.setStyleSheet("color: #0f172a;")
        self.source_column_combo = QComboBox()
        self.source_column_combo.setMinimumWidth(280)
        self.source_column_combo.setPlaceholderText("Select source column")
        source_column_cell_layout.addWidget(self.source_column_view_label)
        source_column_cell_layout.addWidget(self.source_column_combo, 1)
        form.addRow("Source column", self._source_column_cell)

        self.target_column_input = QLineEdit()
        self.target_column_input.setPlaceholderText("Defaults to source column name")
        self.target_column_input.setMinimumWidth(280)
        form.addRow("Target column", self.target_column_input)

        self.data_type_input = QLineEdit()
        self.data_type_input.setPlaceholderText("e.g. VARCHAR")
        form.addRow("Data type", self.data_type_input)

        self.status_input = QLineEdit("ACTIVE")
        form.addRow("Status", self.status_input)

        card_layout.addLayout(form)

        action_row = QHBoxLayout()
        action_row.addStretch()
        self.new_btn = QPushButton("New")
        self.delete_all_btn = QPushButton("Delete all")
        self.save_btn = QPushButton("Save")
        self.edit_btn = QPushButton("Edit")
        for btn in (self.new_btn, self.delete_all_btn, self.edit_btn):
            btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self.save_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self.edit_btn.setEnabled(False)
        action_row.addWidget(self.new_btn)
        action_row.addWidget(self.delete_all_btn)
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

        self.columns_table.itemSelectionChanged.connect(self._on_row_selected)
        self.source_alias_combo.currentIndexChanged.connect(self._on_source_alias_changed)
        self.source_column_combo.currentIndexChanged.connect(self._on_source_column_changed)
        self.target_column_input.textEdited.connect(self._on_target_column_edited)
        self.new_btn.clicked.connect(self._on_new)
        self.delete_all_btn.clicked.connect(self._on_delete_all)
        self.save_btn.clicked.connect(self._on_save)
        self.edit_btn.clicked.connect(self._on_edit)

    def set_flow_id(self, flow_id: int | str | None) -> None:
        self._flow_id = flow_id

    def reset(self) -> None:
        self._flow_id = None
        self._columns = []
        self._alias_entries = []
        self._alias_entry_by_alias = {}
        self._columns_by_alias = {}
        self._column_option_rows = {}
        self._column_record_id = None
        self._edit_mode = False
        self._pending_source_column = None
        self._populate_source_alias_combo([])
        self._populate_source_column_combo([])
        self._clear_form()
        self._refresh_table()
        self._clear_messages()
        self._refresh_form_mode()

    def setup_status(self) -> tuple[str, bool]:
        count = len(self._columns)
        if count == 0:
            return "No column mappings yet — click New, map columns, then Save.", False
        suffix = "s" if count != 1 else ""
        return f"{count} column mapping{suffix} configured.", True

    def load_columns(self, flow_id: int | str) -> tuple[bool, str]:
        ok, rows, msg = self._service.load_transformation_columns_by_flow(flow_id)
        if not ok:
            return False, msg
        self._columns = rows

        ok, alias_entries, columns_by_alias, msg = self._service.load_source_column_options_for_flow(
            flow_id
        )
        if not ok:
            return False, msg
        self._alias_entries = alias_entries
        self._alias_entry_by_alias = {
            str(entry.get("alias") or "").strip(): entry
            for entry in alias_entries
            if str(entry.get("alias") or "").strip()
        }
        self._columns_by_alias = columns_by_alias
        self._populate_source_alias_combo(alias_entries)
        if not alias_entries:
            self._show_error("No source aliases found. Configure source tables in the Source step first.")

        self._refresh_table()
        self._on_new()
        return True, ""

    def _populate_source_alias_combo(self, alias_entries: list[dict[str, Any]]) -> None:
        current_alias = ""
        current_data = self.source_alias_combo.currentData()
        if isinstance(current_data, str):
            current_alias = current_data.strip()
        self.source_alias_combo.blockSignals(True)
        self.source_alias_combo.clear()
        self.source_alias_combo.addItem("Select source alias…", "")
        for entry in alias_entries:
            alias = str(entry.get("alias") or "").strip()
            if not alias:
                continue
            self.source_alias_combo.addItem(alias, alias)
        if current_alias:
            index = self.source_alias_combo.findData(current_alias)
            if index >= 0:
                self.source_alias_combo.setCurrentIndex(index)
        self.source_alias_combo.blockSignals(False)

    def _selected_alias_entry(self) -> dict[str, Any] | None:
        alias = self.source_alias_combo.currentData()
        if isinstance(alias, str) and alias.strip():
            return self._alias_entry_by_alias.get(alias.strip())
        return None

    def _populate_source_column_combo(
        self, options: list[dict[str, Any]], *, selected_column: str | None = None
    ) -> None:
        self._column_option_rows = {}
        self.source_column_combo.blockSignals(True)
        self.source_column_combo.clear()
        self.source_column_combo.addItem("Select source column…", "")
        select_index = 0
        combo_index = 1
        for row in options:
            name = _column_option_name(row)
            if not name:
                continue
            self._column_option_rows[name] = row
            self.source_column_combo.addItem(name, name)
            if selected_column and name == selected_column:
                select_index = combo_index
            combo_index += 1
        self.source_column_combo.setCurrentIndex(select_index)
        self.source_column_combo.blockSignals(False)
        if select_index > 0:
            name = self.source_column_combo.currentData()
            if isinstance(name, str) and name.strip():
                self._apply_source_column_defaults(name.strip())

    def _infer_alias_for_column(self, source_column: str) -> str:
        matches: list[str] = []
        target = source_column.strip()
        if not target:
            return ""
        for alias, rows in self._columns_by_alias.items():
            for row in rows:
                if _column_option_name(row) == target:
                    if alias not in matches:
                        matches.append(alias)
                    break
        if len(matches) == 1:
            return matches[0]
        return ""

    def _set_source_alias_combo(self, alias: str | None) -> None:
        if not alias:
            self.source_alias_combo.setCurrentIndex(0)
            self._populate_source_column_combo([])
            return
        index = self.source_alias_combo.findData(alias.strip())
        if index >= 0:
            self.source_alias_combo.setCurrentIndex(index)
            return
        self.source_alias_combo.setCurrentIndex(0)

    def _set_source_column_combo(self, column_name: str | None) -> None:
        if not column_name:
            return
        index = self.source_column_combo.findText(column_name)
        if index >= 0:
            self.source_column_combo.setCurrentIndex(index)

    def _on_source_alias_changed(self) -> None:
        if self._column_record_id is not None and not self._edit_mode:
            return
        alias = self.source_alias_combo.currentData()
        if not isinstance(alias, str) or not alias.strip():
            self._populate_source_column_combo([])
            return
        options = self._columns_by_alias.get(alias.strip(), [])
        pending = self._pending_source_column
        self._populate_source_column_combo(options, selected_column=pending)
        self._pending_source_column = None

    def _apply_source_column_defaults(self, column_name: str) -> None:
        row = self._column_option_rows.get(column_name.strip())
        data_type = _normalize_data_type(_column_option_type(row)) if isinstance(row, dict) else ""
        if data_type:
            self.data_type_input.setText(data_type)
        if self._target_linked_to_source:
            self.target_column_input.blockSignals(True)
            self.target_column_input.setText(column_name.strip())
            self.target_column_input.blockSignals(False)

    def _on_target_column_edited(self, _text: str) -> None:
        if self._column_record_id is not None and not self._edit_mode:
            return
        self._target_linked_to_source = False

    def _on_source_column_changed(self) -> None:
        if self._column_record_id is not None and not self._edit_mode:
            return
        column_name = self.source_column_combo.currentData()
        if not isinstance(column_name, str) or not column_name.strip():
            return
        self._apply_source_column_defaults(column_name.strip())

    def _refresh_table(self) -> None:
        self._loading_selection = True
        self.columns_table.setRowCount(len(self._columns))
        for row_index, record in enumerate(self._columns):
            values = (
                _column_field(record, "sourceAlias", "source_alias", "SOURCE_ALIAS"),
                _column_field(record, "sourceColumn", "source_column", "SOURCE_COLUMN"),
                _column_field(record, "targetColumn", "target_column", "TARGET_COLUMN"),
                _column_field(record, "dataType", "data_type", "DATA_TYPE"),
                _column_field(record, "status", "STATUS") or "ACTIVE",
            )
            for col_index, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, record)
                self.columns_table.setItem(row_index, col_index, item)
        self.columns_table.clearSelection()
        self._loading_selection = False

    def _clear_form(self) -> None:
        self._target_linked_to_source = True
        self._set_source_alias_combo(None)
        self.source_alias_view_label.setText("—")
        self.source_column_view_label.setText("—")
        self.target_column_input.clear()
        self.data_type_input.clear()
        self.status_input.setText("ACTIVE")

    def _apply_record(self, record: dict[str, Any]) -> None:
        self._column_record_id = transformation_record_id(
            record, "id", "columnId", "column_id", "ID"
        )
        self._edit_mode = False
        alias = _column_field(record, "sourceAlias", "source_alias", "SOURCE_ALIAS")
        if not alias:
            alias = transformation_source_alias(record)
        source_column = _column_field(record, "sourceColumn", "source_column", "SOURCE_COLUMN")
        if not alias and source_column:
            alias = self._infer_alias_for_column(source_column)
        self._pending_source_column = source_column or None
        self._set_source_alias_combo(alias or None)
        self.source_alias_view_label.setText(alias or "—")
        self._on_source_alias_changed()
        if source_column:
            self._set_source_column_combo(source_column)
            self.source_column_view_label.setText(source_column)
        self.target_column_input.setText(
            _column_field(record, "targetColumn", "target_column", "TARGET_COLUMN")
        )
        self.data_type_input.setText(
            _normalize_data_type(_column_field(record, "dataType", "data_type", "DATA_TYPE"))
        )
        self.status_input.setText(_column_field(record, "status", "STATUS") or "ACTIVE")
        target_column = _column_field(record, "targetColumn", "target_column", "TARGET_COLUMN")
        self._target_linked_to_source = not target_column or target_column == source_column
        self._clear_messages()
        self._refresh_form_mode()

    def _refresh_form_mode(self) -> None:
        has_record = self._column_record_id is not None
        view_only = has_record and not self._edit_mode

        if view_only:
            alias_text = str(self.source_alias_combo.currentData() or "").strip()
            if not alias_text:
                alias_text = self.source_alias_view_label.text().strip() or "—"
            self.source_alias_view_label.setText(alias_text)
            self.source_alias_view_label.setVisible(True)
            self.source_alias_combo.setVisible(False)

            column_text = self.source_column_combo.currentText()
            if self.source_column_combo.currentIndex() <= 0:
                column_text = self.source_column_view_label.text() or "—"
            self.source_column_view_label.setText(column_text)
            self.source_column_view_label.setVisible(True)
            self.source_column_combo.setVisible(False)
        else:
            self.source_alias_view_label.setVisible(False)
            self.source_alias_combo.setVisible(True)
            self.source_column_view_label.setVisible(False)
            self.source_column_combo.setVisible(True)

        self.source_alias_combo.setEnabled(not view_only)
        self.source_column_combo.setEnabled(not view_only)
        self.target_column_input.setReadOnly(view_only)
        self.data_type_input.setReadOnly(view_only)
        self.status_input.setReadOnly(view_only)
        self.columns_table.setEnabled(not self._edit_mode)

        self.save_btn.setEnabled((not has_record) or self._edit_mode)
        self.edit_btn.setEnabled(has_record and not self._edit_mode)
        self.new_btn.setEnabled(True)
        self.delete_all_btn.setEnabled(bool(self._columns))

    def build_payload(
        self, flow_id: int | str | None, *, for_create: bool
    ) -> tuple[dict[str, Any] | None, str]:
        entry = self._selected_alias_entry()
        source_alias = str(entry.get("alias") or "").strip() if isinstance(entry, dict) else ""
        if not source_alias:
            current = self.source_alias_combo.currentData()
            source_alias = current.strip() if isinstance(current, str) else ""
            if source_alias == "Select source alias…":
                source_alias = ""
        column_row = self.source_column_combo.currentData()
        source_column = column_row.strip() if isinstance(column_row, str) else ""
        if not source_column:
            source_column = self.source_column_combo.currentText().strip()
            if source_column in ("Select source column…", ""):
                source_column = ""
        target_column = self.target_column_input.text().strip()
        data_type = self.data_type_input.text().strip()
        if not source_alias or source_alias == "Select source alias…":
            return None, "Source alias is required."
        if not source_column:
            return None, "Source column is required."
        if not target_column:
            return None, "Target column is required."
        if not data_type:
            return None, "Data type is required."
        payload: dict[str, Any] = {
            "sourceAlias": source_alias,
            "sourceColumn": source_column,
            "targetColumn": target_column,
            "dataType": data_type,
            "status": self.status_input.text().strip() or "ACTIVE",
        }
        if for_create:
            if flow_id is None:
                return None, "Select a flow using Switch Flow first."
            payload["flowId"] = int(flow_id) if str(flow_id).isdigit() else flow_id
        return payload, ""

    def create_column(self) -> tuple[bool, str]:
        if self._flow_id is None:
            return False, "Select a flow using Switch Flow first."
        if not self._alias_entries:
            return False, "Configure source tables before adding column mappings."
        payload, err = self.build_payload(self._flow_id, for_create=True)
        if payload is None:
            return False, err or "Column mapping is incomplete."
        result = self._service.save_transformation_column(payload)
        if not result.get("success"):
            return False, str(result.get("message") or "Failed to save column mapping.")
        if self._flow_id is not None:
            ok, msg = self.load_columns(self._flow_id)
            if not ok:
                return False, msg
        self._show_success(str(result.get("message") or "Column mapping saved."))
        return True, ""

    def update_column(self) -> tuple[bool, str]:
        if self._flow_id is None:
            return False, "Select a flow using Switch Flow first."
        if self._column_record_id is None:
            return False, "Column mapping is incomplete."
        payload, err = self.build_payload(self._flow_id, for_create=False)
        if payload is None:
            return False, err or "Column mapping is incomplete."
        result = self._service.update_transformation_column(self._column_record_id, payload)
        if not result.get("success"):
            return False, str(result.get("message") or "Failed to update column mapping.")
        if self._flow_id is not None:
            ok, msg = self.load_columns(self._flow_id)
            if not ok:
                return False, msg
            self._select_row_by_id(self._column_record_id)
        self._edit_mode = False
        self._refresh_form_mode()
        self._show_success(str(result.get("message") or "Column mapping updated."))
        return True, ""

    def save_column(self) -> tuple[bool, str]:
        if self._column_record_id is not None and self._edit_mode:
            return self.update_column()
        if self._column_record_id is not None and not self._edit_mode:
            return True, ""
        return self.create_column()

    def _select_row_by_id(self, record_id: int | str | None) -> None:
        if record_id is None:
            return
        target = str(record_id).strip()
        for row in range(self.columns_table.rowCount()):
            item = self.columns_table.item(row, 0)
            if item is None:
                continue
            record = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(record, dict):
                continue
            row_id = transformation_record_id(record, "id", "columnId", "column_id", "ID")
            if row_id is not None and str(row_id).strip() == target:
                self.columns_table.selectRow(row)
                self._apply_record(record)
                break

    def _on_row_selected(self) -> None:
        if self._loading_selection or self._edit_mode:
            return
        rows = self.columns_table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.columns_table.item(rows[0].row(), 0)
        if item is None:
            return
        record = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(record, dict):
            self._apply_record(record)

    def _on_new(self) -> None:
        self._column_record_id = None
        self._edit_mode = True
        self._pending_source_column = None
        self._loading_selection = True
        self.columns_table.clearSelection()
        self._loading_selection = False
        self._clear_form()
        self._clear_messages()
        self._refresh_form_mode()

    def _on_edit(self) -> None:
        if self._column_record_id is None:
            return
        self._edit_mode = True
        target_column = self.target_column_input.text().strip()
        source_column = self.source_column_view_label.text().strip()
        if source_column == "—":
            source_column = ""
        self._target_linked_to_source = not target_column or target_column == source_column
        self._pending_source_column = source_column or None
        alias = self.source_alias_view_label.text().strip()
        if alias and alias != "—":
            self._set_source_alias_combo(alias)
            self._on_source_alias_changed()
            if self._pending_source_column:
                self._set_source_column_combo(self._pending_source_column)
        self._clear_messages()
        self._refresh_form_mode()

    def _on_save(self) -> None:
        ok, msg = self.save_column()
        if not ok:
            self._show_error(msg)

    def _on_delete_all(self) -> None:
        if self._flow_id is None:
            self._show_error("Select a flow using Switch Flow first.")
            return
        if not self._columns:
            return
        reply = QMessageBox.question(
            self,
            "Delete all columns",
            "Delete all column mappings for this flow?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = self._service.delete_transformation_columns_by_flow(self._flow_id)
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Failed to delete column mappings."))
            return
        ok, msg = self.load_columns(self._flow_id)
        if not ok:
            self._show_error(msg)
            return
        self._show_success(str(result.get("message") or "Column mappings deleted."))

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
