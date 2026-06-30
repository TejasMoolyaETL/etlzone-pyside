"""Dialog to pick imported tables to add to an extract group."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.data_table import apply_data_table_appearance, configure_data_table_header, format_data_table_cell
from ui.form_page_styles import FORM_ERROR_LABEL_STYLE


_TABLE_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("TABLE_NAME", ("TABLE_NAME", "tableName", "table_name", "name")),
)

_TGT_NAME_KEYS: tuple[str, ...] = (
    "TGT_TABLE_NAME",
    "tgtTableName",
    "tgt_table_name",
    "newTableName",
)


def _value_for_row(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key), key
    return None, keys[0] if keys else ""


def _format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    text = format_data_table_cell(value, key, key_candidates)
    return text if text else "--"


def table_name_from_row(row: dict[str, Any]) -> str:
    value, key_used = _value_for_row(row, _TABLE_COLUMN_SPEC[0][1])
    text = _format_cell(value, key_used, _TABLE_COLUMN_SPEC[0][1])
    return text if text and text != "--" else ""


def tgt_table_name_from_row(row: dict[str, Any]) -> str:
    value, key_used = _value_for_row(row, _TGT_NAME_KEYS)
    text = _format_cell(value, key_used, _TGT_NAME_KEYS)
    return text if text and text != "--" else ""


def build_group_table_entry(row: dict[str, Any]) -> dict[str, str]:
    return {
        "tableName": table_name_from_row(row),
        "newTableName": tgt_table_name_from_row(row),
    }


def group_table_names(group: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    raw = group.get("tableName") or group.get("tables") or group.get("tableList")
    if not isinstance(raw, list):
        return names
    for item in raw:
        if isinstance(item, str) and item.strip():
            names.add(item.strip())
            continue
        if isinstance(item, dict):
            name = str(
                item.get("tableName")
                or item.get("TABLE_NAME")
                or item.get("table_name")
                or item.get("name")
                or ""
            ).strip()
            if name:
                names.add(name)
    return names


class ExtractGroupAddTablesDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        group_name: str = "",
        tables: list[dict[str, Any]],
        checked_table_names: set[str] | frozenset[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Tables to Group")
        self.setModal(True)
        self.setMinimumSize(520, 420)

        self._tables = [dict(row) for row in tables if isinstance(row, dict)]
        self._initial_checked = frozenset(checked_table_names or set())
        self._rendering = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = group_name.strip() or "Extract group"
        hint = QLabel(
            f"Select tables to add to \"{title}\". Tables already in the group are checked."
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        header_row = QHBoxLayout()
        self._select_all = QCheckBox("Select all")
        self._select_all.stateChanged.connect(self._on_select_all_changed)
        header_row.addWidget(self._select_all)
        header_row.addStretch()
        root.addLayout(header_row)

        self._table = QTableWidget(0, len(_TABLE_COLUMN_SPEC) + 1)
        self._table.setHorizontalHeaderLabels([""] + [label for label, _ in _TABLE_COLUMN_SPEC])
        apply_data_table_appearance(self._table, read_only=True, stretch_last_section=True)
        configure_data_table_header(self._table, stretch_last=True)
        self._table.setColumnWidth(0, 40)
        self._table.itemChanged.connect(self._on_item_changed)
        root.addWidget(self._table, 1)

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setVisible(False)
        root.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._render_table()

    def _row_data_at(self, table_row: int) -> dict[str, Any] | None:
        name_item = self._table.item(table_row, 1)
        if name_item is None:
            return None
        row_data = name_item.data(Qt.ItemDataRole.UserRole)
        return row_data if isinstance(row_data, dict) else None

    def _render_table(self) -> None:
        self._rendering = True
        self._table.setRowCount(len(self._tables))
        for row_idx, row in enumerate(self._tables):
            table_name = table_name_from_row(row)
            check_item = QTableWidgetItem()
            check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            check_item.setCheckState(
                Qt.CheckState.Checked
                if table_name in self._initial_checked
                else Qt.CheckState.Unchecked
            )
            self._table.setItem(row_idx, 0, check_item)
            for col_idx, (_, keys) in enumerate(_TABLE_COLUMN_SPEC, start=1):
                value, key_used = _value_for_row(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self._table.setItem(row_idx, col_idx, item)
        self._rendering = False
        self._sync_select_all()

    def _sync_select_all(self) -> None:
        self._select_all.blockSignals(True)
        if self._table.rowCount() == 0:
            self._select_all.setChecked(False)
        else:
            all_checked = all(
                self._table.item(row, 0)
                and self._table.item(row, 0).checkState() == Qt.CheckState.Checked
                for row in range(self._table.rowCount())
                if self._table.item(row, 0)
            )
            self._select_all.setChecked(all_checked)
        self._select_all.blockSignals(False)

    def _on_select_all_changed(self, state: int) -> None:
        checked = Qt.CheckState(state) == Qt.CheckState.Checked
        self._rendering = True
        for row in range(self._table.rowCount()):
            check_item = self._table.item(row, 0)
            if check_item:
                check_item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._rendering = False

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if self._rendering or item.column() != 0:
            return
        self._sync_select_all()

    def newly_checked_table_entries(self) -> list[dict[str, str]]:
        entries: list[dict[str, str]] = []
        for row in range(self._table.rowCount()):
            check_item = self._table.item(row, 0)
            row_data = self._row_data_at(row)
            if not check_item or check_item.checkState() != Qt.CheckState.Checked:
                continue
            if not isinstance(row_data, dict):
                continue
            table_name = table_name_from_row(row_data)
            if not table_name or table_name in self._initial_checked:
                continue
            entries.append(build_group_table_entry(row_data))
        return entries

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(bool(message))

    def _on_accept(self) -> None:
        if not self.newly_checked_table_entries():
            self._show_error("Select at least one new table to add.")
            return
        self._show_error("")
        self.accept()
