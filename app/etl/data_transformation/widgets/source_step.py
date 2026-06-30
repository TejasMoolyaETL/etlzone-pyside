"""Step 1: select source connection and imported tables."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.etl.data_transformation.constants import CARD_STYLE, PANEL_HINT_STYLE, PANEL_TITLE_STYLE
from app.etl.data_transformation.models import TransformationState
from ui.data_table import apply_data_table_appearance, attach_table_copy_shortcut
from ui.form_page_styles import FORM_SECONDARY_BUTTON_STYLESHEET


class SourceStepWidget(QWidget):
    load_tables_requested = Signal()
    source_connection_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        card = QFrame()
        card.setObjectName("dtCard")
        card.setStyleSheet(CARD_STYLE)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(8)

        title = QLabel("Source (imported tables)")
        title.setStyleSheet(PANEL_TITLE_STYLE)
        cl.addWidget(title)
        hint = QLabel(
            "Choose the connection and one or more imported tables that feed the transformation."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(PANEL_HINT_STYLE)
        cl.addWidget(hint)

        row = QHBoxLayout()
        row.addWidget(QLabel("Connection"))
        self.conn_combo = QComboBox()
        self.conn_combo.setMinimumWidth(260)
        row.addWidget(self.conn_combo, 1)
        self.load_btn = QPushButton("Load tables")
        self.load_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        row.addWidget(self.load_btn)
        cl.addLayout(row)

        self.tables_table = QTableWidget(0, 2)
        self.tables_table.setHorizontalHeaderLabels(["", "Table name"])
        apply_data_table_appearance(self.tables_table, read_only=False, hide_vertical_header=True)
        self.tables_table.setColumnWidth(0, 40)
        self.tables_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        attach_table_copy_shortcut(self.tables_table)
        cl.addWidget(self.tables_table, 1)

        self.selection_label = QLabel("0 table(s) selected")
        self.selection_label.setStyleSheet(PANEL_HINT_STYLE)
        cl.addWidget(self.selection_label)

        root.addWidget(card, 1)

        self.load_btn.clicked.connect(self.load_tables_requested.emit)
        self.conn_combo.currentIndexChanged.connect(self.source_connection_changed.emit)
        self.tables_table.itemChanged.connect(self._on_item_changed)

    def set_connections(self, connections: list) -> None:
        self.conn_combo.blockSignals(True)
        self.conn_combo.clear()
        for conn in connections:
            from app.etl.data_transformation.metadata_helpers import connection_label

            label = connection_label(conn) or str(conn.get("id", ""))
            if label:
                self.conn_combo.addItem(label, conn)
        self.conn_combo.blockSignals(False)

    def current_connection(self):
        data = self.conn_combo.currentData()
        return data if isinstance(data, dict) else None

    def set_table_names(self, names: list[str]) -> None:
        self.tables_table.setRowCount(len(names))
        for row, name in enumerate(names):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check.setCheckState(Qt.CheckState.Unchecked)
            self.tables_table.setItem(row, 0, check)
            item = QTableWidgetItem(name)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.tables_table.setItem(row, 1, item)
        self._update_selection_label()

    def selected_tables(self) -> list[str]:
        selected: list[str] = []
        for row in range(self.tables_table.rowCount()):
            check = self.tables_table.item(row, 0)
            name_item = self.tables_table.item(row, 1)
            if check and name_item and check.checkState() == Qt.CheckState.Checked:
                name = name_item.text().strip()
                if name:
                    selected.append(name)
        return selected

    def apply_state(self, state: TransformationState) -> None:
        if state.source_connection:
            idx = self.conn_combo.findData(state.source_connection)
            if idx >= 0:
                self.conn_combo.setCurrentIndex(idx)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            self._update_selection_label()

    def _update_selection_label(self) -> None:
        n = len(self.selected_tables())
        self.selection_label.setText(f"{n} table(s) selected")
