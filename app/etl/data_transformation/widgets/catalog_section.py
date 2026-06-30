"""Read-only catalog table for Object, Job, and Work Flow sections."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.etl.data_transformation.constants import CARD_STYLE, PANEL_HINT_STYLE, PANEL_TITLE_STYLE
from ui.data_table import (
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    configure_data_table_header,
    format_data_table_cell,
    resize_data_table_columns_to_content,
)
from ui.form_page_styles import FORM_PAGE_FONT_SIZE_PX, FORM_SECONDARY_BUTTON_STYLESHEET


def _cell_text(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return ""


def _value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for key in keys:
        if key in row and row.get(key) is not None:
            return (row.get(key), key)
    return (None, keys[0] if keys else "")


class CatalogSectionWidget(QWidget):
    """List + detail panel for a transformation catalog level."""

    refresh_requested = Signal()
    add_requested = Signal()
    edit_requested = Signal(object)
    delete_requested = Signal(object)

    def __init__(
        self,
        *,
        section_title: str,
        section_hint: str,
        column_spec: tuple[tuple[str, tuple[str, ...]], ...],
        rows: list[dict[str, Any]] | None = None,
        enable_crud: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._column_spec = column_spec
        self._rows = list(rows or [])
        self._enable_crud = enable_crud
        self._detail_keys: tuple[tuple[str, str], ...] = (
            ("Description", "description"),
            ("Status", "status"),
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        title = QLabel(section_title)
        title.setStyleSheet(PANEL_TITLE_STYLE)
        root.addWidget(title)

        hint = QLabel(section_hint)
        hint.setWordWrap(True)
        hint.setStyleSheet(PANEL_HINT_STYLE)
        root.addWidget(hint)

        if enable_crud:
            toolbar = QHBoxLayout()
            toolbar.addStretch()
            for label, slot in (
                ("Refresh", self.refresh_requested.emit),
                ("New", self.add_requested.emit),
                ("Edit", self._emit_edit),
                ("Delete", self._emit_delete),
            ):
                btn = QPushButton(label)
                btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
                btn.clicked.connect(slot)
                toolbar.addWidget(btn)
                if label == "Edit":
                    self._edit_btn = btn
                elif label == "Delete":
                    self._delete_btn = btn
            self._edit_btn.setEnabled(False)
            self._delete_btn.setEnabled(False)
            root.addLayout(toolbar)

        card = QFrame()
        card.setObjectName("dtCard")
        card.setStyleSheet(CARD_STYLE)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(12, 10, 12, 10)
        card_layout.setSpacing(8)

        self.table = QTableWidget(0, len(column_spec))
        self.table.setHorizontalHeaderLabels([label for label, _ in column_spec])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        apply_data_table_appearance(self.table)
        configure_data_table_header(self.table)
        attach_table_copy_shortcut(self.table)
        card_layout.addWidget(self.table, 1)

        detail_bar = QFrame()
        detail_bar.setObjectName("dtSummary")
        detail_bar.setStyleSheet(
            "QFrame#dtSummary { background: #f8fafc; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 8px; }"
        )
        detail_layout = QVBoxLayout(detail_bar)
        detail_layout.setContentsMargins(10, 8, 10, 8)
        detail_layout.setSpacing(4)
        self.detail_title = QLabel("Select a row to view details.")
        self.detail_title.setStyleSheet(
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 600; color: #334155;"
        )
        detail_layout.addWidget(self.detail_title)
        self.detail_body = QLabel("")
        self.detail_body.setWordWrap(True)
        self.detail_body.setStyleSheet(PANEL_HINT_STYLE)
        detail_layout.addWidget(self.detail_body)
        card_layout.addWidget(detail_bar)

        root.addWidget(card, 1)

        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.set_rows(self._rows)

    def _emit_edit(self) -> None:
        row = self._selected_row()
        if row:
            self.edit_requested.emit(row)

    def _emit_delete(self) -> None:
        row = self._selected_row()
        if row:
            self.delete_requested.emit(row)

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        self._rows = list(rows)
        self.table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            for col_index, (_, keys) in enumerate(self._column_spec):
                text = _cell_text(row, keys)
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(row_index, col_index, item)
        resize_data_table_columns_to_content(
            self.table,
            list(self._column_spec),
            self._rows,
            _value_for_column,
            format_data_table_cell,
        )
        if self._rows:
            self.table.selectRow(0)
        else:
            self._show_detail(None)

    def _selected_row(self) -> dict[str, Any] | None:
        items = self.table.selectedItems()
        if not items:
            return None
        data = items[0].data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _on_selection_changed(self) -> None:
        row = self._selected_row()
        if self._enable_crud:
            enabled = row is not None
            self._edit_btn.setEnabled(enabled)
            self._delete_btn.setEnabled(enabled)
        self._show_detail(row)

    def _show_detail(self, row: dict[str, Any] | None) -> None:
        if not row:
            self.detail_title.setText("Select a row to view details.")
            self.detail_body.setText("")
            return
        primary = _cell_text(row, self._column_spec[0][1])
        self.detail_title.setText(primary or "—")
        parts: list[str] = []
        for label, key in self._detail_keys:
            value = str(row.get(key) or "").strip()
            if value:
                parts.append(f"{label}: {value}")
        for label, keys in self._column_spec[1:]:
            value = _cell_text(row, keys)
            if value:
                parts.append(f"{label}: {value}")
        self.detail_body.setText("\n".join(parts) if parts else "No additional details.")
