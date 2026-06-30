"""Wizard step 4: join configurations between source tables."""

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
    transformation_table_name,
)
from ui.data_table import apply_data_table_appearance, attach_table_copy_shortcut
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
)


def _join_field(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _source_id(record: dict[str, Any]) -> int | str | None:
    return transformation_record_id(record, "id", "sourceId", "source_id", "ID")


def _source_label(record: dict[str, Any]) -> str:
    alias = _join_field(record, "aliasName", "alias_name", "ALIAS_NAME")
    table = transformation_table_name(record) or _join_field(
        record, "tableName", "table_name", "TABLE_NAME"
    )
    source_id = _source_id(record)
    if alias and table:
        return f"{alias} — {table}"
    if alias:
        return alias
    if table:
        return table
    return str(source_id) if source_id is not None else ""


class StepJoinStepWidget(QWidget):
    def __init__(self, service: TransformationDataService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._flow_id: int | str | None = None
        self._sources: list[dict[str, Any]] = []
        self._source_labels: dict[str, str] = {}
        self._all_source_columns: list[str] = []
        self._columns_by_source_id: dict[str, list[str]] = {}
        self._joins: list[dict[str, Any]] = []
        self._join_record_id: int | str | None = None
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

        title = QLabel("Join configuration")
        title.setStyleSheet(PANEL_TITLE_STYLE)
        card_layout.addWidget(title)

        hint = QLabel(
            "Define joins between configured source tables. Select left and right sources, "
            "then pick join columns from mappings added in the Column step."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(PANEL_HINT_STYLE)
        card_layout.addWidget(hint)

        list_lbl = QLabel("Configured joins")
        list_lbl.setStyleSheet(PANEL_TITLE_STYLE)
        card_layout.addWidget(list_lbl)

        self.joins_table = QTableWidget(0, 7)
        self.joins_table.setHorizontalHeaderLabels(
            [
                "Join type",
                "Left source",
                "Left column",
                "Right source",
                "Right column",
                "Sequence",
                "Status",
            ]
        )
        apply_data_table_appearance(self.joins_table, read_only=True, hide_vertical_header=True)
        self.joins_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.joins_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.joins_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.joins_table.setMinimumHeight(140)
        attach_table_copy_shortcut(self.joins_table)
        card_layout.addWidget(self.joins_table)

        form = QFormLayout()
        form.setSpacing(10)

        self.left_source_combo = QComboBox()
        self.left_source_combo.setMinimumWidth(280)
        form.addRow("Left source", self.left_source_combo)

        self.left_column_combo = QComboBox()
        self.left_column_combo.setMinimumWidth(280)
        self.left_column_view_label = QLabel("—")
        self.left_column_view_label.setMinimumWidth(280)
        self.left_column_view_label.setStyleSheet("color: #0f172a;")
        self.left_column_view_label.setVisible(False)
        left_column_cell = QWidget()
        left_column_layout = QHBoxLayout(left_column_cell)
        left_column_layout.setContentsMargins(0, 0, 0, 0)
        left_column_layout.addWidget(self.left_column_combo)
        left_column_layout.addWidget(self.left_column_view_label)
        form.addRow("Left column", left_column_cell)

        self.right_source_combo = QComboBox()
        self.right_source_combo.setMinimumWidth(280)
        form.addRow("Right source", self.right_source_combo)

        self.right_column_combo = QComboBox()
        self.right_column_combo.setMinimumWidth(280)
        self.right_column_view_label = QLabel("—")
        self.right_column_view_label.setMinimumWidth(280)
        self.right_column_view_label.setStyleSheet("color: #0f172a;")
        self.right_column_view_label.setVisible(False)
        right_column_cell = QWidget()
        right_column_layout = QHBoxLayout(right_column_cell)
        right_column_layout.setContentsMargins(0, 0, 0, 0)
        right_column_layout.addWidget(self.right_column_combo)
        right_column_layout.addWidget(self.right_column_view_label)
        form.addRow("Right column", right_column_cell)

        self.join_type_input = QLineEdit()
        self.join_type_input.setPlaceholderText("e.g. LEFT, INNER")
        self.join_type_input.setMinimumWidth(280)
        form.addRow("Join type", self.join_type_input)

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

        self.joins_table.itemSelectionChanged.connect(self._on_row_selected)
        self.left_source_combo.currentIndexChanged.connect(self._on_left_source_changed)
        self.right_source_combo.currentIndexChanged.connect(self._on_right_source_changed)
        self.new_btn.clicked.connect(self._on_new)
        self.delete_btn.clicked.connect(self._on_delete)
        self.save_btn.clicked.connect(self._on_save)
        self.edit_btn.clicked.connect(self._on_edit)

    def set_flow_id(self, flow_id: int | str | None) -> None:
        self._flow_id = flow_id

    def reset(self) -> None:
        self._flow_id = None
        self._sources = []
        self._source_labels = {}
        self._all_source_columns = []
        self._columns_by_source_id = {}
        self._joins = []
        self._join_record_id = None
        self._edit_mode = False
        self._populate_source_combos([])
        self._clear_form()
        self._refresh_table()
        self._clear_messages()
        self._refresh_form_mode()

    def load_joins(self, flow_id: int | str) -> tuple[bool, str]:
        ok, sources, msg = self._service.load_transformation_sources_by_flow(flow_id)
        if not ok:
            return False, msg
        self._sources = sources
        self._source_labels = {}
        for row in sources:
            sid = _source_id(row)
            if sid is None:
                continue
            self._source_labels[str(sid).strip()] = _source_label(row)
        self._populate_source_combos(sources)

        ok, columns, msg = self._service.load_transformation_columns_by_flow(flow_id)
        if not ok:
            return False, msg
        self._all_source_columns = self._service.build_flow_source_columns(columns)
        self._columns_by_source_id = self._service.build_mapped_columns_by_source(
            sources, columns
        )

        ok, rows, msg = self._service.load_transformation_joins_by_flow(flow_id)
        if not ok:
            return False, msg
        self._joins = rows
        self._refresh_table()
        self._on_new()
        return True, ""

    def _populate_source_combos(self, sources: list[dict[str, Any]]) -> None:
        left_id = self.left_source_combo.currentData()
        right_id = self.right_source_combo.currentData()
        for combo in (self.left_source_combo, self.right_source_combo):
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("Select source…", None)
            for row in sources:
                sid = _source_id(row)
                if sid is None:
                    continue
                combo.addItem(_source_label(row), sid)
            combo.blockSignals(False)
        self._set_source_combo(self.left_source_combo, left_id)
        self._set_source_combo(self.right_source_combo, right_id)
        self._on_left_source_changed()
        self._on_right_source_changed()

    def _column_names_for_source(self, source_id: int | str | None) -> list[str]:
        if source_id is not None:
            names = self._columns_by_source_id.get(str(source_id).strip(), [])
            if names:
                return names
        return list(self._all_source_columns)

    def _populate_column_combo(
        self,
        combo: QComboBox,
        source_id: int | str | None,
        *,
        selected: str | None = None,
    ) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("Select column…", "")
        for name in self._column_names_for_source(source_id):
            combo.addItem(name, name)
        if selected and combo.findData(selected) < 0:
            combo.addItem(selected, selected)
        combo.blockSignals(False)
        if selected:
            index = combo.findData(selected)
            combo.setCurrentIndex(index if index >= 0 else 0)
        else:
            combo.setCurrentIndex(0)

    def _on_left_source_changed(self) -> None:
        if self._loading_selection:
            return
        current = str(self.left_column_combo.currentData() or "").strip()
        self._populate_column_combo(
            self.left_column_combo,
            self.left_source_combo.currentData(),
            selected=current or None,
        )

    def _on_right_source_changed(self) -> None:
        if self._loading_selection:
            return
        current = str(self.right_column_combo.currentData() or "").strip()
        self._populate_column_combo(
            self.right_column_combo,
            self.right_source_combo.currentData(),
            selected=current or None,
        )

    def setup_status(self) -> tuple[str, bool]:
        if len(self._sources) < 2:
            return "Not required — only one source table is configured.", True
        count = len(self._joins)
        if count == 0:
            return "No joins yet — click New to add a join between your sources.", False
        suffix = "s" if count != 1 else ""
        return f"{count} join{suffix} configured.", True

    def _set_source_combo(self, combo: QComboBox, source_id: int | str | None) -> None:
        if source_id is None:
            combo.setCurrentIndex(0)
            return
        index = combo.findData(source_id)
        if index < 0:
            index = combo.findData(str(source_id).strip())
        if index < 0 and str(source_id).strip().isdigit():
            index = combo.findData(int(str(source_id).strip()))
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _source_display(self, record: dict[str, Any], *id_keys: str) -> str:
        source_id = transformation_record_id(record, *id_keys)
        if source_id is not None:
            label = self._source_labels.get(str(source_id).strip())
            if label:
                return label
        return str(source_id).strip() if source_id is not None else ""

    def _refresh_table(self) -> None:
        self._loading_selection = True
        self.joins_table.setRowCount(len(self._joins))
        for row_index, record in enumerate(self._joins):
            values = (
                _join_field(record, "joinType", "join_type", "JOIN_TYPE"),
                self._source_display(record, "leftSourceId", "left_source_id", "LEFT_SOURCE_ID"),
                _join_field(record, "leftColumn", "left_column", "LEFT_COLUMN"),
                self._source_display(record, "rightSourceId", "right_source_id", "RIGHT_SOURCE_ID"),
                _join_field(record, "rightColumn", "right_column", "RIGHT_COLUMN"),
                _join_field(record, "sequenceNo", "sequence_no", "SEQUENCE_NO") or "1",
                _join_field(record, "status", "STATUS") or "ACTIVE",
            )
            for col_index, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, record)
                self.joins_table.setItem(row_index, col_index, item)
        self.joins_table.clearSelection()
        self._loading_selection = False

    def _clear_form(self) -> None:
        self._set_source_combo(self.left_source_combo, None)
        self._set_source_combo(self.right_source_combo, None)
        self._populate_column_combo(self.left_column_combo, None)
        self._populate_column_combo(self.right_column_combo, None)
        self.left_column_view_label.setText("—")
        self.right_column_view_label.setText("—")
        self.join_type_input.clear()
        self.sequence_input.setText("1")
        self.status_input.setText("ACTIVE")

    def _apply_record(self, record: dict[str, Any]) -> None:
        self._join_record_id = transformation_record_id(
            record, "id", "joinId", "join_id", "ID"
        )
        self._edit_mode = False
        self._loading_selection = True
        left_source_id = transformation_record_id(
            record, "leftSourceId", "left_source_id", "LEFT_SOURCE_ID"
        )
        right_source_id = transformation_record_id(
            record, "rightSourceId", "right_source_id", "RIGHT_SOURCE_ID"
        )
        self._set_source_combo(self.left_source_combo, left_source_id)
        self._set_source_combo(self.right_source_combo, right_source_id)
        left_column = _join_field(record, "leftColumn", "left_column", "LEFT_COLUMN")
        right_column = _join_field(record, "rightColumn", "right_column", "RIGHT_COLUMN")
        self._populate_column_combo(
            self.left_column_combo, left_source_id, selected=left_column or None
        )
        self._populate_column_combo(
            self.right_column_combo, right_source_id, selected=right_column or None
        )
        self.left_column_view_label.setText(left_column or "—")
        self.right_column_view_label.setText(right_column or "—")
        self._loading_selection = False
        self.join_type_input.setText(_join_field(record, "joinType", "join_type", "JOIN_TYPE"))
        self.sequence_input.setText(
            _join_field(record, "sequenceNo", "sequence_no", "SEQUENCE_NO") or "1"
        )
        self.status_input.setText(_join_field(record, "status", "STATUS") or "ACTIVE")
        self._clear_messages()
        self._refresh_form_mode()

    def _refresh_form_mode(self) -> None:
        has_record = self._join_record_id is not None
        view_only = has_record and not self._edit_mode

        self.left_source_combo.setEnabled(not view_only)
        self.right_source_combo.setEnabled(not view_only)

        if view_only:
            left_text = str(self.left_column_combo.currentData() or "").strip()
            if not left_text:
                left_text = self.left_column_view_label.text().strip() or "—"
            self.left_column_view_label.setText(left_text)
            self.left_column_view_label.setVisible(True)
            self.left_column_combo.setVisible(False)

            right_text = str(self.right_column_combo.currentData() or "").strip()
            if not right_text:
                right_text = self.right_column_view_label.text().strip() or "—"
            self.right_column_view_label.setText(right_text)
            self.right_column_view_label.setVisible(True)
            self.right_column_combo.setVisible(False)
        else:
            self.left_column_view_label.setVisible(False)
            self.left_column_combo.setVisible(True)
            self.right_column_view_label.setVisible(False)
            self.right_column_combo.setVisible(True)
            self.left_column_combo.setEnabled(True)
            self.right_column_combo.setEnabled(True)

        for widget in (self.join_type_input, self.sequence_input, self.status_input):
            widget.setReadOnly(view_only)
        self.joins_table.setEnabled(not self._edit_mode)

        self.save_btn.setEnabled((not has_record) or self._edit_mode)
        self.edit_btn.setEnabled(has_record and not self._edit_mode)
        self.new_btn.setEnabled(True)
        self.delete_btn.setEnabled(has_record and not self._edit_mode)

    def build_payload(
        self, flow_id: int | str | None, *, for_create: bool
    ) -> tuple[dict[str, Any] | None, str]:
        left_source_id = self.left_source_combo.currentData()
        right_source_id = self.right_source_combo.currentData()
        left_column = str(self.left_column_combo.currentData() or "").strip()
        if not left_column:
            left_column = self.left_column_combo.currentText().strip()
            if left_column == "Select column…":
                left_column = ""
        right_column = str(self.right_column_combo.currentData() or "").strip()
        if not right_column:
            right_column = self.right_column_combo.currentText().strip()
            if right_column == "Select column…":
                right_column = ""
        join_type = self.join_type_input.text().strip()
        sequence_text = self.sequence_input.text().strip() or "1"

        if left_source_id is None:
            return None, "Left source is required."
        if right_source_id is None:
            return None, "Right source is required."
        if not left_column:
            return None, "Left column is required. Add mappings in the Column step first."
        if not right_column:
            return None, "Right column is required. Add mappings in the Column step first."
        if not join_type:
            return None, "Join type is required."
        if not sequence_text.isdigit():
            return None, "Sequence no. must be a number."

        payload: dict[str, Any] = {
            "leftSourceId": int(left_source_id)
            if str(left_source_id).isdigit()
            else left_source_id,
            "rightSourceId": int(right_source_id)
            if str(right_source_id).isdigit()
            else right_source_id,
            "leftColumn": left_column,
            "rightColumn": right_column,
            "joinType": join_type,
            "sequenceNo": int(sequence_text),
            "status": self.status_input.text().strip() or "ACTIVE",
        }
        if for_create:
            if flow_id is None:
                return None, "Select a flow using Switch Flow first."
            payload["flowId"] = int(flow_id) if str(flow_id).isdigit() else flow_id
        return payload, ""

    def create_join(self) -> tuple[bool, str]:
        if self._flow_id is None:
            return False, "Select a flow using Switch Flow first."
        if not self._sources:
            return False, "Configure at least one source table before adding joins."
        payload, err = self.build_payload(self._flow_id, for_create=True)
        if payload is None:
            return False, err or "Join configuration is incomplete."
        result = self._service.save_transformation_join(payload)
        if not result.get("success"):
            return False, str(result.get("message") or "Failed to save join configuration.")
        if self._flow_id is not None:
            ok, msg = self.load_joins(self._flow_id)
            if not ok:
                return False, msg
        self._show_success(str(result.get("message") or "Join configuration saved."))
        return True, ""

    def update_join(self) -> tuple[bool, str]:
        if self._join_record_id is None:
            return False, "Join configuration is incomplete."
        payload, err = self.build_payload(self._flow_id, for_create=False)
        if payload is None:
            return False, err or "Join configuration is incomplete."
        result = self._service.update_transformation_join(self._join_record_id, payload)
        if not result.get("success"):
            return False, str(result.get("message") or "Failed to update join configuration.")
        if self._flow_id is not None:
            ok, msg = self.load_joins(self._flow_id)
            if not ok:
                return False, msg
            self._select_row_by_id(self._join_record_id)
        self._edit_mode = False
        self._refresh_form_mode()
        self._show_success(str(result.get("message") or "Join configuration updated."))
        return True, ""

    def save_join(self) -> tuple[bool, str]:
        if self._join_record_id is not None and self._edit_mode:
            return self.update_join()
        if self._join_record_id is not None and not self._edit_mode:
            return True, ""
        return self.create_join()

    def _select_row_by_id(self, record_id: int | str | None) -> None:
        if record_id is None:
            return
        target = str(record_id).strip()
        for row in range(self.joins_table.rowCount()):
            item = self.joins_table.item(row, 0)
            if item is None:
                continue
            record = item.data(Qt.ItemDataRole.UserRole)
            if not isinstance(record, dict):
                continue
            row_id = transformation_record_id(record, "id", "joinId", "join_id", "ID")
            if row_id is not None and str(row_id).strip() == target:
                self.joins_table.selectRow(row)
                self._apply_record(record)
                break

    def _on_row_selected(self) -> None:
        if self._loading_selection or self._edit_mode:
            return
        rows = self.joins_table.selectionModel().selectedRows()
        if not rows:
            return
        item = self.joins_table.item(rows[0].row(), 0)
        if item is None:
            return
        record = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(record, dict):
            self._apply_record(record)

    def _on_new(self) -> None:
        self._join_record_id = None
        self._edit_mode = True
        self._loading_selection = True
        self.joins_table.clearSelection()
        self._loading_selection = False
        self._clear_form()
        self._clear_messages()
        self._refresh_form_mode()

    def _on_edit(self) -> None:
        if self._join_record_id is None:
            return
        self._edit_mode = True
        self._clear_messages()
        self._refresh_form_mode()

    def _on_save(self) -> None:
        ok, msg = self.save_join()
        if not ok:
            self._show_error(msg)

    def _on_delete(self) -> None:
        if self._join_record_id is None:
            return
        reply = QMessageBox.question(
            self,
            "Delete join",
            "Delete the selected join configuration?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        result = self._service.delete_transformation_join(self._join_record_id)
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Failed to delete join configuration."))
            return
        if self._flow_id is not None:
            ok, msg = self.load_joins(self._flow_id)
            if not ok:
                self._show_error(msg)
                return
        self._show_success(str(result.get("message") or "Join configuration deleted."))

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
