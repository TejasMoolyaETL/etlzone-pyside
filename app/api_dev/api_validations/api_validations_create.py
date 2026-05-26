"""API Validations create page — layout and UX aligned with Create API Detail."""

from __future__ import annotations

import re
from typing import Any, Callable

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCompleter,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.api import (
    api_create_api_validation,
    api_get_all_api_details,
    api_get_all_projects,
    api_get_all_user_type_in_api_project,
)
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    placeholder_example,
    placeholder_search_select,
)
from ui.post_save_navigation import schedule_after_success
from ui.searchable_form_combo import wire_searchable_labeled_rows_combo
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label, labeled_field_block

_COL1_FIELDS = (
    ("Project Id", "project_id"),
    ("Project Name*", "project_name"),
    ("API Id", "api_id"),
    ("API name*", "api_name"),
    ("Field Name*", "field_name"),
    ("API Summary*", "api_validation_summary"),
    ("Role", "role"),
    ("API Validation", "api_validation"),
    ("Validation Type", "validation_type"),
)
_COL2_FIELDS = (
    ("API Validation Status", "api_validation_status"),
    ("Error Message", "error_message"),
    ("Success Message", "success_message"),
)


class CreateAPIValidationPage(QWidget):
    """Page with form to add API validation."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._project_completions: list[tuple[str, Any, dict[str, Any]]] = []
        self._api_completions: list[tuple[str, Any, str, dict[str, Any]]] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(FORM_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        header_layout.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        title = QLabel("Create API Validation")
        header_layout.addWidget(title)
        header_layout.addStretch()
        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._handle_back)
        header_layout.addWidget(back_btn)
        layout.addWidget(header)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Maximum)
        card.setMinimumWidth(520)
        card.setMaximumWidth(800)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        _col_v_spacing = 10
        cols_row = QHBoxLayout()
        cols_row.setSpacing(24)
        cols_row.setContentsMargins(0, 0, 0, 0)
        col1_lay = QVBoxLayout()
        col1_lay.setSpacing(_col_v_spacing)
        col1_lay.setContentsMargins(0, 0, 0, 0)
        col2_lay = QVBoxLayout()
        col2_lay.setSpacing(_col_v_spacing)
        col2_lay.setContentsMargins(0, 0, 0, 0)
        col1_w = QWidget()
        col1_w.setLayout(col1_lay)
        col1_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        col2_w = QWidget()
        col2_w.setLayout(col2_lay)
        col2_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        cols_row.addWidget(col1_w, 1)
        cols_row.addWidget(col2_w, 1)

        placeholders = {
            "project_id": "Select a project above",
            "project_name": placeholder_search_select("Project Id", "Project Name"),
            "api_id": "Select project first",
            "api_name": placeholder_search_select("API Id", "API Name"),
            "field_name": placeholder_example("userName"),
            "api_validation_summary": "Short summary for validation",
            "role": "Select project first",
            "api_validation": "Validation rule",
            "validation_type": placeholder_example("REQUIRED"),
            "api_validation_status": "",
            "error_message": "Error message when validation fails",
            "success_message": "Success message",
        }

        _multiline_h = 80

        def append_field(stack: QVBoxLayout, label_text: str, field_key: str) -> None:
            if field_key == "api_validation_status":
                lbl = QLabel("API Validation Status:")
                lbl.setStyleSheet(LABEL_STYLE)
                w = QComboBox()
                apply_form_combobox_field(w, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX)
                wire_searchable_labeled_rows_combo(
                    w,
                    rows=[("ACTIVE", "ACTIVE"), ("INACTIVE", "INACTIVE")],
                    search_field_label="API validation status",
                    default_display_text="ACTIVE",
                )
                self.api_validation_status_combo = w
                stack.addWidget(labeled_field_block(lbl, w))
                return

            lbl = field_caption_label(label_text, LABEL_STYLE)
            if field_key == "project_id":
                w = QLineEdit()
                w.setReadOnly(True)
                w.setStyleSheet(READONLY_INPUT_STYLE)
                self.project_id_edit = w
            elif field_key == "project_name":
                w = QLineEdit()
                w.setStyleSheet(INPUT_STYLE)
                self.project_name_edit = w
                w.installEventFilter(self)
            elif field_key == "api_id":
                w = QLineEdit()
                w.setReadOnly(True)
                w.setStyleSheet(READONLY_INPUT_STYLE)
                self.api_id_edit = w
            elif field_key == "api_name":
                w = QLineEdit()
                w.setStyleSheet(INPUT_STYLE)
                self.api_name_edit = w
                w.installEventFilter(self)
            elif field_key == "role":
                w = QComboBox()
                w.setEditable(False)
                self.role_combo = w
                self._setup_role_combo()
                apply_form_combobox_field(w, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX)
            elif field_key in ("api_validation", "error_message", "success_message"):
                w = QPlainTextEdit()
                w.setFixedHeight(_multiline_h)
                w.setStyleSheet(INPUT_STYLE)
                if field_key == "api_validation":
                    self.api_validation_edit = w
                elif field_key == "error_message":
                    self.error_message_edit = w
                else:
                    self.success_message_edit = w
            else:
                w = QLineEdit()
                w.setStyleSheet(INPUT_STYLE)
                if field_key == "field_name":
                    self.field_name_edit = w
                elif field_key == "api_validation_summary":
                    self.api_validation_summary_edit = w
                elif field_key == "validation_type":
                    self.validation_type_edit = w

            ph = placeholders.get(field_key)
            if ph and hasattr(w, "setPlaceholderText"):
                w.setPlaceholderText(ph)

            stack.addWidget(labeled_field_block(lbl, w))

        for label_text, field_key in _COL1_FIELDS:
            append_field(col1_lay, label_text, field_key)
        for label_text, field_key in _COL2_FIELDS:
            append_field(col2_lay, label_text, field_key)
        col1_lay.addStretch()
        col2_lay.addStretch()

        card_layout.addLayout(cols_row)
        card_layout.addSpacing(16)
        self.error_label = QLabel()
        self.error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.error_label.setVisible(False)
        card_layout.addWidget(self.error_label)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        create_btn = QPushButton("Create")
        create_btn.setFixedWidth(100)
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        create_btn.clicked.connect(self._handle_create)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self._handle_back)
        btn_layout.addWidget(create_btn)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        card_layout.addLayout(btn_layout)

        content_layout.addWidget(card)
        content_layout.addStretch()
        layout.addWidget(content)

    def _setup_project_completer(self) -> None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_projects(token=token)
        projects = result.get("data", []) if result.get("success") else []
        self._project_completions = []
        for p in projects:
            if not isinstance(p, dict):
                continue
            pid = p.get("projectId") or p.get("project_id") or p.get("id")
            if pid is None or str(pid).strip() == "":
                continue
            pname = (
                p.get("projectName")
                or p.get("project_name")
                or p.get("name")
                or ""
            ).strip()
            display = f"{pname} (ID: {pid})" if pname else f"ID: {pid}"
            self._project_completions.append((display, pid, p))
        completer = QCompleter([d for d, _, _ in self._project_completions])
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(10)

        def on_activated(text: str) -> None:
            for disp, pid, _ in self._project_completions:
                if disp == text:
                    self.project_id_edit.setText(str(pid))
                    self.project_name_edit.setText(disp)
                    self.api_id_edit.clear()
                    self.api_name_edit.clear()
                    self._api_completions = []
                    self._setup_role_combo()
                    break

        completer.activated.connect(on_activated)
        self.project_name_edit.setCompleter(completer)

    def _setup_role_combo(self) -> None:
        self.role_combo.clear()
        project_id_str = self.project_id_edit.text().strip()
        if not project_id_str:
            self.role_combo.addItem("")
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_user_type_in_api_project(token=token)
        records = result.get("data", []) if result.get("success") else []
        roles: set[str] = set()
        for r in records:
            if not isinstance(r, dict):
                continue
            pid = r.get("projectId") or r.get("project_id")
            if str(pid) != project_id_str:
                continue
            ut = (r.get("userType") or r.get("user_type") or "").strip()
            if ut:
                roles.add(ut)
        items = sorted(roles)
        if items:
            self.role_combo.addItems(items)
        else:
            self.role_combo.addItem("")

    def _setup_api_completer(self) -> None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_api_details(token=token)
        api_details = result.get("data", []) if result.get("success") else []
        project_id_str = self.project_id_edit.text().strip()
        self._api_completions = []
        for a in api_details:
            if not isinstance(a, dict):
                continue
            pid = a.get("projectId") or a.get("project_id")
            if project_id_str and str(pid) != project_id_str:
                continue
            api_id = a.get("apiId") or a.get("api_id") or a.get("id")
            if api_id is None:
                continue
            api_name = (a.get("apiName") or a.get("api_name") or a.get("name") or "").strip()
            display = f"{api_name} (ID: {api_id})" if api_name else f"ID: {api_id}"
            self._api_completions.append((display, api_id, api_name, a))
        completer = QCompleter([d for d, _, _, _ in self._api_completions])
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(10)

        def on_activated(text: str) -> None:
            for disp, aid, _aname, _ in self._api_completions:
                if disp == text:
                    self.api_id_edit.setText(str(aid))
                    self.api_name_edit.setText(disp)
                    break

        completer.activated.connect(on_activated)
        self.api_name_edit.setCompleter(completer)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._setup_project_completer()
        if self.project_id_edit.text().strip():
            self._setup_role_combo()
        self._setup_api_completer()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        # FocusIn can fire during construction before later fields (e.g. api_name) exist.
        if event.type() == QEvent.Type.FocusIn:
            proj = getattr(self, "project_name_edit", None)
            if proj is not None and obj == proj:
                self._setup_project_completer()
                self._setup_role_combo()
            api = getattr(self, "api_name_edit", None)
            if api is not None and obj == api:
                self._setup_api_completer()
        return super().eventFilter(obj, event)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)

    def _get_default_values(self) -> dict[str, str]:
        return {
            "project_id": "",
            "project_name": "",
            "api_id": "",
            "api_name": "",
            "field_name": "",
            "api_validation_summary": "",
            "role": "",
            "api_validation": "",
            "validation_type": "",
            "api_validation_status": "ACTIVE",
            "error_message": "",
            "success_message": "",
        }

    def is_dirty(self) -> bool:
        d = self._get_default_values()
        return (
            self.project_id_edit.text().strip() != d["project_id"]
            or self.project_name_edit.text().strip() != d["project_name"]
            or self.api_id_edit.text().strip() != d["api_id"]
            or self.api_name_edit.text().strip() != d["api_name"]
            or self.field_name_edit.text().strip() != d["field_name"]
            or self.api_validation_summary_edit.text().strip() != d["api_validation_summary"]
            or self.role_combo.currentText().strip() != d["role"]
            or self.api_validation_edit.toPlainText().strip() != d["api_validation"]
            or self.validation_type_edit.text().strip() != d["validation_type"]
            or self.api_validation_status_combo.currentText().strip() != d["api_validation_status"]
            or self.error_message_edit.toPlainText().strip() != d["error_message"]
            or self.success_message_edit.toPlainText().strip() != d["success_message"]
        )

    def reset_to_default(self) -> None:
        self.project_id_edit.clear()
        self.project_name_edit.clear()
        self.api_id_edit.clear()
        self.api_name_edit.clear()
        self.field_name_edit.clear()
        self.api_validation_summary_edit.clear()
        self.role_combo.clear()
        self.role_combo.addItem("")
        self.api_validation_edit.clear()
        self.validation_type_edit.clear()
        self.api_validation_status_combo.setCurrentText("ACTIVE")
        self.error_message_edit.clear()
        self.success_message_edit.clear()

    def _handle_back(self) -> None:
        self._clear_error()
        if not self.is_dirty():
            if self.on_back:
                self.on_back()
            return
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard and leave?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Discard:
            self.reset_to_default()
            if self.on_back:
                self.on_back()

    def _parse_project_id(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        match = re.search(r"\(ID:\s*([^)]+)\)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return text

    def _is_valid_project_selection(self) -> bool:
        text = self.project_name_edit.text().strip()
        if not text:
            return False
        valid_displays = {disp for disp, _, _ in self._project_completions}
        return text in valid_displays

    def _is_valid_api_selection(self) -> bool:
        text = self.api_name_edit.text().strip()
        if not text:
            return False
        return text in {disp for disp, _, _, _ in self._api_completions}

    def _parse_api_id(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        match = re.search(r"\(ID:\s*([^)]+)\)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return text

    def _handle_create(self) -> None:
        self._clear_error()
        self._setup_api_completer()
        if not self.project_name_edit.text().strip():
            self._show_error("Please select a project from the Project Name field.")
            return
        if not self._is_valid_project_selection():
            self._show_error(strict_list_selection_message("a project"))
            return
        if not self.api_name_edit.text().strip():
            self._show_error("Please select an API from the API name field.")
            return
        if not self._is_valid_api_selection():
            self._show_error(strict_list_selection_message("an API"))
            return
        api_id_raw = self.api_id_edit.text().strip() or self._parse_api_id(self.api_name_edit.text())
        if not api_id_raw:
            self._show_error("Please select an API from the API name field.")
            return
        if not self.field_name_edit.text().strip():
            self._show_error("Field Name is required.")
            return
        if not self.api_validation_summary_edit.text().strip():
            self._show_error("API Summary is required.")
            return

        project_id_raw = self.project_id_edit.text().strip() or self._parse_project_id(
            self.project_name_edit.text()
        )
        if not project_id_raw:
            self._show_error("Please select a project from the Project Name field.")
            return

        try:
            api_id = int(api_id_raw)
        except ValueError:
            api_id = api_id_raw

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_create_api_validation(
            token=token,
            api_id=api_id,
            field_name=self.field_name_edit.text().strip(),
            api_validation_summary=self.api_validation_summary_edit.text().strip(),
            role=self.role_combo.currentText().strip(),
            api_validation=self.api_validation_edit.toPlainText().strip(),
            validation_type=self.validation_type_edit.text().strip(),
            api_validation_status=self.api_validation_status_combo.currentText().strip(),
            error_message=self.error_message_edit.toPlainText().strip(),
            success_message=self.success_message_edit.toPlainText().strip(),
        )

        if result.get("success"):
            self._show_success(result.get("message", "API validation created successfully."))
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(result.get("message", "Failed to create API validation."))
