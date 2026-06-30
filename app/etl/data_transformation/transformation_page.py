"""ETL: Data Transformation — Object, Job, Work Flow, Flow, and Step sections."""

from __future__ import annotations

from typing import Any

from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QStackedWidget, QVBoxLayout, QWidget

from app.etl.data_transformation.constants import NAV_ITEM_TO_SECTION, SECTION_HINTS, SECTION_LABELS
from app.etl.data_transformation.data_service import TransformationDataService
from app.etl.data_transformation.flow_switch_dialog import SwitchFlowDialog
from app.etl.data_transformation.transformation_catalog_dialog import TransformationCatalogDialog
from app.etl.data_transformation.widgets.catalog_section import CatalogSectionWidget
from app.etl.data_transformation.widgets.flow_section import FlowSectionWidget
from app.etl.data_transformation.widgets.step_section import StepSectionWidget
from ui.form_page_styles import (
    FORM_PAGE_FONT_SIZE_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    LIST_PAGE_HEADER_TITLE_FONT_PX,
)

_OBJECT_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Object Name", ("objectName",)),
    ("Description", ("description",)),
    ("Status", ("status",)),
)

_JOB_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Job Name", ("jobName",)),
    ("Object", ("objectName", "objectId")),
    ("Description", ("description",)),
    ("Status", ("status",)),
)

_WORKFLOW_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Work Flow Name", ("workflowName",)),
    ("Job", ("jobName", "jobId")),
    ("Sequence", ("sequenceNo",)),
    ("Status", ("status",)),
)


def _record_id(row: dict[str, Any] | None) -> int | str | None:
    if not row:
        return None
    for key in ("id", "ID", "objectId", "jobId", "workflowId", "flowId"):
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


