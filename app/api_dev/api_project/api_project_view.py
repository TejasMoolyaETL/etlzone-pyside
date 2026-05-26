"""View Project page — layout and behavior aligned with org_view (ViewOrgPage)."""

from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.api import api_update_project
from core.app_preferences import format_datetime_display, is_datetime_field
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps, get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.blank_display import is_blank_display_value
from ui.form_combobox_style import FORM_COMBOBOX_STYLE, apply_form_combobox_field
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
    placeholder_example,
    FORM_SECONDARY_BUTTON_STYLESHEET,
)
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success
from ui.searchable_form_combo import wire_searchable_labeled_rows_combo
from ui.widgets.required_label import field_caption_label, labeled_field_block

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})


def _get_value(project: dict[str, Any], keys: tuple[str, ...]) -> Any:
    flat = {k: v for k, v in project.items() if k not in _HIDDEN_KEYS}
    for key in keys:
        if key in flat:
            return flat[key]
    return None


def _format_value(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


def _get_project_id(project: dict[str, Any]) -> int | str | None:
    for k in ("projectId", "projectid", "project_id"):
        v = project.get(k)
        if v is not None:
            return v
    return None


_PROJECT_STATUS = ("ACTIVE", "INACTIVE", "DISABLE", "COMPLETE")

# Column 1: main project fields (canonical key first)
_PROJECT_COL1 = (
    ("Project Id (Internal)", ("projectId", "projectid", "project_id")),
    ("Project Name*", ("projectName", "project_name")),
    ("Project Description", ("projectDesc", "project_desc", "projectDescription")),
    ("Project Status", ("projectStatus", "project_status")),
    ("Project Server", ("projectServer", "project_server")),
    ("Project Port", ("projectPort", "project_port")),
    ("Project Owner User ID*", ("projectOwnerUserId", "projectOwnerUserld", "project_owner_user_id")),
)
# Column 2: audit fields (read-only)
_PROJECT_COL2 = (
    ("Created By", ("createdBy", "created_by", "CreatedBy")),
    ("Created At", ("createdAt", "created_at", "CreatedAt")),
    ("Modified By", ("modifiedBy", "modified_by", "ModifiedBy")),
    ("Modified At", ("modifiedAt", "modified_at", "ModifiedAt", "updatedAt", "updated_at")),
)
_PROJECT_FIELD_GROUPS = _PROJECT_COL1 + _PROJECT_COL2

_READONLY_KEYS = frozenset({
    "projectId", "projectid", "project_id",
    "createdBy", "created_by", "CreatedBy",
    "createdAt", "created_at", "CreatedAt",
    "modifiedBy", "modified_by", "ModifiedBy",
    "modifiedAt", "modified_at", "ModifiedAt", "updatedAt", "updated_at",
})


class ViewProjectPage(QWidget):
    """Page that displays project details with view and edit modes (same pattern as ViewOrgPage)."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._project: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit | QComboBox] = {}
        self._editable_keys: list[str] = []
        self._can_edit_action = True
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
        title = QLabel("Project Details")
        header_layout.addWidget(title)
        header_layout.addStretch()
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll_content = QWidget()
        scroll_content.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        card.setMinimumWidth(520)
        card.setMaximumWidth(800)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        def add_field(col: int, idx: int, label_text: str, keys: tuple[str, ...]) -> None:
            canonical = keys[0]
            if canonical not in _READONLY_KEYS:
                self._editable_keys.append(canonical)

            label_widget = field_caption_label(label_text, LABEL_STYLE)

            if canonical in ("projectStatus", "project_status"):
                value_edit = QComboBox()
                apply_form_combobox_field(
                    value_edit, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX, min_width=240
                )
                wire_searchable_labeled_rows_combo(
                    value_edit,
                    rows=[(s, s) for s in _PROJECT_STATUS],
                    search_field_label="Project status",
                    default_display_text="ACTIVE",
                )
                if canonical in _READONLY_KEYS:
                    value_edit.setEnabled(False)
                else:
                    value_edit.setEnabled(True)
            else:
                value_edit = QLineEdit()
                value_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
                value_edit.setMinimumWidth(240)
                value_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                value_edit.setReadOnly(canonical in _READONLY_KEYS)
                value_edit.setStyleSheet(READONLY_INPUT_STYLE if canonical in _READONLY_KEYS else INPUT_STYLE)
                value_edit.setText("")
                if canonical not in _READONLY_KEYS:
                    if canonical in ("projectName", "project_name"):
                        value_edit.setPlaceholderText(placeholder_example("Etlzone App"))
                    elif canonical in ("projectDesc", "project_desc"):
                        value_edit.setPlaceholderText("Optional")
                    elif canonical in ("projectOwnerUserId", "project_owner_user_id"):
                        value_edit.setPlaceholderText("Required")
                    elif canonical in ("projectServer", "project_server"):
                        value_edit.setPlaceholderText(placeholder_example("192.168.1.100"))
                    elif canonical in ("projectPort", "project_port"):
                        value_edit.setPlaceholderText(placeholder_example("9091"))

            self._field_edits[canonical] = value_edit
            grid.addWidget(labeled_field_block(label_widget, value_edit), idx, col)

        for idx, (label_text, keys) in enumerate(_PROJECT_COL1):
            add_field(0, idx, label_text, keys)
        for idx, (label_text, keys) in enumerate(_PROJECT_COL2):
            add_field(1, idx, label_text, keys)

        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self._handle_back)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedWidth(100)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._edit_btn.setStyleSheet(
            FORM_PRIMARY_BUTTON_STYLESHEET
            + " QPushButton:disabled {"
            + " background-color: #e5e7eb;"
            + " color: #6b7280;"
            + " border: 1px solid #cbd5e1;"
            + "}"
        )
        self._edit_btn.clicked.connect(self._handle_edit)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedWidth(100)
        self._cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._cancel_btn.clicked.connect(self._handle_cancel)

        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedWidth(100)
        self._save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._save_btn.setStyleSheet(FORM_PRIMARY_BUTTON_STYLESHEET)
        self._save_btn.clicked.connect(self._handle_save)

        display_btns = QWidget()
        display_btns.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        display_btns_layout = QHBoxLayout(display_btns)
        display_btns_layout.setContentsMargins(0, 0, 0, 0)
        display_btns_layout.setSpacing(12)
        display_btns_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        display_btns_layout.addWidget(self._edit_btn)
        display_btns_layout.addWidget(self._back_btn)

        edit_btns = QWidget()
        edit_btns.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        edit_btns_layout = QHBoxLayout(edit_btns)
        edit_btns_layout.setContentsMargins(0, 0, 0, 0)
        edit_btns_layout.setSpacing(12)
        edit_btns_layout.addWidget(self._save_btn)
        edit_btns_layout.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._btn_stack.addWidget(display_btns)
        self._btn_stack.addWidget(edit_btns)

        self._error_label = QLabel()
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setWordWrap(True)
        self._error_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._error_label.setVisible(False)

        btn_row = max(len(_PROJECT_COL1), len(_PROJECT_COL2))
        grid.addWidget(self._error_label, btn_row, 0, 1, 2)
        grid.addWidget(self._btn_stack, btn_row + 1, 0, 1, 2, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        grid.setRowMinimumHeight(btn_row + 1, 52)

        card_layout.addLayout(grid)
        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        self._switch_to_view_mode()

    def set_project(self, project: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        """Load and display the given project record. If edit_mode=True, open in edit mode."""
        self._project = dict(project) if project else {}
        self._refresh_edit_action_access()
        self._refresh_values()
        if edit_mode and self._project and self._can_edit_action:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _refresh_edit_action_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_edit_action = True
        else:
            allowed_actions = collect_allowed_action_names(steps)
            self._can_edit_action = nav_action_visible(
                "API: Projects", "edit", allowed_actions
            )
        self._edit_btn.setEnabled(self._can_edit_action)
        self._edit_btn.setToolTip("" if self._can_edit_action else "Require Permission.")

    def _refresh_values(self) -> None:
        """Sync field values from _project."""
        for label_text, keys in _PROJECT_FIELD_GROUPS:
            canonical = keys[0]
            value = _get_value(self._project, keys)
            text = _format_value(value, keys[0], keys)
            if canonical in ("projectStatus", "project_status"):
                text = (str(value).strip().upper() if value is not None else "") or "ACTIVE"
            edit = self._field_edits.get(canonical)
            if edit:
                if isinstance(edit, QComboBox):
                    if text and edit.findText(text) < 0:
                        edit.addItem(text)
                    edit.setCurrentText(text if text else "ACTIVE")
                else:
                    edit.setText(text)

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def _get_edit_value(self, *keys: str) -> str:
        for key in keys:
            edit = self._field_edits.get(key)
            if edit:
                if isinstance(edit, QComboBox):
                    return edit.currentText().strip()
                return edit.text().strip()
        return ""

    def _handle_edit(self) -> None:
        if not self._can_edit_action:
            self._show_error("Require Permission.")
            return
        self._clear_error()
        for key in self._editable_keys:
            edit = self._field_edits.get(key)
            if edit:
                if isinstance(edit, QComboBox):
                    edit.setEnabled(True)
                    edit.setStyleSheet(FORM_COMBOBOX_STYLE)
                else:
                    edit.setReadOnly(False)
                    edit.setStyleSheet(INPUT_STYLE)
        self._btn_stack.setCurrentIndex(1)

    def _handle_cancel(self) -> None:
        if not self._has_unsaved_changes():
            self._clear_error()
            self._refresh_values()
            self._switch_to_view_mode()
            return
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard and leave?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Discard:
            self._clear_error()
            self._refresh_values()
            self._switch_to_view_mode()

    def _has_unsaved_changes(self) -> bool:
        for label_text, keys in _PROJECT_FIELD_GROUPS:
            canonical = keys[0]
            if canonical not in self._editable_keys:
                continue
            original = _get_value(self._project, keys)
            if canonical in ("projectStatus", "project_status"):
                orig_str = (str(original).strip().upper() if original is not None else "") or "ACTIVE"
            else:
                orig_str = _format_value(original, keys[0], keys)
            current = self._get_edit_value(canonical)
            if orig_str.strip() != (current or "").strip():
                return True
        return False

    def _handle_save(self) -> None:
        self._clear_error()
        if not self._has_unsaved_changes():
            navigate_after_no_changes(
                show_non_error_message=self._show_success,
                clear_message=self._clear_error,
                on_back=self.on_back,
            )
            return
        project_name = self._get_edit_value("projectName", "project_name")
        project_owner = self._get_edit_value("projectOwnerUserId", "projectOwnerUserld", "project_owner_user_id")
        project_desc = self._get_edit_value("projectDesc", "project_desc", "projectDescription")
        project_status = self._get_edit_value("projectStatus", "project_status") or "ACTIVE"
        project_server = self._get_edit_value("projectServer", "project_server")
        project_port = self._get_edit_value("projectPort", "project_port")

        if not project_name:
            self._show_error("Project name is required.")
            return
        if not project_owner:
            self._show_error("Project Owner User ID is required.")
            return

        project_id = _get_project_id(self._project)
        if project_id is None:
            self._show_error("Project Id (Internal) is missing.")
            return

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_update_project(
            project_id,
            project_name,
            token=token,
            project_desc=project_desc or None,
            project_owner_user_id=project_owner,
            project_status=project_status,
            project_server=project_server or None,
            project_port=project_port or None,
        )

        if not result.get("success"):
            self._show_error(result.get("message", "Failed to update project."))
            return

        self._project["projectName"] = project_name
        self._project["projectDesc"] = project_desc
        self._project["projectOwnerUserId"] = project_owner
        self._project["projectStatus"] = project_status
        self._project["projectServer"] = project_server
        self._project["projectPort"] = project_port
        self._show_success(result.get("message", "Project updated successfully."))

        schedule_after_success(
            delay_ms=800,
            clear_error=self._clear_error,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )

    def _switch_to_view_mode(self) -> None:
        for key in self._editable_keys:
            edit = self._field_edits.get(key)
            if edit:
                if isinstance(edit, QComboBox):
                    edit.setEnabled(False)
                    edit.setStyleSheet(FORM_COMBOBOX_STYLE)
                else:
                    edit.setReadOnly(True)
                    edit.setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1
