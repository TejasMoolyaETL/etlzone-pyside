"""Step 2: select target connection, table, and columns."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.etl.data_transformation.constants import CARD_STYLE, PANEL_HINT_STYLE, PANEL_TITLE_STYLE
from app.etl.data_transformation.models import TransformationState
from ui.form_page_styles import FORM_SECONDARY_BUTTON_STYLESHEET


class TargetStepWidget(QWidget):
    load_tables_requested = Signal()
    load_columns_requested = Signal()
    target_connection_changed = Signal()
    target_table_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QFrame()
        card.setObjectName("dtCard")
        card.setStyleSheet(CARD_STYLE)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(14, 12, 14, 12)
        cl.setSpacing(10)

        title = QLabel("Target table")
        title.setStyleSheet(PANEL_TITLE_STYLE)
        cl.addWidget(title)
        hint = QLabel("Select the target connection and imported table to receive mapped output fields.")
        hint.setWordWrap(True)
        hint.setStyleSheet(PANEL_HINT_STYLE)
        cl.addWidget(hint)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Connection"))
        self.conn_combo = QComboBox()
        self.conn_combo.setMinimumWidth(260)
        row1.addWidget(self.conn_combo, 1)
        self.load_tables_btn = QPushButton("Load tables")
        self.load_tables_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        row1.addWidget(self.load_tables_btn)
        cl.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Table"))
        self.table_combo = QComboBox()
        self.table_combo.setMinimumWidth(280)
        row2.addWidget(self.table_combo, 1)
        self.load_columns_btn = QPushButton("Load columns")
        self.load_columns_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        row2.addWidget(self.load_columns_btn)
        cl.addLayout(row2)

        self.summary_label = QLabel("No target table selected.")
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet(PANEL_HINT_STYLE)
        cl.addWidget(self.summary_label)
        cl.addStretch()

        root.addWidget(card, 1)

        self.load_tables_btn.clicked.connect(self.load_tables_requested.emit)
        self.load_columns_btn.clicked.connect(self.load_columns_requested.emit)
        self.conn_combo.currentIndexChanged.connect(self.target_connection_changed.emit)
        self.table_combo.currentIndexChanged.connect(self.target_table_changed.emit)

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
        self.table_combo.clear()
        for name in names:
            self.table_combo.addItem(name, name)

    def current_table_name(self) -> str:
        return str(self.table_combo.currentData() or self.table_combo.currentText() or "").strip()

    def set_column_summary(self, table: str, column_count: int) -> None:
        self.summary_label.setText(f"Target: {table} — {column_count} column(s) loaded.")

    def apply_state(self, state: TransformationState) -> None:
        if state.target_connection:
            idx = self.conn_combo.findData(state.target_connection)
            if idx >= 0:
                self.conn_combo.setCurrentIndex(idx)
        if state.target_table:
            idx = self.table_combo.findText(state.target_table)
            if idx >= 0:
                self.table_combo.setCurrentIndex(idx)
