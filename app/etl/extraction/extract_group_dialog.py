"""Create / edit extract group dialog."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    MODAL_FIELD_HEIGHT_PX,
    placeholder_enter,
)


def _parse_optional_int(text: str) -> int | None:
    stripped = (text or "").strip()
    if not stripped:
        return None
    try:
        return int(stripped)
    except ValueError:
        return None


def _connection_by_id(
    connections: list[dict[str, Any]],
    connection_id: int | str | None,
) -> dict[str, Any] | None:
    if connection_id is None:
        return None
    target = str(connection_id).strip()
    for conn in connections:
        cid = conn.get("connectionId") or conn.get("connectionID") or conn.get("id")
        if cid is not None and str(cid).strip() == target:
            return conn
    return None


def _connection_numeric_field(conn: dict[str, Any] | None, *keys: str) -> str:
    if not conn:
        return ""
    for key in keys:
        value = conn.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


def build_extract_group_payload(
    *,
    group_name: str,
    description: str,
    source_connection_id: int | str | None,
    target_connection_id: int | str | None,
    fetch_size: int | None = None,
    chunk_size: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "groupName": group_name.strip(),
        "description": description.strip(),
        "sourceConnectionId": source_connection_id,
        "targetConnectionId": target_connection_id,
    }
    if fetch_size is not None:
        payload["fetchSize"] = fetch_size
    if chunk_size is not None:
        payload["chunkSize"] = chunk_size
    return payload


def _connection_combo_index(combo: QComboBox, connection_id: int | str | None) -> int:
    if connection_id is None:
        return 0
    target = str(connection_id).strip()
    for index in range(combo.count()):
        data = combo.itemData(index)
        if data is not None and str(data).strip() == target:
            return index
    return 0


def _group_numeric_field(group: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = group.get(key)
        if value is not None and str(value).strip() != "":
            return str(value).strip()
    return ""


class ExtractGroupDialog(QDialog):
    def __init__(
        self,
        parent=None,
        *,
        connections: list[dict[str, Any]],
        initial: dict[str, Any] | None = None,
        title: str = "Create Extract Group",
        default_source_connection_id: int | str | None = None,
    ) -> None:
        super().__init__(parent)
        self._connections = connections
        self._edit_mode = initial is not None
        self.setWindowTitle(title)
        self.setMinimumWidth(460)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        form = QFormLayout()
        form.setSpacing(10)
        field_h = MODAL_FIELD_HEIGHT_PX

        self._name = QLineEdit()
        self._name.setPlaceholderText(placeholder_enter("group name"))
        self._name.setFixedHeight(field_h)

        self._description = QLineEdit()
        self._description.setPlaceholderText(placeholder_enter("description"))
        self._description.setFixedHeight(field_h)

        self._source_combo = QComboBox()
        self._target_combo = QComboBox()
        for combo in (self._source_combo, self._target_combo):
            combo.addItem("-- Select connection --", None)
            apply_form_combobox_field(combo, height_px=field_h, min_width=280)
        for conn in connections:
            label = str(conn.get("connectionName") or "Unnamed connection").strip()
            conn_id = conn.get("connectionId") or conn.get("connectionID") or conn.get("id")
            if conn_id is None:
                continue
            self._source_combo.addItem(label, conn_id)
            self._target_combo.addItem(label, conn_id)

        self._fetch_size = QLineEdit()
        self._fetch_size.setPlaceholderText(placeholder_enter("fetch size"))
        self._fetch_size.setFixedHeight(field_h)

        self._chunk_size = QLineEdit()
        self._chunk_size.setPlaceholderText(placeholder_enter("chunk size"))
        self._chunk_size.setFixedHeight(field_h)

        form.addRow("Group name*", self._name)
        form.addRow("Description", self._description)
        form.addRow("Source connection*", self._source_combo)
        form.addRow("Target connection*", self._target_combo)
        if self._edit_mode:
            form.addRow("Fetch size*", self._fetch_size)
            form.addRow("Chunk size*", self._chunk_size)
        root.addLayout(form)

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

        if initial:
            self._name.setText(str(initial.get("groupName") or ""))
            self._description.setText(str(initial.get("description") or ""))
            self._source_combo.setCurrentIndex(
                _connection_combo_index(self._source_combo, initial.get("sourceConnectionId"))
            )
            self._target_combo.setCurrentIndex(
                _connection_combo_index(self._target_combo, initial.get("targetConnectionId"))
            )
            src_conn = _connection_by_id(self._connections, initial.get("sourceConnectionId"))
            tgt_conn = _connection_by_id(self._connections, initial.get("targetConnectionId"))
            fetch_text = _group_numeric_field(initial, "fetchSize", "fetch_size")
            if not fetch_text:
                fetch_text = _connection_numeric_field(src_conn, "fetchSize", "fetch_size")
            chunk_text = _group_numeric_field(initial, "chunkSize", "chunk_size", "chunkSIze")
            if not chunk_text:
                chunk_text = _connection_numeric_field(tgt_conn, "chunkSize", "chunk_size", "chunkSIze")
            self._fetch_size.setText(fetch_text)
            self._chunk_size.setText(chunk_text)
        elif default_source_connection_id is not None:
            self._source_combo.setCurrentIndex(
                _connection_combo_index(self._source_combo, default_source_connection_id)
            )

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.setVisible(bool(message))

    def _on_accept(self) -> None:
        if not self._name.text().strip():
            self._show_error("Group name is required.")
            return
        if self._source_combo.currentData() is None:
            self._show_error("Source connection is required.")
            return
        if self._target_combo.currentData() is None:
            self._show_error("Target connection is required.")
            return
        if self._edit_mode:
            if _parse_optional_int(self._fetch_size.text()) is None:
                self._show_error("Fetch size must be a whole number.")
                return
            if _parse_optional_int(self._chunk_size.text()) is None:
                self._show_error("Chunk size must be a whole number.")
                return
        self._show_error("")
        self.accept()

    def payload(self) -> dict[str, Any]:
        fetch_size: int | None = None
        chunk_size: int | None = None
        if self._edit_mode:
            fetch_size = _parse_optional_int(self._fetch_size.text())
            chunk_size = _parse_optional_int(self._chunk_size.text())
        return build_extract_group_payload(
            group_name=self._name.text(),
            description=self._description.text(),
            source_connection_id=self._source_combo.currentData(),
            target_connection_id=self._target_combo.currentData(),
            fetch_size=fetch_size,
            chunk_size=chunk_size,
        )