class DataTransformationPage(QWidget):
    """Left-nav selects one of Object, Job, Work Flow, Flow, or Step."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._section = 0
        self._pending_section: int | None = None
        self._service = TransformationDataService()
        self._objects: list[dict[str, Any]] = []
        self._jobs: list[dict[str, Any]] = []
        self._workflows: list[dict[str, Any]] = []
        self._flows: list[dict[str, Any]] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        self.header_title = QLabel()
        self.header_title.setStyleSheet(
            f"font-size: {LIST_PAGE_HEADER_TITLE_FONT_PX}px; font-weight: 600; color: #ffffff;"
        )
        hl.addWidget(self.header_title)
        hl.addStretch()
        root.addWidget(header)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(12, 12, 12, 12)
        bl.setSpacing(10)

        self.section_hint = QLabel()
        self.section_hint.setWordWrap(True)
        self.section_hint.setStyleSheet(f"font-size: {FORM_PAGE_FONT_SIZE_PX}px; color: #64748b;")
        bl.addWidget(self.section_hint)

        self.stack = QStackedWidget()
        self.object_section = CatalogSectionWidget(
            section_title="Transformation objects",
            section_hint="Business objects that group related jobs.",
            column_spec=_OBJECT_COLUMNS,
            enable_crud=True,
        )
        self.job_section = CatalogSectionWidget(
            section_title="Jobs",
            section_hint="Jobs under each object.",
            column_spec=_JOB_COLUMNS,
            enable_crud=True,
        )
        self.workflow_section = CatalogSectionWidget(
            section_title="Work flows",
            section_hint="Ordered sequences of flows for each job.",
            column_spec=_WORKFLOW_COLUMNS,
            enable_crud=True,
        )
        self.flow_section = FlowSectionWidget()
        self.step_section = StepSectionWidget(self._service)
        self.stack.addWidget(self.object_section)
        self.stack.addWidget(self.job_section)
        self.stack.addWidget(self.workflow_section)
        self.stack.addWidget(self.flow_section)
        self.stack.addWidget(self.step_section)
        bl.addWidget(self.stack, 1)

        root.addWidget(body, 1)
        self._wire_catalog_signals()
        self._show_section(self._section)

    def _wire_catalog_signals(self) -> None:
        self.object_section.refresh_requested.connect(self._load_objects)
        self.object_section.add_requested.connect(lambda: self._edit_catalog("object"))
        self.object_section.edit_requested.connect(lambda row: self._edit_catalog("object", row))
        self.object_section.delete_requested.connect(lambda row: self._delete_catalog("object", row))

        self.job_section.refresh_requested.connect(self._load_jobs)
        self.job_section.add_requested.connect(lambda: self._edit_catalog("job"))
        self.job_section.edit_requested.connect(lambda row: self._edit_catalog("job", row))
        self.job_section.delete_requested.connect(lambda row: self._delete_catalog("job", row))

        self.workflow_section.refresh_requested.connect(self._load_workflows)
        self.workflow_section.add_requested.connect(lambda: self._edit_catalog("workflow"))
        self.workflow_section.edit_requested.connect(lambda row: self._edit_catalog("workflow", row))
        self.workflow_section.delete_requested.connect(lambda row: self._delete_catalog("workflow", row))

        self.flow_section.refresh_requested.connect(self._refresh_flow_section)
        self.flow_section.workflow_changed.connect(self._load_flows)
        self.flow_section.add_requested.connect(lambda: self._edit_catalog("flow"))
        self.flow_section.edit_requested.connect(lambda row: self._edit_catalog("flow", row))
        self.flow_section.delete_requested.connect(lambda row: self._delete_catalog("flow", row))

        self.step_section.switch_flow_requested.connect(self._on_step_switch_flow)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._pending_section is not None:
            self.go_to_section(self._pending_section)
            self._pending_section = None
        self.refresh_all()

    def refresh_all(self) -> None:
        self._load_objects()
        self._load_jobs()
        self._load_workflows()

    def set_pending_section(self, section_index: int) -> None:
        section_index = max(0, min(len(SECTION_LABELS) - 1, section_index))
        if self.isVisible():
            self.go_to_section(section_index)
        else:
            self._pending_section = section_index

    def set_pending_step(self, section_index: int) -> None:
        self.set_pending_section(section_index)

    def go_to_section(self, section_index: int) -> None:
        section_index = max(0, min(len(SECTION_LABELS) - 1, section_index))
        self._pending_section = None
        if section_index == self._section and self.stack.currentIndex() == section_index:
            self._show_section(section_index)
            return
        self._section = section_index
        self._show_section(section_index)

    def go_to_nav_item(self, nav_item: str) -> None:
        self.go_to_section(NAV_ITEM_TO_SECTION.get(nav_item, 0))

    def current_section_index(self) -> int:
        return self._section

    def _show_section(self, index: int) -> None:
        self.header_title.setText(f"ETL: Data Transformation — {SECTION_LABELS[index]}")
        self.section_hint.setText(SECTION_HINTS[index])
        self.stack.setCurrentIndex(index)

    def _load_objects(self) -> None:
        ok, rows, msg = self._service.load_objects()
        if not ok:
            QMessageBox.warning(self, "Failed", msg)
            return
        self._objects = rows
        self.object_section.set_rows(rows)

    def _load_jobs(self) -> None:
        ok, rows, msg = self._service.load_jobs(self._objects)
        if not ok:
            QMessageBox.warning(self, "Failed", msg)
            return
        self._jobs = rows
        self.job_section.set_rows(rows)

    def _load_workflows(self) -> None:
        ok, rows, msg = self._service.load_workflows(self._jobs)
        if not ok:
            QMessageBox.warning(self, "Failed", msg)
            return
        self._workflows = rows
        self.workflow_section.set_rows(rows)
        self.flow_section.set_workflows(rows)
        self.step_section.set_workflows(rows)

    def _workflow_name(self, workflow_id: str | None) -> str:
        if not workflow_id:
            return ""
        wid = str(workflow_id).strip()
        for row in self._workflows:
            row_id = _record_id(row)
            if row_id is not None and str(row_id) == wid:
                return str(row.get("workflowName") or row.get("name") or wid)
        return wid

    def _on_step_switch_flow(self) -> None:
        if not self._workflows:
            self._load_workflows()
        if not self._workflows:
            QMessageBox.information(self, "Switch Flow", "No work flows are available.")
            return

        active = self.step_section.selected_flow()
        dlg = SwitchFlowDialog(
            self,
            workflows=self._workflows,
            service=self._service,
            current_workflow_id=self.step_section.selected_workflow_id(),
            current_flow_id=str(_record_id(active)) if active else None,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        workflow, flow = dlg.selection()
        if not workflow or not flow:
            return
        workflow_id = str(_record_id(workflow) or "")
        if not workflow_id:
            return
        self._apply_step_context(workflow_id, flow)

    def _apply_step_context(self, workflow_id: str, active_flow: dict[str, Any] | None = None) -> None:
        self.step_section.set_selection(
            workflow_id,
            self._workflow_name(workflow_id),
            active_flow,
        )

    def _reload_step_context(self) -> None:
        wid = self.step_section.selected_workflow_id()
        if not wid:
            self.step_section.set_selection(None, "", None)
            return
        active = self.step_section.selected_flow()
        self.step_section.set_selection(wid, self._workflow_name(wid), active)

    def _refresh_flow_section(self) -> None:
        self._load_workflows()

    def _load_flows(self, workflow_id: str = "") -> None:
        wid = workflow_id or self.flow_section.selected_workflow_id()
        if not wid:
            self._flows = []
            self.flow_section.set_flows([])
            return
        ok, rows, msg = self._service.load_flows_by_workflow(wid)
        if not ok:
            QMessageBox.warning(self, "Failed", msg)
            return
        self._flows = rows
        self.flow_section.set_flows(rows)

    def _edit_catalog(self, entity: str, row: dict[str, Any] | None = None) -> None:
        if entity == "job" and not self._objects:
            self._load_objects()
        if entity == "workflow" and not self._jobs:
            self._load_jobs()
        if entity == "flow" and not self._workflows:
            self._load_workflows()

        initial: dict[str, Any] | None = dict(row) if isinstance(row, dict) else None
        if entity == "flow":
            wid = self.flow_section.selected_workflow_id()
            if wid:
                if initial is None:
                    initial = {}
                initial.setdefault("workflowId", wid)

        dlg = TransformationCatalogDialog(
            self,
            entity=entity,
            initial=initial,
            objects=self._objects,
            jobs=self._jobs,
            workflows=self._workflows,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        payload = dlg.payload()
        record_id = _record_id(row)
        if entity == "object":
            result = self._service.save_object(payload, record_id)
        elif entity == "job":
            result = self._service.save_job(payload, record_id)
        elif entity == "workflow":
            result = self._service.save_workflow(payload, record_id)
        else:
            result = self._service.save_flow(payload, record_id)
        if not result.get("success"):
            QMessageBox.warning(self, "Failed", str(result.get("message") or "Save failed."))
            return
        self.refresh_all()
        self._reload_step_context()

    def _delete_catalog(self, entity: str, row: dict[str, Any]) -> None:
        record_id = _record_id(row)
        if record_id is None:
            QMessageBox.warning(self, "Missing", "Record ID is missing.")
            return
        label = str(
            row.get("objectName")
            or row.get("jobName")
            or row.get("workflowName")
            or row.get("flowName")
            or record_id
        )
        reply = QMessageBox.question(
            self,
            "Delete",
            f"Delete \"{label}\"?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if entity == "object":
            result = self._service.delete_object(record_id)
        elif entity == "job":
            result = self._service.delete_job(record_id)
        elif entity == "workflow":
            result = self._service.delete_workflow(record_id)
        else:
            result = self._service.delete_flow(record_id)
        if not result.get("success"):
            QMessageBox.warning(self, "Failed", str(result.get("message") or "Delete failed."))
            return
        self.refresh_all()
        self._reload_step_context()
