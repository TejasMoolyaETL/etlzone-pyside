"""Reporting manager — Users-style list; Create opens Assign manager dialog."""

from __future__ import annotations

import traceback
from typing import Any

from PySide6.QtCore import QObject, QPoint, Qt, QStringListModel, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCursor, QShowEvent
from PySide6.QtWidgets import (
    QApplication,
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
    QSizePolicy,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.user_management.users.user_create import INPUT_STYLE
from app.user_management.users.user_view import READONLY_INPUT_STYLE, _display_for_column
from app.user_management.user_timepass.user_role_ui_helpers import (
    _VIEW_USER_ID_KEYS,
    _VIEW_USERNAME_KEYS,
    _add_view_user_form_row,
)

from core.api import (
    api_get_all_users,
    api_user_hierarchy_get_all,
    api_user_hierarchy_assign,
    api_user_hierarchy_delete,
    api_user_hierarchy_update,
)
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
from ui.form_combobox_style import FORM_COMBOBOX_STYLE, apply_form_combobox_field
from ui.post_save_navigation import NO_CHANGES_MESSAGE
from ui.strict_completer import strict_list_selection_message
from ui.styles import CONTEXT_MENU_STYLESHEET

_HIERARCHY_LEVEL_VALUES = [str(i) for i in range(1, 31)]

_HIERARCHY_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Hierarchy Id", ("hierarchyId", "hierarchy_id", "id")),
    ("Level", ("level",)),
    ("Employee", ("__rm_emp_name__",)),
    ("Emp username", ("__rm_emp_user__",)),
    ("Manager", ("__rm_mgr_name__",)),
    ("Manager username", ("__rm_mgr_user__",)),
)


def _value_for_hierarchy_row(row: dict[str, Any], keys: tuple[str, ...]) -> tuple[Any, str]:
    k0 = keys[0]
    if k0 == "__rm_emp_name__":
        return (_user_name(_hierarchy_employee_payload(row)), k0)
    if k0 == "__rm_emp_user__":
        return (_username_from_user_dict(_hierarchy_employee_payload(row)), k0)
    if k0 == "__rm_mgr_name__":
        return (_user_name(_hierarchy_manager_payload(row)), k0)
    if k0 == "__rm_mgr_user__":
        return (_username_from_user_dict(_hierarchy_manager_payload(row)), k0)
    for kk in keys:
        v = row.get(kk)
        if v is not None:
            return (v, kk)
    return (None, keys[0] if keys else "")


