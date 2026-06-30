"""Create / edit dialog for DT Object, Job, Work Flow, and Flow catalog rows."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ui.form_page_styles import FORM_ERROR_LABEL_STYLE


def _record_id(row: dict[str, Any] | None, *keys: str) -> int | str | None:
    if not row:
        return None
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


class TransformationCatalogDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        *,
        entity: str,
        initial: dict[str, Any] | None = None,
        objects: list[dict[str, Any]] | None = None,
        jobs: list[dict[str, Any]] | None = None,
        workflows: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._entity = entity.strip().lower()
        self._initial = dict(initial) if isinstance(initial, dict) else {}
        self._objects = list(objects or [])
        self._jobs = list(jobs or [])
        self._workflows = list(workflows or [])
        self._fields: dict[str, QWidget] = {}

        titles = {
            "object": "Transformation Object",
            "job": "Transformation Job",
            "workflow": "Work Flow",
            "flow": "Transformation Flow",
        }
        self.setWindowTitle(f"Edit {titles.get(self._entity, 'Record')}" if initial else f"New {titles.get(self._entity, 'Record')}")
        self.setModal(True)
        self.setMinimumWidth(420)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)

        if self._entity == "object":
            self._add_line(form, "objectName", "Object name", self._initial.get("objectName"))
            self._add_line(form, "description", "Description", self._initial.get("description"))
            self._add_line(form, "status", "Status", self._initial.get("status") or "ACTIVE")
        elif self._entity == "job":
            self._add_parent_combo(
                form,
                "objectId",
                "Object",
                self._objects,
                ("id", "objectId"),
                ("objectName", "name"),
                self._initial.get("objectId"),
            )
            self._add_line(form, "jobName", "Job name", self._initial.get("jobName"))
            self._add_line(form, "description", "Description", self._initial.get("description"))
            self._add_line(form, "status", "Status", self._initial.get("status") or "ACTIVE")
        elif self._entity == "workflow":
            self._add_parent_combo(
                form,
                "jobId",
                "Job",
                self._jobs,
                ("id", "jobId"),
                ("jobName", "name"),
                self._initial.get("jobId"),
            )
            self._add_line(form, "workflowName", "Work flow name", self._initial.get("workflowName"))
            self._add_line(form, "description", "Description", self._initial.get("description"))
            self._add_spin(form, "sequenceNo", "Sequence no.", self._initial.get("sequenceNo") or 1)
            self._add_line(form, "status", "Status", self._initial.get("status") or "ACTIVE")
        elif self._entity == "flow":
            self._add_parent_combo(
                form,
                "workflowId",
                "Work flow",
                self._workflows,
                ("id", "workflowId"),
                ("workflowName", "name"),
                self._initial.get("workflowId"),
            )
            self._add_line(form, "flowName", "Flow name", self._initial.get("flowName"))
            self._add_spin(form, "sequenceNo", "Sequence no.", self._initial.get("sequenceNo") or 1)
            self._add_line(form, "status", "Status", self._initial.get("status") or "ACTIVE")

        root.addLayout(form)

        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error.setVisible(False)
        root.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _add_line(
        self,
        form: QFormLayout,
        key: str,
        label: str,
        value: Any,
    ) -> None:
        edit = QLineEdit(str(value or ""))
        self._fields[key] = edit
        form.addRow(label, edit)

    def _add_spin(self, form: QFormLayout, key: str, label: str, value: Any) -> None:
        spin = QSpinBox()
        spin.setRange(0, 999999)
        try:
            spin.setValue(int(value))
        except (TypeError, ValueError):
            spin.setValue(1)
        self._fields[key] = spin
        form.addRow(label, spin)

    def _add_parent_combo(
        self,
        form: QFormLayout,
        key: str,
        label: str,
        rows: list[dict[str, Any]],
        id_keys: tuple[str, ...],
        name_keys: tuple[str, ...],
        selected_id: Any,
    ) -> None:
        combo = QComboBox()
        selected_text = str(selected_id or "").strip()
        for row in rows:
            row_id = _record_id(row, *id_keys)
            if row_id is None:
                continue
            name = ""
            for nk in name_keys:
                text = str(row.get(nk) or "").strip()
                if text:
                    name = text
                    break
            combo.addItem(name or str(row_id), row_id)
            if selected_text and str(row_id) == selected_text:
                combo.setCurrentIndex(combo.count() - 1)
        self._fields[key] = combo
        form.addRow(label, combo)

    def payload(self) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, widget in self._fields.items():
            if isinstance(widget, QLineEdit):
                text = widget.text().strip()
                if text:
                    data[key] = text
            elif isinstance(widget, QSpinBox):
                data[key] = widget.value()
            elif isinstance(widget, QComboBox):
                value = widget.currentData()
                if value is not None and str(value).strip() != "":
                    try:
                        data[key] = int(str(value))
                    except ValueError:
                        data[key] = value
        if self._entity == "flow":
            return {
                "workflowId": data.get("workflowId"),
                "flowName": str(data.get("flowName") or "").strip(),
                "sequenceNo": int(data.get("sequenceNo") or 1),
                "status": str(data.get("status") or "ACTIVE").strip() or "ACTIVE",
            }
        return data

    def _show_error(self, message: str) -> None:
        self._error.setText(message)
        self._error.setVisible(bool(message))

    def _on_accept(self) -> None:
        payload = self.payload()
        if self._entity == "object" and not str(payload.get("objectName") or "").strip():
            self._show_error("Object name is required.")
            return
        if self._entity == "job":
            if payload.get("objectId") is None:
                self._show_error("Object is required.")
                return
            if not str(payload.get("jobName") or "").strip():
                self._show_error("Job name is required.")
                return
        if self._entity == "workflow":
            if payload.get("jobId") is None:
                self._show_error("Job is required.")
                return
            if not str(payload.get("workflowName") or "").strip():
                self._show_error("Work flow name is required.")
                return
        if self._entity == "flow":
            if payload.get("workflowId") is None:
                self._show_error("Work flow is required.")
                return
            if not str(payload.get("flowName") or "").strip():
                self._show_error("Flow name is required.")
                return
        self._show_error("")
        self.accept()
