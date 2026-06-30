"""Compact connection selector for ETL page headers."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSizePolicy, QWidget

from core.etl_connection_context import (
    etl_connection_display_label,
    etl_connection_id,
    get_etl_connection_context,
)
from ui.form_combobox_style import apply_compact_combo_popup_list
from ui.form_page_styles import APP_FONT_SIZE_PX, LIST_PAGE_HEADER_TITLE_FONT_PX

# Light field on the navy header — avoids global QComboBox white text clashing with white background.
_HEADER_PICKER_COMBO_STYLE = f"""
QComboBox {{
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 4px;
    padding: 2px 24px 2px 8px;
    min-height: 24px;
    font-size: {APP_FONT_SIZE_PX}px;
}}
QComboBox:hover {{
    border-color: #94a3b8;
}}
QComboBox:disabled {{
    color: #64748b;
    background-color: #f8fafc;
}}
QComboBox::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox QAbstractItemView {{
    background-color: #ffffff;
    color: #0f172a;
    border: 1px solid #e2e8f0;
    selection-background-color: #eef2ff;
    selection-color: #4338ca;
    outline: 0;
}}
"""


class EtlConnectionHeaderPicker(QWidget):
    """Header dropdown synced with :class:`EtlConnectionContext`."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._ctx = get_etl_connection_context()
        self._syncing = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 12, 0)
        layout.setSpacing(8)

        label = QLabel("Connection:")
        label.setStyleSheet(
            f"color: #ffffff; font-size: {LIST_PAGE_HEADER_TITLE_FONT_PX - 1}px; font-weight: 500;"
        )
        self.combo = QComboBox()
        self.combo.setMinimumWidth(220)
        self.combo.setMaximumWidth(360)
        self.combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo.setEditable(False)
        self.combo.setStyleSheet(_HEADER_PICKER_COMBO_STYLE)
        apply_compact_combo_popup_list(self.combo.view())
        self.combo.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(label)
        layout.addWidget(self.combo)

        self.combo.currentIndexChanged.connect(self._on_combo_changed)
        self._ctx.connections_changed.connect(self._rebuild_items)
        self._ctx.connection_selected.connect(self._sync_selection)
        self._rebuild_items()

    def _rebuild_items(self) -> None:
        current_id = etl_connection_id(self._ctx.current_connection())
        self._syncing = True
        try:
            self.combo.blockSignals(True)
            self.combo.clear()
            self.combo.addItem("-- Select connection --", None)
            select_index = 0
            for conn in self._ctx.connections():
                self.combo.addItem(etl_connection_display_label(conn), conn)
                if current_id is not None and etl_connection_id(conn) == current_id:
                    select_index = self.combo.count() - 1
            self.combo.setCurrentIndex(select_index)
        finally:
            self.combo.blockSignals(False)
            self._syncing = False

    def _sync_selection(self, conn: object) -> None:
        if self._syncing:
            return
        target_id = etl_connection_id(conn if isinstance(conn, dict) else None)
        self._syncing = True
        try:
            self.combo.blockSignals(True)
            if target_id is None:
                self.combo.setCurrentIndex(0)
                return
            for index in range(self.combo.count()):
                data = self.combo.itemData(index)
                if isinstance(data, dict) and etl_connection_id(data) == target_id:
                    self.combo.setCurrentIndex(index)
                    return
            self.combo.setCurrentIndex(0)
        finally:
            self.combo.blockSignals(False)
            self._syncing = False

    def _on_combo_changed(self, index: int) -> None:
        if self._syncing:
            return
        data = self.combo.itemData(index)
        conn = data if isinstance(data, dict) else None
        self._ctx.select_connection(conn)
