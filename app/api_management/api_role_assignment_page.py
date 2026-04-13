"""API–Role assignment page — list APIs and grant role access."""

from __future__ import annotations

import json
import traceback
from typing import Any

from PySide6.QtCore import QObject, QPoint, QSize, Qt, QStringListModel, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCursor, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.api import (
    api_change_api_access_by_id,
    api_delete_api_access_by_id,
    api_get_all_apis,
    api_get_all_roles,
    api_get_api_access_by_api_id,
    api_grant_api_access,
)
from core.app_preferences import format_datetime_display, is_datetime_field
from ui.blank_display import is_blank_display_value
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET,
    MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET,
    MODAL_FIELD_HEIGHT_PX,
    MODAL_FIELD_LABEL_STYLE,
    placeholder_search_select,
)
from ui.data_table import (
    apply_data_table_appearance,
    attach_table_copy_shortcut,
    clear_filter_row_widgets,
    data_row_offset,
    filter_dict_rows_by_column_edits,
    install_filter_row,
    MIN_DATA_COL_WIDTH_PX,
    resize_data_table_columns_to_content,
    sync_vertical_header_labels,
)
from ui.post_save_navigation import NO_CHANGES_MESSAGE
from ui.strict_completer import strict_list_selection_message

from app.user_management.users.user_create import INPUT_STYLE
from ui.form_combobox_style import FORM_COMBOBOX_STYLE, apply_form_combobox_field
from ui.styles import CONTEXT_MENU_STYLESHEET
from app.user_management.users.user_view import READONLY_INPUT_STYLE
from app.user_management.user_timepass.user_role_ui_helpers import _add_view_user_form_row

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})

_API_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("API Id", ("apiId", "api_id", "id")),
    ("Name", ("apiName", "api_name", "name", "title")),
    ("Method", ("httpMethod", "http_method", "method", "verb")),
    ("Endpoint", ("apiEndpoint", "api_endpoint", "endpoint", "path", "urlPath", "url_path", "url", "uri")),
    ("App Id", ("appId", "app_id", "appIdVal", "app_id_val")),
    ("App Desc", ("appDesc", "app_desc", "appDescription", "app_description", "description", "desc")),
    ("Created By", ("createdBy", "created_by")),
    ("Created At", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified At", ("modifiedAt", "modified_at", "updatedAt", "updated_at")),
)


def _flatten_row(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in _HIDDEN_KEYS}


def _value_for_column(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    flat = _flatten_row(row)
    for key in keys:
        if key in flat:
            return (flat[key], key)
    return (None, keys[0] if keys else "")


# Fixed columns for per-API role assignments (not extended from API payload keys).
_ASSIGNMENT_COLUMNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Role Name", ("roleName", "role_name")),
    ("API Assign Id", ("apiAssignId", "api_assign_id")),
    ("Status", ("status",)),
)

# Status values for PATCH .../change-access-api-by-id/{id}/{status}
_ACCESS_STATUS_CHOICES = ("ACTIVE", "DEACTIVE")


def _format_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


class _LoadWorker(QObject):
    finished = Signal(bool, object, object, str)

    def __init__(self, token: str | None) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        roles_result = api_get_all_roles(token=self._token)
        if not roles_result.get("success"):
            self.finished.emit(False, [], [], str(roles_result.get("message", "Failed to load roles.")))
            return
        apis_result = api_get_all_apis(token=self._token)
        if not apis_result.get("success"):
            self.finished.emit(False, [], [], str(apis_result.get("message", "Failed to load APIs.")))
            return
        roles = [r for r in (roles_result.get("data") or []) if isinstance(r, dict)]
        apis = [a for a in (apis_result.get("data") or []) if isinstance(a, dict)]
        self.finished.emit(True, roles, apis, "")


