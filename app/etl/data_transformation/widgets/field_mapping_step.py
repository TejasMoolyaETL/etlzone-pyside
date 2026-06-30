"""Step 3: source → target field mapping (redesigned BODS-style layout)."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.etl.data_transformation.constants import (
    CARD_STYLE,
    MAPPING_TABLE_HEADERS,
    PANEL_HINT_STYLE,
    PANEL_TITLE_STYLE,
    SUMMARY_BAR_STYLE,
)
from app.etl.data_transformation.mapping_logic import mapping_from_source_field
from app.etl.data_transformation.models import FieldMappingRow, TransformationState
from ui.data_table import apply_data_table_appearance, attach_table_copy_shortcut
from ui.form_page_styles import FORM_PRIMARY_BUTTON_STYLESHEET, FORM_SECONDARY_BUTTON_STYLESHEET


class FieldMappingStepWidget(QWidget):
    auto_map_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._state: TransformationState | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        summary = QFrame()
        summary.setObjectName("dtSummary")
        summary.setStyleSheet(SUMMARY_BAR_STYLE)
        sl = QHBoxLayout(summary)
        sl.setContentsMargins(14, 10, 14, 10)
        self.flow_label = QLabel("Source → Target")
        self.flow_label.setStyleSheet("font-size: 12px; font-weight: 600; color: #0f172a;")
        sl.addWidget(self.flow_label, 1)
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet(PANEL_HINT_STYLE)
        sl.addWidget(self.stats_label)
        root.addWidget(summary)

        tools = QHBoxLayout()
        self.map_selected_btn = QPushButton("Map selected field →")
        self.map_selected_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self.add_row_btn = QPushButton("Add row")
        self.add_row_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self.auto_map_btn = QPushButton("Auto-map all targets")
        self.auto_map_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self.remove_btn = QPushButton("Remove selected")
        self.remove_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self.clear_btn = QPushButton("Clear all")
        self.clear_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        tools.addWidget(self.map_selected_btn)
        tools.addWidget(self.add_row_btn)
        tools.addWidget(self.auto_map_btn)
        tools.addWidget(self.remove_btn)
        tools.addWidget(self.clear_btn)
        tools.addStretch()
        root.addLayout(tools)

        split = QSplitter(Qt.Orientation.Horizontal)

        # --- Source tree ---
        src_card = QFrame()
        src_card.setStyleSheet(CARD_STYLE)
        src_l = QVBoxLayout(src_card)
        src_l.setContentsMargins(10, 10, 10, 10)
        src_title = QLabel("Source fields")
        src_title.setStyleSheet(PANEL_TITLE_STYLE)
        src_l.addWidget(src_title)
        src_hint = QLabel("Double-click a field to add a mapping row.")
        src_hint.setWordWrap(True)
        src_hint.setStyleSheet(PANEL_HINT_STYLE)
        src_l.addWidget(src_hint)
        self.source_tree = QTreeWidget()
        self.source_tree.setHeaderHidden(True)
        self.source_tree.setAlternatingRowColors(True)
        src_l.addWidget(self.source_tree, 1)
        split.addWidget(src_card)

        # --- Mapping grid ---
        map_card = QFrame()
        map_card.setStyleSheet(CARD_STYLE)
        map_l = QVBoxLayout(map_card)
        map_l.setContentsMargins(10, 10, 10, 10)
        map_title = QLabel("Field mappings")
        map_title.setStyleSheet(PANEL_TITLE_STYLE)
        map_l.addWidget(map_title)
        map_hint = QLabel("Each row links source column(s) to a target output column.")
        map_hint.setWordWrap(True)
        map_hint.setStyleSheet(PANEL_HINT_STYLE)
        map_l.addWidget(map_hint)
        self.mapping_table = QTableWidget(0, len(MAPPING_TABLE_HEADERS))
        self.mapping_table.setHorizontalHeaderLabels(list(MAPPING_TABLE_HEADERS))
        apply_data_table_appearance(self.mapping_table, read_only=False, stretch_last_section=True)
        self.mapping_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        attach_table_copy_shortcut(self.mapping_table)
        map_l.addWidget(self.mapping_table, 1)
        split.addWidget(map_card)

        # --- Target list ---
        tgt_card = QFrame()
        tgt_card.setStyleSheet(CARD_STYLE)
        tgt_l = QVBoxLayout(tgt_card)
        tgt_l.setContentsMargins(10, 10, 10, 10)
        tgt_title = QLabel("Target columns")
        tgt_title.setStyleSheet(PANEL_TITLE_STYLE)
        tgt_l.addWidget(tgt_title)
        self.target_table = QTableWidget(0, 2)
        self.target_table.setHorizontalHeaderLabels(["Column", "Status"])
        apply_data_table_appearance(self.target_table, read_only=True, hide_vertical_header=True)
        self.target_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        attach_table_copy_shortcut(self.target_table)
        tgt_l.addWidget(self.target_table, 1)
        split.addWidget(tgt_card)

        split.setSizes([240, 520, 200])
        root.addWidget(split, 1)

        self.map_selected_btn.clicked.connect(self._map_selected_field)
        self.add_row_btn.clicked.connect(self._add_empty_row)
        self.auto_map_btn.clicked.connect(self.auto_map_requested.emit)
        self.remove_btn.clicked.connect(self._remove_selected_rows)
        self.clear_btn.clicked.connect(self._clear_mappings)
        self.source_tree.itemDoubleClicked.connect(self._on_source_double_click)

    def bind_state(self, state: TransformationState) -> None:
        self._state = state
        self._refresh_summary()
        self._populate_source_tree()
        self._populate_target_status()
        self._render_mapping_table()

    def set_mappings(self, rows: list[FieldMappingRow]) -> None:
        if self._state is None:
            return
        self._state.mappings = list(rows)
        self._render_mapping_table()
        self._populate_target_status()
        self._refresh_summary()

    def collect_mappings(self) -> list[FieldMappingRow]:
        rows: list[FieldMappingRow] = []
        for r in range(self.mapping_table.rowCount()):
            row = self._read_mapping_row(r)
            if row.target_column or row.source_column or row.source_table:
                rows.append(row)
        return rows

    def _refresh_summary(self) -> None:
        if not self._state:
            return
        src = ", ".join(self._state.source_tables) or "—"
        tgt = self._state.target_table or "—"
        self.flow_label.setText(
            f"{self._state.source_connection_label()} · [{src}]  →  "
            f"{self._state.target_connection_label()} · {tgt}"
        )
        mapped = self._state.mapped_target_count()
        total = len(self._state.target_columns)
        self.stats_label.setText(f"{mapped} / {total} target columns mapped")

    def _populate_source_tree(self) -> None:
        self.source_tree.clear()
        if not self._state:
            return
        for table, cols in sorted(self._state.source_columns.items()):
            table_item = QTreeWidgetItem([table])
            table_item.setData(0, Qt.ItemDataRole.UserRole, {"table": table, "column": ""})
            for col in cols:
                child = QTreeWidgetItem([col])
                child.setData(0, Qt.ItemDataRole.UserRole, {"table": table, "column": col})
                table_item.addChild(child)
            self.source_tree.addTopLevelItem(table_item)
            table_item.setExpanded(True)

    def _populate_target_status(self) -> None:
        self.target_table.setRowCount(0)
        if not self._state:
            return
        mapped_targets = {m.target_column for m in self._state.mappings if m.target_column}
        for col in self._state.target_columns:
            row = self.target_table.rowCount()
            self.target_table.insertRow(row)
            name_item = QTableWidgetItem(col)
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            status = "Mapped" if col in mapped_targets else "Unmapped"
            status_item = QTableWidgetItem(status)
            status_item.setFlags(status_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if status == "Mapped":
                status_item.setForeground(QColor("#166534"))
            else:
                status_item.setForeground(QColor("#b45309"))
            self.target_table.setItem(row, 0, name_item)
            self.target_table.setItem(row, 1, status_item)

    def _render_mapping_table(self) -> None:
        if not self._state:
            return
        self.mapping_table.setRowCount(len(self._state.mappings))
        for row_index, mapping in enumerate(self._state.mappings):
            self._write_mapping_row(row_index, mapping)
        self._refresh_summary()

    def _combo(self, items: list[str], current: str = "") -> QComboBox:
        combo = QComboBox()
        combo.addItem("", "")
        for item in items:
            combo.addItem(item, item)
        if current:
            idx = combo.findText(current)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.addItem(current, current)
                combo.setCurrentText(current)
        return combo

    def _source_tables(self) -> list[str]:
        return list(self._state.source_columns.keys()) if self._state else []

    def _columns_for_table(self, table: str) -> list[str]:
        if not self._state:
            return []
        return list(self._state.source_columns.get(table, []))

    def _write_mapping_row(self, row_index: int, mapping: FieldMappingRow) -> None:
        tgt_combo = self._combo(list(self._state.target_columns if self._state else []), mapping.target_column)
        tbl_combo = self._combo(self._source_tables(), mapping.source_table)
        col_combo = self._combo(self._columns_for_table(mapping.source_table), mapping.source_column)

        def on_table_change(_text: str) -> None:
            tbl = tbl_combo.currentText()
            col_combo.blockSignals(True)
            col_combo.clear()
            col_combo.addItem("", "")
            for c in self._columns_for_table(tbl):
                col_combo.addItem(c, c)
            col_combo.blockSignals(False)

        def on_col_change(_text: str) -> None:
            tbl = tbl_combo.currentText()
            col = col_combo.currentText()
            expr_item = self.mapping_table.cellWidget(row_index, 3)
            out_item = self.mapping_table.cellWidget(row_index, 4)
            if isinstance(expr_item, QLineEdit) and tbl and col:
                expr_item.setText(f"{tbl}.{col}")
            if isinstance(out_item, QLineEdit) and col and not out_item.text().strip():
                out_item.setText(col)

        tbl_combo.currentTextChanged.connect(on_table_change)
        col_combo.currentTextChanged.connect(on_col_change)

        expr_edit = QLineEdit(mapping.expression)
        out_edit = QLineEdit(mapping.output_name or mapping.target_column)

        self.mapping_table.setCellWidget(row_index, 0, tgt_combo)
        self.mapping_table.setCellWidget(row_index, 1, tbl_combo)
        self.mapping_table.setCellWidget(row_index, 2, col_combo)
        self.mapping_table.setCellWidget(row_index, 3, expr_edit)
        self.mapping_table.setCellWidget(row_index, 4, out_edit)

    def _read_mapping_row(self, row_index: int) -> FieldMappingRow:
        def text_from(col: int) -> str:
            w = self.mapping_table.cellWidget(row_index, col)
            if isinstance(w, QComboBox):
                return w.currentText().strip()
            if isinstance(w, QLineEdit):
                return w.text().strip()
            item = self.mapping_table.item(row_index, col)
            return item.text().strip() if item else ""

        return FieldMappingRow(
            target_column=text_from(0),
            source_table=text_from(1),
            source_column=text_from(2),
            expression=text_from(3),
            output_name=text_from(4),
        )

    def _selected_source_field(self) -> tuple[str, str] | None:
        item = self.source_tree.currentItem()
        if item is None:
            return None
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return None
        table = str(data.get("table") or "").strip()
        column = str(data.get("column") or "").strip()
        if table and column:
            return table, column
        return None

    def _map_selected_field(self) -> None:
        sel = self._selected_source_field()
        if not sel or not self._state:
            return
        table, column = sel
        if self._state:
            row = mapping_from_source_field(self._state, table, column)
            self._state.mappings.insert(0, row)
            self._render_mapping_table()
            self._populate_target_status()

    def _on_source_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict) or not self._state:
            return
        table = str(data.get("table") or "").strip()
        column = str(data.get("column") or "").strip()
        if not table or not column:
            return
        self._state.mappings.insert(0, mapping_from_source_field(self._state, table, column))
        self._render_mapping_table()
        self._populate_target_status()

    def _add_empty_row(self) -> None:
        if self._state is None:
            return
        self._state.mappings.append(FieldMappingRow())
        self._render_mapping_table()

    def _remove_selected_rows(self) -> None:
        if self._state is None:
            return
        rows = sorted({i.row() for i in self.mapping_table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self._state.mappings):
                del self._state.mappings[r]
        self._render_mapping_table()
        self._populate_target_status()

    def _clear_mappings(self) -> None:
        if self._state:
            self._state.mappings = []
        self._render_mapping_table()
        self._populate_target_status()
