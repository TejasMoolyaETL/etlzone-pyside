"""Dialog shown when import-metadata field check reports a mismatch."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.data_table import apply_data_table_appearance, attach_table_copy_shortcut
from ui.form_page_styles import FORM_PAGE_FONT_SIZE_PX
from ui.theme import Theme


class ImportFieldMismatchDialog(QDialog):
    """Shows FIELD MISMATCH rows.

    Import flow: Yes/No — user may proceed with import anyway.
    Scan flow (``warning_only=True``): OK only — informational warning.
    """

    def __init__(
        self,
        parent: QWidget | None,
        *,
        message: str,
        rows: list[dict[str, Any]],
        warning_only: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Field mismatch")
        self.setModal(True)
        self.setMinimumSize(480, 320)
        self.setStyleSheet("QDialog { background: #ffffff; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        intro = QLabel(
            message.strip()
            or "Column definitions do not match. Review the details below."
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: {Theme.TEXT_PRIMARY};"
        )
        layout.addWidget(intro)

        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Column name", "Table"])
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        apply_data_table_appearance(table, read_only=True, stretch_last_section=True)
        attach_table_copy_shortcut(table)

        for row in rows:
            if not isinstance(row, dict):
                continue
            col_name = str(
                row.get("column_name") or row.get("columnName") or row.get("COLUMN_NAME") or ""
            ).strip()
            table_name = str(
                row.get("msg") or row.get("table") or row.get("tableName") or row.get("TABLE_NAME") or ""
            ).strip()
            r_index = table.rowCount()
            table.insertRow(r_index)
            for c, text in enumerate((col_name, table_name)):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(r_index, c, item)

        if table.rowCount() == 0:
            table.setRowCount(1)
            for c, text in enumerate(("--", "--")):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                table.setItem(0, c, item)

        layout.addWidget(table, 1)

        if warning_only:
            buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
            buttons.accepted.connect(self.accept)
        else:
            prompt = QLabel("Do you want to import anyway?")
            prompt.setStyleSheet(
                f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: {Theme.TEXT_SECONDARY};"
            )
            layout.addWidget(prompt)
            buttons = QDialogButtonBox(
                QDialogButtonBox.StandardButton.Yes | QDialogButtonBox.StandardButton.No
            )
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
