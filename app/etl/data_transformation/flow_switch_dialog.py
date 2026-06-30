"""Dialog to pick a work flow and flow."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from app.etl.data_transformation.data_service import TransformationDataService
from ui.form_page_styles import FORM_ERROR_LABEL_STYLE


def _record_id(row: dict[str, Any] | None, *keys: str) -> str:
    if not row:
        return ""
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _workflow_label(row: dict[str, Any]) -> str:
    for key in ("workflowName", "name"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return _record_id(row, "id", "workflowId") or "Work flow"


def _flow_label(row: dict[str, Any]) -> str:
    for key in ("flowName", "name"):
        text = str(row.get(key) or "").strip()
        if text:
            return text
    return _record_id(row, "id", "flowId") or "Flow"


class SwitchFlowDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        workflows: list[dict[str, Any]],
        service: TransformationDataService,
        current_workflow_id: str | None = None,
        current_flow_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._service = service
        self._workflows = list(workflows)
        self._flows: list[dict[str, Any]] = []
        self._selected_workflow: dict[str, Any] | None = None
        self._selected_flow: dict[str, Any] | None = None

        self.setWindowTitle("Switch Flow")
        self.setModal(True)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        self.workflow_combo = QComboBox()
        self.workflow_combo.setMinimumWidth(280)
        self.workflow_combo.addItem("Select work flow", None)
        for row in self._workflows:
            wid = _record_id(row, "id", "workflowId")
            if not wid:
                continue
            self.workflow_combo.addItem(_workflow_label(row), wid)
        form.addRow("Work flow", self.workflow_combo)

        self.flow_combo = QComboBox()
        self.flow_combo.setMinimumWidth(280)
        self.flow_combo.addItem("Select flow", None)
        form.addRow("Flow", self.flow_combo)

        root.addLayout(form)

        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error.setVisible(False)
        root.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.workflow_combo.currentIndexChanged.connect(self._on_workflow_changed)

        if current_workflow_id:
            for index in range(self.workflow_combo.count()):
                if str(self.workflow_combo.itemData(index)) == str(current_workflow_id):
                    self.workflow_combo.setCurrentIndex(index)
                    break
        if current_flow_id and self.flow_combo.count() > 1:
            for index in range(self.flow_combo.count()):
                if str(self.flow_combo.itemData(index)) == str(current_flow_id):
                    self.flow_combo.setCurrentIndex(index)
                    break

    def selection(self) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        return self._selected_workflow, self._selected_flow

    def _show_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.setVisible(bool(message))

    def _on_workflow_changed(self) -> None:
        self.flow_combo.blockSignals(True)
        self.flow_combo.clear()
        self.flow_combo.addItem("Select flow", None)
        self.flow_combo.blockSignals(False)

        wid = self.workflow_combo.currentData()
        if wid is None or str(wid).strip() == "":
            self._flows = []
            self._selected_workflow = None
            self._show_error("")
            return

        wid_text = str(wid).strip()
        self._selected_workflow = None
        for row in self._workflows:
            if _record_id(row, "id", "workflowId") == wid_text:
                self._selected_workflow = row
                break

        ok, rows, msg = self._service.load_flows_by_workflow(wid_text)
        if not ok:
            self._show_error(msg)
            return
        self._show_error("")
        self._flows = rows
        for row in rows:
            fid = _record_id(row, "id", "flowId")
            if not fid:
                continue
            self.flow_combo.addItem(_flow_label(row), fid)

    def _on_accept(self) -> None:
        if self.workflow_combo.currentData() is None:
            self._show_error("Select a work flow.")
            return
        if self.flow_combo.currentData() is None:
            self._show_error("Select a flow.")
            return

        fid = str(self.flow_combo.currentData()).strip()
        self._selected_flow = None
        for row in self._flows:
            if _record_id(row, "id", "flowId") == fid:
                self._selected_flow = row
                break
        if self._selected_flow is None:
            self._show_error("Flow is required.")
            return

        self._show_error("")
        self.accept()
