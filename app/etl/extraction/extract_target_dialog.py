"""Dialog to pick a target connection before running extraction."""

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

from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    MODAL_FIELD_HEIGHT_PX,
)


class ExtractTargetDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        connections: list[dict[str, Any]],
        source_connection_name: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Extract")
        self.setModal(True)
        self.setMinimumWidth(460)

        self._selected: dict[str, Any] | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        hint = QLabel("Select the target connection for this extraction run.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        if source_connection_name.strip():
            src_label = QLabel(f"Source: {source_connection_name.strip()}")
            root.addWidget(src_label)

        form = QFormLayout()
        form.setSpacing(10)
        self._target_combo = QComboBox()
        self._target_combo.addItem("-- Select target connection --", None)
        apply_form_combobox_field(self._target_combo, height_px=MODAL_FIELD_HEIGHT_PX, min_width=300)
        for conn in connections:
            name = str(conn.get("connectionName") or "Unnamed connection").strip()
            self._target_combo.addItem(name, conn)
        form.addRow("Target connection*", self._target_combo)
        root.addLayout(form)

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setVisible(False)
        root.addWidget(self._error_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def selected_connection(self) -> dict[str, Any] | None:
        return self._selected

    def _on_accept(self) -> None:
        target = self._target_combo.currentData()
        if not isinstance(target, dict):
            self._error_label.setText("Target connection is required.")
            self._error_label.setVisible(True)
            return
        self._error_label.setVisible(False)
        self._selected = target
        self.accept()
