"""Shared QTableWidget styling and behavior for read-only data tables (Users list pattern)."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHeaderView,
    QLineEdit,
    QPlainTextEdit,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QWidget,
)

from ui.form_page_styles import DATA_TABLE_STYLESHEET, FILTER_EDIT_STYLE

DEFAULT_DATA_ROW_HEIGHT_PX = 22
MIN_DATA_COL_WIDTH_PX = 28
FILTER_ROW_HEIGHT_PX = 22
# Fixed height so every QTableWidget horizontal header matches (stylesheet padding alone varies by style).
DATA_TABLE_HORIZONTAL_HEADER_HEIGHT_PX = 24


def data_row_offset(filter_visible: bool) -> int:
    return 1 if filter_visible else 0


def clear_filter_row_widgets(table: QTableWidget) -> None:
    for c in range(table.columnCount()):
        table.removeCellWidget(0, c)


def install_filter_row(
    table: QTableWidget,
    column_count: int,
    *,
    on_text_changed: Callable[[], None],
    row_height_px: int = FILTER_ROW_HEIGHT_PX,
) -> None:
    table.setRowHeight(0, row_height_px)
    for col in range(column_count):
        w = table.cellWidget(0, col)
        if not isinstance(w, QLineEdit):
            if w is not None:
                table.removeCellWidget(0, col)
            ed = QLineEdit()
            ed.setPlaceholderText("Filter…")
            ed.setStyleSheet(FILTER_EDIT_STYLE)
            ed.setClearButtonEnabled(True)
            ed.textChanged.connect(lambda _t="", cb=on_text_changed: cb())
            table.setCellWidget(0, col, ed)


def sync_vertical_header_labels(
    table: QTableWidget,
    *,
    filter_visible: bool,
    data_row_count: int,
) -> None:
    off = data_row_offset(filter_visible)
    for r in range(table.rowCount()):
        if filter_visible and r == 0:
            table.setVerticalHeaderItem(0, QTableWidgetItem(""))
        elif r >= off and r < off + data_row_count:
            table.setVerticalHeaderItem(r, QTableWidgetItem(str(r - off + 1)))
        elif r >= off:
            table.setVerticalHeaderItem(r, QTableWidgetItem(""))


def resize_data_table_columns_to_content(
    table: QTableWidget,
    column_spec: list[tuple[str, tuple[str, ...]]],
    source_rows: list[dict[str, Any]],
    value_for_column: Callable[[dict[str, Any], tuple[str, ...]], tuple[Any, str]],
    format_cell: Callable[..., str],
    *,
    min_width_px: int = MIN_DATA_COL_WIDTH_PX,
    cell_margin_px: int = 12,
    header_margin_px: int = 18,
) -> None:
    """Set each column width from max(header label, formatted values in ``source_rows``).

    Ignores the filter row and any widgets in row 0 so toggling filters does not reshape columns.
    """
    if not column_spec or table.columnCount() < 1:
        return
    n = min(len(column_spec), table.columnCount())
    fm_cell = QFontMetrics(table.font())
    fm_header = QFontMetrics(table.horizontalHeader().font())
    for col in range(n):
        header_text, keys = column_spec[col]
        w = fm_header.horizontalAdvance(header_text) + header_margin_px
        for row in source_rows:
            if not isinstance(row, dict):
                continue
            value, key_used = value_for_column(row, keys)
            text = format_cell(value, key_used, keys)
            w = max(w, fm_cell.horizontalAdvance(text) + cell_margin_px)
        table.setColumnWidth(col, max(min_width_px, w))


def filter_dict_rows_by_column_edits(
    source_rows: list[dict[str, Any]],
    table: QTableWidget,
    column_spec: list[tuple[str, tuple[str, ...]]],
    filter_visible: bool,
    value_for_column: Callable[[dict[str, Any], tuple[str, ...]], tuple[Any, str]],
    format_cell: Callable[..., str],
) -> list[dict[str, Any]]:
    rows = list(source_rows)
    if not filter_visible or not column_spec:
        return rows
    for col, (_, keys) in enumerate(column_spec):
        w = table.cellWidget(0, col)
        if not isinstance(w, QLineEdit):
            continue
        q = w.text().strip().lower()
        if not q:
            continue

        def cell_text(row: dict[str, Any], k: tuple[str, ...] = keys) -> str:
            v, ku = value_for_column(row, k)
            return format_cell(v, ku, k).lower()

        rows = [r for r in rows if q in cell_text(r)]
    return rows


def copy_table_selection_to_clipboard(table: QTableWidget) -> None:
    """Copy selected cells as tab-separated rows (Excel-friendly)."""
    items = table.selectedItems()
    if not items:
        return
    rows: dict[int, list[tuple[int, str]]] = {}
    for item in items:
        row, col = item.row(), item.column()
        rows.setdefault(row, []).append((col, item.text()))
    lines = [
        "\t".join(t for _, t in sorted(cells, key=lambda x: x[0]))
        for _, cells in sorted(rows.items(), key=lambda x: x[0])
    ]
    QApplication.clipboard().setText("\n".join(lines))


def try_copy_from_focused_text_widget() -> bool:
    """If focus is in a text control, copy its selection (or line) and return True.

    Needed because :func:`attach_table_copy_shortcut` uses ``WidgetWithChildrenShortcut`` so Ctrl+C
    also fires while the filter-row :class:`QLineEdit` has focus; without this, the table handler
    runs first and often copies nothing.
    """
    w = QApplication.focusWidget()
    if isinstance(w, QLineEdit):
        w.copy()
        return True
    if isinstance(w, QPlainTextEdit):
        w.copy()
        return True
    if isinstance(w, QTextEdit):
        w.copy()
        return True
    return False


def attach_table_copy_shortcut(table: QTableWidget, parent: QWidget | None = None) -> QShortcut:
    """Wire StandardKey.Copy on ``parent`` (default: ``table``).

    Delegates to the focused line/plain/text edit when applicable (filter row, embedded editors),
    otherwise copies selected table cells.
    """
    target = parent or table
    sc = QShortcut(QKeySequence.StandardKey.Copy, target)
    sc.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)

    def _on_copy() -> None:
        if try_copy_from_focused_text_widget():
            return
        copy_table_selection_to_clipboard(table)

    sc.activated.connect(_on_copy)
    return sc


def apply_data_table_appearance(
    table: QTableWidget,
    *,
    read_only: bool = True,
    stretch_last_section: bool = False,
    hide_vertical_header: bool = False,
    horizontal_uniform_stretch: bool = False,
    alternating_row_colors: bool = True,
    sort_indicator_shown: bool = True,
) -> None:
    """Apply shared stylesheet, selection, and header defaults. Per-column modes may be set afterward."""
    table.setAlternatingRowColors(alternating_row_colors)
    table.setStyleSheet(DATA_TABLE_STYLESHEET)
    if read_only:
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    hh = table.horizontalHeader()
    vh = table.verticalHeader()
    if horizontal_uniform_stretch:
        for col in range(table.columnCount()):
            hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
    else:
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setStretchLastSection(stretch_last_section)
        hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
    hh.setSortIndicatorShown(sort_indicator_shown)
    hh.setFixedHeight(DATA_TABLE_HORIZONTAL_HEADER_HEIGHT_PX)
    if hide_vertical_header:
        vh.setVisible(False)
    else:
        vh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        vh.setDefaultSectionSize(DEFAULT_DATA_ROW_HEIGHT_PX)
        vh.setMinimumSectionSize(18)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
