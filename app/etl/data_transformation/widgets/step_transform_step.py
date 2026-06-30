"""Wizard step 5: transform step configurations."""

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
from app.etl.data_transformation.metadata_helpers import transformation_record_id
from ui.data_table import apply_data_table_appearance, attach_table_copy_shortcut
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
)


def _step_field(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _step_master_label(record: dict[str, Any]) -> str:
    return _step_field(
        record,
        "stepMasterName",
        "stepName",
        "name",
        "description",
        "stepMasterCode",
        "code",
    )


def _column_mapping_label(record: dict[str, Any]) -> str:
    source = _step_field(record, "sourceColumn", "source_column", "SOURCE_COLUMN")
    target = _step_field(record, "targetColumn", "target_column", "TARGET_COLUMN")
    if source and target and source != target:
        return f"{source} → {target}"
    return source or target or str(
        transformation_record_id(record, "id", "columnId", "column_id", "ID") or ""
    )


class StepTransformStepWidget(QWidget):
    def __init__(self, service: TransformationDataService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._flow_id: int | str | None = None
        self._steps: list[dict[str, Any]] = []
        self._step_masters: list[dict[str, Any]] = []
        self._master_labels: dict[str, str] = {}
        self._column_mappings: list[dict[str, Any]] = []
        self._column_by_id: dict[str, dict[str, Any]] = {}
        self._step_record_id: int | str | None = None
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

        title = QLabel("Transform step configuration")
        title.setStyleSheet(PANEL_TITLE_STYLE)
        card_layout.addWidget(title)

        hint = QLabel(
            "Define transformation steps for the selected flow. Choose a step master, "
            "select a column mapping from the Column step, then set step name and sequence."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(PANEL_HINT_STYLE)
        card_layout.addWidget(hint)

        list_lbl = QLabel("Configured transform steps")
        list_lbl.setStyleSheet(PANEL_TITLE_STYLE)
        card_layout.addWidget(list_lbl)

        self.steps_table = QTableWidget(0, 6)
        self.steps_table.setHorizontalHeaderLabels(
            [
                "Step master",
                "Step name",
                "Column mapping",
                "Step value",
                "Sequence",
                "Status",
            ]
        )
        apply_data_table_appearance(self.steps_table, read_only=True, hide_vertical_header=True)
        self.steps_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.steps_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.steps_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.steps_table.setMinimumHeight(140)
        attach_table_copy_shortcut(self.steps_table)
        card_layout.addWidget(self.steps_table)

        form = QFormLayout()
        form.setSpacing(10)

        self.step_master_combo = QComboBox()
        self.step_master_combo.setMinimumWidth(280)
        form.addRow("Step master", self.step_master_combo)

        self.step_name_input = QLineEdit()
        self.step_name_input.setPlaceholderText("e.g. Trim Employee Name")
        self.step_name_input.setMinimumWidth(280)
        form.addRow("Step name", self.step_name_input)

        self.column_mapping_combo = QComboBox()
        self.column_mapping_combo.setMinimumWidth(280)
        self.column_mapping_view_label = QLabel("—")
        self.column_mapping_view_label.setMinimumWidth(280)
        self.column_mapping_view_label.setStyleSheet("color: #0f172a;")
        self.column_mapping_view_label.setVisible(False)
        column_cell = QWidget()
        column_layout = QHBoxLayout(column_cell)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.addWidget(self.column_mapping_combo)
        column_layout.addWidget(self.column_mapping_view_label)
        form.addRow("Column mapping", column_cell)

        self.step_value_input = QLineEdit()
        self.step_value_input.setPlaceholderText("Optional")
        self.step_value_input.setMinimumWidth(280)
        form.addRow("Step value", self.step_value_input)

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

        self.steps_table.itemSelectionChanged.connect(self._on_row_selected)
        self.new_btn.clicked.connect(self._on_new)
        self.delete_btn.clicked.connect(self._on_delete)
        self.save_btn.clicked.connect(self._on_save)
        self.edit_btn.clicked.connect(self._on_edit)

    def set_flow_id(self, flow_id: int | str | None) -> None:
        self._flow_id = flow_id

    def reset(self) -> None:
        self._flow_id = None
        self._steps = []
        self._step_masters = []
        self._master_labels = {}
        self._column_mappings = []
        self._column_by_id = {}
        self._step_record_id = None
        self._edit_mode = False
        self._populate_step_masters([])
        self._populate_column_mapping_combo()
        self._clear_form()
        self._refresh_table()
        self._clear_messages()
        self._refresh_form_mode()

    def setup_status(self) -> tuple[str, bool]:
        count = len(self._steps)
        if count == 0:
            return "No transform steps yet — click New to add a rule.", False
        suffix = "s" if count != 1 else ""
        return f"{count} transform step{suffix} configured.", True

    def load_step_masters(self) -> tuple[bool, str]:
        ok, rows, msg = self._service.load_transformation_step_masters()
        if not ok:
            return False, msg
        self._step_masters = rows
        self._master_labels = {}
        for row in rows:
            master_id = transformation_record_id(
                row, "id", "stepMasterId", "step_master_id", "ID"
            )
            if master_id is None:
                continue
            label = _step_master_label(row) or str(master_id)
            self._master_labels[str(master_id).strip()] = label
        self._populate_step_masters(rows)
        return True, ""

    def load_steps(self, flow_id: int | str) -> tuple[bool, str]:
        ok, msg = self.load_step_masters()
        if not ok:
            return False, msg
        ok, columns, msg = self._service.load_transformation_columns_by_flow(flow_id)
        if not ok:
            return False, msg
        self._column_mappings = columns
        self._column_by_id = {}
        for col in columns:
            cid = transformation_record_id(col, "id", "columnId", "column_id", "ID")
            if cid is not None:
                self._column_by_id[str(cid).strip()] = col
        self._populate_column_mapping_combo()
        ok, rows, msg = self._service.load_transformation_steps_by_flow(flow_id)
        if not ok:
            return False, msg
        self._steps = rows
        self._refresh_table()
        self._on_new()
        return True, ""

    def _populate_step_masters(self, rows: list[dict[str, Any]]) -> None:
        current_id = self.step_master_combo.currentData()
        self.step_master_combo.blockSignals(True)
        self.step_master_combo.clear()
        self.step_master_combo.addItem("Select step master…", None)
        for row in rows:
            master_id = transformation_record_id(
                row, "id", "stepMasterId", "step_master_id", "ID"
            )
            if master_id is None:
                continue
            label = _step_master_label(row) or str(master_id)
            self.step_master_combo.addItem(label, master_id)
        if current_id is not None:
            index = self.step_master_combo.findData(current_id)
            if index >= 0:
                self.step_master_combo.setCurrentIndex(index)
        self.step_master_combo.blockSignals(False)

    def _populate_column_mapping_combo(
        self, *, selected_id: int | str | None = None
    ) -> None:
        self.column_mapping_combo.blockSignals(True)
        self.column_mapping_combo.clear()
        self.column_mapping_combo.addItem("Select column mapping…", "")
        select_index = 0
        combo_index = 1
        selected_key = str(selected_id).strip() if selected_id is not None else ""
        for col in self._column_mappings:
            cid = transformation_record_id(col, "id", "columnId", "column_id", "ID")
            if cid is None:
                continue
            key = str(cid).strip()
            label = _column_mapping_label(col)
            self.column_mapping_combo.addItem(label, key)
            if selected_key and key == selected_key:
                select_index = combo_index
            combo_index += 1
        if selected_key and self.column_mapping_combo.findData(selected_key) < 0:
            self.column_mapping_combo.addItem(f"Column #{selected_key}", selected_key)
            select_index = self.column_mapping_combo.findData(selected_key)
        self.column_mapping_combo.setCurrentIndex(select_index)
        self.column_mapping_combo.blockSignals(False)

    def _set_column_mapping_combo(self, column_id: int | str | None) -> None:
        if column_id is None:
            self.column_mapping_combo.setCurrentIndex(0)
            return
        key = str(column_id).strip()
        index = self.column_mapping_combo.findData(key)
        if index < 0 and key.isdigit():
            index = self.column_mapping_combo.findData(int(key))
        if index < 0:
            self.column_mapping_combo.addItem(f"Column #{key}", key)
            index = self.column_mapping_combo.findData(key)
        self.column_mapping_combo.setCurrentIndex(index if index >= 0 else 0)

    def _column_display_for_step(self, record: dict[str, Any]) -> str:
        cid = transformation_record_id(
            record, "columnId", "column_id", "coumnId", "COLUMN_ID"
        )
        if cid is not None:
            mapped = self._column_by_id.get(str(cid).strip())
            if mapped is not None:
                return _column_mapping_label(mapped)
        nested = record.get("column")
        if isinstance(nested, dict):
            return _column_mapping_label(nested)
        source = _step_field(record, "sourceColumn", "source_column", "SOURCE_COLUMN")
        target = _step_field(record, "targetColumn", "target_column", "TARGET_COLUMN")
        if source and target and source != target:
            return f"{source} → {target}"
        return source or target or (str(cid) if cid is not None else "")

    def _resolve_column_id(self, record: dict[str, Any]) -> int | str | None:
        cid = transformation_record_id(
            record, "columnId", "column_id", "coumnId", "COLUMN_ID"
        )
        if cid is not None:
            return cid
        nested = record.get("column")
        if isinstance(nested, dict):
            cid = transformation_record_id(nested, "id", "columnId", "column_id", "ID")
            if cid is not None:
                return cid
        source = _step_field(record, "sourceColumn", "source_column", "SOURCE_COLUMN")
        if not source:
            return None
        for col in self._column_mappings:
            if _step_field(col, "sourceColumn", "source_column", "SOURCE_COLUMN") == source:
                return transformation_record_id(col, "id", "columnId", "column_id", "ID")
        return None

    def _master_display(self, record: dict[str, Any]) -> str:
        master_id = transformation_record_id(
            record, "stepMasterId", "step_master_id", "STEP_MASTER_ID"
        )
        if master_id is not None:
            label = self._master_labels.get(str(master_id).strip())
            if label:
                return label
        nested = record.get("stepMaster")
        if isinstance(nested, dict):
            nested_label = _step_master_label(nested)
            if nested_label:
                return nested_label
        return str(master_id).strip() if master_id is not None else ""

    def _set_step_master_combo(self, master_id: int | str | None) -> None:
        if master_id is None:
            self.step_master_combo.setCurrentIndex(0)
            return
        index = self.step_master_combo.findData(master_id)
        if index < 0:
            index = self.step_master_combo.findData(str(master_id).strip())
        if index < 0 and str(master_id).strip().isdigit():
            index = self.step_master_combo.findData(int(str(master_id).strip()))
        self.step_master_combo.setCurrentIndex(index if index >= 0 else 0)

    def _refresh_table(self) -> None:
        self._loading_selection = True
        self.steps_table.setRowCount(len(self._steps))
        for row_index, record in enumerate(self._steps):
            step_value = record.get("stepValue")
            if step_value is None:
                step_value = record.get("step_value")
            step_value_text = "" if step_value is None else str(step_value).strip()
            values = (
                self._master_display(record),
                _step_field(record, "stepName", "step_name", "STEP_NAME"),
                self._column_display_for_step(record),
                step_value_text,
                _step_field(record, "sequenceNo", "sequence_no", "SEQUENCE_NO") or "1",
                _step_field(record, "status", "STATUS") or "ACTIVE",
            )
            for col_index, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, record)
                self.steps_table.setItem(row_index, col_index, item)
        self.steps_table.clearSelection()
        self._loading_selection = False

    def _clear_form(self) -> None:
        self._set_step_master_combo(None)
        self.step_name_input.clear()
        self._populate_column_mapping_combo()
        self.column_mapping_view_label.setText("—")
        self.step_value_input.clear()
        self.sequence_input.setText("1")
        self.status_input.setText("ACTIVE")

    def _apply_record(self, record: dict[str, Any]) -> None:
        self._step_record_id = transformation_record_id(
            record, "id", "stepId", "step_id", "ID"
        )
        self._edit_mode = False
        self._loading_selection = True
        master_id = transformation_record_id(
            record, "stepMasterId", "step_master_id", "STEP_MASTER_ID"
        )
        if master_id is None:
            nested = record.get("stepMaster")
            if isinstance(nested, dict):
                master_id = transformation_record_id(
                    nested, "id", "stepMasterId", "step_master_id", "ID"
                )
        self._set_step_master_combo(master_id)
        self.step_name_input.setText(_step_field(record, "stepName", "step_name", "STEP_NAME"))
        column_id = self._resolve_column_id(record)
        self._set_column_mapping_combo(column_id)
        mapping_label = self._column_display_for_step(record)
        self.column_mapping_view_label.setText(mapping_label or "—")
        self._loading_selection = False
        step_value = record.get("stepValue")
        if step_value is None:
            step_value = record.get("step_value")
        self.step_value_input.setText("" if step_value is None else str(step_value).strip())
        self.sequence_input.setText(
            _step_field(record, "sequenceNo", "sequence_no", "SEQUENCE_NO") or "1"
        )
        self.status_input.setText(_step_field(record, "status", "STATUS") or "ACTIVE")
        self._clear_messages()
        self._refresh_form_mode()

    def _refresh_form_mode(self) -> None:
        has_record = self._step_record_id is not None
        view_only = has_record and not self._edit_mode

        self.step_master_combo.setEnabled(not view_only)

        if view_only:
            mapping_text = str(self.column_mapping_combo.currentData() or "").strip()
            if not mapping_text:
                mapping_text = self.column_mapping_view_label.text().strip() or "—"
            elif self.column_mapping_combo.currentIndex() > 0:
                mapping_text = self.column_mapping_combo.currentText()
            self.column_mapping_view_label.setText(mapping_text)
            self.column_mapping_view_label.setVisible(True)
            self.column_mapping_combo.setVisible(False)
        else:
            self.column_mapping_view_label.setVisible(False)
            self.column_mapping_combo.setVisible(True)
            self.column_mapping_combo.setEnabled(True)

        for widget in (
            self.step_name_input,
            self.step_value_input,
            self.sequence_input,
            self.status_input,
        ):
            widget.setReadOnly(view_only)
        self.steps_table.setEnabled(not self._edit_mode)

        self.save_btn.setEnabled((not has_record) or self._edit_mode)
        self.edit_btn.setEnabled(has_record and not self._edit_mode)
        self.new_btn.setEnabled(True)
        self.delete_btn.setEnabled(has_record and not self._edit_mode)

    def build_payload(
        self, flow_id: int | str | None, *, for_create: bool
    ) -> tuple[dict[str, Any] | None, str]:
        master_id = self.step_master_combo.currentData()
        if master_id is None:
            return None, "Step master is required."
        column_key = str(self.column_mapping_combo.currentData() or "").strip()
        if not column_key:
            return None, "Column mapping is required. Add mappings in the Column step first."
        step_name = self.step_name_input.text().strip()
        sequence_text = self.sequence_input.text().strip() or "1"
        if not step_name:
            return None, "Step name is required."
        if not sequence_text.isdigit():
            return None, "Sequence no. must be a number."
        step_value_text = self.step_value_input.text().strip()
        column_id: int | str = int(column_key) if column_key.isdigit() else column_key
        master_value: int | str = (
            int(master_id) if str(master_id).isdigit() else master_id
        )
        payload: dict[str, Any] = {
            "stepMasterId": master_value,
            "columnId": column_id,
            "stepName": step_name,
            "step_value": step_value_text if step_value_text else None,
            "sequenceNo": int(sequence_text),
            "status": self.status_input.text().strip() or "ACTIVE",
        }
        if for_create:
            if flow_id is None:
                return None, "Select a flow using Switch Flow first."
            payload["flowId"] = int(flow_id) if str(flow_id).isdigit() else flow_id
        return payload, ""

    def create_step(self) -> tuple[bool, str]:
        if self._flow_id is None:
            return False, "Select a flow using Switch Flow first."
        payload, err = self.build_payload(self._flow_id, for_create=True)
        if payload is None:
            return False, err or "Transform step is incomplete."
        result = self._service.save_transformation_step(payload)
        if not result.get("success"):
            return False, str(result.get("message") or "Failed to save transform step.")
        if self._flow_id is not None:
            ok, msg = self.load_steps(self._flow_id)
            if not ok:
                return False, msg
        self._show_success(str(result.get("message") or "Transform step saved."))
        return True, ""

    def update_step(self) -> tuple[bool, str]:
        if self._flow_id is None:
            return False, "Select a flow using Switch Flow first."
        if self._step_record_id is None:
            return False, "Transform step is incomplete."
        payload, err = self.build_payload(self._flow_id, for_create=False)
        if payload is None:
            return False, err or "Transform step is incomplete."
        result = self._service.update_transformation_step(self._step_record_id, payload)
        if not result.get("success"):
            return False, str(result.get("message") or "Failed to update transform step.")
        if self._flow_id is not None:
            ok, msg = self.load_steps(self._flow_id)
            if not ok:
                return False, msg
            self._select_row_by_id(self._step_record_id)
        self._edit_mode = False
        self._refresh_form_mode()
        self._show_success(str(result.get("message") or "Transform step updated."))
        return True, ""

    def save_step(self) -> tuple[bool, str]:
        if self._step_record_id is not None and self._edit_mode:
            return self.update_step()
        if self._step_record_id is not None and not self._edit_mode:
            return True, ""
        return self.create_step()

    def _select_row_by_id(self, record_id: int | str | None) -> None:
        if record_id is None:
            return
        target = str(record_id).strip()
        for row in range(self.steps_table.rowCount()):
            item = self.steps_table.item(row, 0)
            if item is None:
                continue
            record = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(record, dict):
                continue
            row_id = transformation_record_id(record, "id", "stepId", "step_id", "ID")
            if row_id is not None and str(row_id).strip() == target:
                self.steps_table.selectRow(row)
                self._apply_record(record)
                break

    def _on_row_selected(self) -> None:
        if self._loading_selection or self._edit_mode:
            return
        rows = self.steps_table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.steps_table.item(rows[0].row(), 0)
        if item is None:
            return
        record = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(record, dict):
            self._apply_record(record)

    def _on_new(self) -> None:
        self._step_record_id = None
        self._edit_mode = True
        self._loading_selection = True
        self.steps_table.clearSelection()
        self._loading_selection = False
        self._clear_form()
        self._clear_messages()
        self._refresh_form_mode()

    def _on_edit(self) -> None:
        if self._step_record_id is None:
            return
        self._edit_mode = True
        self._clear_messages()
        self._refresh_form_mode()

    def _on_save(self) -> None:
        ok, msg = self.save_step()
        if not ok:
            self._show_error(msg)

    def _on_delete(self) -> None:
        if self._step_record_id is None:
            return
        reply = QMessageBox.question(
            self,
            "Delete transform step",
            "Delete the selected transform step?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = self._service.delete_transformation_step(self._step_record_id)
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Failed to delete transform step."))
            return
        if self._flow_id is not None:
            ok, msg = self.load_steps(self._flow_id)
            if not ok:
                self._show_error(msg)
                return
        self._show_success(str(result.get("message") or "Transform step deleted."))

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
