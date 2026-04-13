"""User role assignment list page with users-page options."""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QPoint, Qt, QDate, QTimer, QStringListModel
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QCheckBox,
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
    api_assign_user_role,
    api_delete_user_role_assignment_by_id,
    api_get_all_roles,
    api_get_all_users,
    api_update_user_role_assignment_by_id,
)
from core.app_preferences import format_datetime_display
from core.user_context import get_user_profile
from ui.auto_hide_message import show_auto_hiding_message
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET,
    MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET,
    MODAL_FEEDBACK_SUCCESS_STYLE,
    MODAL_FIELD_HEIGHT_PX,
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

from app.user_management.users.user_create import INPUT_STYLE, _DatePickerEdit
from ui.form_combobox_style import FORM_COMBOBOX_STYLE, apply_form_combobox_field
from ui.styles import CONTEXT_MENU_STYLESHEET
from app.user_management.users.user_view import READONLY_INPUT_STYLE, _display_for_column
from app.user_management.user_timepass.user_role_ui_helpers import (
    _STATUS_CHOICES,
    _VIEW_USER_ID_KEYS,
    _VIEW_USERNAME_KEYS,
    _add_view_user_form_row,
    _default_role_checked_from_assignment,
    _make_current_validity_widget,
    _normalize_role_name,
    _normalize_status_name,
)


def _default_role_display_from_row(r: dict[str, Any] | None) -> str:
    """Map UI Default Role column from API ``defaultRole`` (and aliases) on the assignment/role row."""
    if not isinstance(r, dict):
        return ""
    raw: Any = None
    for k in (
        "defaultRole",
        "default_role",
        "defaultrole",
        "DefaultRole",
        "isDefault",
        "is_default",
        "isDefaultRole",
        "is_default_role",
    ):
        if k not in r:
            continue
        v = r[k]
        if v is None:
            continue
        raw = v
        break
    if raw is None:
        return ""
    if isinstance(raw, bool):
        return "Yes" if raw else "No"
    if isinstance(raw, (int, float)):
        return "Yes" if raw != 0 else "No"
    s = str(raw).strip().lower()
    if s in ("yes", "y", "true", "1", "on"):
        return "Yes"
    if s in ("no", "n", "false", "0", "off"):
        return "No"
    return ""


def _row_with_default_role_from_user(user: dict[str, Any], r: dict[str, Any]) -> dict[str, Any]:
    """Enrich role row from ``userRoleAssignments``: default flags, ``roleId``, assignment ids (for Edit/API)."""
    out = dict(r)
    assigns = user.get("userRoleAssignments")
    if not isinstance(assigns, list):
        return out
    rname = _normalize_role_name(
        str(out.get("roleName") or out.get("role") or out.get("name") or "").strip()
    )
    rid = out.get("roleId") or out.get("role_id")
    for ar in assigns:
        if not isinstance(ar, dict):
            continue
        aname = _normalize_role_name(
            str(ar.get("roleName") or ar.get("role") or ar.get("name") or "").strip()
        )
        aid = ar.get("roleId") or ar.get("role_id")
        by_id = rid is not None and aid is not None and str(rid) == str(aid)
        by_name = bool(rname) and bool(aname) and rname == aname
        if not (by_id or by_name):
            continue
        if aid is not None:
            out["roleId"] = aid
        nested = ar.get("role")
        if isinstance(nested, dict):
            nid = nested.get("roleId") or nested.get("role_id") or nested.get("id")
            if nid is not None and out.get("roleId") is None and out.get("role_id") is None:
                out["roleId"] = nid
        for k in ("userRoleAssignmentId", "user_role_assignment_id", "assignmentId"):
            if out.get(k) is None and ar.get(k) is not None:
                out[k] = ar[k]
        if not any(
            out.get(x) for x in ("userRoleAssignmentId", "user_role_assignment_id", "assignmentId")
        ):
            if ar.get("id") is not None and (
                ar.get("roleId") is not None
                or ar.get("role_id") is not None
                or ar.get("userId") is not None
                or ar.get("user_id") is not None
            ):
                out["assignmentId"] = ar["id"]
        if _default_role_display_from_row(out) not in ("Yes", "No"):
            for k in (
                "defaultRole",
                "default_role",
                "defaultrole",
                "DefaultRole",
                "isDefault",
                "is_default",
                "isDefaultRole",
                "is_default_role",
            ):
                if k not in ar:
                    continue
                v = ar[k]
                if v is None:
                    continue
                out[k] = v
        break
    return out


_URA_USER_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("User Id", ("userId", "user_id", "id")),
    ("Username", ("userName", "username", "user_name")),
    ("Name", ("__ura_full_name__",)),
    ("Account status", ("status", "userStatus")),
)


def _value_for_ura_user(user: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    if keys == ("__ura_full_name__",):
        full = f"{user.get('firstName') or ''} {user.get('lastName') or ''}".strip()
        return (full, "name")
    if keys == ("status", "userStatus"):
        raw = user.get("status") or user.get("userStatus") or ""
        if str(raw).strip():
            return (_normalize_status_name(str(raw).strip().upper()), "status")
        return ("", "status")
    for kk in keys:
        v = user.get(kk)
        if v is not None:
            return (v, kk)
    return (None, keys[0] if keys else "")


def _format_ura_user_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if value is None:
        return ""
    return str(value)


_URA_ROLE_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Role", ("role",)),
    ("Status", ("status",)),
    ("Valid From", ("validFrom",)),
    ("Valid To", ("validTo",)),
    ("Default Role", ("defaultDisplay",)),
)