def _format_hierarchy_cell(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if value is None:
        return ""
    return str(value)


def _level_combo_items_including(current: int) -> list[str]:
    """Same 1–30 as Create Position; include ``current`` if outside that range (existing API data)."""
    items = list(_HIERARCHY_LEVEL_VALUES)
    s = str(current)
    if s not in items:
        items.append(s)
        items.sort(key=int)
    return items


def _user_name(u: dict[str, Any]) -> str:
    fn = str(u.get("firstName") or u.get("first_name") or "").strip()
    ln = str(u.get("lastName") or u.get("last_name") or "").strip()
    return f"{fn} {ln}".strip()


def _hierarchy_employee_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Report / subordinate (assign API: userId) — prefer explicit API keys."""
    for k in (
        "user",
        "employee",
        "reportee",
        "subordinate",
        "childUser",
        "userDto",
        "employeeUser",
    ):
        v = row.get(k)
        if isinstance(v, dict):
            return v
    return {}


def _hierarchy_manager_payload(row: dict[str, Any]) -> dict[str, Any]:
    """Manager (assign API: managerId)."""
    for k in (
        "manager",
        "reportingManager",
        "parentUser",
        "managerDto",
        "parent",
    ):
        v = row.get(k)
        if isinstance(v, dict):
            return v
    return {}


def _username_from_user_dict(u: dict[str, Any]) -> str:
    return str(u.get("userName") or u.get("username") or u.get("user_name") or "").strip()


class _HierarchyLoadWorker(QObject):
    finished = Signal(list, int)

    def __init__(self, token: str) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        seen: dict[str, dict[str, Any]] = {}
        errors = 0
        res = api_user_hierarchy_get_all(token=self._token)
        if not res.get("success"):
            errors = 1
        else:
            for row in res.get("data") or []:
                if not isinstance(row, dict):
                    continue
                # Dedupe only by hierarchy id — avoid generic ``id`` (may collide with user/row ids).
                hid = row.get("hierarchyId")
                if hid is None:
                    hid = row.get("hierarchy_id")
                if hid is not None:
                    seen[str(hid)] = row
                else:
                    seen[f"_noid_{len(seen)}"] = row
        self.finished.emit(list(seen.values()), errors)


def _id_from_display_line(text: str) -> str:
    raw = (text or "").strip()
    if "|" in raw:
        raw = raw.split("|", 1)[0].strip()
    return raw


class _AssignManagerDialog(QDialog):
    """Assign reporting manager — same form chrome as Add User Role (Save / Cancel)."""

    def __init__(self, parent: QWidget, users: list[tuple[str, str]]) -> None:
        super().__init__(parent)
        self._users = users
        self.success_message = "Assigned."
        self.setWindowTitle("Assign Reporting Manager")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setStyleSheet("QDialog { background: #ffffff; }")

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
        form = _make_form()
        suggestions = [d for _, d in self._users]
        model = QStringListModel(suggestions)

        self.employee_input = QLineEdit()
        self.employee_input.setPlaceholderText(placeholder_search_select("User Id", "Username", "Name"))
        self.employee_input.setStyleSheet(INPUT_STYLE)
        self.employee_input.setFixedHeight(fh)
        self.employee_input.setMinimumWidth(360)
        self.employee_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ec = QCompleter(self.employee_input)
        ec.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        ec.setFilterMode(Qt.MatchFlag.MatchContains)
        ec.setMaxVisibleItems(12)
        ec.setModel(model)
        self.employee_input.setCompleter(ec)
        _add_view_user_form_row(form, "Employee (reports to manager)*", self.employee_input)

        self.manager_input = QLineEdit()
        self.manager_input.setPlaceholderText(placeholder_search_select("User Id", "Username", "Name"))
        self.manager_input.setStyleSheet(INPUT_STYLE)
        self.manager_input.setFixedHeight(fh)
        self.manager_input.setMinimumWidth(360)
        self.manager_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        mc = QCompleter(self.manager_input)
        mc.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        mc.setFilterMode(Qt.MatchFlag.MatchContains)
        mc.setMaxVisibleItems(12)
        mc.setModel(model)
        self.manager_input.setCompleter(mc)
        _add_view_user_form_row(form, "Manager*", self.manager_input)

        self.level_combo = QComboBox()
        self.level_combo.addItems(_HIERARCHY_LEVEL_VALUES)
        self.level_combo.setCurrentText("1")
        apply_form_combobox_field(self.level_combo, height_px=fh, min_width=360)
        _add_view_user_form_row(form, "Hierarchy Level*", self.level_combo)

        layout.addLayout(form)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #cbd5e1; border: none; max-height: 1px;")
        layout.addWidget(sep)

        save_btn = QPushButton("Save")
        save_btn.setFixedWidth(100)
        save_btn.setDefault(True)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        save_btn.clicked.connect(self._try_assign)

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

    def _clear_msg(self) -> None:
        self.msg.clear()
        self.msg.setVisible(False)

    def _show_err(self, text: str) -> None:
        self.msg.setText(text)
        self.msg.setVisible(bool(text))

    def _try_assign(self) -> None:
        self._clear_msg()
        allowed = {d for _, d in self._users}
        emp_text = self.employee_input.text().strip()
        mgr_text = self.manager_input.text().strip()
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        if not token:
            self._show_err("Session expired. Please log in again.")
            return
        if not emp_text or emp_text not in allowed:
            self._show_err(strict_list_selection_message("an employee"))
            return
        if not mgr_text or mgr_text not in allowed:
            self._show_err(strict_list_selection_message("a manager"))
            return
        emp = _id_from_display_line(emp_text)
        mgr = _id_from_display_line(mgr_text)
        if emp == mgr:
            self._show_err("Employee and manager must be different users.")
            return
        try:
            level_val = int(self.level_combo.currentText().strip())
        except ValueError:
            self._show_err("Select a valid hierarchy level.")
            return
        result = api_user_hierarchy_assign(emp, mgr, level_val, token=token)
        if not result.get("success"):
            self._show_err(result.get("message", "Assign failed."))
            return
        self.success_message = result.get("message", "Assigned.")
        self.accept()


class _UpdateHierarchyDialog(QDialog):
    """Edit hierarchy — Edit / Back / Save / Cancel like Edit User Role."""

    def __init__(self, parent: QWidget, rec: dict[str, Any], users: list[tuple[str, str]]) -> None:
        super().__init__(parent)
        self._rec = rec
        self._users = users
        self.success_message = "Hierarchy updated."
        self._hid = rec.get("hierarchyId") or rec.get("hierarchy_id") or rec.get("id")
        self._emp = _hierarchy_employee_payload(rec)
        self._mgr = _hierarchy_manager_payload(rec)
        self._user_id = (
            str(self._emp.get("userId") or self._emp.get("user_id") or self._emp.get("id") or "").strip()
            or None
        )
        self._current_mgr_id = (
            str(self._mgr.get("userId") or self._mgr.get("user_id") or self._mgr.get("id") or "").strip()
            or None
        )
        try:
            self._current_level = int(rec.get("level") if rec.get("level") is not None else 1)
        except (TypeError, ValueError):
            self._current_level = 1

        self.setWindowTitle("Reporting Hierarchy Detail")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setStyleSheet("QDialog { background: #ffffff; }")

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

        hid_edit = QLineEdit(str(self._hid) if self._hid is not None else "")
        hid_edit.setReadOnly(True)
        hid_edit.setFixedHeight(fh)
        hid_edit.setMinimumWidth(240)
        hid_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        hid_edit.setStyleSheet(READONLY_INPUT_STYLE)
        _add_view_user_form_row(top_form, "Hierarchy Id", hid_edit)

        uid_edit = QLineEdit(_display_for_column(self._emp, _VIEW_USER_ID_KEYS))
        uid_edit.setReadOnly(True)
        uid_edit.setFixedHeight(fh)
        uid_edit.setMinimumWidth(240)
        uid_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        uid_edit.setStyleSheet(READONLY_INPUT_STYLE)
        _add_view_user_form_row(top_form, "User Id", uid_edit)

        uname_edit = QLineEdit(_display_for_column(self._emp, _VIEW_USERNAME_KEYS))
        uname_edit.setReadOnly(True)
        uname_edit.setFixedHeight(fh)
        uname_edit.setMinimumWidth(240)
        uname_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        uname_edit.setStyleSheet(READONLY_INPUT_STYLE)
        _add_view_user_form_row(top_form, "Username", uname_edit)

        full_name = f"{self._emp.get('firstName') or ''} {self._emp.get('lastName') or ''}".strip()
        name_edit = QLineEdit(full_name)
        name_edit.setReadOnly(True)
        name_edit.setFixedHeight(fh)
        name_edit.setMinimumWidth(240)
        name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        name_edit.setStyleSheet(READONLY_INPUT_STYLE)
        _add_view_user_form_row(top_form, "Name", name_edit)

        cur_mgr_disp = self._display_for_user_id(self._current_mgr_id)
        cur_mgr_edit = QLineEdit(cur_mgr_disp or "")
        cur_mgr_edit.setReadOnly(True)
        cur_mgr_edit.setFixedHeight(fh)
        cur_mgr_edit.setMinimumWidth(240)
        cur_mgr_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cur_mgr_edit.setStyleSheet(READONLY_INPUT_STYLE)
        _add_view_user_form_row(top_form, "Current manager", cur_mgr_edit)

        cur_lvl_edit = QLineEdit(str(self._current_level))
        cur_lvl_edit.setReadOnly(True)
        cur_lvl_edit.setFixedHeight(fh)
        cur_lvl_edit.setMinimumWidth(240)
        cur_lvl_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cur_lvl_edit.setStyleSheet(READONLY_INPUT_STYLE)
        _add_view_user_form_row(top_form, "Current hierarchy level", cur_lvl_edit)

        layout.addLayout(top_form)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #cbd5e1; border: none; max-height: 1px;")
        layout.addWidget(sep)

        bottom_form = _make_form()
        self.manager_edit = QLineEdit()
        self.manager_edit.setStyleSheet(INPUT_STYLE)
        self.manager_edit.setPlaceholderText(placeholder_search_select("User Id", "Username", "Name"))
        self.manager_edit.setText(self._display_for_user_id(self._current_mgr_id))
        self.manager_edit.setFixedHeight(fh)
        self.manager_edit.setMinimumWidth(240)
        self.manager_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        mgr_completer = QCompleter(self.manager_edit)
        mgr_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        mgr_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        mgr_completer.setMaxVisibleItems(12)
        mgr_completer.setModel(QStringListModel([d for _, d in self._users]))
        self.manager_edit.setCompleter(mgr_completer)
        _add_view_user_form_row(bottom_form, "New manager*", self.manager_edit)

        self.level_combo = QComboBox()
        self.level_combo.addItems(_level_combo_items_including(self._current_level))
        self.level_combo.setCurrentText(str(self._current_level))
        apply_form_combobox_field(self.level_combo, height_px=fh, min_width=240)
        _add_view_user_form_row(bottom_form, "New hierarchy level*", self.level_combo)

        layout.addLayout(bottom_form)

        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
        back_btn.clicked.connect(self.reject)

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedWidth(100)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
        edit_btn.clicked.connect(self._enter_edit_mode)

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

        btn_wrap = QWidget()
        bwl = QHBoxLayout(btn_wrap)
        bwl.setContentsMargins(0, 0, 0, 0)
        bwl.setSpacing(12)
        bwl.addWidget(self._btn_stack)
        bwl.addStretch(1)
        layout.addWidget(btn_wrap)

        self._editing = False
        self._snap_mgr = ""
        self._snap_level = ""
        self._enter_view_mode()

    def _display_for_user_id(self, uid: str | None) -> str:
        if not uid:
            return ""
        uid_s = str(uid)
        for saved_uid, display in self._users:
            if saved_uid == uid_s:
                return display
        return uid_s

    def _exists_user(self, uid: str) -> bool:
        return any(i == uid for i, _ in self._users)

    def _enter_view_mode(self) -> None:
        self._editing = False
        self.msg.clear()
        self.msg.setVisible(False)
        self.manager_edit.setEnabled(False)
        self.manager_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self.level_combo.setEnabled(False)
        self._btn_stack.setCurrentIndex(0)

    def _enter_edit_mode(self) -> None:
        self.msg.clear()
        self.msg.setVisible(False)
        self._editing = True
        self.manager_edit.setEnabled(True)
        self.manager_edit.setStyleSheet(INPUT_STYLE)
        self.level_combo.setEnabled(True)
        self._snap_mgr = self.manager_edit.text()
        self._snap_level = self.level_combo.currentText()
        self._btn_stack.setCurrentIndex(1)

    def _has_unsaved_changes(self) -> bool:
        if not self._editing:
            return False
        return (
            self.manager_edit.text() != self._snap_mgr
            or self.level_combo.currentText() != self._snap_level
        )

    def _handle_cancel(self) -> None:
        if not self._has_unsaved_changes():
            self.manager_edit.setText(self._display_for_user_id(self._current_mgr_id))
            self.level_combo.setCurrentText(str(self._current_level))
            self._enter_view_mode()
            return
        reply = QMessageBox.question(
            self,
            "Unsaved Changes",
            "You have unsaved changes. Discard and leave edit mode?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Discard:
            self.manager_edit.setText(self._display_for_user_id(self._current_mgr_id))
            self.level_combo.setCurrentText(str(self._current_level))
            self._enter_view_mode()

    def _handle_save(self) -> None:
        self.msg.clear()
        self.msg.setVisible(False)
        if self._hid is None or self._user_id is None:
            self.msg.setText("Missing hierarchy or user id.")
            self.msg.setVisible(True)
            return
        if not self._has_unsaved_changes():
            self.success_message = NO_CHANGES_MESSAGE
            self.accept()
            return
        mgr_text = self.manager_edit.text().strip()
        allowed = {d for _, d in self._users}
        if not mgr_text or mgr_text not in allowed:
            self.msg.setText(strict_list_selection_message("a manager"))
            self.msg.setVisible(True)
            return
        manager_id = _id_from_display_line(mgr_text)
        if manager_id == self._user_id:
            self.msg.setText("Employee and manager must be different users.")
            self.msg.setVisible(True)
            return
        try:
            level_val = int(self.level_combo.currentText().strip())
        except ValueError:
            self.msg.setText("Select a valid hierarchy level.")
            self.msg.setVisible(True)
            return
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
        result = api_user_hierarchy_update(
            self._hid, self._user_id, manager_id, level_val, token=token
        )
        if not result.get("success"):
            self.msg.setText(result.get("message", "Update failed."))
            self.msg.setVisible(True)
            return
        self.success_message = result.get("message", "Hierarchy updated.")
        self.accept()


class ReportingManagerPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self._users: list[tuple[str, str]] = []
        self._hierarchy_thread: QThread | None = None
        self._hierarchy_worker: _HierarchyLoadWorker | None = None
        self._hierarchy_loading = False
        self._pending_reload = False
        self._hierarchy_source_rows: list[dict[str, Any]] = []
        self._hierarchy_column_spec: list[tuple[str, tuple[str, ...]]] = []
        self._filter_visible = False
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.setInterval(200)
        self._filter_apply_timer.timeout.connect(self._apply_hierarchy_column_filters_refresh)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("Reporting Manager"))
        hl.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self._refresh_all)
        hl.addWidget(refresh_btn)

        self._filter_btn = QPushButton("Filters")
        self._filter_btn.setCheckable(True)
        self._filter_btn.setChecked(False)
        self._filter_btn.setFixedWidth(100)
        self._filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_btn.setToolTip("Toggle per-column filters on the hierarchy list")
        self._filter_btn.toggled.connect(self._on_hierarchy_filter_toggle)
        hl.addWidget(self._filter_btn)

        self._create_btn = QPushButton("Create")
        self._create_btn.setFixedWidth(100)
        self._create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_btn.clicked.connect(self._show_assign_dialog)
        hl.addWidget(self._create_btn)
        layout.addWidget(header)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)

        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._message_label.setVisible(False)
        content_layout.addWidget(self._message_label)

        self.hierarchy_table = QTableWidget()
        self._style_table(self.hierarchy_table)
        hh = self.hierarchy_table.horizontalHeader()
        hh.setStretchLastSection(False)
        self.hierarchy_table.setSortingEnabled(True)
        self.hierarchy_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.hierarchy_table.customContextMenuRequested.connect(self._on_hierarchy_menu)
        self.hierarchy_table.itemDoubleClicked.connect(self._on_hierarchy_row_double_clicked)
        content_layout.addWidget(self.hierarchy_table, 1)

        layout.addWidget(content, 1)

    def _style_table(self, t: QTableWidget) -> None:
        apply_data_table_appearance(
            t,
            horizontal_uniform_stretch=False,
            hide_vertical_header=False,
        )
        attach_table_copy_shortcut(t)

    def _hierarchy_data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _is_hierarchy_data_row(self, table_row: int) -> bool:
        return table_row >= self._hierarchy_data_row_offset()

    def _schedule_hierarchy_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_hierarchy_source_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._hierarchy_source_rows,
            self.hierarchy_table,
            self._hierarchy_column_spec,
            self._filter_visible,
            _value_for_hierarchy_row,
            _format_hierarchy_cell,
        )

    def _write_hierarchy_data_rows(self, data_rows: list[dict[str, Any]]) -> None:
        off = self._hierarchy_data_row_offset()
        self.hierarchy_table.setSortingEnabled(False)
        total = off + len(data_rows)
        if self._filter_visible and total < 1:
            total = 1
        self.hierarchy_table.setRowCount(total)
        if self._filter_visible:
            for c in range(self.hierarchy_table.columnCount()):
                self.hierarchy_table.takeItem(0, c)
            install_filter_row(
                self.hierarchy_table,
                len(self._hierarchy_column_spec),
                on_text_changed=self._schedule_hierarchy_filter_apply,
            )
        for r, row in enumerate(data_rows):
            tr = off + r
            for col, (_, keys) in enumerate(self._hierarchy_column_spec):
                value, key_used = _value_for_hierarchy_row(row, keys)
                it = QTableWidgetItem(_format_hierarchy_cell(value, key_used, keys))
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEditable)
                it.setData(Qt.ItemDataRole.UserRole, row)
                self.hierarchy_table.setItem(tr, col, it)
        sync_vertical_header_labels(
            self.hierarchy_table,
            filter_visible=self._filter_visible,
            data_row_count=len(data_rows),
        )
        resize_data_table_columns_to_content(
            self.hierarchy_table,
            self._hierarchy_column_spec,
            self._hierarchy_source_rows,
            _value_for_hierarchy_row,
            _format_hierarchy_cell,
        )
        self.hierarchy_table.setSortingEnabled(not self._filter_visible)

    def _apply_hierarchy_column_filters_refresh(self) -> None:
        if not self._filter_visible or not self._hierarchy_column_spec or not self._hierarchy_source_rows:
            return
        try:
            filtered = self._filtered_hierarchy_source_rows()
            self._write_hierarchy_data_rows(filtered)
        except Exception:
            traceback.print_exc()

    def _on_hierarchy_filter_toggle(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            self._filter_apply_timer.stop()
            clear_filter_row_widgets(self.hierarchy_table)
        if self._hierarchy_column_spec and self._hierarchy_source_rows:
            try:
                to_show = self._filtered_hierarchy_source_rows() if checked else list(self._hierarchy_source_rows)
                self._write_hierarchy_data_rows(to_show)
            except Exception:
                traceback.print_exc()
        elif not self._hierarchy_source_rows:
            self._show_empty_hierarchy_table()

    def _show_empty_hierarchy_table(self) -> None:
        self._hierarchy_source_rows = []
        self._hierarchy_column_spec = []
        self.hierarchy_table.setSortingEnabled(False)
        clear_filter_row_widgets(self.hierarchy_table)
        self.hierarchy_table.setRowCount(0)
        self.hierarchy_table.setColumnCount(0)

    def _refresh_all(self) -> None:
        self._load_user_directory_and_hierarchy()

    def _show_assign_dialog(self) -> None:
        if not self._users:
            self._show_message(
                "User directory is empty. Wait for the list to load or click Refresh.",
                error=True,
            )
            return
        dlg = _AssignManagerDialog(self, list(self._users))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._show_message(dlg.success_message, error=False)
            QTimer.singleShot(200, self._refresh_hierarchy_after_mutation)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._load_user_directory_and_hierarchy()

    def _token(self) -> str | None:
        profile = get_user_profile()
        tok = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(tok) if tok else None

    def _load_user_directory_and_hierarchy(self) -> None:
        """Load user list for completers, then fetch every hierarchy edge (managers per user)."""
        token = self._token()
        if not token:
            self._show_message("Session expired. Please log in again.", error=True)
            self._show_empty_hierarchy_table()
            return

        result = api_get_all_users(token=token)
        rows = result.get("data") or []
        self._users = []
        for u in rows:
            if not isinstance(u, dict):
                continue
            uid = u.get("userId") or u.get("user_id") or u.get("id")
            if uid is None:
                continue
            uid_s = str(uid)
            uname = str(u.get("userName") or u.get("username") or "").strip()
            parts = [uid_s]
            if uname:
                parts.append(uname)
            un = _user_name(u)
            if un:
                parts.append(un)
            disp = " | ".join(parts)
            self._users.append((uid_s, disp))

        self._load_all_hierarchy(token)

    def _load_all_hierarchy(self, token: str) -> None:
        """Merge GET user-hierarchy/managers/{id} for every user; each edge appears once (by hierarchy id)."""
        if self._hierarchy_loading:
            self._pending_reload = True
            return
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self._message_label.setText("Loading hierarchy…")
        self._message_label.setVisible(True)
        self._create_btn.setEnabled(False)
        QApplication.processEvents()
        self._hierarchy_loading = True

        self._hierarchy_thread = QThread(self)
        self._hierarchy_worker = _HierarchyLoadWorker(token)
        self._hierarchy_worker.moveToThread(self._hierarchy_thread)
        self._hierarchy_thread.started.connect(self._hierarchy_worker.run)
        self._hierarchy_worker.finished.connect(self._on_hierarchy_loaded)
        self._hierarchy_worker.finished.connect(self._hierarchy_thread.quit)
        self._hierarchy_thread.finished.connect(self._cleanup_hierarchy_loader)
        self._hierarchy_thread.start()

    def _on_hierarchy_loaded(self, records: list[dict[str, Any]], errors: int) -> None:
        self._create_btn.setEnabled(True)
        self._fill_hierarchy_table_from_records(records)
        n = len(records)
        if n == 0 and errors:
            self._show_message("Could not load hierarchy (request failed).", error=True)
        elif n == 0:
            self._show_message("No hierarchy assignments found.", error=False)
        else:
            show_auto_hiding_message(self, self._message_label, "")
        self._hierarchy_loading = False
        if self._pending_reload:
            self._pending_reload = False
            tok = self._token()
            if tok:
                self._load_all_hierarchy(tok)

    def _cleanup_hierarchy_loader(self) -> None:
        if self._hierarchy_worker is not None:
            self._hierarchy_worker.deleteLater()
            self._hierarchy_worker = None
        if self._hierarchy_thread is not None:
            self._hierarchy_thread.deleteLater()
            self._hierarchy_thread = None

    def _refresh_hierarchy_after_mutation(self) -> None:
        tok = self._token()
        if tok:
            self._load_all_hierarchy(tok)

    def _fill_hierarchy_table_from_records(self, records: list[dict[str, Any]]) -> None:
        records = sorted(
            records,
            key=lambda r: str(r.get("hierarchyId") or r.get("hierarchy_id") or r.get("id") or ""),
        )
        if not records:
            self._show_empty_hierarchy_table()
            return
        try:
            self._hierarchy_source_rows = [dict(r) for r in records if isinstance(r, dict)]
            self._hierarchy_column_spec = list(_HIERARCHY_COLUMN_SPEC)
            self.hierarchy_table.setSortingEnabled(False)
            headers = [s[0] for s in self._hierarchy_column_spec]
            self.hierarchy_table.setColumnCount(len(self._hierarchy_column_spec))
            self.hierarchy_table.setHorizontalHeaderLabels(headers)
            hh = self.hierarchy_table.horizontalHeader()
            hh.setStretchLastSection(False)
            for col in range(self.hierarchy_table.columnCount()):
                hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
            filtered = (
                self._filtered_hierarchy_source_rows()
                if self._filter_visible
                else list(self._hierarchy_source_rows)
            )
            self._write_hierarchy_data_rows(filtered)
        except Exception:
            traceback.print_exc()
            self._show_empty_hierarchy_table()

    def _id_from_display(self, text: str) -> str:
        return _id_from_display_line(text)

    def _show_message(self, text: str, *, error: bool) -> None:
        show_auto_hiding_message(self, self._message_label, text, error=error)

    def _has_hierarchy_data_selection(self) -> bool:
        for it in self.hierarchy_table.selectedItems():
            if self._is_hierarchy_data_row(it.row()):
                return True
        return False

    def _on_hierarchy_menu(self, pos: QPoint) -> None:
        clicked_item = self.hierarchy_table.itemAt(pos)
        if clicked_item is not None and self._is_hierarchy_data_row(clicked_item.row()):
            self.hierarchy_table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self.hierarchy_table.selectRow(clicked_item.row())
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Assign Reporting Manager")
        edit_action = menu.addAction("Edit Selected Assignment")
        remove_action = menu.addAction("Remove Selected Assignment")
        has_selected_row = self._has_hierarchy_data_selection() or (
            clicked_item is not None and self._is_hierarchy_data_row(clicked_item.row())
        )
        edit_action.setEnabled(has_selected_row)
        remove_action.setEnabled(has_selected_row)
        action = menu.exec(QCursor.pos())
        if action == add_action:
            self._show_assign_dialog()
        elif action == remove_action:
            self._remove_selected_hierarchy()
        elif action == edit_action:
            self._edit_selected_hierarchy()

    def _selected_hierarchy_row(self) -> dict[str, Any] | None:
        items = self.hierarchy_table.selectedItems()
        if not items:
            return None
        r = items[0].row()
        if not self._is_hierarchy_data_row(r):
            return None
        item = self.hierarchy_table.item(r, 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _on_hierarchy_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if not self._is_hierarchy_data_row(item.row()):
            return
        row_item = self.hierarchy_table.item(item.row(), 0)
        if row_item is None:
            return
        rec = row_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(rec, dict):
            return
        hid = rec.get("hierarchyId") or rec.get("hierarchy_id") or rec.get("id")
        if hid is None:
            return
        self._run_edit_hierarchy_dialog(rec)

    def _run_edit_hierarchy_dialog(self, rec: dict[str, Any]) -> None:
        if not self._users:
            self._show_message(
                "User directory is empty. Wait for the list to load or click Refresh.",
                error=True,
            )
            return
        dlg = _UpdateHierarchyDialog(self, rec, list(self._users))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._show_message(dlg.success_message, error=False)
            QTimer.singleShot(200, self._refresh_hierarchy_after_mutation)

    def _edit_selected_hierarchy(self) -> None:
        rec = self._selected_hierarchy_row()
        if not rec:
            self._show_message("Select a reporting assignment to edit.", error=True)
            return
        hid = rec.get("hierarchyId") or rec.get("hierarchy_id") or rec.get("id")
        if hid is None:
            self._show_message("Cannot edit: missing hierarchy id.", error=True)
            return
        self._run_edit_hierarchy_dialog(rec)

    def _remove_selected_hierarchy(self) -> None:
        rec = self._selected_hierarchy_row()
        if not rec:
            self._show_message("Select a reporting assignment to remove.", error=True)
            return
        self._confirm_delete(rec)

    def _display_for_user_id(self, uid: str | None) -> str:
        if not uid:
            return ""
        uid_s = str(uid)
        for saved_uid, display in self._users:
            if saved_uid == uid_s:
                return display
        return uid_s

    def _confirm_delete(self, rec: dict[str, Any]) -> None:
        hid = rec.get("hierarchyId") or rec.get("hierarchy_id") or rec.get("id")
        if hid is None:
            return
        reply = QMessageBox.question(
            self,
            "Remove reporting line",
            "Remove this hierarchy assignment?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        token = self._token()
        result = api_user_hierarchy_delete(hid, token=token)
        if result.get("success"):
            self._show_message(result.get("message", "Removed."), error=False)
            QTimer.singleShot(200, self._refresh_hierarchy_after_mutation)
        else:
            self._show_message(result.get("message", "Delete failed."), error=True)

    def is_dirty(self) -> bool:
        return False
