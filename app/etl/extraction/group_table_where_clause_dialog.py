"""Dialog to add or edit a WHERE clause on a group or imported table."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.api import api_validate_group_table_where_clause
from ui.form_page_styles import FORM_ERROR_LABEL_STYLE, MODAL_FIELD_HEIGHT_PX


def normalize_where_clause_input(text: str) -> str:
    stripped = (text or "").strip()
    if stripped.upper().startswith("WHERE "):
        return stripped[6:].strip()
    return stripped


class GroupTableWhereClauseDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        table_name: str,
        connection_id: int | str,
        token: str | None = None,
        initial: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Where Clause")
        self.setModal(True)
        self.setMinimumSize(520, 260)

        self._table_name = table_name.strip()
        self._connection_id = connection_id
        self._token = token
        self._validated_clause: str | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = self._table_name or "Table"
        hint = QLabel(
            f"Condition for \"{title}\". Enter the expression only — do not include the WHERE keyword.\n"
            "Click Validate before Save. Example: status = 'ACTIVE'"
        )
        hint.setWordWrap(True)
        root.addWidget(hint)

        self._editor = QTextEdit()
        self._editor.setPlaceholderText("status = 'ACTIVE'")
        self._editor.setPlainText(initial)
        self._editor.setMinimumHeight(MODAL_FIELD_HEIGHT_PX * 3)
        self._editor.textChanged.connect(self._on_text_changed)
        root.addWidget(self._editor, 1)

        self._success_label = QLabel("")
        self._success_label.setWordWrap(True)
        self._success_label.setStyleSheet("color: #15803d;")
        self._success_label.setVisible(False)
        root.addWidget(self._success_label)

        self._error_label = QLabel("")
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setVisible(False)
        root.addWidget(self._error_label)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        self._validate_btn = self._buttons.addButton("Validate", QDialogButtonBox.ButtonRole.ActionRole)
        self._save_btn = self._buttons.button(QDialogButtonBox.StandardButton.Save)
        if self._save_btn is not None:
            self._save_btn.setEnabled(False)
        self._validate_btn.clicked.connect(self._on_validate)
        self._buttons.accepted.connect(self._on_accept)
        self._buttons.rejected.connect(self.reject)
        root.addWidget(self._buttons)

    def where_clause(self) -> str:
        return normalize_where_clause_input(self._editor.toPlainText())

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

    def _on_text_changed(self) -> None:
        self._validated_clause = None
        if self._save_btn is not None:
            self._save_btn.setEnabled(False)
        self._success_label.clear()
        self._success_label.setVisible(False)
        self._error_label.clear()
        self._error_label.setVisible(False)

    def _on_validate(self) -> None:
        clause = self.where_clause()
        if not clause:
            self._show_error("Where clause cannot be empty.")
            return
        if not self._table_name:
            self._show_error("Table name is missing.")
            return
        result = api_validate_group_table_where_clause(
            self._connection_id,
            self._table_name,
            clause,
            token=self._token,
        )
        if result.get("valid"):
            self._validated_clause = clause
            if self._save_btn is not None:
                self._save_btn.setEnabled(True)
            self._show_success(str(result.get("message") or "Validation successful."))
            return
        self._validated_clause = None
        if self._save_btn is not None:
            self._save_btn.setEnabled(False)
        self._show_error(str(result.get("message") or "Validation failed."))

    def _on_accept(self) -> None:
        clause = self.where_clause()
        if not clause:
            self._show_error("Where clause cannot be empty.")
            return
        if self._validated_clause != clause:
            self._show_error("Validate the where clause before saving.")
            return
        self._show_error("")
        self.accept()
