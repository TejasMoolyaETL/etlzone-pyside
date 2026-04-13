"""Create User Type (Role) page — layout aligned with Create Project."""

from __future__ import annotations

import re
from typing import Callable

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtWidgets import (
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.api import api_create_user_type_in_api_project, api_get_all_projects
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
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
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label, labeled_field_block


class CreateUserTypePage(QWidget):
    """Add a role to an API project (User Involved) — same shell as Create Project."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._project_completions: list[tuple[str, int | str]] = []
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
        title = QLabel("Create Role")
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
        card.setMaximumWidth(520)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        label_project_id = QLabel("Project ID:")
        label_project_id.setStyleSheet(LABEL_STYLE)
        self.project_id_edit = QLineEdit()
        self.project_id_edit.setReadOnly(True)
        self.project_id_edit.setPlaceholderText("Select a project below")
        self.project_id_edit.setStyleSheet(READONLY_INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_project_id, self.project_id_edit))

        label_project = field_caption_label("Project Name*", LABEL_STYLE)
        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText(placeholder_search_select("Project Id", "Project name"))
        self.project_name_edit.setStyleSheet(INPUT_STYLE)
        self.project_name_edit.installEventFilter(self)
        card_layout.addWidget(labeled_field_block(label_project, self.project_name_edit))

        label_role = field_caption_label("Role*", LABEL_STYLE)
        self.role_edit = QLineEdit()
        self.role_edit.setPlaceholderText(placeholder_example("SADMIN, PADMIN, USER"))
        self.role_edit.setStyleSheet(INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_role, self.role_edit))

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
            self._project_completions.append((display, pid))
        completer = QCompleter([d for d, _ in self._project_completions])
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(10)

        def on_activated(text: str) -> None:
            for disp, pid in self._project_completions:
                if disp == text:
                    self.project_id_edit.setText(str(pid))
                    self.project_name_edit.setText(disp)
                    break

        completer.activated.connect(on_activated)
        self.project_name_edit.setCompleter(completer)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj == self.project_name_edit and event.type() == QEvent.Type.FocusIn:
            self._setup_project_completer()
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
            "role": "",
        }

    def is_dirty(self) -> bool:
        d = self._get_default_values()
        return (
            self.project_id_edit.text().strip() != d["project_id"]
            or self.project_name_edit.text().strip() != d["project_name"]
            or self.role_edit.text().strip() != d["role"]
        )

    def reset_to_default(self) -> None:
        self.project_id_edit.clear()
        self.project_name_edit.clear()
        self.role_edit.clear()

    def _handle_back(self) -> None:
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
        valid_displays = {disp for disp, _ in self._project_completions}
        return text in valid_displays

    def _handle_create(self) -> None:
        self._clear_error()
        project_name_text = self.project_name_edit.text().strip()
        if not project_name_text:
            self._show_error("Please select a project from the Project Name field.")
            return
        if not self._is_valid_project_selection():
            self._show_error(strict_list_selection_message("a project"))
            return
        project_id_raw = self.project_id_edit.text().strip() or self._parse_project_id(
            project_name_text
        )
        if not project_id_raw:
            self._show_error("Please select a project from the Project Name field.")
            return
        role = self.role_edit.text().strip()
        if not role:
            self._show_error("Role is required.")
            return
        try:
            project_id = int(project_id_raw)
        except ValueError:
            project_id = project_id_raw

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_create_user_type_in_api_project(
            project_id,
            role,
            token=token,
        )

        if result.get("success"):
            self._show_success(result.get("message", "Role added successfully."))

            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(result.get("message", "Failed to add role."))
