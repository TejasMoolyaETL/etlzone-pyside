"""Wizard step 2: target connection, table name, load type, and commit size."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.etl.data_transformation.constants import CARD_STYLE, PANEL_HINT_STYLE, PANEL_TITLE_STYLE
from app.etl.data_transformation.data_service import TransformationDataService
from app.etl.data_transformation.metadata_helpers import (
    connection_id,
    connection_label,
    transformation_connection_id,
    transformation_record_id,
    transformation_table_name,
)
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
)


class StepTargetStepWidget(QWidget):
    def __init__(self, service: TransformationDataService, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._service = service
        self._connections: list[dict[str, Any]] = []
        self._flow_id: int | str | None = None
        self._target_record_id: int | str | None = None
        self._saved_table_name: str | None = None
        self._edit_mode = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        card = QFrame()
        card.setObjectName("dtCard")
        card.setStyleSheet(CARD_STYLE)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(10)

        title = QLabel("Target table")
        title.setStyleSheet(PANEL_TITLE_STYLE)
        card_layout.addWidget(title)

        hint = QLabel(
            "Select a connection and enter the target table name for the transformation output."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(PANEL_HINT_STYLE)
        card_layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(10)

        self.connection_combo = QComboBox()
        self.connection_combo.setMinimumWidth(280)
        form.addRow("Connection", self.connection_combo)

        self._table_cell = QWidget()
        table_cell_layout = QHBoxLayout(self._table_cell)
        table_cell_layout.setContentsMargins(0, 0, 0, 0)
        table_cell_layout.setSpacing(0)
        self.table_view_label = QLabel("—")
        self.table_view_label.setMinimumWidth(280)
        self.table_view_label.setStyleSheet("color: #0f172a;")
        self.table_name_input = QLineEdit()
        self.table_name_input.setMinimumWidth(280)
        self.table_name_input.setPlaceholderText("Enter target table name")
        table_cell_layout.addWidget(self.table_view_label)
        table_cell_layout.addWidget(self.table_name_input, 1)
        form.addRow("Table name", self._table_cell)

        self.commit_size_input = QLineEdit("1000")
        form.addRow("Commit size", self.commit_size_input)

        self.load_type_input = QLineEdit()
        self.load_type_input.setPlaceholderText("e.g. TRUNCATE_INSERT, APPEND")
        self.load_type_input.setMinimumWidth(280)
        form.addRow("Load type", self.load_type_input)

        self.status_input = QLineEdit("ACTIVE")
        form.addRow("Status", self.status_input)

        card_layout.addLayout(form)

        action_row = QHBoxLayout()
        action_row.addStretch()
        self.save_btn = QPushButton("Save")
        self.edit_btn = QPushButton("Edit")
        self.save_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self.edit_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self.edit_btn.setEnabled(False)
        action_row.addWidget(self.save_btn)
        action_row.addWidget(self.edit_btn)
        card_layout.addLayout(action_row)

        self._success_label = QLabel("")
        self._success_label.setWordWrap(True)
        self._success_label.setStyleSheet("color: #15803d;")
        self._success_label.setVisible(False)
        card_layout.addWidget(self._success_label)

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setVisible(False)
        card_layout.addWidget(self._error_label)

        root.addWidget(card, 1)

        self.save_btn.clicked.connect(self._on_save)
        self.edit_btn.clicked.connect(self._on_edit)

    def set_flow_id(self, flow_id: int | str | None) -> None:
        self._flow_id = flow_id

    def reset(self) -> None:
        self._flow_id = None
        self._target_record_id = None
        self._saved_table_name = None
        self._edit_mode = False
        self.load_type_input.clear()
        self.commit_size_input.setText("1000")
        self.status_input.setText("ACTIVE")
        self.table_name_input.clear()
        self.table_view_label.setText("—")
        self._clear_messages()
        self._refresh_form_mode()

    def _refresh_form_mode(self) -> None:
        has_record = self._target_record_id is not None or bool(self._saved_table_name)
        view_only = has_record and not self._edit_mode

        self.connection_combo.setEnabled(not view_only)
        self.commit_size_input.setReadOnly(view_only)
        self.status_input.setReadOnly(view_only)
        self.load_type_input.setReadOnly(view_only)

        if view_only:
            self.table_view_label.setText(self._saved_table_name or "—")
            self.table_view_label.setVisible(True)
            self.table_name_input.setVisible(False)
        else:
            self.table_view_label.setVisible(False)
            self.table_name_input.setVisible(True)
            if self._saved_table_name and not self.table_name_input.text().strip():
                self.table_name_input.setText(self._saved_table_name)

        self.save_btn.setEnabled((not has_record) or self._edit_mode)
        self.edit_btn.setEnabled(has_record and not self._edit_mode)

    def load_connections(self) -> tuple[bool, str]:
        ok, rows, msg = self._service.load_connections()
        if not ok:
            return False, msg
        self._connections = rows
        self.connection_combo.blockSignals(True)
        self.connection_combo.clear()
        for conn in rows:
            label = connection_label(conn) or str(connection_id(conn) or "")
            if label:
                self.connection_combo.addItem(label, conn)
        self.connection_combo.blockSignals(False)
        return True, ""

    def setup_status(self) -> tuple[str, bool]:
        if self._target_record_id is None:
            return "No target table saved — choose connection and table, then Save.", False
        table = self._saved_table_name or self.table_view_label.text().strip() or "target"
        return f"Target table configured: {table}.", True

    def load_existing_target(self, flow_id: int | str) -> tuple[bool, str]:
        ok, record, msg = self._service.load_transformation_target_by_flow(flow_id)
        if not ok:
            return False, msg
        if not record:
            self._target_record_id = None
            self._saved_table_name = None
            self._edit_mode = False
            self._refresh_form_mode()
            return True, ""
        self.apply_existing_target(record)
        return True, ""

    def apply_existing_target(self, record: dict[str, Any]) -> None:
        self._target_record_id = transformation_record_id(
            record, "id", "targetId", "target_id", "ID"
        )
        self._saved_table_name = transformation_table_name(record) or None
        self._edit_mode = False

        target_conn = str(transformation_connection_id(record) or "").strip()
        if target_conn:
            for index in range(self.connection_combo.count()):
                conn = self.connection_combo.itemData(index)
                if isinstance(conn, dict) and str(connection_id(conn) or "") == target_conn:
                    self.connection_combo.blockSignals(True)
                    self.connection_combo.setCurrentIndex(index)
                    self.connection_combo.blockSignals(False)
                    break

        self.table_name_input.setText(self._saved_table_name or "")
        self.load_type_input.setText(str(record.get("loadType") or ""))
        commit_size = record.get("commitSize")
        self.commit_size_input.setText(
            str(commit_size).strip() if commit_size is not None and str(commit_size).strip() else ""
        )
        self.status_input.setText(str(record.get("status") or "ACTIVE"))
        self._clear_messages()
        self._refresh_form_mode()

    def build_payload(
        self, flow_id: int | str | None, *, for_create: bool
    ) -> tuple[dict[str, Any] | None, str]:
        conn = self.connection_combo.currentData()
        if not isinstance(conn, dict):
            return None, "Connection is required."
        cid = connection_id(conn)
        if cid is None:
            return None, "Connection ID is missing."

        table_name = self.table_name_input.text().strip()
        if not table_name:
            return None, "Table name is required."

        load_type = self.load_type_input.text().strip()
        if not load_type:
            return None, "Load type is required."

        commit_text = self.commit_size_input.text().strip() or "1000"
        if not commit_text.isdigit():
            return None, "Commit size must be a number."

        payload: dict[str, Any] = {
            "connectionId": int(cid) if str(cid).isdigit() else cid,
            "tableName": table_name,
            "loadType": load_type,
            "commitSize": int(commit_text),
            "status": self.status_input.text().strip() or "ACTIVE",
        }
        if for_create:
            if flow_id is None:
                return None, "Select a flow using Switch Flow first."
            payload["flowId"] = int(flow_id) if str(flow_id).isdigit() else flow_id
        return payload, ""

    def create_target(self) -> tuple[bool, str]:
        if self._flow_id is None:
            return False, "Select a flow using Switch Flow first."
        payload, err = self.build_payload(self._flow_id, for_create=True)
        if payload is None:
            return False, err or "Target configuration is incomplete."
        result = self._service.save_transformation_target(payload)
        if not result.get("success"):
            return False, str(result.get("message") or "Failed to save target configuration.")
        if self._flow_id is not None:
            ok, record, load_msg = self._service.load_transformation_target_by_flow(self._flow_id)
            if not ok:
                return False, load_msg
            if record:
                self.apply_existing_target(record)
            else:
                record_id = result.get("recordId")
                if record_id is not None:
                    self._target_record_id = record_id
                self._saved_table_name = str(payload.get("tableName") or "").strip() or None
                self._edit_mode = False
                self._refresh_form_mode()
        else:
            self._saved_table_name = str(payload.get("tableName") or "").strip() or None
            self._edit_mode = False
            self._refresh_form_mode()
        self._show_success(str(result.get("message") or "Target configuration saved."))
        return True, ""

    def update_target(self) -> tuple[bool, str]:
        if self._target_record_id is None:
            return False, "Target configuration is incomplete."
        payload, err = self.build_payload(self._flow_id, for_create=False)
        if payload is None:
            return False, err or "Target configuration is incomplete."
        result = self._service.update_transformation_target(self._target_record_id, payload)
        if not result.get("success"):
            return False, str(result.get("message") or "Failed to update target configuration.")
        if self._flow_id is not None:
            ok, record, load_msg = self._service.load_transformation_target_by_flow(self._flow_id)
            if not ok:
                return False, load_msg
            if record:
                self.apply_existing_target(record)
            else:
                self._saved_table_name = str(payload.get("tableName") or "").strip() or None
                self._edit_mode = False
                self._refresh_form_mode()
        else:
            self._saved_table_name = str(payload.get("tableName") or "").strip() or None
            self._edit_mode = False
            self._refresh_form_mode()
        self._show_success(str(result.get("message") or "Target configuration updated."))
        return True, ""

    def save_target(self) -> tuple[bool, str]:
        if self._target_record_id is not None and self._edit_mode:
            return self.update_target()
        if self._target_record_id is not None and not self._edit_mode:
            return True, ""
        return self.create_target()

    def is_view_mode(self) -> bool:
        return (self._target_record_id is not None or bool(self._saved_table_name)) and not self._edit_mode

    def _on_save(self) -> None:
        ok, msg = self.save_target()
        if not ok:
            self._show_error(msg)

    def _on_edit(self) -> None:
        self._edit_mode = True
        if self._saved_table_name:
            self.table_name_input.setText(self._saved_table_name)
        self._clear_messages()
        self._refresh_form_mode()

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(bool(message))
        if message:
            self._success_label.clear()
            self._success_label.setVisible(False)

    def _show_success(self, message: str) -> None:
        self._success_label.setText(message)
        self._success_label.setVisible(bool(message))
        if message:
            self._error_label.clear()
            self._error_label.setVisible(False)

    def _clear_messages(self) -> None:
        self._error_label.clear()
        self._error_label.setVisible(False)
        self._success_label.clear()
        self._success_label.setVisible(False)
