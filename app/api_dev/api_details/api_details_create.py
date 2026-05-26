"""API Details create page - form to add API detail."""

from __future__ import annotations

import re
from typing import Any, Callable

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QCompleter,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.api_dev.api_details.api_method_combo import configure_api_method_combo
from core.api import (
    api_create_api_detail,
    api_get_all_projects,
    api_get_master_key_by_app_id_field_name,
    master_key_row_seq_value,
)
from core.nav_access import LEFT_PANEL_NAV_ITEM_APP_ID_KEYS
from core.user_context import get_nav_access_steps, get_user_profile
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
from ui.searchable_form_combo import (
    combo_resolved_master_key_seq,
    master_key_invalid_typed_text,
    master_key_seq_for_payload,
    require_master_key_seq_for_payload,
    populate_master_key_by_field_name,
    set_searchable_combo_by_user_data,
    wire_searchable_master_key_combo,
)
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label, labeled_field_block

# Two independent vertical columns (no QGridLayout — no row alignment across columns).
_COL1_FIELDS = (
    ("Project Id", "project_id"),
    ("Project Name*", "project_name"),
    ("Folder", "folder"),
    ("API Method*", "api_method"),
    ("API name*", "api_name"),
    ("localhost path", "localhost_path"),
    ("Server path", "server_path"),
    ("Requirement", "requirement"),
)
_COL2_FIELDS = (
    ("API Status", "api_status"),
    ("Comments", "comments"),
    ("Request", "request"),
    ("Response", "response"),
)
_API_DETAILS_NAV_LABEL = "API: Details"
_API_STATUS_FIELD_NAME = "api_status"