def _grant_dialog_cell(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    v, key_used = _value_for_column(row, keys)
    return _format_cell(v, key_used, keys)


class _GrantAccessDialog(QDialog):
    """Grant role access to an API — layout aligned with Add User Role (_AssignRoleDialog)."""

    _API_ID_KEYS = ("apiId", "api_id", "id")
    _API_NAME_KEYS = ("apiName", "api_name", "name", "title")
    _API_METHOD_KEYS = ("httpMethod", "http_method", "method", "verb")
    _API_EP_KEYS = ("apiEndpoint", "api_endpoint", "endpoint", "path", "urlPath", "url_path", "url", "uri")

    def __init__(
        self,
        roles: list[dict[str, Any]],
        api_row: dict[str, Any],
        parent: QWidget | None = None,
        *,
        token: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._token = token
        self._api_id = api_row.get("apiId") or api_row.get("api_id") or api_row.get("id")
        self._grant_success_message = "Access granted successfully."
        self.setWindowTitle("Grant API Access")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setStyleSheet("QDialog { background: #ffffff; }")

        self._resolved_role_id: str | None = None
        self._role_pairs: list[tuple[str, str]] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.msg = QLabel()
        self.msg.setWordWrap(True)
        self.msg.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.msg.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.msg.setVisible(False)
        layout.addWidget(self.msg)

        form_opts = {
            "contents_margins": (0, 0, 0, 0),
            "h_spacing": 12,
            "v_spacing": 8,
            "label_align": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        }

        def _make_form() -> QFormLayout:
            f = QFormLayout()
            f.setContentsMargins(*form_opts["contents_margins"])
            f.setHorizontalSpacing(form_opts["h_spacing"])
            f.setVerticalSpacing(form_opts["v_spacing"])
            f.setLabelAlignment(form_opts["label_align"])
            return f

        fh = MODAL_FIELD_HEIGHT_PX
        top_form = _make_form()

        id_disp = _grant_dialog_cell(api_row, self._API_ID_KEYS)
        name_disp = _grant_dialog_cell(api_row, self._API_NAME_KEYS)
        method_disp = _grant_dialog_cell(api_row, self._API_METHOD_KEYS)
        ep_disp = _grant_dialog_cell(api_row, self._API_EP_KEYS)
        if not method_disp.strip() and not ep_disp.strip():
            meth_ep = ""
        elif not method_disp.strip():
            meth_ep = ep_disp
        elif not ep_disp.strip():
            meth_ep = method_disp
        else:
            meth_ep = f"{method_disp} {ep_disp}".strip()

        for caption, text in (
            ("API Id", id_disp),
            ("API Name", name_disp),
            ("Method / Endpoint", meth_ep),
        ):
            ro = QLineEdit(text)
            ro.setReadOnly(True)
            ro.setFixedHeight(fh)
            ro.setMinimumWidth(240)
            ro.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            ro.setStyleSheet(READONLY_INPUT_STYLE)
            _add_view_user_form_row(top_form, caption, ro)

        layout.addLayout(top_form)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #cbd5e1; border: none; max-height: 1px;")
        layout.addWidget(sep)

        bottom_form = _make_form()
        suggestions: list[str] = []
        for role in roles:
            rid = role.get("roleId") or role.get("role_id") or role.get("id")
            rname = str(role.get("roleName") or role.get("role_name") or role.get("name") or "").strip()
            if rid is None:
                continue
            disp = f"{rid} | {rname}" if rname else str(rid)
            self._role_pairs.append((str(rid), disp))
            suggestions.append(disp)

        self.role_edit = QLineEdit()
        self.role_edit.setPlaceholderText(placeholder_search_select("Role Id", "Role Name"))
        self.role_edit.setStyleSheet(INPUT_STYLE)
        self.role_edit.setFixedHeight(fh)
        self.role_edit.setMinimumWidth(240)
        self.role_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.role_completer = QCompleter(self.role_edit)
        self.role_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.role_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.role_completer.setMaxVisibleItems(12)
        self.role_edit.setCompleter(self.role_completer)
        self.role_completer.setModel(QStringListModel(suggestions))
        self.role_completer.activated.connect(self._on_role_selected)
        _add_view_user_form_row(bottom_form, "Role", self.role_edit)

        layout.addLayout(bottom_form)

        save_btn = QPushButton("Save")
        save_btn.setFixedWidth(100)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        save_btn.clicked.connect(self._submit)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self.reject)

        btn_row = QWidget()
        btn_row.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        br = QHBoxLayout(btn_row)
        br.setContentsMargins(0, 0, 0, 0)
        br.setSpacing(12)
        br.setAlignment(Qt.AlignmentFlag.AlignLeft)
        br.addWidget(save_btn)
        br.addWidget(cancel_btn)
        br.addStretch(1)
        layout.addWidget(btn_row)

    def _on_role_selected(self, text: str) -> None:
        self.role_edit.setText(text)

    def _role_id_from_text(self, txt: str) -> str:
        raw = txt.strip()
        if "|" in raw:
            raw = raw.split("|", 1)[0].strip()
        return raw

    def _submit(self) -> None:
        self.msg.clear()
        self.msg.setVisible(False)
        raw = self.role_edit.text().strip()
        allowed = {d for _, d in self._role_pairs}
        if not raw:
            self.msg.setText("Please enter or select a role.")
            self.msg.setVisible(True)
            return
        if raw not in allowed:
            self.msg.setText(strict_list_selection_message("a role"))
            self.msg.setVisible(True)
            return
        rid = self._role_id_from_text(raw)
        self._resolved_role_id = rid
        if self._api_id is None:
            self.msg.setText("Selected API does not have an API Id.")
            self.msg.setVisible(True)
            return
        if not self._token or not str(self._token).strip():
            self.msg.setText("Session expired. Please log in again.")
            self.msg.setVisible(True)
            return
        result = api_grant_api_access(role_id=rid, api_id=self._api_id, token=self._token)
        if not result.get("success"):
            self.msg.setText(str(result.get("message") or "Failed to grant access."))
            self.msg.setVisible(True)
            return
        self._grant_success_message = str(result.get("message") or "Access granted successfully.")
        self.accept()

    def selected_role_id(self) -> str | None:
        return self._resolved_role_id

    def grant_success_message(self) -> str:
        return self._grant_success_message


def _edit_dialog_assign_id(row: dict[str, Any]) -> Any:
    return row.get("apiAssignId") or row.get("api_assign_id") or row.get("assignId") or row.get("assign_id")


def _edit_dialog_status_index(current: str) -> int:
    cur = (current or "").strip().upper()
    for i, s in enumerate(_ACCESS_STATUS_CHOICES):
        if s == cur:
            return i
    return 0


class _EditApiAssignmentDialog(QDialog):
    """Edit API–role access status — layout aligned with User Role Detail (view / Edit / Save)."""

    def __init__(
        self,
        parent: QWidget,
        api_row: dict[str, Any] | None,
        assignment_row: dict[str, Any],
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("API Assignment Detail")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setStyleSheet("QDialog { background: #ffffff; }")

        self._success_message: str | None = None
        self._assignment_row = dict(assignment_row)
        self._assign_id = _edit_dialog_assign_id(self._assignment_row)
        api_r = dict(api_row) if isinstance(api_row, dict) else {}

        self._status_before_edit = str(
            self._assignment_row.get("status") or self._assignment_row.get("roleStatus") or ""
        ).strip().upper()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        self.msg = QLabel()
        self.msg.setWordWrap(True)
        self.msg.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.msg.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.msg.setVisible(False)
        layout.addWidget(self.msg)

        form_opts = {
            "contents_margins": (0, 0, 0, 0),
            "h_spacing": 12,
            "v_spacing": 8,
            "label_align": Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        }

        def _make_form() -> QFormLayout:
            f = QFormLayout()
            f.setContentsMargins(*form_opts["contents_margins"])
            f.setHorizontalSpacing(form_opts["h_spacing"])
            f.setVerticalSpacing(form_opts["v_spacing"])
            f.setLabelAlignment(form_opts["label_align"])
            return f

        fh = MODAL_FIELD_HEIGHT_PX
        top_form = _make_form()

        id_disp = _grant_dialog_cell(api_r, _GrantAccessDialog._API_ID_KEYS)
        name_disp = _grant_dialog_cell(api_r, _GrantAccessDialog._API_NAME_KEYS)
        method_disp = _grant_dialog_cell(api_r, _GrantAccessDialog._API_METHOD_KEYS)
        ep_disp = _grant_dialog_cell(api_r, _GrantAccessDialog._API_EP_KEYS)
        if not method_disp.strip() and not ep_disp.strip():
            meth_ep = ""
        elif not method_disp.strip():
            meth_ep = ep_disp
        elif not ep_disp.strip():
            meth_ep = method_disp
        else:
            meth_ep = f"{method_disp} {ep_disp}".strip()

        assign_disp = _format_cell(self._assign_id, "apiAssignId", ("apiAssignId",))
        role_disp = (
            str(
                self._assignment_row.get("roleName")
                or self._assignment_row.get("role")
                or self._assignment_row.get("name")
                or ""
            ).strip()
        )
        cur_st = self._status_before_edit if self._status_before_edit else ""

        for caption, text in (
            ("API Id", id_disp),
            ("API Name", name_disp),
            ("Method / Endpoint", meth_ep),
            ("API Assign Id", assign_disp),
            ("Role", role_disp),
            ("Current access status", cur_st),
        ):
            ro = QLineEdit(text)
            ro.setReadOnly(True)
            ro.setFixedHeight(fh)
            ro.setMinimumWidth(240)
            ro.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            ro.setStyleSheet(READONLY_INPUT_STYLE)
            _add_view_user_form_row(top_form, caption, ro)

        layout.addLayout(top_form)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #cbd5e1; border: none; max-height: 1px;")
        layout.addWidget(sep)

        bottom_form = _make_form()
        self.new_status = QComboBox()
        for st in _ACCESS_STATUS_CHOICES:
            self.new_status.addItem(st)
        self.new_status.setCurrentIndex(_edit_dialog_status_index(self._status_before_edit))
        apply_form_combobox_field(self.new_status, height_px=fh, min_width=240)
        _add_view_user_form_row(bottom_form, "New status", self.new_status)
        layout.addLayout(bottom_form)

        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
        back_btn.clicked.connect(self._handle_back)

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedWidth(100)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        edit_btn.clicked.connect(self._handle_edit)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self._handle_cancel)

        save_btn = QPushButton("Save")
        save_btn.setFixedWidth(100)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        save_btn.clicked.connect(self._handle_save)

        display_btns = QWidget()
        dbl = QHBoxLayout(display_btns)
        dbl.setContentsMargins(0, 0, 0, 0)
        dbl.setSpacing(12)
        dbl.addWidget(edit_btn)
        dbl.addWidget(back_btn)

        edit_btns = QWidget()
        ebl = QHBoxLayout(edit_btns)
        ebl.setContentsMargins(0, 0, 0, 0)
        ebl.setSpacing(12)
        ebl.addWidget(save_btn)
        ebl.addWidget(cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._btn_stack.addWidget(display_btns)
        self._btn_stack.addWidget(edit_btns)

        btn_row = QWidget()
        btn_row.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        br = QHBoxLayout(btn_row)
        br.setContentsMargins(0, 0, 0, 0)
        br.setSpacing(12)
        br.setAlignment(Qt.AlignmentFlag.AlignLeft)
        br.addWidget(self._btn_stack)
        br.addStretch(1)
        layout.addWidget(btn_row)

        self._editing = False
        self._snap_status = ""
        self._switch_to_view_mode()

    def success_message(self) -> str | None:
        return self._success_message

    def _apply_status_from_row(self) -> None:
        self.new_status.setCurrentIndex(_edit_dialog_status_index(self._status_before_edit))

    def _switch_to_view_mode(self) -> None:
        self._editing = False
        self.msg.clear()
        self.msg.setVisible(False)
        self.new_status.setEnabled(False)
        self._btn_stack.setCurrentIndex(0)

    def _switch_to_edit_mode(self) -> None:
        self._editing = True
        self.new_status.setEnabled(True)
        self.new_status.setStyleSheet(FORM_COMBOBOX_STYLE)
        self._snap_status = self.new_status.currentText().strip().upper()
        self._btn_stack.setCurrentIndex(1)

    def _has_unsaved_changes(self) -> bool:
        if not self._editing:
            return False
        return self.new_status.currentText().strip().upper() != self._snap_status

    def _handle_back(self) -> None:
        self.reject()

    def _handle_edit(self) -> None:
        self.msg.clear()
        self.msg.setVisible(False)
        self._switch_to_edit_mode()

    def _handle_cancel(self) -> None:
        if not self._has_unsaved_changes():
            self.msg.clear()
            self.msg.setVisible(False)
            self._apply_status_from_row()
            self._switch_to_view_mode()
            return
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard and leave edit mode?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Discard:
            self.msg.clear()
            self.msg.setVisible(False)
            self._apply_status_from_row()
            self._switch_to_view_mode()

    def _handle_save(self) -> None:
        self._submit_api()

    def _submit_api(self) -> None:
        self.msg.clear()
        self.msg.setVisible(False)
        if not self._has_unsaved_changes():
            self._success_message = NO_CHANGES_MESSAGE
            self.accept()
            return
        new_status = self.new_status.currentText().strip().upper()
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        if not token:
            self.msg.setText("Session expired.")
            self.msg.setVisible(True)
            return
        result = api_change_api_access_by_id(self._assign_id, new_status, token=token)
        if result.get("success"):
            self._success_message = str(result.get("message", "Access updated."))
            self.accept()
        else:
            self.msg.setText(result.get("message", "Failed to update access."))
            self.msg.setVisible(True)


class ApiRoleAssignmentPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._loading = False
        self._pending_refresh = False
        self._roles: list[dict[str, Any]] = []
        self._apis: list[dict[str, Any]] = []
        self._load_thread: QThread | None = None
        self._load_worker: _LoadWorker | None = None
        self._current_api_id: Any = None
        self._current_api_row: dict[str, Any] | None = None
        self._api_column_spec: list[tuple[str, tuple[str, ...]]] = []
        self._filter_visible = False
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.setInterval(200)
        self._filter_apply_timer.timeout.connect(self._apply_api_column_filters_refresh)
        self._save_api_id_for_restore: Any = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        header_layout.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        title = QLabel("API: API-Role Assignment")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self._filter_btn = QPushButton("Filters")
        self._filter_btn.setCheckable(True)
        self._filter_btn.setChecked(False)
        self._filter_btn.setFixedWidth(100)
        self._filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_btn.setToolTip("Toggle per-column filters on the API list")
        self._filter_btn.setIconSize(QSize(18, 18))
        self._filter_btn.toggled.connect(self._on_api_filter_toggled)
        header_layout.addWidget(self._filter_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        header_layout.addWidget(refresh_btn)

        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
        )

        content = QWidget()
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        content.setMinimumHeight(320)
        content.setMinimumWidth(560)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.message_label.setVisible(False)
        content_layout.addWidget(self.message_label)

        self.table = QTableWidget()
        apply_data_table_appearance(self.table)
        self.table.setSortingEnabled(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.itemSelectionChanged.connect(self._on_api_selection_changed)
        attach_table_copy_shortcut(self.table)

        right_panel = QWidget()
        right_panel.setMinimumWidth(420)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self._assignments_table = QTableWidget()
        apply_data_table_appearance(self._assignments_table)
        assignment_cols = list(_ASSIGNMENT_COLUMNS)
        self._assignments_table.setColumnCount(len(assignment_cols))
        self._assignments_table.setHorizontalHeaderLabels([h for h, _ in assignment_cols])
        assign_hh = self._assignments_table.horizontalHeader()
        assign_hh.setStretchLastSection(False)
        for col in range(len(assignment_cols)):
            assign_hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        assign_hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        self._assignments_table.setSortingEnabled(True)
        self._assignments_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._assignments_table.customContextMenuRequested.connect(self._on_assignment_context_menu)
        self._assignments_table.itemDoubleClicked.connect(self._on_assignment_row_double_clicked)
        attach_table_copy_shortcut(self._assignments_table)
        right_layout.addWidget(self._assignments_table, 1)
        self._roles_msg = QLabel("")
        self._roles_msg.setVisible(False)
        self._roles_msg.setWordWrap(True)
        right_layout.addWidget(self._roles_msg)

        main_split = QSplitter(Qt.Orientation.Horizontal)
        main_split.setChildrenCollapsible(False)
        main_split.setHandleWidth(6)
        main_split.setMinimumHeight(260)
        main_split.addWidget(self.table)
        main_split.addWidget(right_panel)
        main_split.setStretchFactor(0, 1)
        main_split.setStretchFactor(1, 1)
        main_split.setSizes([480, 520])
        content_layout.addWidget(main_split, 1)

        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

    def _get_token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _populate_roles(self, roles: list[dict[str, Any]]) -> None:
        self._roles = roles

    def _api_data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _is_api_data_table_row(self, table_row: int) -> bool:
        return table_row >= self._api_data_row_offset()

    def _schedule_api_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_api_source_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._apis,
            self.table,
            self._api_column_spec,
            self._filter_visible,
            _value_for_column,
            _format_cell,
        )

    def _write_api_data_rows(self, data_rows: list[dict[str, Any]]) -> None:
        off = self._api_data_row_offset()
        self.table.setSortingEnabled(False)
        total = off + len(data_rows)
        if self._filter_visible and total < 1:
            total = 1
        self.table.setRowCount(total)
        if self._filter_visible:
            for c in range(self.table.columnCount()):
                self.table.takeItem(0, c)
            install_filter_row(
                self.table,
                len(self._api_column_spec),
                on_text_changed=self._schedule_api_filter_apply,
            )
        for r, row in enumerate(data_rows):
            tr = off + r
            for col_idx, (_, keys) in enumerate(self._api_column_spec):
                value, key_used = _value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(tr, col_idx, item)
        sync_vertical_header_labels(
            self.table,
            filter_visible=self._filter_visible,
            data_row_count=len(data_rows),
        )
        resize_data_table_columns_to_content(
            self.table,
            self._api_column_spec,
            self._apis,
            _value_for_column,
            _format_cell,
        )
        self.table.setSortingEnabled(not self._filter_visible)

    def _apply_api_column_filters_refresh(self) -> None:
        if not self._filter_visible or not self._api_column_spec or not self._apis:
            return
        try:
            filtered = self._filtered_api_source_rows()
            self._write_api_data_rows(filtered)
        except Exception:
            traceback.print_exc()

    def _on_api_filter_toggled(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            self._filter_apply_timer.stop()
            clear_filter_row_widgets(self.table)
        if self._api_column_spec and self._apis:
            try:
                to_show = self._filtered_api_source_rows() if checked else list(self._apis)
                self._write_api_data_rows(to_show)
            except Exception:
                traceback.print_exc()
        elif not self._apis:
            self.table.setSortingEnabled(False)
            clear_filter_row_widgets(self.table)
            self.table.setRowCount(0)
            self.table.setColumnCount(0)

    def _populate_table(self, rows: list[dict[str, Any]]) -> None:
        self._apis = [dict(r) for r in rows if isinstance(r, dict)]
        if not self._apis:
            self._api_column_spec = []
            self.table.setSortingEnabled(False)
            clear_filter_row_widgets(self.table)
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return
        try:
            self._api_column_spec = list(_API_COLUMNS)
            headers = [col for col, _ in self._api_column_spec]
            self.table.setSortingEnabled(False)
            self.table.setColumnCount(len(self._api_column_spec))
            self.table.setHorizontalHeaderLabels(headers)
            th = self.table.horizontalHeader()
            th.setStretchLastSection(False)
            for col in range(len(self._api_column_spec)):
                th.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            th.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
            filtered = self._filtered_api_source_rows() if self._filter_visible else list(self._apis)
            self._write_api_data_rows(filtered)
        except Exception:
            traceback.print_exc()
            self._api_column_spec = []
            self.table.setSortingEnabled(False)
            clear_filter_row_widgets(self.table)
            self.table.setRowCount(0)
            self.table.setColumnCount(0)

    def _api_name(self, row: dict[str, Any]) -> str:
        for key in ("apiName", "api_name", "name", "title"):
            val = row.get(key)
            if val is not None and str(val).strip():
                return str(val).strip()
        return "Selected API"

    def _load_roles_for_api(self, api_id: Any, api_name: str, *, api_row: dict[str, Any] | None = None) -> None:
        self._current_api_id = api_id
        self._current_api_row = api_row
        self._assignments_table.setSortingEnabled(False)
        self._assignments_table.setRowCount(0)
        self._roles_msg.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self._roles_msg.setText("Loading assignments...")
        self._roles_msg.setVisible(True)
        result = api_get_api_access_by_api_id(api_id, token=self._get_token())
        if not result.get("success"):
            self._roles_msg.setStyleSheet(FORM_ERROR_LABEL_STYLE)
            self._roles_msg.setText(result.get("message", "Failed to load assignments."))
            self._roles_msg.setVisible(True)
            show_auto_hiding_message(self, self.message_label, "")
            return
        raw = result.get("data") or []
        rows: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, dict):
                rows.append(item)
            elif isinstance(item, str) and item.strip():
                rows.append({"roleName": item.strip()})
        self._populate_assignments_table(rows)
        # Like Reporting Manager after hierarchy reload: clear top bar once data is in.
        show_auto_hiding_message(self, self.message_label, "")

    def _populate_assignments_table(self, rows: list[dict[str, Any]]) -> None:
        col_spec = list(_ASSIGNMENT_COLUMNS)
        if not rows:
            self._roles_msg.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
            self._roles_msg.setText("No role assignments for this API.")
            self._roles_msg.setVisible(True)
            self._assignments_table.setSortingEnabled(False)
            self._assignments_table.setRowCount(0)
            self._assignments_table.setSortingEnabled(True)
            return
        self._roles_msg.setVisible(False)
        try:
            data_rows = [dict(r) for r in rows if isinstance(r, dict)]
            self._assignments_table.setSortingEnabled(False)
            self._assignments_table.setRowCount(len(data_rows))
            for r_idx, row in enumerate(data_rows):
                full = dict(row)
                for c_idx, (_, keys) in enumerate(col_spec):
                    val, key_used = _value_for_column(full, keys)
                    cell = QTableWidgetItem(_format_cell(val, key_used, keys))
                    cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    cell.setData(Qt.ItemDataRole.UserRole, full)
                    self._assignments_table.setItem(r_idx, c_idx, cell)
            resize_data_table_columns_to_content(
                self._assignments_table,
                list(col_spec),
                data_rows,
                _value_for_column,
                _format_cell,
            )
            self._assignments_table.setSortingEnabled(True)
        except Exception:
            traceback.print_exc()
            self._assignments_table.setSortingEnabled(False)
            self._assignments_table.setRowCount(0)
            self._assignments_table.setSortingEnabled(True)

    def _assign_id_from_row(self, row: dict[str, Any]) -> Any:
        return row.get("apiAssignId") or row.get("api_assign_id") or row.get("assignId") or row.get("assign_id")

    def _reload_current_api_assignments(self) -> None:
        if self._current_api_id is None or not isinstance(self._current_api_row, dict):
            return
        api_id = self._current_api_id
        row = self._current_api_row
        name = self._api_name(row)
        # Same idea as Reporting Manager: replace success/error with a loading line, then clear when fetch finishes.
        cancel_auto_hide_message(self, self.message_label)
        self.message_label.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self.message_label.setText("Refreshing assignments…")
        self.message_label.setVisible(True)
        self._load_roles_for_api(api_id, name, api_row=row)
        QTimer.singleShot(350, lambda: self._load_roles_for_api(api_id, name, api_row=row))

    def _selected_api_table_row(self) -> int:
        sm = self.table.selectionModel()
        if sm is not None:
            srows = sm.selectedRows(0)
            if srows:
                r = int(srows[0].row())
                return r if self._is_api_data_table_row(r) else -1
        r = self.table.currentRow()
        if r >= 0 and self._is_api_data_table_row(r):
            return int(r)
        return -1

    def _on_api_selection_changed(self) -> None:
        row_idx = self._selected_api_table_row()
        if row_idx < 0:
            self._current_api_id = None
            self._current_api_row = None
            self._assignments_table.setSortingEnabled(False)
            self._assignments_table.setRowCount(0)
            self._assignments_table.setSortingEnabled(True)
            self._roles_msg.setVisible(False)
            return
        first = self.table.item(row_idx, 0)
        row_data = first.data(Qt.ItemDataRole.UserRole) if first else None
        if not isinstance(row_data, dict):
            return
        api_id = self._api_id(row_data)
        if api_id is None:
            self._assignments_table.setSortingEnabled(False)
            self._assignments_table.setRowCount(0)
            self._assignments_table.setSortingEnabled(True)
            self._current_api_id = None
            self._current_api_row = None
            self._roles_msg.setStyleSheet(FORM_ERROR_LABEL_STYLE)
            self._roles_msg.setText("Selected API does not have an API Id.")
            self._roles_msg.setVisible(True)
            return
        self._load_roles_for_api(api_id, self._api_name(row_data), api_row=row_data)

    def refresh(self) -> None:
        if self._loading:
            self._pending_refresh = True
            return
        self._save_api_id_for_restore = self._current_api_id
        self._loading = True
        cancel_auto_hide_message(self, self.message_label)
        self.message_label.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self.message_label.setText("Loading roles and APIs...")
        self.message_label.setVisible(True)
        self._load_thread = QThread(self)
        self._load_worker = _LoadWorker(self._get_token())
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.finished.connect(self._on_loaded)
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._cleanup_loader)
        self._load_thread.start()

    @Slot()
    def _on_loaded(self, success: bool, roles_obj: object, apis_obj: object, message: str) -> None:
        self._loading = False
        if not success:
            self._save_api_id_for_restore = None
            self._show_message(message or "Failed to load data.", error=True)
            self._populate_roles([])
            self._populate_table([])
        else:
            roles = list(roles_obj) if isinstance(roles_obj, list) else []
            apis = list(apis_obj) if isinstance(apis_obj, list) else []
            self._populate_roles([r for r in roles if isinstance(r, dict)])
            self._populate_table([a for a in apis if isinstance(a, dict)])
            show_auto_hiding_message(self, self.message_label, "")
            restored = False
            if self._save_api_id_for_restore is not None:
                restored = self._restore_api_selection(self._save_api_id_for_restore)
            if not restored and self.table.rowCount() > self._api_data_row_offset():
                self.table.selectRow(self._api_data_row_offset())
            self._save_api_id_for_restore = None
        if self._pending_refresh:
            self._pending_refresh = False
            self.refresh()

    def _cleanup_loader(self) -> None:
        if self._load_worker is not None:
            self._load_worker.deleteLater()
            self._load_worker = None
        if self._load_thread is not None:
            self._load_thread.deleteLater()
            self._load_thread = None

    def _show_message(self, text: str, *, error: bool) -> None:
        """Same pattern as Reporting Manager: green success / red error."""
        show_auto_hiding_message(self, self.message_label, text, error=error)

    def _api_id(self, row: dict[str, Any]) -> Any:
        return row.get("apiId") or row.get("api_id") or row.get("id")

    def _restore_api_selection(self, api_id: Any) -> bool:
        if api_id is None:
            return False
        target = str(api_id)
        off = self._api_data_row_offset()
        for row in range(off, self.table.rowCount()):
            item = self.table.item(row, 0)
            data = item.data(Qt.ItemDataRole.UserRole) if item else None
            if not isinstance(data, dict):
                continue
            aid = self._api_id(data)
            if aid is not None and str(aid) == target:
                self.table.setCurrentCell(row, 0)
                self.table.selectRow(row)
                return True
        return False

    def _get_row_api(self, row_index: int) -> dict[str, Any] | None:
        if row_index < 0 or row_index >= self.table.rowCount():
            return None
        if not self._is_api_data_table_row(row_index):
            return None
        first_cell = self.table.item(row_index, 0)
        row = first_cell.data(Qt.ItemDataRole.UserRole) if first_cell else None
        return row if isinstance(row, dict) else None

    def _selected_api_row_dict(self) -> dict[str, Any] | None:
        r = self._selected_api_table_row()
        return self._get_row_api(r)

    def _api_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        vp = self.table.viewport()

        def _from_viewport(vp_point: QPoint) -> dict[str, Any] | None:
            idx = self.table.indexAt(vp_point)
            if idx.isValid():
                return self._get_row_api(idx.row())
            item = self.table.itemAt(vp_point)
            if item:
                return self._get_row_api(item.row())
            return None

        api_row = _from_viewport(pos)
        if api_row is not None:
            return api_row
        return _from_viewport(vp.mapFrom(self.table, pos))

    def _on_context_menu(self, pos: QPoint) -> None:
        clicked_item = self.table.itemAt(pos)
        if clicked_item is not None and self._is_api_data_table_row(clicked_item.row()):
            self.table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self.table.selectRow(clicked_item.row())
        api_row = self._api_at_pos(pos)
        if api_row is None:
            api_row = self._selected_api_row_dict()
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        grant_action = menu.addAction("Grant API Access")
        has_api = api_row is not None and self._api_id(api_row) is not None
        grant_action.setEnabled(has_api)
        action = menu.exec(QCursor.pos())
        if action == grant_action and api_row is not None:
            self._grant_access(api_row)

    def _grant_access(self, api_row: dict[str, Any]) -> None:
        if not self._roles:
            self._show_message("Roles are not loaded yet. Please refresh and try again.", error=True)
            return
        token = self._get_token()
        if not token:
            self._show_message("Session expired. Please log in again.", error=True)
            return
        dlg = _GrantAccessDialog(self._roles, api_row, self, token=token)
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        api_id = self._api_id(api_row)
        if api_id is None:
            return
        self._current_api_id = api_id
        self._current_api_row = api_row
        self._show_message(dlg.grant_success_message(), error=False)
        self._reload_current_api_assignments()
        QTimer.singleShot(350, self._reload_current_api_assignments)

    def _selected_assignment_row(self) -> dict[str, Any] | None:
        items = self._assignments_table.selectedItems()
        if not items:
            return None
        item = self._assignments_table.item(items[0].row(), 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _prompt_edit_assignment_status(self, row_data: dict[str, Any]) -> None:
        assign_id = self._assign_id_from_row(row_data)
        if assign_id is None:
            self._show_message("Cannot edit: assignment id (apiAssignId) is missing.", error=True)
            return
        api_row = self._current_api_row if isinstance(self._current_api_row, dict) else None
        dlg = _EditApiAssignmentDialog(self, api_row, row_data)
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        msg = dlg.success_message() or "Access updated."
        self._show_message(msg, error=False)
        self._reload_current_api_assignments()
        QTimer.singleShot(350, self._reload_current_api_assignments)

    def _remove_selected_assignment_impl(self, row_data: dict[str, Any]) -> None:
        assign_id = self._assign_id_from_row(row_data)
        if assign_id is None:
            self._show_message("Cannot remove: assignment id is missing.", error=True)
            return
        role_name = row_data.get("roleName") or row_data.get("name") or str(assign_id)
        reply = QMessageBox.question(
            self,
            "Remove Role Assignment",
            f"Remove role assignment '{role_name}' for this API?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        token = self._get_token()
        if not token:
            self._show_message("Session expired.", error=True)
            return
        result = api_delete_api_access_by_id(assign_id, token=token)
        if result.get("success"):
            self._show_message(result.get("message", "Assignment removed."), error=False)
            self._reload_current_api_assignments()
            QTimer.singleShot(350, self._reload_current_api_assignments)
        else:
            self._show_message(result.get("message", "Failed to remove access."), error=True)

    def _on_assignment_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if self._current_api_id is None:
            self._show_message("Select an API first.", error=True)
            return
        row_item = self._assignments_table.item(item.row(), 0)
        if row_item is None:
            return
        row_data = row_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(row_data, dict):
            return
        self._prompt_edit_assignment_status(row_data)

    def _on_assignment_context_menu(self, pos: QPoint) -> None:
        clicked_item = self._assignments_table.itemAt(pos)
        if clicked_item is not None:
            self._assignments_table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self._assignments_table.selectRow(clicked_item.row())
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Grant API access")
        edit_action = menu.addAction("Edit Selected Assignment")
        remove_action = menu.addAction("Remove Selected Assignment")
        has_api = self._current_api_id is not None and isinstance(self._current_api_row, dict)
        has_assign_row = clicked_item is not None or bool(self._assignments_table.selectedItems())
        add_action.setEnabled(has_api)
        edit_action.setEnabled(has_assign_row)
        remove_action.setEnabled(has_assign_row)
        action = menu.exec(QCursor.pos())
        if action == add_action:
            if self._current_api_row is not None:
                self._grant_access(self._current_api_row)
            else:
                self._show_message("Select an API first.", error=True)
        elif action == remove_action:
            row_data = self._selected_assignment_row()
            if not row_data:
                self._show_message("Select a role assignment to remove.", error=True)
                return
            self._remove_selected_assignment_impl(row_data)
        elif action == edit_action:
            row_data = self._selected_assignment_row()
            if not row_data:
                self._show_message("Select a role assignment to edit.", error=True)
                return
            self._prompt_edit_assignment_status(row_data)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh()