def _value_for_ura_role_payload(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    k = keys[0]
    return (row.get(k), k)


def _format_ura_role_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if key in ("validFrom", "validTo"):
        return format_datetime_display(value or None)
    if value is None:
        return ""
    return str(value)


class _AssignRoleDialog(QDialog):
    """Assign a role to a user or edit an existing assignment (status, validity, default)."""

    def __init__(
        self,
        parent: QWidget,
        user: dict[str, Any],
        *,
        assignment: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self.user = user
        self.assignment = assignment or {}
        self._assignment_id = (
            self.assignment.get("userRoleAssignmentId")
            or self.assignment.get("user_role_assignment_id")
            or self.assignment.get("assignmentId")
            or self.assignment.get("id")
        )
        is_edit = self._assignment_id is not None
        self.setWindowTitle("User Role Detail" if is_edit else "Add User Role")
        self.setModal(True)
        self.setMinimumWidth(480)

        user_id = str(user.get("userId") or user.get("user_id") or user.get("id") or "")
        self._user_id = user_id

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

        uid_edit = QLineEdit(_display_for_column(user, _VIEW_USER_ID_KEYS))
        uid_edit.setReadOnly(True)
        uid_edit.setFixedHeight(fh)
        uid_edit.setMinimumWidth(240)
        uid_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        uid_edit.setStyleSheet(READONLY_INPUT_STYLE)
        _add_view_user_form_row(top_form, "User Id", uid_edit)

        uname_edit = QLineEdit(_display_for_column(user, _VIEW_USERNAME_KEYS))
        uname_edit.setReadOnly(True)
        uname_edit.setFixedHeight(fh)
        uname_edit.setMinimumWidth(240)
        uname_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        uname_edit.setStyleSheet(READONLY_INPUT_STYLE)
        _add_view_user_form_row(top_form, "Username", uname_edit)

        full_name = f"{user.get('firstName') or ''} {user.get('lastName') or ''}".strip()
        name_edit = QLineEdit(full_name)
        name_edit.setReadOnly(True)
        name_edit.setFixedHeight(fh)
        name_edit.setMinimumWidth(240)
        name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        name_edit.setStyleSheet(READONLY_INPUT_STYLE)
        _add_view_user_form_row(top_form, "Name", name_edit)

        if is_edit:
            role_disp = (
                str(
                    self.assignment.get("roleName")
                    or self.assignment.get("role")
                    or self.assignment.get("name")
                    or ""
                ).strip()
            )
            cur_role_edit = QLineEdit(role_disp)
            cur_role_edit.setReadOnly(True)
            cur_role_edit.setFixedHeight(fh)
            cur_role_edit.setMinimumWidth(240)
            cur_role_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            cur_role_edit.setStyleSheet(READONLY_INPUT_STYLE)
            _add_view_user_form_row(top_form, "Role", cur_role_edit)

            st_raw = (
                self.assignment.get("status")
                or self.assignment.get("roleStatus")
                or self.assignment.get("userRoleStatus")
                or ""
            )
            cur_st = _normalize_status_name(str(st_raw).strip().upper()) or ""
            cur_status_edit = QLineEdit(cur_st)
            cur_status_edit.setReadOnly(True)
            cur_status_edit.setFixedHeight(fh)
            cur_status_edit.setMinimumWidth(240)
            cur_status_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            cur_status_edit.setStyleSheet(READONLY_INPUT_STYLE)
            _add_view_user_form_row(top_form, "Current role status", cur_status_edit)

            vf_raw = str(
                self.assignment.get("validFrom") or self.assignment.get("valid_from") or ""
            ).strip()
            vt_raw = str(
                self.assignment.get("validTo") or self.assignment.get("valid_to") or ""
            ).strip()
            cur_vf = _make_current_validity_widget(vf_raw, field_height=fh, min_width=240)
            _add_view_user_form_row(top_form, "Current valid from", cur_vf)
            cur_vt = _make_current_validity_widget(vt_raw, field_height=fh, min_width=240)
            _add_view_user_form_row(top_form, "Current valid to", cur_vt)

        layout.addLayout(top_form)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #cbd5e1; border: none; max-height: 1px;")
        layout.addWidget(sep)

        bottom_form = _make_form()

        self.role_edit: QLineEdit | None = None
        self.role_completer: QCompleter | None = None
        self.new_status = QComboBox()
        for st in _STATUS_CHOICES:
            self.new_status.addItem(st)
        apply_form_combobox_field(self.new_status, height_px=fh, min_width=240)
        self.new_status.currentTextChanged.connect(self._on_edit_new_status_changed)

        if is_edit:
            _add_view_user_form_row(bottom_form, "New status", self.new_status)
        else:
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
            self.role_completer.activated.connect(self._on_role_selected)
            _add_view_user_form_row(bottom_form, "Role", self.role_edit)
            _add_view_user_form_row(bottom_form, "Status", self.new_status)

        self.valid_from = _DatePickerEdit()
        self.valid_from.setDate(QDate.currentDate())
        self.valid_from.setMinimumWidth(240)
        self.valid_from.setFixedHeight(fh)
        self.valid_from.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_view_user_form_row(
            bottom_form, "New valid from" if is_edit else "Valid from", self.valid_from
        )

        self.valid_to = _DatePickerEdit()
        self.valid_to.setDate(QDate.currentDate().addYears(1))
        self.valid_to.setMinimumWidth(240)
        self.valid_to.setFixedHeight(fh)
        self.valid_to.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_view_user_form_row(
            bottom_form, "New valid to" if is_edit else "Valid to", self.valid_to
        )

        self.default_chk = QCheckBox("Default Role")
        self.default_chk.setCursor(Qt.CursorShape.PointingHandCursor)
        self.default_chk.setChecked(
            _default_role_checked_from_assignment(
                self.assignment,
                fallback=True if not is_edit else False,
            )
        )
        _add_view_user_form_row(bottom_form, "Default role", self.default_chk)

        layout.addLayout(bottom_form)

        self._is_edit_flow = is_edit
        self._editing = False
        self._snap_status = ""
        self._snap_vf = QDate.currentDate()
        self._snap_vt = QDate.currentDate()
        self._snap_default = False
        self._btn_stack: QStackedWidget | None = None

        if is_edit:
            back_btn = QPushButton("Back")
            back_btn.setFixedWidth(100)
            back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            back_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
            back_btn.clicked.connect(self._handle_edit_dialog_back)

            edit_btn = QPushButton("Edit")
            edit_btn.setFixedWidth(100)
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
            edit_btn.clicked.connect(self._handle_edit_dialog_edit)

            cancel_btn = QPushButton("Cancel")
            cancel_btn.setFixedWidth(100)
            cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            cancel_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
            cancel_btn.clicked.connect(self._handle_edit_dialog_cancel)

            save_btn = QPushButton("Save")
            save_btn.setFixedWidth(100)
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
            save_btn.clicked.connect(self._handle_edit_dialog_save)

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
            btn_row_layout = QHBoxLayout(btn_row)
            btn_row_layout.setContentsMargins(0, 0, 0, 0)
            btn_row_layout.setSpacing(12)
            btn_row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            btn_row_layout.addWidget(self._btn_stack)
            btn_row_layout.addStretch(1)
            layout.addWidget(btn_row)
        else:
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
            btn_row_layout = QHBoxLayout(btn_row)
            btn_row_layout.setContentsMargins(0, 0, 0, 0)
            btn_row_layout.setSpacing(12)
            btn_row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            btn_row_layout.addWidget(save_btn)
            btn_row_layout.addWidget(cancel_btn)
            btn_row_layout.addStretch(1)
            layout.addWidget(btn_row)

        self._roles: list[tuple[str, str]] = []
        self._submitted_assignment: dict[str, Any] | None = None
        self._closed_without_changes = False
        self._load_roles()
        self._prefill_from_assignment()
        self._on_edit_new_status_changed(self.new_status.currentText())
        if is_edit:
            self._switch_assign_role_to_view_mode()

    def _on_edit_new_status_changed(self, text: str) -> None:
        if self.new_status is None:
            return
        if self._is_edit_flow and not self._editing:
            self.valid_from.setEnabled(False)
            self.valid_to.setEnabled(False)
            self.valid_from.setStyleSheet(READONLY_INPUT_STYLE)
            self.valid_to.setStyleSheet(READONLY_INPUT_STYLE)
            return
        is_active = (text or "").strip().upper() == "ACTIVE"
        self.valid_from.setEnabled(is_active)
        self.valid_to.setEnabled(is_active)
        self.valid_from.setStyleSheet(INPUT_STYLE if is_active else READONLY_INPUT_STYLE)
        self.valid_to.setStyleSheet(INPUT_STYLE if is_active else READONLY_INPUT_STYLE)

    def _apply_bottom_fields_from_assignment(self) -> None:
        if self._assignment_id is not None and self.new_status is not None:
            st_raw = (
                self.assignment.get("status")
                or self.assignment.get("roleStatus")
                or self.assignment.get("userRoleStatus")
                or ""
            )
            cur_st = _normalize_status_name(str(st_raw).strip().upper()) or "ACTIVE"
            idx = self.new_status.findText(cur_st)
            self.new_status.setCurrentIndex(idx if idx >= 0 else 0)
        vf = str(self.assignment.get("validFrom") or self.assignment.get("valid_from") or "").strip()
        vt = str(self.assignment.get("validTo") or self.assignment.get("valid_to") or "").strip()
        if vf and "T" in vf:
            parsed_vf = QDate.fromString(vf.split("T", 1)[0], "yyyy-MM-dd")
            if parsed_vf.isValid():
                self.valid_from.setDate(parsed_vf)
        if vt and "T" in vt:
            parsed_vt = QDate.fromString(vt.split("T", 1)[0], "yyyy-MM-dd")
            if parsed_vt.isValid():
                self.valid_to.setDate(parsed_vt)
        self.default_chk.setChecked(
            _default_role_checked_from_assignment(
                self.assignment,
                fallback=False,
            )
        )

    def _switch_assign_role_to_view_mode(self) -> None:
        if not self._is_edit_flow or self._btn_stack is None or self.new_status is None:
            return
        self._editing = False
        self.msg.clear()
        self.msg.setVisible(False)
        self.new_status.setEnabled(False)
        self.default_chk.setEnabled(False)
        self._on_edit_new_status_changed(self.new_status.currentText())
        self._btn_stack.setCurrentIndex(0)

    def _switch_assign_role_to_edit_mode(self) -> None:
        if not self._is_edit_flow or self._btn_stack is None or self.new_status is None:
            return
        self._editing = True
        self.new_status.setEnabled(True)
        self.new_status.setStyleSheet(FORM_COMBOBOX_STYLE)
        self.default_chk.setEnabled(True)
        self._snap_status = self.new_status.currentText()
        self._snap_vf = self.valid_from.date()
        self._snap_vt = self.valid_to.date()
        self._snap_default = self.default_chk.isChecked()
        self._on_edit_new_status_changed(self.new_status.currentText())
        self._btn_stack.setCurrentIndex(1)

    def _assign_role_has_unsaved_changes(self) -> bool:
        if not self._editing or self.new_status is None:
            return False
        if self.new_status.currentText() != self._snap_status:
            return True
        if self.valid_from.date() != self._snap_vf:
            return True
        if self.valid_to.date() != self._snap_vt:
            return True
        if self.default_chk.isChecked() != self._snap_default:
            return True
        return False

    def _handle_edit_dialog_back(self) -> None:
        self.reject()

    def _handle_edit_dialog_edit(self) -> None:
        self.msg.clear()
        self.msg.setVisible(False)
        self._switch_assign_role_to_edit_mode()

    def _handle_edit_dialog_cancel(self) -> None:
        if not self._assign_role_has_unsaved_changes():
            self.msg.clear()
            self.msg.setVisible(False)
            self._apply_bottom_fields_from_assignment()
            self._switch_assign_role_to_view_mode()
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
            self._apply_bottom_fields_from_assignment()
            self._switch_assign_role_to_view_mode()

    def _handle_edit_dialog_save(self) -> None:
        self._submit()

    def _load_roles(self) -> None:
        if self.role_completer is None:
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_roles(token=token)
        self._roles = []
        suggestions: list[str] = []
        for r in (result.get("data") or []):
            if not isinstance(r, dict):
                continue
            rid = r.get("roleId") or r.get("role_id") or r.get("id")
            rname = str(r.get("roleName") or r.get("role_name") or r.get("name") or "").strip()
            if rid is None:
                continue
            display = f"{rid} | {rname}" if rname else str(rid)
            self._roles.append((str(rid), display))
            suggestions.append(display)
        self.role_completer.setModel(QStringListModel(suggestions))

    def _on_role_selected(self, text: str) -> None:
        if self.role_edit is not None:
            self.role_edit.setText(text)

    def _prefill_from_assignment(self) -> None:
        if not self.assignment:
            return
        if self._assignment_id is not None and self.new_status is not None:
            self._apply_bottom_fields_from_assignment()
        elif self.role_edit is not None:
            role_name = str(
                self.assignment.get("roleName")
                or self.assignment.get("role")
                or self.assignment.get("name")
                or ""
            ).strip()
            role_id = self.assignment.get("roleId") or self.assignment.get("role_id")
            if role_id is not None:
                disp = f"{role_id} | {role_name}" if role_name else str(role_id)
                self.role_edit.setText(disp)
            elif role_name:
                for rid, disp in self._roles:
                    if f"| {role_name}".lower() in disp.lower():
                        self.role_edit.setText(f"{rid} | {role_name}")
                        break

            vf = str(self.assignment.get("validFrom") or self.assignment.get("valid_from") or "").strip()
            vt = str(self.assignment.get("validTo") or self.assignment.get("valid_to") or "").strip()
            if vf and "T" in vf:
                parsed_vf = QDate.fromString(vf.split("T", 1)[0], "yyyy-MM-dd")
                if parsed_vf.isValid():
                    self.valid_from.setDate(parsed_vf)
            if vt and "T" in vt:
                parsed_vt = QDate.fromString(vt.split("T", 1)[0], "yyyy-MM-dd")
                if parsed_vt.isValid():
                    self.valid_to.setDate(parsed_vt)
            self.default_chk.setChecked(
                _default_role_checked_from_assignment(self.assignment, fallback=True)
            )
            st_raw = (
                self.assignment.get("status")
                or self.assignment.get("roleStatus")
                or self.assignment.get("userRoleStatus")
                or ""
            )
            cur_st = _normalize_status_name(str(st_raw).strip().upper()) or "ACTIVE"
            idx = self.new_status.findText(cur_st)
            self.new_status.setCurrentIndex(idx if idx >= 0 else 0)

    def _role_id_from_text(self, txt: str) -> str:
        raw = txt.strip()
        if "|" in raw:
            raw = raw.split("|", 1)[0].strip()
        return raw

    def _role_name_from_id(self, role_id: str) -> str:
        for rid, display in self._roles:
            if rid == role_id:
                if "|" in display:
                    return display.split("|", 1)[1].strip() or display.strip()
                return display.strip()
        return ""

    def submitted_assignment(self) -> dict[str, Any] | None:
        return self._submitted_assignment

    def closed_without_changes(self) -> bool:
        return self._closed_without_changes

    def _picker_date_ymd(self, picker: _DatePickerEdit) -> str:
        return picker.date().strftime("%Y-%m-%d")

    def _submit(self) -> None:
        if (
            self._is_edit_flow
            and self.new_status is not None
            and self._editing
            and not self._assign_role_has_unsaved_changes()
        ):
            self._closed_without_changes = True
            self.msg.setStyleSheet(MODAL_FEEDBACK_SUCCESS_STYLE)
            self.msg.setText(NO_CHANGES_MESSAGE)
            self.msg.setVisible(True)
            self.accept()
            return
        vf_ymd = self._picker_date_ymd(self.valid_from)
        vt_ymd = self._picker_date_ymd(self.valid_to)
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        if self._assignment_id is not None:
            role_id_raw = self.assignment.get("roleId") or self.assignment.get("role_id")
            if role_id_raw is None or str(role_id_raw).strip() == "":
                self.msg.setText("Role id is missing on this assignment; cannot save.")
                self.msg.setVisible(True)
                return
            role_id = str(role_id_raw).strip()
            status_new = self.new_status.currentText().strip().upper()
            if not status_new:
                self.msg.setText("Please select a status.")
                self.msg.setVisible(True)
                return
            if status_new == "ACTIVE":
                vf_d = self.valid_from.date()
                vt_d = self.valid_to.date()
                if vt_d < vf_d:
                    self.msg.setText(
                        "New valid to must be greater than or equal to new valid from."
                    )
                    self.msg.setVisible(True)
                    return
            result = api_update_user_role_assignment_by_id(
                self._assignment_id,
                user_id=int(self._user_id) if self._user_id.isdigit() else self._user_id,
                role_id=int(role_id) if role_id.isdigit() else role_id,
                valid_from=f"{vf_ymd}T00:00:00",
                valid_to=f"{vt_ymd}T23:59:59",
                default_role=self.default_chk.isChecked(),
                status=status_new,
                token=token,
            )
        else:
            if self.role_edit is None:
                return
            role_disp = self.role_edit.text().strip()
            allowed_roles = {d for _, d in self._roles}
            if not role_disp or role_disp not in allowed_roles:
                self.msg.setText(strict_list_selection_message("a role"))
                self.msg.setVisible(True)
                return
            role_id = self._role_id_from_text(role_disp)
            status_new = self.new_status.currentText().strip().upper()
            if not status_new:
                self.msg.setText("Please select a status.")
                self.msg.setVisible(True)
                return
            if status_new == "ACTIVE":
                vf_d = self.valid_from.date()
                vt_d = self.valid_to.date()
                if vt_d < vf_d:
                    self.msg.setText(
                        "Valid to must be greater than or equal to valid from."
                    )
                    self.msg.setVisible(True)
                    return
            result = api_assign_user_role(
                user_id=int(self._user_id) if self._user_id.isdigit() else self._user_id,
                role_id=int(role_id) if role_id.isdigit() else role_id,
                valid_from=f"{vf_ymd}T00:00:00",
                valid_to=f"{vt_ymd}T23:59:59",
                default_role=self.default_chk.isChecked(),
                status=status_new,
                token=token,
            )

        if not result.get("success"):
            self.msg.setText(result.get("message", "Failed to assign role."))
            self.msg.setVisible(True)
            return

        role_name_out = self._role_name_from_id(str(role_id))
        if not role_name_out and self.role_edit is not None:
            role_name_out = self.role_edit.text().strip()
        if not role_name_out:
            role_name_out = str(
                self.assignment.get("roleName")
                or self.assignment.get("role")
                or self.assignment.get("name")
                or ""
            ).strip()
        self._submitted_assignment = {
            "userRoleAssignmentId": self._assignment_id,
            "roleId": int(role_id) if str(role_id).isdigit() else role_id,
            "roleName": role_name_out or "",
            "validFrom": f"{vf_ymd}T00:00:00",
            "validTo": f"{vt_ymd}T23:59:59",
            "defaultRole": self.default_chk.isChecked(),
        }
        self._submitted_assignment["status"] = self.new_status.currentText().strip().upper()
        self.accept()


class UserRoleAssignmentListPage(QWidget):
    """User role assignments: users table, role assignments table, Create and assignment CRUD."""

    def __init__(
        self,
        on_create_clicked: Callable[[], None] | None = None,
        on_edit_clicked: Callable[[dict[str, Any], bool], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_create_clicked = on_create_clicked
        self.on_edit_clicked = on_edit_clicked
        self._filter_visible = False
        self._user_filter_timer = QTimer(self)
        self._user_filter_timer.setSingleShot(True)
        self._user_filter_timer.setInterval(200)
        self._user_filter_timer.timeout.connect(self._apply_user_column_filters_refresh)
        self._rows: list[dict[str, Any]] = []
        self._user_column_spec: list[tuple[str, tuple[str, ...]]] = []
        self._selected_user: dict[str, Any] | None = None
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
        header_layout.addWidget(QLabel("User Role Assignments"))
        header_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        header_layout.addWidget(refresh_btn)

        self._filter_btn = QPushButton("Filters")
        self._filter_btn.setCheckable(True)
        self._filter_btn.setChecked(False)
        self._filter_btn.setFixedWidth(100)
        self._filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_btn.setToolTip("Toggle per-column filters on the user list")
        self._filter_btn.toggled.connect(self._on_user_filter_toggle)
        header_layout.addWidget(self._filter_btn)

        create_btn = QPushButton("Create")
        create_btn.setFixedWidth(100)
        create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        create_btn.clicked.connect(
            lambda: self.on_create_clicked() if self.on_create_clicked else None
        )
        header_layout.addWidget(create_btn)
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

        self.message_label = QLabel("")
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
        self.table.customContextMenuRequested.connect(self._on_users_context_menu)
        self.table.itemSelectionChanged.connect(self._on_user_selection_changed)
        attach_table_copy_shortcut(self.table)

        right_panel = QWidget()
        right_panel.setMinimumWidth(420)
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        self.roles_table = QTableWidget()
        apply_data_table_appearance(self.roles_table)
        self.roles_table.setColumnCount(5)
        self.roles_table.setHorizontalHeaderLabels(
            ["Role", "Status", "Valid From", "Valid To", "Default Role"]
        )
        rh = self.roles_table.horizontalHeader()
        rh.setStretchLastSection(False)
        for col in range(5):
            rh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        rh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
        self.roles_table.setSortingEnabled(True)
        self.roles_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.roles_table.customContextMenuRequested.connect(self._on_roles_context_menu)
        self.roles_table.itemDoubleClicked.connect(self._on_role_row_double_clicked)
        attach_table_copy_shortcut(self.roles_table)
        right_layout.addWidget(self.roles_table, 1)

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

    def _user_data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _is_user_data_table_row(self, table_row: int) -> bool:
        return table_row >= self._user_data_row_offset()

    def _schedule_user_filter_apply(self) -> None:
        if self._filter_visible:
            self._user_filter_timer.start()

    def _filtered_user_source_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._rows,
            self.table,
            self._user_column_spec,
            self._filter_visible,
            _value_for_ura_user,
            _format_ura_user_cell,
        )

    def _write_user_data_rows(self, data_rows: list[dict[str, Any]]) -> None:
        off = self._user_data_row_offset()
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
                len(self._user_column_spec),
                on_text_changed=self._schedule_user_filter_apply,
            )
        for r, user in enumerate(data_rows):
            tr = off + r
            for col, (_, keys) in enumerate(self._user_column_spec):
                value, key_used = _value_for_ura_user(user, keys)
                item = QTableWidgetItem(_format_ura_user_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, user)
                self.table.setItem(tr, col, item)
        sync_vertical_header_labels(
            self.table,
            filter_visible=self._filter_visible,
            data_row_count=len(data_rows),
        )
        resize_data_table_columns_to_content(
            self.table,
            self._user_column_spec,
            self._rows,
            _value_for_ura_user,
            _format_ura_user_cell,
        )
        self.table.setSortingEnabled(not self._filter_visible)

    def _apply_user_column_filters_refresh(self) -> None:
        if not self._filter_visible or not self._user_column_spec or not self._rows:
            return
        try:
            filtered = self._filtered_user_source_rows()
            self._write_user_data_rows(filtered)
        except Exception:
            traceback.print_exc()

    def _on_user_filter_toggle(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            self._user_filter_timer.stop()
            clear_filter_row_widgets(self.table)
        if self._user_column_spec and self._rows:
            try:
                to_show = self._filtered_user_source_rows() if checked else list(self._rows)
                self._write_user_data_rows(to_show)
            except Exception:
                traceback.print_exc()
        elif not self._rows:
            self._user_column_spec = []
            self.table.setSortingEnabled(False)
            clear_filter_row_widgets(self.table)
            self.table.setRowCount(0)
            self.table.setColumnCount(0)

    def _clear_roles_table(self) -> None:
        self.roles_table.setSortingEnabled(False)
        self.roles_table.setRowCount(0)
        self.roles_table.setSortingEnabled(True)

    def _selected_users_table_row(self) -> int:
        """Visual row for the selected user (reliable with sorting; avoid selectedItems()[0] order)."""
        sm = self.table.selectionModel()
        if sm is not None:
            srows = sm.selectedRows(0)
            if srows:
                r = int(srows[0].row())
                return r if self._is_user_data_table_row(r) else -1
        r = self.table.currentRow()
        if r >= 0 and self._is_user_data_table_row(r):
            return int(r)
        return -1

    def _get_row_user(self, row_index: int) -> dict[str, Any] | None:
        if row_index < 0 or row_index >= self.table.rowCount():
            return None
        if not self._is_user_data_table_row(row_index):
            return None
        first_cell = self.table.item(row_index, 0)
        row = first_cell.data(Qt.ItemDataRole.UserRole) if first_cell else None
        return row if isinstance(row, dict) else None

    def _user_at_pos(self, pos: QPoint) -> dict[str, Any] | None:
        vp = self.table.viewport()

        def _from_viewport(vp_point: QPoint) -> dict[str, Any] | None:
            idx = self.table.indexAt(vp_point)
            if idx.isValid():
                return self._get_row_user(idx.row())
            item = self.table.itemAt(vp_point)
            if item:
                return self._get_row_user(item.row())
            return None

        user = _from_viewport(pos)
        if user is not None:
            return user
        return _from_viewport(vp.mapFrom(self.table, pos))


    def _on_user_selection_changed(self) -> None:
        row = self._selected_users_table_row()
        if row < 0:
            self._selected_user = None
            self._clear_roles_table()
            return
        user = self._get_row_user(row)
        if not isinstance(user, dict):
            return
        self._selected_user = user
        self._populate_roles_table(user)

    def _populate_roles_table(self, user: dict[str, Any]) -> None:
        role_val = user.get("role") or user.get("roles")
        raw_rows: list[dict[str, Any]] = []
        if isinstance(role_val, list):
            for r in role_val:
                if isinstance(r, dict):
                    raw_rows.append(r)
                elif r is not None:
                    raw_rows.append({"roleName": str(r)})
        elif isinstance(role_val, dict):
            raw_rows.append(role_val)
        elif isinstance(role_val, str) and role_val.strip():
            raw_rows.append({"roleName": role_val.strip()})

        payloads: list[dict[str, Any]] = []
        for r in raw_rows:
            if not isinstance(r, dict):
                r = {}
            row_src = _row_with_default_role_from_user(user, r)
            role_name = row_src.get("roleName") or row_src.get("name") or row_src.get("role") or ""
            st_raw = (
                row_src.get("status")
                or row_src.get("roleStatus")
                or row_src.get("userRoleStatus")
                or ""
            )
            st = _normalize_status_name(str(st_raw).strip().upper()) or ""
            vf_raw = str(row_src.get("validFrom") or row_src.get("valid_from") or "").strip()
            vt_raw = str(row_src.get("validTo") or row_src.get("valid_to") or "").strip()
            default_disp = _default_role_display_from_row(row_src)
            row_payload: dict[str, Any] = dict(row_src)
            row_payload["role"] = str(role_name).strip()
            row_payload["status"] = st
            row_payload["validFrom"] = vf_raw
            row_payload["validTo"] = vt_raw
            row_payload["defaultDisplay"] = default_disp
            payloads.append(row_payload)

        self.roles_table.setSortingEnabled(False)
        self.roles_table.setRowCount(len(payloads))
        for i, row_payload in enumerate(payloads):
            valid_from = format_datetime_display(row_payload.get("validFrom") or None)
            valid_to = format_datetime_display(row_payload.get("validTo") or None)
            vals = [
                row_payload.get("role") or "",
                row_payload.get("status") or "",
                str(valid_from),
                str(valid_to),
                row_payload.get("defaultDisplay") or "",
            ]
            for col, val in enumerate(vals):
                it = QTableWidgetItem(str(val))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                it.setData(Qt.ItemDataRole.UserRole, row_payload)
                self.roles_table.setItem(i, col, it)
        resize_data_table_columns_to_content(
            self.roles_table,
            list(_URA_ROLE_COLUMN_SPEC),
            payloads,
            _value_for_ura_role_payload,
            _format_ura_role_cell,
        )
        self.roles_table.setSortingEnabled(True)

    def _selected_role_row(self) -> dict[str, Any] | None:
        items = self.roles_table.selectedItems()
        if not items:
            return None
        item = self.roles_table.item(items[0].row(), 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _on_role_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if not self._selected_user:
            return
        role_item = self.roles_table.item(item.row(), 0)
        if role_item is None:
            return
        row_data = role_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(row_data, dict):
            return
        role_txt = (row_data.get("role") or "").strip()
        if not role_txt:
            return
        self._run_edit_assignment_dialog(row_data)

    def _run_edit_assignment_dialog(self, row_data: dict[str, Any]) -> None:
        if not self._selected_user:
            return
        selected_uid = (
            self._selected_user.get("userId")
            or self._selected_user.get("user_id")
            or self._selected_user.get("id")
        )
        dlg = _AssignRoleDialog(self, self._selected_user, assignment=row_data)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            if dlg.closed_without_changes():
                self._show_message(NO_CHANGES_MESSAGE, error=False)
                QTimer.singleShot(200, lambda: self._refresh_and_restore(selected_uid))
                return
            updated = dlg.submitted_assignment() or {}
            if isinstance(updated, dict):
                row_data.update(updated)
                self._populate_roles_table(self._selected_user)
            self._show_message("Role assignment updated successfully.", error=False)
            QTimer.singleShot(200, lambda: self._refresh_and_restore(selected_uid))
            QTimer.singleShot(700, lambda: self._refresh_and_restore(selected_uid))

    def _open_add_user_role_assignment_dialog(self) -> None:
        if not self._selected_user:
            self._show_message("Select a user first.", error=True)
            return
        selected_uid = (
            self._selected_user.get("userId")
            or self._selected_user.get("user_id")
            or self._selected_user.get("id")
        )
        dlg = _AssignRoleDialog(self, self._selected_user)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh()
            self._restore_user_selection(selected_uid)
            QTimer.singleShot(350, lambda: self._refresh_and_restore(selected_uid))

    def _on_users_context_menu(self, pos: QPoint) -> None:
        clicked_item = self.table.itemAt(pos)
        if clicked_item is not None and self._is_user_data_table_row(clicked_item.row()):
            self.table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self.table.selectRow(clicked_item.row())
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Add User Role Assignment")
        action = menu.exec(QCursor.pos())
        if action == add_action:
            self._open_add_user_role_assignment_dialog()

    def _on_roles_context_menu(self, pos: QPoint) -> None:
        clicked_item = self.roles_table.itemAt(pos)
        if clicked_item is not None:
            self.roles_table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self.roles_table.selectRow(clicked_item.row())
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Add User Role Assignment")
        edit_action = menu.addAction("Edit Selected Assignment")
        remove_action = menu.addAction("Remove Selected Assignment")

        has_selected_row = clicked_item is not None or bool(self.roles_table.selectedItems())
        edit_action.setEnabled(has_selected_row)
        remove_action.setEnabled(has_selected_row)

        action = menu.exec(QCursor.pos())
        if action == add_action:
            self._open_add_user_role_assignment_dialog()
        elif action == remove_action:
            self._remove_selected_assignment()
        elif action == edit_action:
            self._edit_selected_assignment()

    def _edit_selected_assignment(self) -> None:
        if not self._selected_user:
            self._show_message("Select a user first.", error=True)
            return
        row_data = self._selected_role_row()
        if not row_data:
            self._show_message("Select a role assignment to edit.", error=True)
            return

        self._run_edit_assignment_dialog(row_data)

    def _remove_selected_assignment(self) -> None:
        if not self._selected_user:
            self._show_message("Select a user first.", error=True)
            return
        row_data = self._selected_role_row()
        if not row_data:
            self._show_message("Select a role assignment to remove.", error=True)
            return
        assignment_id = (
            row_data.get("userRoleAssignmentId")
            or row_data.get("user_role_assignment_id")
            or row_data.get("assignmentId")
            or row_data.get("id")
        )
        if assignment_id is None:
            self._show_message("Cannot remove: assignment id is missing.", error=True)
            return

        selected_uid = (
            self._selected_user.get("userId")
            or self._selected_user.get("user_id")
            or self._selected_user.get("id")
        )
        role_name = row_data.get("roleName") or row_data.get("name") or str(assignment_id)
        reply = QMessageBox.question(
            self,
            "Remove Role Assignment",
            f"Are you sure you want to remove role assignment '{role_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_delete_user_role_assignment_by_id(assignment_id, token=token)
        if result.get("success"):
            self._show_message(
                result.get("message", "Role assignment removed successfully."),
                error=False,
            )
            # Refresh immediately and keep same user selected so right table reflects instantly.
            self.refresh()
            self._restore_user_selection(selected_uid)
            # One short delayed refresh handles eventual backend commit lag.
            QTimer.singleShot(350, lambda: self._refresh_and_restore(selected_uid))
        else:
            self._show_message(result.get("message", "Failed to remove role assignment."), error=True)

    def _refresh_and_restore(self, user_id: Any) -> None:
        self.refresh()
        self._restore_user_selection(user_id)

    def _restore_user_selection(self, user_id: Any) -> None:
        if user_id is None:
            return
        target = str(user_id)
        off = self._user_data_row_offset()
        for row in range(off, self.table.rowCount()):
            item = self.table.item(row, 0)
            data = item.data(Qt.ItemDataRole.UserRole) if item else None
            if not isinstance(data, dict):
                continue
            uid = data.get("userId") or data.get("user_id") or data.get("id")
            if uid is not None and str(uid) == target:
                self.table.setCurrentCell(row, 0)
                self.table.selectRow(row)
                self._on_user_selection_changed()
                return

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.refresh()

    def _roles_text(self, row: dict[str, Any]) -> str:
        roles = row.get("role") or row.get("roles")
        if isinstance(roles, list):
            return ", ".join(str(v) for v in roles if v is not None) or ""
        if isinstance(roles, str):
            return roles or ""
        return ""

    def _show_message(self, text: str, *, error: bool) -> None:
        """Same pattern as Reporting Manager: green success / red error."""
        show_auto_hiding_message(self, self.message_label, text, error=error)

    def refresh(self) -> None:
        sel_uid: Any = None
        if self._selected_user:
            sel_uid = (
                self._selected_user.get("userId")
                or self._selected_user.get("user_id")
                or self._selected_user.get("id")
            )
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_users(token=token)
        if not result.get("success"):
            self._show_message(result.get("message", "Failed to load users."), error=True)
            self._rows = []
            self._user_column_spec = []
            self.table.setSortingEnabled(False)
            clear_filter_row_widgets(self.table)
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self._selected_user = None
            self._clear_roles_table()
            return
        show_auto_hiding_message(self, self.message_label, "")
        self._rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
        self._populate_table(self._rows)
        if sel_uid is not None:
            self._restore_user_selection(sel_uid)

    def _populate_table(self, rows: list[dict[str, Any]]) -> None:
        self._rows = [dict(r) for r in rows if isinstance(r, dict)]
        if not self._rows:
            self._user_column_spec = []
            self.table.setSortingEnabled(False)
            clear_filter_row_widgets(self.table)
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            return
        try:
            self._user_column_spec = list(_URA_USER_COLUMN_SPEC)
            headers = [s[0] for s in self._user_column_spec]
            self.table.setSortingEnabled(False)
            self.table.setColumnCount(len(self._user_column_spec))
            self.table.setHorizontalHeaderLabels(headers)
            th = self.table.horizontalHeader()
            th.setStretchLastSection(False)
            for col in range(self.table.columnCount()):
                th.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            th.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
            filtered = self._filtered_user_source_rows() if self._filter_visible else list(self._rows)
            self._write_user_data_rows(filtered)
        except Exception:
            traceback.print_exc()
            self._rows = []
            self._user_column_spec = []
            self.table.setSortingEnabled(False)
            clear_filter_row_widgets(self.table)
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