class CreateAPIDetailPage(QWidget):
    """Page with form to add API detail."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._project_completions: list[tuple[str, Any, dict[str, Any]]] = []
        self._default_api_status = "ACTIVE"
        self._build_ui()
        self._load_api_status_options()

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
        title = QLabel("Create API Detail")
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
            "folder": placeholder_example("/api/v1"),
            "api_name": placeholder_example("GetUser"),
            "localhost_path": placeholder_example("http://localhost:8080/api"),
            "server_path": placeholder_example("https://api.example.com"),
            "requirement": "Requirement description",
            "api_status": "",
            "comments": "Optional comments",
            "request": "Request body or description",
            "response": "Expected or sample response",
        }

        _multiline_h = 80

        def append_field(stack: QVBoxLayout, label_text: str, field_key: str) -> None:
            if field_key == "api_status":
                lbl = QLabel("API Status:")
                lbl.setStyleSheet(LABEL_STYLE)
                w = QComboBox()
                apply_form_combobox_field(w, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX)
                wire_searchable_master_key_combo(w, search_field_label="API status")
                self.api_status_combo = w
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
            elif field_key == "api_method":
                w = QComboBox()
                configure_api_method_combo(w, current=None, default_index=0)
                apply_form_combobox_field(w, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX)
                self.api_method_combo = w
            elif field_key == "comments":
                w = QPlainTextEdit()
                w.setFixedHeight(_multiline_h)
                w.setStyleSheet(INPUT_STYLE)
                self.comments_edit = w
            elif field_key == "request":
                w = QPlainTextEdit()
                w.setFixedHeight(_multiline_h)
                w.setStyleSheet(INPUT_STYLE)
                self.request_edit = w
            elif field_key == "response":
                w = QPlainTextEdit()
                w.setFixedHeight(_multiline_h)
                w.setStyleSheet(INPUT_STYLE)
                self.response_edit = w
            else:
                w = QLineEdit()
                w.setStyleSheet(INPUT_STYLE)
                if field_key == "folder":
                    self.folder_edit = w
                elif field_key == "api_name":
                    self.api_name_edit = w
                elif field_key == "localhost_path":
                    self.localhost_path_edit = w
                elif field_key == "server_path":
                    self.server_path_edit = w
                elif field_key == "requirement":
                    self.requirement_edit = w

            ph = placeholders.get(field_key)
            if ph:
                w.setPlaceholderText(ph)

            if field_key in ("localhost_path", "server_path"):
                icon_btn = QToolButton()
                icon_btn.setIcon(
                    QIcon(
                        QApplication.style().standardPixmap(
                            QStyle.StandardPixmap.SP_BrowserReload
                        )
                    )
                )
                icon_btn.setToolTip("Auto-fill from project")
                icon_btn.setFixedSize(22, 22)
                icon_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                icon_btn.setStyleSheet(
                    "QToolButton { background: transparent; border: none; border-radius: 4px; }"
                    "QToolButton:hover { background: #e2e8f0; }"
                )
                label_row = QWidget()
                label_row_layout = QHBoxLayout(label_row)
                label_row_layout.setContentsMargins(0, 0, 0, 0)
                label_row_layout.setSpacing(6)
                label_row_layout.addWidget(lbl)
                label_row_layout.addWidget(icon_btn)
                label_row_layout.addStretch()
                if field_key == "localhost_path":
                    icon_btn.clicked.connect(self._on_localhost_path_icon_clicked)
                else:
                    icon_btn.clicked.connect(self._on_server_path_icon_clicked)
                stack.addWidget(labeled_field_block(label_row, w))
                return

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
        """Fetch projects and setup completer for project name/ID search."""
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
            for disp, pid, project in self._project_completions:
                if disp == text:
                    self.project_id_edit.setText(str(pid))
                    self.project_name_edit.setText(disp)
                    break

        completer.activated.connect(on_activated)
        self.project_name_edit.setCompleter(completer)

    def _get_selected_project(self) -> dict[str, Any] | None:
        """Return the project dict for the currently selected project, or None."""
        text = self.project_name_edit.text().strip()
        if not text:
            return None
        for disp, _pid, project in self._project_completions:
            if disp == text:
                return project
        return None

    def _on_localhost_path_icon_clicked(self) -> None:
        """Populate localhost path from selected project (port + api_name). If port is blank/null/0, set to blank."""
        project = self._get_selected_project()
        if not project:
            return
        port_raw = project.get("projectPort") or project.get("project_port")
        if port_raw is None or str(port_raw).strip() == "":
            self.localhost_path_edit.clear()
            return
        try:
            port_val = int(port_raw)
        except (ValueError, TypeError):
            self.localhost_path_edit.clear()
            return
        if port_val == 0:
            self.localhost_path_edit.clear()
            return
        api_name = self.api_name_edit.text().strip()
        if api_name and not api_name.startswith("/"):
            api_name = "/" + api_name
        self.localhost_path_edit.setText(f"localhost:{port_val}{api_name}")

    def _on_server_path_icon_clicked(self) -> None:
        """Populate server path from selected project (server + port + api_name). If port or server is blank/null/0, set to blank."""
        project = self._get_selected_project()
        if not project:
            return
        port_raw = project.get("projectPort") or project.get("project_port")
        if port_raw is None or str(port_raw).strip() == "":
            self.server_path_edit.clear()
            return
        try:
            port_val = int(port_raw)
        except (ValueError, TypeError):
            self.server_path_edit.clear()
            return
        if port_val == 0:
            self.server_path_edit.clear()
            return
        server = (
            project.get("projectServer")
            or project.get("project_server")
            or ""
        )
        server = str(server).strip()
        if not server:
            self.server_path_edit.clear()
            return
        api_name = self.api_name_edit.text().strip()
        if api_name and not api_name.startswith("/"):
            api_name = "/" + api_name
        self.server_path_edit.setText(f"http://{server}:{port_val}{api_name}")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._load_api_status_options()
        self._setup_project_completer()

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if obj == self.project_name_edit and event.type() == QEvent.Type.FocusIn:
            self._setup_project_completer()
        return super().eventFilter(obj, event)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=True)

    def _load_api_status_options(self) -> None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_master_key_by_app_id_field_name(
            field_name=_API_STATUS_FIELD_NAME,
            token=token,
        )
        rows = result.get("data") if result.get("success") else []
        default_seq: Any | None = None
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if str(row.get("keyValue") or row.get("key_value") or "").strip().upper() == "ACTIVE":
                    default_seq = master_key_row_seq_value(row)
                    break
        populate_master_key_by_field_name(
            self.api_status_combo,
            _API_STATUS_FIELD_NAME,
            token=token,
            include_placeholder=False,
        )
        if self.api_status_combo.count() == 0:
            self.api_status_combo.blockSignals(True)
            self.api_status_combo.addItem("ACTIVE", "ACTIVE")
            self.api_status_combo.addItem("INACTIVE", "INACTIVE")
            self.api_status_combo.setCurrentIndex(-1)
            le = self.api_status_combo.lineEdit()
            if le is not None:
                le.clear()
            self.api_status_combo.blockSignals(False)
            default_seq = "ACTIVE"
        if default_seq is not None:
            set_searchable_combo_by_user_data(self.api_status_combo, default_seq)
        elif self.api_status_combo.count() > 0:
            set_searchable_combo_by_user_data(self.api_status_combo, self.api_status_combo.itemData(0))
        self._default_api_status = str(
            combo_resolved_master_key_seq(self.api_status_combo) or default_seq or "ACTIVE"
        )

    def reload_api_status_options(self) -> None:
        self._load_api_status_options()

    def _app_id_from_nav_steps(self) -> int | str | None:
        steps = get_nav_access_steps()
        allowed_desc = LEFT_PANEL_NAV_ITEM_APP_ID_KEYS.get(_API_DETAILS_NAV_LABEL, ())
        if not allowed_desc:
            return None
        if steps:
            for row in steps:
                if not isinstance(row, dict):
                    continue
                desc = str(
                    row.get("appIdDescription")
                    or row.get("app_id_description")
                    or ""
                ).strip()
                if desc not in allowed_desc:
                    continue
                app_id = row.get("appId")
                if app_id is None:
                    app_id = row.get("app_id")
                if app_id is None:
                    app_id = row.get("applicationId")
                if app_id is None:
                    continue
                app_id_text = str(app_id).strip()
                if not app_id_text:
                    continue
                return int(app_id_text) if app_id_text.isdigit() else app_id_text
        return None

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
            "folder": "",
            "api_method": "GET",
            "api_name": "",
            "localhost_path": "",
            "server_path": "",
            "requirement": "",
            "api_status": self._default_api_status,
            "comments": "",
            "request": "",
            "response": "",
        }

    def is_dirty(self) -> bool:
        d = self._get_default_values()
        return (
            self.project_id_edit.text().strip() != d["project_id"]
            or self.project_name_edit.text().strip() != d["project_name"]
            or self.folder_edit.text().strip() != d["folder"]
            or self.api_method_combo.currentText().strip() != d["api_method"]
            or self.api_name_edit.text().strip() != d["api_name"]
            or self.localhost_path_edit.text().strip() != d["localhost_path"]
            or self.server_path_edit.text().strip() != d["server_path"]
            or self.requirement_edit.text().strip() != d["requirement"]
            or str(combo_resolved_master_key_seq(self.api_status_combo) or "").strip()
            != str(d["api_status"]).strip()
            or self.comments_edit.toPlainText().strip() != d["comments"]
            or self.request_edit.toPlainText().strip() != d["request"]
            or self.response_edit.toPlainText().strip() != d["response"]
        )

    def reset_to_default(self) -> None:
        self.project_id_edit.clear()
        self.project_name_edit.clear()
        self.folder_edit.clear()
        configure_api_method_combo(self.api_method_combo, current=None, default_index=0)
        self.api_name_edit.clear()
        self.localhost_path_edit.clear()
        self.server_path_edit.clear()
        self.requirement_edit.clear()
        ds = self._default_api_status
        parsed: Any = int(ds) if str(ds).isdigit() else ds
        set_searchable_combo_by_user_data(self.api_status_combo, parsed)
        self.comments_edit.clear()
        self.request_edit.clear()
        self.response_edit.clear()

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

        api_method = self.api_method_combo.currentText().strip()
        if not api_method:
            self._show_error("API Method is required.")
            return

        api_name = self.api_name_edit.text().strip()
        if not api_name:
            self._show_error("API name is required.")
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

        api_status_val, api_status_err = require_master_key_seq_for_payload(
            self.api_status_combo, field_caption="API Status", strict_phrase="an API status"
        )
        if api_status_err:
            self._show_error(api_status_err)
            self.api_status_combo.setFocus()
            return

        result = api_create_api_detail(
            project_id,
            token=token,
            app_id=self._app_id_from_nav_steps(),
            folder=self.folder_edit.text().strip(),
            api_method=api_method,
            api_name=api_name,
            localhost_path=self.localhost_path_edit.text().strip(),
            server_path=self.server_path_edit.text().strip(),
            requirement=self.requirement_edit.text().strip(),
            api_status=api_status_val,
            comments=self.comments_edit.toPlainText().strip(),
            request_body=self.request_edit.toPlainText().strip(),
            response_body=self.response_edit.toPlainText().strip(),
        )

        if result.get("success"):
            self._show_success(result.get("message", "API detail created successfully."))
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
        else:
            self._show_error(result.get("message", "Failed to create API detail."))
