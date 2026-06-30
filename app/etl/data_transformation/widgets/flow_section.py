"""Flow list filtered by selected work flow."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
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

_FLOW_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Flow Name", ("flowName",)),
    ("Sequence", ("sequenceNo",)),
    ("Status", ("status",)),
    ("Created At", ("createdAt", "created_at")),
)


def _workflow_id(row: dict[str, Any] | None) -> str:
    if not row:
        return ""
    for key in ("id", "workflowId", "ID"):
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _workflow_label(row: dict[str, Any]) -> str:
    for key in ("workflowName", "name"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    wid = _workflow_id(row)
    return wid or "Work flow"


def _flow_cell(row: dict[str, Any], keys: tuple[str, ...]) -> str:
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


class FlowSectionWidget(QWidget):
    refresh_requested = Signal()
    workflow_changed = Signal(str)
    add_requested = Signal()
    edit_requested = Signal(object)
    delete_requested = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._workflows: list[dict[str, Any]] = []
        self._flows: list[dict[str, Any]] = []
        self._selected_flow: dict[str, Any] | None = None
        self._pending_workflow_id: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel("Flow")
        title.setStyleSheet(PANEL_TITLE_STYLE)
        header_row.addWidget(title)
        header_row.addStretch()

        workflow_lbl = QLabel("Work Flow:")
        workflow_lbl.setStyleSheet(PANEL_HINT_STYLE)
        header_row.addWidget(workflow_lbl)
        self.workflow_combo = QComboBox()
        self.workflow_combo.setMinimumWidth(260)
        self.workflow_combo.setPlaceholderText("Select work flow")
        header_row.addWidget(self.workflow_combo)
        root.addLayout(header_row)

        hint = QLabel(
            "Choose a work flow, then view and manage the flows defined for that work flow."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(PANEL_HINT_STYLE)
        root.addWidget(hint)

        toolbar = QHBoxLayout()
        toolbar.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._new_btn = QPushButton("New")
        self._edit_btn = QPushButton("Edit")
        self._delete_btn = QPushButton("Delete")
        for btn in (self._refresh_btn, self._new_btn, self._edit_btn, self._delete_btn):
            btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
            toolbar.addWidget(btn)
        self._edit_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        root.addLayout(toolbar)

        body_row = QHBoxLayout()
        body_row.setSpacing(12)

        list_card = QFrame()
        list_card.setObjectName("dtCard")
        list_card.setStyleSheet(CARD_STYLE)
        list_layout = QVBoxLayout(list_card)
        list_layout.setContentsMargins(12, 10, 12, 10)
        list_layout.setSpacing(8)

        list_hdr = QLabel("Flows")
        list_hdr.setStyleSheet(
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 600; color: #334155;"
        )
        list_layout.addWidget(list_hdr)

        self.flow_table = QTableWidget(0, len(_FLOW_COLUMNS))
        self.flow_table.setHorizontalHeaderLabels([label for label, _ in _FLOW_COLUMNS])
        self.flow_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.flow_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.flow_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        apply_data_table_appearance(self.flow_table)
        configure_data_table_header(self.flow_table)
        attach_table_copy_shortcut(self.flow_table)
        list_layout.addWidget(self.flow_table, 1)

        body_row.addWidget(list_card, 1)
        body_row.addStretch(2)
        root.addLayout(body_row, 1)

        self._refresh_btn.clicked.connect(self.refresh_requested.emit)
        self._new_btn.clicked.connect(self.add_requested.emit)
        self._edit_btn.clicked.connect(self._emit_edit)
        self._delete_btn.clicked.connect(self._emit_delete)
        self.workflow_combo.currentIndexChanged.connect(self._on_workflow_changed)
        self.flow_table.itemSelectionChanged.connect(self._on_flow_selected)

    def set_workflows(self, workflows: list[dict[str, Any]]) -> None:
        self._workflows = list(workflows)
        current_id = self._pending_workflow_id or self.selected_workflow_id()
        self._pending_workflow_id = None

        self.workflow_combo.blockSignals(True)
        self.workflow_combo.clear()
        for row in self._workflows:
            wid = _workflow_id(row)
            if not wid:
                continue
            self.workflow_combo.addItem(_workflow_label(row), wid)
        self.workflow_combo.blockSignals(False)

        if not self._workflows:
            self.set_flows([])
            return

        index_to_select = 0
        if current_id:
            for index in range(self.workflow_combo.count()):
                if str(self.workflow_combo.itemData(index)) == current_id:
                    index_to_select = index
                    break
        self.workflow_combo.setCurrentIndex(index_to_select)
        self._on_workflow_changed()

    def set_flows(self, flows: list[dict[str, Any]]) -> None:
        self._flows = list(flows)
        self._selected_flow = None
        self._edit_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        self._populate_flows()

    def selected_workflow(self) -> dict[str, Any] | None:
        wid = self.selected_workflow_id()
        if not wid:
            return None
        for row in self._workflows:
            if _workflow_id(row) == wid:
                return row
        return None

    def selected_workflow_id(self) -> str | None:
        if self.workflow_combo.count() == 0:
            return None
        data = self.workflow_combo.currentData()
        if data is None:
            return None
        text = str(data).strip()
        return text or None

    def _on_workflow_changed(self) -> None:
        self._selected_flow = None
        self._edit_btn.setEnabled(False)
        self._delete_btn.setEnabled(False)
        wid = self.selected_workflow_id() or ""
        self.workflow_changed.emit(wid)

    def _populate_flows(self) -> None:
        self.flow_table.setRowCount(len(self._flows))
        for row_index, row in enumerate(self._flows):
            for col_index, (_, keys) in enumerate(_FLOW_COLUMNS):
                item = QTableWidgetItem(_flow_cell(row, keys))
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.flow_table.setItem(row_index, col_index, item)
        resize_data_table_columns_to_content(
            self.flow_table,
            list(_FLOW_COLUMNS),
            self._flows,
            _value_for_column,
            format_data_table_cell,
        )
        if self._flows:
            self.flow_table.selectRow(0)
        else:
            self._selected_flow = None
            self._edit_btn.setEnabled(False)
            self._delete_btn.setEnabled(False)

    def _on_flow_selected(self) -> None:
        items = self.flow_table.selectedItems()
        if not items:
            self._selected_flow = None
            self._edit_btn.setEnabled(False)
            self._delete_btn.setEnabled(False)
            return
        flow = items[0].data(Qt.ItemDataRole.UserRole)
        if not isinstance(flow, dict):
            return
        self._selected_flow = flow
        self._edit_btn.setEnabled(True)
        self._delete_btn.setEnabled(True)

    def _emit_edit(self) -> None:
        if isinstance(self._selected_flow, dict):
            self.edit_requested.emit(self._selected_flow)

    def _emit_delete(self) -> None:
        if isinstance(self._selected_flow, dict):
            self.delete_requested.emit(self._selected_flow)
