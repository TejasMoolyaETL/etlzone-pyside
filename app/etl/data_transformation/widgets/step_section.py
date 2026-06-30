"""Step section with Switch Flow and setup wizard."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.etl.data_transformation.constants import CARD_STYLE, PANEL_HINT_STYLE, PANEL_TITLE_STYLE
from app.etl.data_transformation.data_service import TransformationDataService
from app.etl.data_transformation.widgets.step_setup_wizard import StepSetupWizardWidget
from ui.form_page_styles import FORM_PAGE_FONT_SIZE_PX, FORM_PRIMARY_BUTTON_STYLESHEET


def _record_id(row: dict[str, Any] | None, *keys: str) -> str:
    if not row:
        return ""
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


class StepSectionWidget(QWidget):
    switch_flow_requested = Signal()

    def __init__(self, service: TransformationDataService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._selected_workflow_id: str | None = None
        self._selected_workflow_name: str = ""
        self._active_flow: dict[str, Any] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        header_row = QHBoxLayout()
        title = QLabel("Step")
        title.setStyleSheet(PANEL_TITLE_STYLE)
        header_row.addWidget(title)
        header_row.addStretch()
        self.switch_flow_btn = QPushButton("Switch Flow")
        self.switch_flow_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        header_row.addWidget(self.switch_flow_btn)
        root.addLayout(header_row)

        hint = QLabel(
            "Configure a flow in five guided steps: Source → Target → Column → Join → Transform. "
            "Use Switch Flow to pick the work flow and flow you want to edit."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(PANEL_HINT_STYLE)
        root.addWidget(hint)

        self.selection_label = QLabel("No flow selected")
        self.selection_label.setWordWrap(True)
        self.selection_label.setStyleSheet(
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 600; color: #334155;"
        )
        root.addWidget(self.selection_label)

        self._empty_state = QFrame()
        self._empty_state.setObjectName("dtCard")
        self._empty_state.setStyleSheet(CARD_STYLE)
        empty_layout = QVBoxLayout(self._empty_state)
        empty_layout.setContentsMargins(24, 28, 24, 28)
        empty_layout.setSpacing(8)
        empty_title = QLabel("Get started")
        empty_title.setStyleSheet(
            f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; font-weight: 600; color: #0f172a;"
        )
        empty_layout.addWidget(empty_title)
        empty_body = QLabel(
            "1. Click Switch Flow and choose a work flow and flow.\n"
            "2. Work through each setup step using Next, or jump to a step from the breadcrumb.\n"
            "3. Save your changes on each step before moving on."
        )
        empty_body.setWordWrap(True)
        empty_body.setStyleSheet("font-size: 11px; color: #64748b; line-height: 1.4;")
        empty_layout.addWidget(empty_body)
        empty_action = QPushButton("Switch Flow…")
        empty_action.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        empty_action.clicked.connect(self.switch_flow_requested.emit)
        empty_layout.addWidget(empty_action, alignment=Qt.AlignmentFlag.AlignLeft)
        root.addWidget(self._empty_state)

        self.setup_wizard = StepSetupWizardWidget(service)
        self.setup_wizard.setVisible(False)
        root.addWidget(self.setup_wizard, 1)

        self.switch_flow_btn.clicked.connect(self.switch_flow_requested.emit)

    def set_workflows(self, workflows: list[dict[str, Any]]) -> None:
        del workflows

    def set_selection(
        self,
        workflow_id: str | None,
        workflow_name: str,
        active_flow: dict[str, Any] | None = None,
    ) -> None:
        self._selected_workflow_id = str(workflow_id).strip() if workflow_id else None
        self._selected_workflow_name = workflow_name.strip()
        self._active_flow = active_flow if isinstance(active_flow, dict) else None
        self._update_selection_label()
        flow_id = _record_id(self._active_flow, "id", "flowId")
        has_flow = bool(flow_id)
        self._empty_state.setVisible(not has_flow)
        self.setup_wizard.setVisible(has_flow)
        self.setup_wizard.set_flow_id(flow_id or None)

    def selected_workflow_id(self) -> str | None:
        return self._selected_workflow_id

    def selected_flow(self) -> dict[str, Any] | None:
        return self._active_flow

    def _update_selection_label(self) -> None:
        if not isinstance(self._active_flow, dict):
            self.selection_label.setText("No flow selected — click Switch Flow to begin.")
            return
        workflow = self._selected_workflow_name or "Work flow"
        flow_name = str(self._active_flow.get("flowName") or _record_id(self._active_flow, "id"))
        self.selection_label.setText(f"Editing: {workflow}  →  {flow_name}")
