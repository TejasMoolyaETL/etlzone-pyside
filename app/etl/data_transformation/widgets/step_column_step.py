"""Wizard step 3: source-to-target column mappings."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
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


def _parse_sequence_no(text: str) -> tuple[int | None, str]:
    sequence_text = text.strip() or "1"
    if not sequence_text.isdigit():
        return None, "Sequence no. must be a number."
    return int(sequence_text), ""


class _BoundedTableWidget(QTableWidget):
    """Table that scrolls internally instead of growing the parent layout."""

    def __init__(self, *args: Any, layout_min_height: int = 120, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._layout_min_height = layout_min_height
        self.setMinimumHeight(layout_min_height)
        self.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def minimumSizeHint(self) -> QSize:
        return QSize(super().minimumSizeHint().width(), self._layout_min_height)


class StepColumnStepWidget(QWidget):
    def __init__(self, service: TransformationDataService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
        self._columns_table_rendering = False
        self._target_linked_to_source = True

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        card = QFrame()
        card.setObjectName("dtCard")
        card.setStyleSheet(CARD_STYLE)
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(8)

        title = QLabel("Column mapping")
        title.setStyleSheet(PANEL_TITLE_STYLE)
        card_layout.addWidget(title)

        hint = QLabel(
            "On the left, pick a source alias and check columns to map. "
            "On the right, review saved mappings. Click Save to add selected columns."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(PANEL_HINT_STYLE)
        card_layout.addWidget(hint)

        self._action_section = QWidget()
        self._action_section.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        action_section_layout = QVBoxLayout(self._action_section)
        action_section_layout.setContentsMargins(0, 0, 0, 0)
        action_section_layout.setSpacing(6)

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
        action_section_layout.addLayout(action_row)

        self._success_label = QLabel("")
        self._success_label.setWordWrap(True)
        self._success_label.setStyleSheet("color: #15803d;")
        self._success_label.setVisible(False)
        action_section_layout.addWidget(self._success_label)

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setVisible(False)
        action_section_layout.addWidget(self._error_label)
        card_layout.addWidget(self._action_section)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)

        self._bulk_section = QFrame()
        self._bulk_section.setFrameShape(QFrame.Shape.StyledPanel)
        self._bulk_section.setStyleSheet(
            "QFrame { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; }"
        )
        self._bulk_section.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        bulk_layout = QVBoxLayout(self._bulk_section)
        bulk_layout.setContentsMargins(10, 10, 10, 10)
        bulk_layout.setSpacing(6)

        left_title = QLabel("Source columns")
        left_title.setStyleSheet(PANEL_TITLE_STYLE)
        bulk_layout.addWidget(left_title)

        alias_row = QHBoxLayout()
        alias_row.addWidget(QLabel("Source alias"))
        self.source_alias_combo = QComboBox()
        self.source_alias_combo.setMinimumWidth(180)
        alias_row.addWidget(self.source_alias_combo, 1)
        bulk_layout.addLayout(alias_row)

        select_row = QHBoxLayout()
        self.select_all_checkbox = QCheckBox("Select all")
        select_row.addWidget(self.select_all_checkbox)
        select_row.addStretch()
        bulk_layout.addLayout(select_row)

        self.source_columns_table = _BoundedTableWidget(0, 3, layout_min_height=120)
        self.source_columns_table.setHorizontalHeaderLabels(["", "Column name", "Data type"])
        apply_data_table_appearance(
            self.source_columns_table, read_only=False, hide_vertical_header=True
        )
        self.source_columns_table.setColumnWidth(0, 40)
        self.source_columns_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.source_columns_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        attach_table_copy_shortcut(self.source_columns_table)
        bulk_layout.addWidget(self.source_columns_table, 1)

        self.selection_label = QLabel("0 column(s) selected")
        self.selection_label.setStyleSheet(PANEL_HINT_STYLE)
        bulk_layout.addWidget(self.selection_label)
        split.addWidget(self._bulk_section)

        self._right_panel = QFrame()
        self._right_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self._right_panel.setStyleSheet(
            "QFrame { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 6px; }"
        )
        self._right_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        right_layout = QVBoxLayout(self._right_panel)
        right_layout.setContentsMargins(10, 10, 10, 10)
        right_layout.setSpacing(6)

        right_title = QLabel("Mapped columns")
        right_title.setStyleSheet(PANEL_TITLE_STYLE)
        right_layout.addWidget(right_title)

        self.columns_table = _BoundedTableWidget(0, 5, layout_min_height=120)
        self.columns_table.setHorizontalHeaderLabels(
            ["Source alias", "Source column", "Target column", "Data type", "Status"]
        )
        apply_data_table_appearance(self.columns_table, read_only=True, hide_vertical_header=True)
        self.columns_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.columns_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.columns_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        attach_table_copy_shortcut(self.columns_table)
        right_layout.addWidget(self.columns_table, 1)

        self._detail_section = QWidget()
        detail_layout = QFormLayout(self._detail_section)
        detail_layout.setSpacing(10)

        self.source_alias_view_label = QLabel("—")
        self.source_alias_view_label.setMinimumWidth(200)
        self.source_alias_view_label.setStyleSheet("color: #0f172a;")
        detail_layout.addRow("Source alias", self.source_alias_view_label)

        self.source_column_view_label = QLabel("—")
        self.source_column_view_label.setMinimumWidth(200)
        self.source_column_view_label.setStyleSheet("color: #0f172a;")
        detail_layout.addRow("Source column", self.source_column_view_label)

        self.target_column_input = QLineEdit()
        self.target_column_input.setPlaceholderText("Defaults to source column name")
        self.target_column_input.setMinimumWidth(200)
        detail_layout.addRow("Target column", self.target_column_input)

        self.data_type_input = QLineEdit()
        self.data_type_input.setPlaceholderText("e.g. VARCHAR")
        detail_layout.addRow("Data type", self.data_type_input)

        self.sequence_input = QLineEdit("1")
        detail_layout.addRow("Sequence no.", self.sequence_input)

        self.status_input = QLineEdit("ACTIVE")
        detail_layout.addRow("Status", self.status_input)
        right_layout.addWidget(self._detail_section)
        split.addWidget(self._right_panel)

        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        split.setSizes([420, 420])
        card_layout.addWidget(split, 1)

        root.addWidget(card, 1)

        self.columns_table.itemSelectionChanged.connect(self._on_row_selected)
        self.source_alias_combo.currentIndexChanged.connect(self._on_source_alias_changed)
        self.source_columns_table.itemChanged.connect(self._on_source_column_item_changed)
        self.select_all_checkbox.stateChanged.connect(self._on_select_all_columns)
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
        self._populate_source_alias_combo([])
        self._populate_source_columns_table([])
        self._clear_form()
        self._refresh_table()
        self._clear_messages()
        self._refresh_form_mode()

    def setup_status(self) -> tuple[str, bool]:
        count = len(self._columns)
        if count == 0:
            return "No column mappings yet — select columns with checkboxes, then Save.", False
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

    def _mapped_columns_for_alias(self, alias: str) -> set[str]:
        mapped: set[str] = set()
        target_alias = alias.strip()
        if not target_alias:
            return mapped
        for record in self._columns:
            record_alias = _column_field(record, "sourceAlias", "source_alias", "SOURCE_ALIAS")
            if not record_alias:
                record_alias = transformation_source_alias(record)
            if record_alias.strip() != target_alias:
                continue
            source_column = _column_field(record, "sourceColumn", "source_column", "SOURCE_COLUMN")
            if source_column:
                mapped.add(source_column)
        return mapped

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

    def _populate_source_columns_table(self, options: list[dict[str, Any]], *, alias: str = "") -> None:
        self._column_option_rows = {}
        mapped = self._mapped_columns_for_alias(alias)
        self._columns_table_rendering = True
        self.source_columns_table.blockSignals(True)
        self.source_columns_table.setRowCount(0)
        for row in options:
            name = _column_option_name(row)
            if not name:
                continue
            self._column_option_rows[name] = row
            row_index = self.source_columns_table.rowCount()
            self.source_columns_table.insertRow(row_index)
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(
                Qt.CheckState.Checked if name in mapped else Qt.CheckState.Unchecked
            )
            self.source_columns_table.setItem(row_index, 0, check)
            name_item = QTableWidgetItem(name)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.source_columns_table.setItem(row_index, 1, name_item)
            type_item = QTableWidgetItem(_normalize_data_type(_column_option_type(row)))
            type_item.setFlags(type_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.source_columns_table.setItem(row_index, 2, type_item)
        self.source_columns_table.blockSignals(False)
        self._columns_table_rendering = False
        self._sync_select_all_checkbox()
        self._update_selection_label()

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
            self._populate_source_columns_table([])
            return
        index = self.source_alias_combo.findData(alias.strip())
        if index >= 0:
            self.source_alias_combo.setCurrentIndex(index)
            return
        self.source_alias_combo.setCurrentIndex(0)

    def _on_source_alias_changed(self) -> None:
        if self._column_record_id is not None and not self._edit_mode:
            return
        alias = self.source_alias_combo.currentData()
        if not isinstance(alias, str) or not alias.strip():
            self._populate_source_columns_table([])
            return
        options = self._columns_by_alias.get(alias.strip(), [])
        self._populate_source_columns_table(options, alias=alias.strip())

    def _selected_source_columns(self) -> list[str]:
        selected: list[str] = []
        for row in range(self.source_columns_table.rowCount()):
            check = self.source_columns_table.item(row, 0)
            name_item = self.source_columns_table.item(row, 1)
            if check and name_item and check.checkState() == Qt.CheckState.Checked:
                name = name_item.text().strip()
                if name:
                    selected.append(name)
        return selected

    def _update_selection_label(self) -> None:
        count = len(self._selected_source_columns())
        suffix = "s" if count != 1 else ""
        self.selection_label.setText(f"{count} column{suffix} selected")

    def _sync_select_all_checkbox(self) -> None:
        self.select_all_checkbox.blockSignals(True)
        row_count = self.source_columns_table.rowCount()
        if row_count == 0:
            self.select_all_checkbox.setChecked(False)
            self.select_all_checkbox.setEnabled(False)
        else:
            self.select_all_checkbox.setEnabled(True)
            all_checked = all(
                self.source_columns_table.item(row, 0)
                and self.source_columns_table.item(row, 0).checkState() == Qt.CheckState.Checked
                for row in range(row_count)
                if self.source_columns_table.item(row, 0)
            )
            self.select_all_checkbox.setChecked(all_checked)
        self.select_all_checkbox.blockSignals(False)

    def _on_select_all_columns(self, state: int) -> None:
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        self._columns_table_rendering = True
        for row in range(self.source_columns_table.rowCount()):
            check_item = self.source_columns_table.item(row, 0)
            if check_item:
                check_item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._columns_table_rendering = False
        self._update_selection_label()

    def _on_source_column_item_changed(self, item: QTableWidgetItem) -> None:
        if self._columns_table_rendering or item.column() != 0:
            return
        self._update_selection_label()
        self._sync_select_all_checkbox()

    def _on_target_column_edited(self, _text: str) -> None:
        if self._column_record_id is not None and not self._edit_mode:
            return
        self._target_linked_to_source = False

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
        self.sequence_input.setText("1")
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
        self.source_alias_view_label.setText(alias or "—")
        self.source_column_view_label.setText(source_column or "—")
        self.target_column_input.setText(
            _column_field(record, "targetColumn", "target_column", "TARGET_COLUMN")
        )
        self.data_type_input.setText(
            _normalize_data_type(_column_field(record, "dataType", "data_type", "DATA_TYPE"))
        )
        self.sequence_input.setText(
            _column_field(record, "sequenceNo", "sequence_no", "SEQUENCE_NO") or "1"
        )
        self.status_input.setText(_column_field(record, "status", "STATUS") or "ACTIVE")
        target_column = _column_field(record, "targetColumn", "target_column", "TARGET_COLUMN")
        self._target_linked_to_source = not target_column or target_column == source_column
        self._clear_messages()
        self._refresh_form_mode()

    def _refresh_form_mode(self) -> None:
        has_record = self._column_record_id is not None
        view_only = has_record and not self._edit_mode
        bulk_mode = not has_record

        self._bulk_section.setEnabled(bulk_mode)
        self._detail_section.setVisible(has_record)

        self.source_alias_combo.setEnabled(bulk_mode)
        self.source_columns_table.setEnabled(bulk_mode)
        self.select_all_checkbox.setEnabled(bulk_mode and self.source_columns_table.rowCount() > 0)

        self.target_column_input.setReadOnly(view_only)
        self.data_type_input.setReadOnly(view_only)
        self.sequence_input.setReadOnly(view_only)
        self.status_input.setReadOnly(view_only)
        self.columns_table.setEnabled(not self._edit_mode)

        self.save_btn.setEnabled(bulk_mode or self._edit_mode)
        self.edit_btn.setEnabled(has_record and not self._edit_mode)
        self.new_btn.setEnabled(True)
        self.delete_all_btn.setEnabled(bool(self._columns))

    def build_payload(
        self, flow_id: int | str | None, *, for_create: bool
    ) -> tuple[dict[str, Any] | None, str]:
        source_alias = self.source_alias_view_label.text().strip()
        if source_alias == "—":
            source_alias = ""
        source_column = self.source_column_view_label.text().strip()
        if source_column == "—":
            source_column = ""
        target_column = self.target_column_input.text().strip()
        data_type = self.data_type_input.text().strip()
        if not source_alias:
            return None, "Source alias is required."
        if not source_column:
            return None, "Source column is required."
        if not target_column:
            return None, "Target column is required."
        if not data_type:
            return None, "Data type is required."
        sequence_no, seq_err = _parse_sequence_no(self.sequence_input.text())
        if sequence_no is None:
            return None, seq_err
        payload: dict[str, Any] = {
            "sourceAlias": source_alias,
            "sourceColumn": source_column,
            "targetColumn": target_column,
            "dataType": data_type,
            "sequenceNo": sequence_no,
            "status": self.status_input.text().strip() or "ACTIVE",
        }
        if for_create:
            if flow_id is None:
                return None, "Select a flow using Switch Flow first."
            payload["flowId"] = int(flow_id) if str(flow_id).isdigit() else flow_id
        return payload, ""

    def _max_sequence_no(self) -> int:
        max_seq = 0
        for record in self._columns:
            seq_text = _column_field(record, "sequenceNo", "sequence_no", "SEQUENCE_NO")
            if seq_text.isdigit():
                max_seq = max(max_seq, int(seq_text))
        return max_seq

    def _build_bulk_payload(
        self, flow_id: int | str, alias: str, source_column: str, *, sequence_no: int = 1
    ) -> dict[str, Any] | None:
        row = self._column_option_rows.get(source_column.strip())
        data_type = _normalize_data_type(_column_option_type(row)) if isinstance(row, dict) else ""
        if not data_type:
            return None
        return {
            "flowId": int(flow_id) if str(flow_id).isdigit() else flow_id,
            "sourceAlias": alias.strip(),
            "sourceColumn": source_column.strip(),
            "targetColumn": source_column.strip(),
            "dataType": data_type,
            "sequenceNo": sequence_no,
            "status": "ACTIVE",
        }

    def create_columns_bulk(self) -> tuple[bool, str]:
        if self._flow_id is None:
            return False, "Select a flow using Switch Flow first."
        if not self._alias_entries:
            return False, "Configure source tables before adding column mappings."
        alias_data = self.source_alias_combo.currentData()
        alias = alias_data.strip() if isinstance(alias_data, str) else ""
        if not alias or alias == "Select source alias…":
            return False, "Source alias is required."
        selected = self._selected_source_columns()
        if not selected:
            return False, "Select at least one column to map."
        already_mapped = self._mapped_columns_for_alias(alias)
        to_create = [name for name in selected if name not in already_mapped]
        if not to_create:
            return False, "All selected columns are already mapped for this alias."
        created = 0
        errors: list[str] = []
        sequence_no = max(self._max_sequence_no() + 1, 1)
        for source_column in to_create:
            payload = self._build_bulk_payload(
                self._flow_id, alias, source_column, sequence_no=sequence_no
            )
            sequence_no += 1
            if payload is None:
                errors.append(f"{source_column}: data type is missing.")
                continue
            result = self._service.save_transformation_column(payload)
            if result.get("success"):
                created += 1
            else:
                errors.append(
                    f"{source_column}: {result.get('message') or 'Failed to save.'}"
                )
        if created == 0:
            return False, errors[0] if errors else "Failed to save column mappings."
        if self._flow_id is not None:
            ok, msg = self.load_columns(self._flow_id)
            if not ok:
                return False, msg
        if errors:
            self._show_success(f"{created} column mapping(s) saved. Some failed: {'; '.join(errors)}")
            return True, ""
        suffix = "s" if created != 1 else ""
        self._show_success(f"{created} column mapping{suffix} saved.")
        return True, ""

    def create_column(self) -> tuple[bool, str]:
        return self.create_columns_bulk()

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
        return self.create_columns_bulk()

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
        self._edit_mode = False
        self._loading_selection = True
        self.columns_table.clearSelection()
        self._loading_selection = False
        self._clear_form()
        if self.source_alias_combo.count() > 1:
            self.source_alias_combo.setCurrentIndex(1)
            self._on_source_alias_changed()
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
