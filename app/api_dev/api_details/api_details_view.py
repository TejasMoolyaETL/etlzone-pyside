"""View API Detail — layout aligned with View User Involved (Role)."""

from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.api_dev.api_details.api_method_combo import configure_api_method_combo
from core.api import (
    api_get_all_projects,
    api_get_master_key_by_app_id_field_name,
    api_update_api_detail_by_id,
    master_key_row_display_label,
    master_key_row_seq_value,
)
from core.nav_access import (
    LEFT_PANEL_NAV_ITEM_APP_ID_KEYS,
    collect_allowed_action_names,
    nav_action_visible,
)
from core.app_preferences import format_datetime_display, is_datetime_field
from ui.blank_display import is_blank_display_value
from core.user_context import get_nav_access_steps, get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
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
    FORM_SECONDARY_BUTTON_STYLESHEET,
)
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success
from ui.widgets.required_label import field_caption_label, labeled_field_block

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})
_API_STATUS_KEYS = (
    "apiStatus",
    "api_status",
    "apistatus",
    "apiStatusResponse.keyValue",
    "keyValue",
    "key_value",
    "seqId",
    "seq_id",
    "apiStatusResponse.seq",
)


def _get_value(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    flat = {k: v for k, v in record.items() if k not in _HIDDEN_KEYS}
    for key in keys:
        if "." in key:
            cur: Any = flat
            ok = True
            for part in key.split("."):
                if isinstance(cur, dict) and part in cur:
                    cur = cur[part]
                else:
                    ok = False
                    break
            if ok:
                return cur
        if key in flat:
            return flat[key]
    return None


def _format_value(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if key_candidates == _API_STATUS_KEYS:
        if isinstance(value, dict):
            kv = str(value.get("keyValue") or value.get("key_value") or "").strip()
            return kv
        return str(value)
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


_MULTILINE_DETAIL_HEIGHT = 120
_API_DETAILS_NAV_LABEL = "API: Details"
_API_STATUS_FIELD_NAME = "api_status"

_DETAIL_COL1 = (
    ("API ID (Internal)", ("apiId", "api_id", "id")),
    ("Project Id", ("projectId", "projectid", "project_id")),
    ("Project Name", ("projectName", "project_name", "name")),
    ("Folder", ("folder", "Folder")),
    ("API Method*", ("apiMethod", "api_method", "method")),
    ("API name*", ("apiName", "api_name", "name")),
    ("localhost path", ("localhostPath", "localhost_path", "localhostpath")),
    ("Server path", ("serverPath", "server_path", "serverpath")),
)
_DETAIL_COL2 = (
    ("Requirement", ("requirement", "Requirement")),
    ("API Status", _API_STATUS_KEYS),
    ("Comments", ("comments", "Comments")),
    ("Request", ("request", "Request")),
)
_DETAIL_COL3 = (
    ("Response", ("response", "Response")),
    ("Created By", ("createdBy", "created_by", "CreatedBy")),
    ("Created At", ("createdAt", "created_at", "CreatedAt")),
    ("Modified By", ("modifiedBy", "modified_by", "ModifiedBy")),
    ("Modified At", ("modifiedAt", "modified_at", "ModifiedAt", "updatedAt", "updated_at")),
)
_DETAIL_FIELD_GROUPS = _DETAIL_COL1 + _DETAIL_COL2 + _DETAIL_COL3

_READONLY_KEYS = frozenset({
    "apiId", "api_id", "id",
    "projectId", "projectid", "project_id",
    "projectName", "project_name", "name",
    "createdBy", "created_by", "CreatedBy",
    "createdAt", "created_at", "CreatedAt",
    "modifiedBy", "modified_by", "ModifiedBy",
    "modifiedAt", "modified_at", "ModifiedAt", "updatedAt", "updated_at",
})

_EDITABLE_KEYS = frozenset(
    {
        "folder",
        "apiMethod",
        "api_method",
        "apiName",
        "api_name",
        "localhostPath",
        "localhost_path",
        "serverPath",
        "server_path",
        "requirement",
        "apiStatus",
        "api_status",
        "comments",
        "request",
        "response",
    }
)


class ViewAPIDetailPage(QWidget):
    """Display and edit an API detail row — same pattern as ViewUserTypePage."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._record: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit | QPlainTextEdit | QComboBox] = {}
        self._editable_keys: list[str] = []
        self._can_edit_action = True
        self._edit_baseline: dict[str, str] = {}
        self._localhost_path_icon: QToolButton | None = None
        self._server_path_icon: QToolButton | None = None
        self._build_ui()
        self._load_api_status_options()

    def set_record(self, record: dict[str, Any], edit_mode: bool = False) -> None:
        self._record = dict(record)
        self._refresh_edit_action_access()
        self._refresh_values()
        if edit_mode and self._record and self._can_edit_action:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _refresh_edit_action_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_edit_action = True
        else:
            allowed_actions = collect_allowed_action_names(steps)
            self._can_edit_action = nav_action_visible("API: Details", "edit", allowed_actions)
        self._edit_btn.setEnabled(self._can_edit_action)
        self._edit_btn.setToolTip("" if self._can_edit_action else "Require Permission.")

    def _refresh_values(self) -> None:
        for _label_text, keys in _DETAIL_FIELD_GROUPS:
            canonical = keys[0]
            value = _get_value(self._record, keys)
            text = _format_value(value, keys[0], keys)
            widget = self._field_edits.get(canonical)
            if widget:
                if isinstance(widget, QComboBox):
                    if canonical == "apiMethod":
                        raw = _get_value(self._record, keys)
                        configure_api_method_combo(
                            widget,
                            current=str(raw).strip() if raw is not None and str(raw).strip() else None,
                            default_index=0,
                        )
                    else:
                        self._select_api_status_from_record(value, text)
                elif isinstance(widget, QPlainTextEdit):
                    widget.setPlainText(text)
                else:
                    widget.setText(text)

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
        title = QLabel("API Detail")
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
        card.setMinimumWidth(720)
        card.setMaximumWidth(1320)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        # Three independent vertical stacks (no QGridLayout) so columns are not row-aligned.
        _col_spacing = 10
        cols_row = QHBoxLayout()
        cols_row.setSpacing(24)
        cols_row.setContentsMargins(0, 0, 0, 0)

        col1_lay = QVBoxLayout()
        col1_lay.setSpacing(_col_spacing)
        col1_lay.setContentsMargins(0, 0, 0, 0)
        col2_lay = QVBoxLayout()
        col2_lay.setSpacing(_col_spacing)
        col2_lay.setContentsMargins(0, 0, 0, 0)
        col3_lay = QVBoxLayout()
        col3_lay.setSpacing(_col_spacing)
        col3_lay.setContentsMargins(0, 0, 0, 0)

        col1_w = QWidget()
        col1_w.setLayout(col1_lay)
        col1_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        col2_w = QWidget()
        col2_w.setLayout(col2_lay)
        col2_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        col3_w = QWidget()
        col3_w.setLayout(col3_lay)
        col3_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        cols_row.addWidget(col1_w, 1)
        cols_row.addWidget(col2_w, 1)
        cols_row.addWidget(col3_w, 1)

        def add_field(stack: QVBoxLayout, label_text: str, key_variants: tuple[str, ...]) -> None:
            chosen = key_variants[0]
            if chosen in _EDITABLE_KEYS and chosen not in self._editable_keys:
                self._editable_keys.append(chosen)

            label_widget = field_caption_label(label_text, LABEL_STYLE)

            is_read_only = chosen in _READONLY_KEYS

            if chosen in ("apiMethod", "api_method", "method"):
                value_widget = QComboBox()
                configure_api_method_combo(value_widget, current=None, default_index=0)
                apply_form_combobox_field(
                    value_widget, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX, min_width=240
                )
                value_widget.setEnabled(False)
                self._field_edits["apiMethod"] = value_widget
            elif chosen in ("apiStatus", "api_status", "apistatus"):
                value_widget = QComboBox()
                value_widget.addItems(["ACTIVE", "INACTIVE"])
                apply_form_combobox_field(
                    value_widget, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX, min_width=240
                )
                value_widget.setEnabled(chosen in _EDITABLE_KEYS)
                self._field_edits["apiStatus"] = value_widget
            elif chosen in ("comments", "Comments"):
                value_widget = QPlainTextEdit()
                value_widget.setFixedHeight(_MULTILINE_DETAIL_HEIGHT)
                value_widget.setReadOnly(is_read_only)
                value_widget.setStyleSheet(READONLY_INPUT_STYLE if is_read_only else INPUT_STYLE)
                self._field_edits["comments"] = value_widget
            elif chosen in ("request", "Request"):
                value_widget = QPlainTextEdit()
                value_widget.setFixedHeight(_MULTILINE_DETAIL_HEIGHT)
                value_widget.setReadOnly(is_read_only)
                value_widget.setStyleSheet(READONLY_INPUT_STYLE if is_read_only else INPUT_STYLE)
                self._field_edits["request"] = value_widget
            elif chosen in ("response", "Response"):
                value_widget = QPlainTextEdit()
                value_widget.setFixedHeight(_MULTILINE_DETAIL_HEIGHT)
                value_widget.setReadOnly(is_read_only)
                value_widget.setStyleSheet(READONLY_INPUT_STYLE if is_read_only else INPUT_STYLE)
                self._field_edits["response"] = value_widget
            else:
                value_widget = QLineEdit()
                value_widget.setReadOnly(is_read_only)
                value_widget.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
                value_widget.setMinimumWidth(240)
                value_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                value_widget.setStyleSheet(
                    READONLY_INPUT_STYLE if is_read_only else INPUT_STYLE
                )
                self._field_edits[chosen] = value_widget

            if chosen in ("localhostPath", "localhost_path", "serverPath", "server_path"):
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
                label_row_w = QWidget()
                lr = QHBoxLayout(label_row_w)
                lr.setContentsMargins(0, 0, 0, 0)
                lr.setSpacing(6)
                lr.addWidget(label_widget)
                lr.addWidget(icon_btn)
                lr.addStretch()
                if chosen in ("localhostPath", "localhost_path"):
                    icon_btn.clicked.connect(self._on_localhost_path_icon_clicked)
                    self._localhost_path_icon = icon_btn
                else:
                    icon_btn.clicked.connect(self._on_server_path_icon_clicked)
                    self._server_path_icon = icon_btn
                stack.addWidget(labeled_field_block(label_row_w, value_widget))
            else:
                stack.addWidget(labeled_field_block(label_widget, value_widget))

        for lt, keys in _DETAIL_COL1:
            add_field(col1_lay, lt, keys)
        for lt, keys in _DETAIL_COL2:
            add_field(col2_lay, lt, keys)
        for lt, keys in _DETAIL_COL3:
            add_field(col3_lay, lt, keys)

        col1_lay.addStretch()
        col2_lay.addStretch()
        col3_lay.addStretch()

        self._back_btn = QPushButton("Back")
        self._back_btn.setFixedWidth(100)
        self._back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._back_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        self._back_btn.clicked.connect(self._handle_back)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedWidth(100)
        self._edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
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
        display_btns.setStyleSheet("background: transparent;")
        dbl = QHBoxLayout(display_btns)
        dbl.setContentsMargins(0, 0, 0, 0)
        dbl.setSpacing(12)
        dbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        dbl.addWidget(self._edit_btn)
        dbl.addWidget(self._back_btn)

        edit_btns = QWidget()
        edit_btns.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        edit_btns.setStyleSheet("background: transparent;")
        ebl = QHBoxLayout(edit_btns)
        ebl.setContentsMargins(0, 0, 0, 0)
        ebl.setSpacing(12)
        ebl.addWidget(self._save_btn)
        ebl.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        self._btn_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
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

        card_layout.addLayout(cols_row)
        card_layout.addWidget(self._error_label)
        card_layout.addWidget(self._btn_stack, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        self._switch_to_view_mode()

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=True)

    def _app_id_from_nav_steps(self) -> int | str | None:
        steps = get_nav_access_steps()
        allowed_desc = LEFT_PANEL_NAV_ITEM_APP_ID_KEYS.get(_API_DETAILS_NAV_LABEL, ())
        if not allowed_desc:
            return None
        if steps:
            for row in steps:
                if not isinstance(row, dict):
                    continue
                desc = str(row.get("appIdDescription") or row.get("app_id_description") or "").strip()
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

    def _load_api_status_options(self) -> None:
        combo = self._field_edits.get("apiStatus")
        if not isinstance(combo, QComboBox):
            return
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
        options: list[tuple[str, Any, str]] = []
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                label = (master_key_row_display_label(row) or "").strip()
                seq = master_key_row_seq_value(row)
                key_value = str(row.get("keyValue") or row.get("key_value") or "").strip().upper()
                if label and seq is not None:
                    options.append((label, seq, key_value))
        if not options:
            options = [("ACTIVE", "ACTIVE", "ACTIVE"), ("INACTIVE", "INACTIVE", "INACTIVE")]
        combo.blockSignals(True)
        combo.clear()
        for label, seq, _ in options:
            combo.addItem(label, seq)
        combo.blockSignals(False)

    def _select_api_status_from_record(self, raw_value: Any, text_value: str) -> None:
        combo = self._field_edits.get("apiStatus")
        if not isinstance(combo, QComboBox):
            return
        seq_text = str(raw_value).strip() if raw_value is not None else ""
        if seq_text:
            idx = combo.findData(int(seq_text) if seq_text.isdigit() else seq_text)
            if idx >= 0:
                combo.setCurrentIndex(idx)
                return
        t = (text_value or "").strip().upper()
        if t:
            for i in range(combo.count()):
                item_t = combo.itemText(i).strip().upper()
                if item_t == t or item_t.endswith(f"| {t}") or item_t.endswith(f"|{t}"):
                    combo.setCurrentIndex(i)
                    return
        if combo.count() > 0:
            combo.setCurrentIndex(0)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def _handle_edit(self) -> None:
        if not self._can_edit_action:
            self._show_error("Require Permission.")
            return
        self._clear_error()
        self._edit_baseline = {}
        for key in self._editable_keys:
            self._edit_baseline[key] = self._get_edit_value(key)
        for key in self._editable_keys:
            widget = self._field_edits.get(key)
            if widget:
                if isinstance(widget, QComboBox):
                    widget.setEnabled(True)
                    widget.setStyleSheet(FORM_COMBOBOX_STYLE)
                elif isinstance(widget, QPlainTextEdit):
                    widget.setReadOnly(False)
                    widget.setStyleSheet(INPUT_STYLE)
                else:
                    widget.setReadOnly(False)
                    widget.setStyleSheet(INPUT_STYLE)
        self._btn_stack.setCurrentIndex(1)
        if self._localhost_path_icon:
            self._localhost_path_icon.setVisible(True)
        if self._server_path_icon:
            self._server_path_icon.setVisible(True)

    def _handle_save(self) -> None:
        self._clear_error()
        if not self._has_unsaved_changes():
            navigate_after_no_changes(
                show_non_error_message=self._show_success,
                clear_message=self._clear_error,
                on_back=self.on_back,
            )
            return
        api_id = (
            self._record.get("apiId")
            or self._record.get("api_id")
            or self._record.get("id")
        )
        if api_id is None:
            self._show_error("API ID (Internal) is missing.")
            return

        api_method = self._get_edit_value("apiMethod") or self._get_edit_value("api_method")
        if not api_method:
            self._show_error("API Method is required.")
            return

        api_name = self._get_edit_value("apiName") or self._get_edit_value("api_name")
        if not api_name:
            self._show_error("API name is required.")
            return

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_update_api_detail_by_id(
            api_id,
            token=token,
            app_id=self._app_id_from_nav_steps(),
            folder=self._get_edit_value("folder"),
            api_method=api_method,
            api_name=api_name,
            localhost_path=self._get_edit_value("localhostPath") or self._get_edit_value("localhost_path"),
            server_path=self._get_edit_value("serverPath") or self._get_edit_value("server_path"),
            requirement=self._get_edit_value("requirement"),
            api_status=self._get_edit_value("apiStatus") or self._get_edit_value("api_status"),
            comments=self._get_edit_value("comments"),
            request_body=self._get_edit_value("request"),
            response_body=self._get_edit_value("response"),
        )

        if not result.get("success"):
            self._show_error(result.get("message", "Failed to update API detail."))
            return
        self._show_success(result.get("message", "API detail updated successfully."))
        schedule_after_success(
            delay_ms=800,
            clear_error=self._clear_error,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )

    def _get_edit_value(self, key: str) -> str | int:
        widget = self._field_edits.get(key)
        if not widget:
            return ""
        if isinstance(widget, QComboBox):
            if key in ("apiStatus", "api_status"):
                data = widget.currentData()
                if data is None:
                    return ""
                if isinstance(data, int):
                    return data
                return str(data).strip()
            return widget.currentText().strip()
        if isinstance(widget, QPlainTextEdit):
            return widget.toPlainText().strip()
        return widget.text().strip()

    def _get_project_by_id(self, project_id: int | str) -> dict[str, Any] | None:
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
        pid_str = str(project_id)
        for p in projects:
            if not isinstance(p, dict):
                continue
            p_id = p.get("projectId") or p.get("project_id") or p.get("id")
            if p_id is not None and str(p_id) == pid_str:
                return p
        return None

    def _project_id_from_record(self) -> Any:
        return self._record.get("projectId") or self._record.get("project_id")

    def _on_localhost_path_icon_clicked(self) -> None:
        project_id = self._project_id_from_record()
        if project_id is None:
            return
        project = self._get_project_by_id(project_id)
        if not project:
            return
        widget = self._field_edits.get("localhostPath") or self._field_edits.get("localhost_path")
        if not widget or not isinstance(widget, QLineEdit):
            return
        port_raw = project.get("projectPort") or project.get("project_port")
        if port_raw is None or str(port_raw).strip() == "":
            widget.setText("")
            return
        try:
            port_val = int(port_raw)
        except (ValueError, TypeError):
            widget.setText("")
            return
        if port_val == 0:
            widget.setText("")
            return
        api_name = self._get_edit_value("apiName") or self._get_edit_value("api_name")
        if api_name and not api_name.startswith("/"):
            api_name = "/" + api_name
        widget.setText(f"localhost:{port_val}{api_name}")

    def _on_server_path_icon_clicked(self) -> None:
        project_id = self._project_id_from_record()
        if project_id is None:
            return
        project = self._get_project_by_id(project_id)
        if not project:
            return
        widget = self._field_edits.get("serverPath") or self._field_edits.get("server_path")
        if not widget or not isinstance(widget, QLineEdit):
            return
        port_raw = project.get("projectPort") or project.get("project_port")
        if port_raw is None or str(port_raw).strip() == "":
            widget.setText("")
            return
        try:
            port_val = int(port_raw)
        except (ValueError, TypeError):
            widget.setText("")
            return
        if port_val == 0:
            widget.setText("")
            return
        server = (
            project.get("projectServer")
            or project.get("project_server")
            or ""
        )
        server = str(server).strip()
        if not server:
            widget.setText("")
            return
        api_name = self._get_edit_value("apiName") or self._get_edit_value("api_name")
        if api_name and not api_name.startswith("/"):
            api_name = "/" + api_name
        widget.setText(f"http://{server}:{port_val}{api_name}")

    def _has_unsaved_changes(self) -> bool:
        if not self._edit_baseline:
            return False
        for key in self._editable_keys:
            baseline = self._edit_baseline.get(key, "")
            current = self._get_edit_value(key)
            if str(baseline or "").strip() != str(current or "").strip():
                return True
        return False

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

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1

    def _switch_to_view_mode(self) -> None:
        if self._localhost_path_icon:
            self._localhost_path_icon.setVisible(False)
        if self._server_path_icon:
            self._server_path_icon.setVisible(False)
        for key in self._editable_keys:
            widget = self._field_edits.get(key)
            if widget:
                if isinstance(widget, QComboBox):
                    widget.setEnabled(False)
                    widget.setStyleSheet(FORM_COMBOBOX_STYLE)
                elif isinstance(widget, QPlainTextEdit):
                    widget.setReadOnly(True)
                    widget.setStyleSheet(READONLY_INPUT_STYLE)
                else:
                    widget.setReadOnly(True)
                    widget.setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)
