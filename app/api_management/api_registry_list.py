"""API catalog list — GET apis/get-all-apis, same layout as Users / Roles lists."""

from __future__ import annotations

import json
import traceback
from typing import Any

from PySide6.QtCore import QObject, QPoint, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCursor, QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDialog,
    QFormLayout,
    QFrame,
    QHeaderView,
    QHBoxLayout,
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

from app.api_dev.api_details.api_method_combo import configure_api_method_combo
from app.user_management.users.user_create import INPUT_STYLE
from app.user_management.users.user_view import READONLY_INPUT_STYLE
from app.user_management.user_timepass.user_role_ui_helpers import _add_view_user_form_row
from core.api import (
    api_create_api,
    api_delete_api_by_id,
    api_get_all_apis,
    api_get_all_app_id,
    api_update_api_by_id,
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
    placeholder_auto_filled,
    placeholder_enter,
    placeholder_example,
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

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})

_API_COLUMN_SPEC: tuple[tuple[str, tuple[str, ...]], ...] = (
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


def _api_catalog_id(row: dict[str, Any]) -> Any:
    return row.get("apiId") or row.get("api_id") or row.get("id")


def _api_catalog_name(row: dict[str, Any]) -> str:
    for k in ("apiName", "api_name", "name", "title"):
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _api_catalog_endpoint(row: dict[str, Any]) -> str:
    for k in ("apiEndpoint", "api_endpoint", "endpoint", "path", "urlPath", "url_path", "url", "uri"):
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _normalize_api_endpoint_for_save(raw: str) -> str:
    """If the endpoint is a relative path without a leading slash, add ``/`` before save.

    ``http://`` and ``https://`` values are left unchanged.
    """
    s = raw.strip()
    if not s:
        return s
    low = s.lower()
    if low.startswith("http://") or low.startswith("https://"):
        return s
    if s.startswith("/"):
        return s
    return "/" + s


def _api_catalog_method(row: dict[str, Any]) -> str:
    for k in ("httpMethod", "http_method", "method", "verb"):
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip().upper()
    return "GET"


def _display_catalog_field(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    value, key_used = _value_for_column(row, keys)
    return _format_cell(value, key_used, keys)


def _app_catalog_row_id_effective(row: dict[str, Any]) -> Any:
    for k in ("appId", "app_id", "id"):
        if k in row and row[k] is not None and str(row[k]).strip() != "":
            return row[k]
    return None


def _app_catalog_row_description(row: dict[str, Any]) -> str:
    for k in ("description", "Description", "desc", "Desc"):
        v = row.get(k)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def _app_id_value_for_api(aid: Any) -> int | str:
    s = str(aid).strip()
    return int(s) if s.isdigit() else s


def _app_search_display_string(row: dict[str, Any]) -> str | None:
    """Completion line: App Id | Description (same shape as Create Department BU search)."""
    aid = _app_catalog_row_id_effective(row)
    if aid is None:
        return None
    desc = _app_catalog_row_description(row)
    return f"{aid} | {desc}" if desc else f"{aid} |"


def _build_app_completions(app_rows: list[dict[str, Any]]) -> list[tuple[str, int | str]]:
    rows = [r for r in app_rows if isinstance(r, dict)]
    rows.sort(key=lambda r: (_app_catalog_row_description(r) or str(_app_catalog_row_id_effective(r) or "")).lower())
    out: list[tuple[str, int | str]] = []
    for row in rows:
        disp = _app_search_display_string(row)
        if not disp:
            continue
        aid = _app_catalog_row_id_effective(row)
        if aid is None:
            continue
        out.append((disp, _app_id_value_for_api(aid)))
    return out


def _api_catalog_app_id_val(row: dict[str, Any]) -> Any:
    for k in ("appId", "app_id", "appIdVal", "app_id_val"):
        if k in row and row[k] is not None and str(row[k]).strip() != "":
            return row[k]
    return None


def _completion_display_for_app_api_value(
    app_id_val: Any, completions: list[tuple[str, int | str]]
) -> str | None:
    if app_id_val is None:
        return None
    coerced = _app_id_value_for_api(app_id_val)
    for disp, av in completions:
        if av == coerced or str(av) == str(coerced):
            return disp
    return None


class _ApisLoadWorker(QObject):
    finished = Signal(bool, object, str)

    def __init__(self, token: str | None) -> None:
        super().__init__()
        self._token = token

    @Slot()
    def run(self) -> None:
        result = api_get_all_apis(token=self._token)
        if not result.get("success"):
            self.finished.emit(False, [], str(result.get("message", "Failed to load APIs.")))
            return
        raw = result.get("data") or []
        rows = [r for r in raw if isinstance(r, dict)]
        self.finished.emit(True, rows, "")


class _CreateApiDialog(QDialog):
    """Create API — same chrome as Assign Reporting Manager (form rows, separator, Save / Cancel)."""

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        app_rows: list[dict[str, Any]] | None = None,
        token: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._token = token
        self._creation_success_message = "API created successfully."
        self.setWindowTitle("Create API")
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

        self.app_id_display_edit = QLineEdit()
        self.app_id_display_edit.setReadOnly(True)
        self.app_id_display_edit.setPlaceholderText(placeholder_auto_filled("search"))
        self.app_id_display_edit.setFixedHeight(fh)
        self.app_id_display_edit.setMinimumWidth(360)
        self.app_id_display_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.app_id_display_edit.setStyleSheet(READONLY_INPUT_STYLE)
        _add_view_user_form_row(form, "App Id:", self.app_id_display_edit)

        self.app_search_edit = QLineEdit()
        self.app_search_edit.setPlaceholderText(placeholder_search_select("App Id", "Description"))
        self.app_search_edit.setStyleSheet(INPUT_STYLE)
        self.app_search_edit.setFixedHeight(fh)
        self.app_search_edit.setMinimumWidth(360)
        self.app_search_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.app_search_edit.textChanged.connect(self._on_app_search_text_changed)
        _add_view_user_form_row(form, "App*", self.app_search_edit)

        self._app_completions: list[tuple[str, int | str]] = []
        self._setup_app_completer(list(app_rows or []))

        self.api_name_edit = QLineEdit()
        self.api_name_edit.setPlaceholderText(placeholder_enter("API name"))
        self.api_name_edit.setStyleSheet(INPUT_STYLE)
        self.api_name_edit.setFixedHeight(fh)
        self.api_name_edit.setMinimumWidth(360)
        self.api_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_view_user_form_row(form, "API name*", self.api_name_edit)

        self.api_endpoint_edit = QLineEdit()
        self.api_endpoint_edit.setPlaceholderText(placeholder_example("/api/example-endpoint"))
        self.api_endpoint_edit.setStyleSheet(INPUT_STYLE)
        self.api_endpoint_edit.setFixedHeight(fh)
        self.api_endpoint_edit.setMinimumWidth(360)
        self.api_endpoint_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_view_user_form_row(form, "API endpoint*", self.api_endpoint_edit)

        self.method_combo = QComboBox()
        configure_api_method_combo(self.method_combo, current="POST", default_index=0)
        apply_form_combobox_field(self.method_combo, height_px=fh, min_width=360)
        _add_view_user_form_row(form, "HTTP method*", self.method_combo)

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

    def _setup_app_completer(self, app_rows: list[dict[str, Any]]) -> None:
        self._app_completions = _build_app_completions(app_rows)
        completer = QCompleter([d for d, _ in self._app_completions])
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(10)

        def on_activated(text: str) -> None:
            self.app_search_edit.setText(text)
            for disp, av in self._app_completions:
                if disp == text:
                    self.app_id_display_edit.setText(str(av))
                    break

        completer.activated.connect(on_activated)
        self.app_search_edit.setCompleter(completer)

    def _on_app_search_text_changed(self, text: str) -> None:
        if not text.strip():
            self.app_id_display_edit.clear()
            return
        for disp, av in self._app_completions:
            if disp == text:
                self.app_id_display_edit.setText(str(av))
                return
        self.app_id_display_edit.clear()

    def _is_valid_app_selection(self) -> bool:
        text = self.app_search_edit.text().strip()
        if not text:
            return False
        return text in {disp for disp, _ in self._app_completions}

    def _resolve_app_id(self) -> int | str | None:
        text = self.app_search_edit.text().strip()
        if not text:
            return None
        for disp, av in self._app_completions:
            if disp == text:
                return av
        return None

    def _clear_msg(self) -> None:
        self.msg.clear()
        self.msg.setVisible(False)

    def _show_err(self, text: str) -> None:
        self.msg.setText(text)
        self.msg.setVisible(bool(text))

    def _submit(self) -> None:
        self._clear_msg()
        api_name = self.api_name_edit.text().strip()
        api_endpoint = _normalize_api_endpoint_for_save(self.api_endpoint_edit.text())
        app_search = self.app_search_edit.text().strip()
        if not app_search:
            self._show_err("Please select an app from the search list.")
            self.app_search_edit.setFocus()
            return
        if not self._is_valid_app_selection():
            self._show_err(strict_list_selection_message("an app"))
            self.app_search_edit.setFocus()
            return
        app_id_val = self._resolve_app_id()
        if app_id_val is None:
            self._show_err("App Id is invalid. Please select from the list.")
            self.app_search_edit.setFocus()
            return
        if not api_name:
            self._show_err("API name is required.")
            self.api_name_edit.setFocus()
            return
        if not api_endpoint:
            self._show_err("API endpoint is required.")
            self.api_endpoint_edit.setFocus()
            return
        if not self._token or not str(self._token).strip():
            self._show_err("Session expired. Please log in again.")
            return
        result = api_create_api(
            api_name=api_name,
            api_endpoint=api_endpoint,
            method=self.method_combo.currentText().strip().upper(),
            app_id=app_id_val,
            token=self._token,
        )
        if result.get("success"):
            self._creation_success_message = str(result.get("message") or "API created successfully.")
            self.accept()
            return
        self._show_err(str(result.get("message") or "Failed to create API."))

    def creation_success_message(self) -> str:
        return self._creation_success_message

    def values(self) -> dict[str, Any]:
        app_id_val = self._resolve_app_id()
        return {
            "app_id": app_id_val,
            "api_name": self.api_name_edit.text().strip(),
            "api_endpoint": _normalize_api_endpoint_for_save(self.api_endpoint_edit.text()),
            "method": self.method_combo.currentText().strip().upper(),
        }


class _EditApiDialog(QDialog):
    """API Detail — Edit / Back / Save / Cancel like Reporting Hierarchy Detail."""

    def __init__(
        self,
        parent: QWidget | None,
        row: dict[str, Any],
        *,
        app_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(parent)
        self._api_id = _api_catalog_id(row)
        self.success_message = "API updated."
        self._orig_name = _api_catalog_name(row)
        self._orig_endpoint = _api_catalog_endpoint(row)
        self._orig_method = _api_catalog_method(row)
        self._orig_app_val = _api_catalog_app_id_val(row)
        self._app_completions = _build_app_completions(list(app_rows or []))

        self.setWindowTitle("API Detail")
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

        def _ro_audit_line(text: str) -> QLineEdit:
            e = QLineEdit(text)
            e.setReadOnly(True)
            e.setFixedHeight(fh)
            e.setMinimumWidth(360)
            e.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            e.setStyleSheet(READONLY_INPUT_STYLE)
            return e

        top_form = _make_form()
        id_edit = QLineEdit(str(self._api_id) if self._api_id is not None else "")
        id_edit.setReadOnly(True)
        id_edit.setFixedHeight(fh)
        id_edit.setMinimumWidth(360)
        id_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        id_edit.setStyleSheet(READONLY_INPUT_STYLE)
        _add_view_user_form_row(top_form, "API Id", id_edit)
        _add_view_user_form_row(
            top_form, "Created By", _ro_audit_line(_display_catalog_field(row, ("createdBy", "created_by")))
        )
        _add_view_user_form_row(
            top_form, "Created At", _ro_audit_line(_display_catalog_field(row, ("createdAt", "created_at")))
        )
        _add_view_user_form_row(
            top_form, "Modified By", _ro_audit_line(_display_catalog_field(row, ("modifiedBy", "modified_by")))
        )
        _add_view_user_form_row(
            top_form,
            "Modified At",
            _ro_audit_line(
                _display_catalog_field(row, ("modifiedAt", "modified_at", "updatedAt", "updated_at"))
            ),
        )
        layout.addLayout(top_form)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFrameShadow(QFrame.Shadow.Plain)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #cbd5e1; border: none; max-height: 1px;")
        layout.addWidget(sep)

        bottom_form = _make_form()
        self.api_name_edit = QLineEdit()
        self.api_name_edit.setText(self._orig_name)
        self.api_name_edit.setPlaceholderText(placeholder_enter("API name"))
        self.api_name_edit.setFixedHeight(fh)
        self.api_name_edit.setMinimumWidth(360)
        self.api_name_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_view_user_form_row(bottom_form, "API name*", self.api_name_edit)

        self.api_endpoint_edit = QLineEdit()
        self.api_endpoint_edit.setText(self._orig_endpoint)
        self.api_endpoint_edit.setPlaceholderText(placeholder_example("/api/example-endpoint"))
        self.api_endpoint_edit.setFixedHeight(fh)
        self.api_endpoint_edit.setMinimumWidth(360)
        self.api_endpoint_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        _add_view_user_form_row(bottom_form, "API endpoint*", self.api_endpoint_edit)

        self.method_combo = QComboBox()
        m = _api_catalog_method(row)
        configure_api_method_combo(self.method_combo, current=m, default_index=0)
        apply_form_combobox_field(self.method_combo, height_px=fh, min_width=360)
        _add_view_user_form_row(bottom_form, "HTTP method*", self.method_combo)

        self.app_id_display_edit = QLineEdit()
        self.app_id_display_edit.setReadOnly(True)
        self.app_id_display_edit.setPlaceholderText(placeholder_auto_filled("search"))
        self.app_id_display_edit.setFixedHeight(fh)
        self.app_id_display_edit.setMinimumWidth(360)
        self.app_id_display_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.app_id_display_edit.setStyleSheet(READONLY_INPUT_STYLE)
        _add_view_user_form_row(bottom_form, "App Id:", self.app_id_display_edit)

        self.app_search_edit = QLineEdit()
        self.app_search_edit.setPlaceholderText(placeholder_search_select("App Id", "Description"))
        self.app_search_edit.setStyleSheet(INPUT_STYLE)
        self.app_search_edit.setFixedHeight(fh)
        self.app_search_edit.setMinimumWidth(360)
        self.app_search_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.app_search_edit.textChanged.connect(self._on_edit_app_search_text_changed)
        _add_view_user_form_row(bottom_form, "App*", self.app_search_edit)

        self._setup_edit_app_completer()
        init_disp = _completion_display_for_app_api_value(self._orig_app_val, self._app_completions)
        if init_disp:
            self.app_search_edit.setText(init_disp)
        elif self._orig_app_val is not None:
            self.app_id_display_edit.setText(str(_app_id_value_for_api(self._orig_app_val)))
        self._orig_app_search = self.app_search_edit.text()

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
        save_btn.setDefault(True)
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
        self._snap_name = ""
        self._snap_endpoint = ""
        self._snap_method = ""
        self._snap_app_search = ""
        self._enter_view_mode()

    def _setup_edit_app_completer(self) -> None:
        completer = QCompleter([d for d, _ in self._app_completions])
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(10)

        def on_activated(text: str) -> None:
            self.app_search_edit.setText(text)
            for disp, av in self._app_completions:
                if disp == text:
                    self.app_id_display_edit.setText(str(av))
                    break

        completer.activated.connect(on_activated)
        self.app_search_edit.setCompleter(completer)

    def _on_edit_app_search_text_changed(self, text: str) -> None:
        if not text.strip():
            self.app_id_display_edit.clear()
            return
        for disp, av in self._app_completions:
            if disp == text:
                self.app_id_display_edit.setText(str(av))
                return
        self.app_id_display_edit.clear()

    def _is_valid_edit_app_selection(self) -> bool:
        t = self.app_search_edit.text().strip()
        if not t:
            return False
        return t in {disp for disp, _ in self._app_completions}

    def _resolve_edit_app_id(self) -> int | str | None:
        t = self.app_search_edit.text().strip()
        if not t:
            return None
        for disp, av in self._app_completions:
            if disp == t:
                return av
        return None

    def _apply_method_to_combo(self, method: str) -> None:
        m = (method or "").strip().upper() or "GET"
        configure_api_method_combo(self.method_combo, current=m, default_index=0)

    def _restore_editable_from_original(self) -> None:
        self.api_name_edit.setText(self._orig_name)
        self.api_endpoint_edit.setText(self._orig_endpoint)
        self._apply_method_to_combo(self._orig_method)
        self.app_search_edit.blockSignals(True)
        self.app_search_edit.setText(self._orig_app_search)
        self.app_search_edit.blockSignals(False)
        if self._orig_app_search.strip():
            for disp, av in self._app_completions:
                if disp == self._orig_app_search:
                    self.app_id_display_edit.setText(str(av))
                    break
            else:
                self.app_id_display_edit.clear()
        elif self._orig_app_val is not None:
            self.app_id_display_edit.setText(str(_app_id_value_for_api(self._orig_app_val)))
        else:
            self.app_id_display_edit.clear()

    def _enter_view_mode(self) -> None:
        self._editing = False
        self.msg.clear()
        self.msg.setVisible(False)
        self.api_name_edit.setEnabled(False)
        self.api_name_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self.api_endpoint_edit.setEnabled(False)
        self.api_endpoint_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self.method_combo.setEnabled(False)
        self.app_search_edit.setEnabled(False)
        self.app_search_edit.setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)

    def _enter_edit_mode(self) -> None:
        self.msg.clear()
        self.msg.setVisible(False)
        self._editing = True
        self.api_name_edit.setEnabled(True)
        self.api_name_edit.setStyleSheet(INPUT_STYLE)
        self.api_endpoint_edit.setEnabled(True)
        self.api_endpoint_edit.setStyleSheet(INPUT_STYLE)
        self.method_combo.setEnabled(True)
        self.method_combo.setStyleSheet(FORM_COMBOBOX_STYLE)
        self.app_search_edit.setEnabled(True)
        self.app_search_edit.setStyleSheet(INPUT_STYLE)
        self._snap_name = self.api_name_edit.text()
        self._snap_endpoint = self.api_endpoint_edit.text()
        self._snap_method = self.method_combo.currentText()
        self._snap_app_search = self.app_search_edit.text()
        self._btn_stack.setCurrentIndex(1)

    def _has_unsaved_changes(self) -> bool:
        if not self._editing:
            return False
        return (
            self.api_name_edit.text() != self._snap_name
            or self.api_endpoint_edit.text() != self._snap_endpoint
            or self.method_combo.currentText() != self._snap_method
            or self.app_search_edit.text() != self._snap_app_search
        )

    def _handle_cancel(self) -> None:
        if not self._has_unsaved_changes():
            self._restore_editable_from_original()
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
            self._restore_editable_from_original()
            self._enter_view_mode()

    def _handle_save(self) -> None:
        self.msg.clear()
        self.msg.setVisible(False)
        if self._api_id is None:
            self.msg.setText("Missing API id.")
            self.msg.setVisible(True)
            return
        if not self._has_unsaved_changes():
            self.success_message = NO_CHANGES_MESSAGE
            self.accept()
            return
        api_name = self.api_name_edit.text().strip()
        api_endpoint = _normalize_api_endpoint_for_save(self.api_endpoint_edit.text())
        method_val = self.method_combo.currentText().strip().upper()
        if not api_name:
            self.msg.setText("API name is required.")
            self.msg.setVisible(True)
            self.api_name_edit.setFocus()
            return
        if not api_endpoint:
            self.msg.setText("API endpoint is required.")
            self.msg.setVisible(True)
            self.api_endpoint_edit.setFocus()
            return
        app_search = self.app_search_edit.text().strip()
        if not app_search:
            self.msg.setText("Please select an app from the search list.")
            self.msg.setVisible(True)
            self.app_search_edit.setFocus()
            return
        if not self._is_valid_edit_app_selection():
            self.msg.setText(strict_list_selection_message("an app"))
            self.msg.setVisible(True)
            self.app_search_edit.setFocus()
            return
        app_id_val = self._resolve_edit_app_id()
        if app_id_val is None:
            self.msg.setText("App Id is invalid. Please select from the list.")
            self.msg.setVisible(True)
            self.app_search_edit.setFocus()
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
        result = api_update_api_by_id(
            self._api_id,
            api_name=api_name,
            api_endpoint=api_endpoint,
            method=method_val,
            app_id=app_id_val,
            token=token,
        )
        if not result.get("success"):
            self.msg.setText(result.get("message", "Update failed."))
            self.msg.setVisible(True)
            return
        self.success_message = result.get("message", "API updated.")
        self.accept()

    def values(self) -> dict[str, str]:
        return {
            "api_name": self.api_name_edit.text().strip(),
            "api_endpoint": _normalize_api_endpoint_for_save(self.api_endpoint_edit.text()),
            "method": self.method_combo.currentText().strip().upper(),
        }

    def api_id(self) -> Any:
        return self._api_id


class ApiRegistryListPage(QWidget):
    """Operational API list (API Management → API: List)."""

    def __init__(self) -> None:
        super().__init__()
        self._loading = False
        self._pending_refresh = False
        self._load_thread: QThread | None = None
        self._load_worker: _ApisLoadWorker | None = None
        self._source_rows: list[dict[str, Any]] = []
        self._column_spec: list[tuple[str, tuple[str, ...]]] = []
        self._filter_visible = False
        self._filter_apply_timer = QTimer(self)
        self._filter_apply_timer.setSingleShot(True)
        self._filter_apply_timer.setInterval(200)
        self._filter_apply_timer.timeout.connect(self._apply_column_filters_refresh)
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
        title = QLabel("API: List")
        header_layout.addWidget(title)
        header_layout.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(100)
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        header_layout.addWidget(refresh_btn)
        self._filter_toggle = QPushButton("Filters")
        self._filter_toggle.setCheckable(True)
        self._filter_toggle.setFixedWidth(100)
        self._filter_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._filter_toggle.toggled.connect(self._on_filter_toggle)
        header_layout.addWidget(self._filter_toggle)
        add_btn = QPushButton("Create")
        add_btn.setFixedWidth(100)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._show_add_api_dialog)
        header_layout.addWidget(add_btn)
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

        self.table = QTableWidget()
        apply_data_table_appearance(self.table)
        self.table.setSortingEnabled(False)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        self.table.itemDoubleClicked.connect(self._on_table_row_double_clicked)
        attach_table_copy_shortcut(self.table)
        content_layout.addWidget(self.table, 1)
        layout.addWidget(content)

    def _data_row_offset(self) -> int:
        return data_row_offset(self._filter_visible)

    def _is_data_table_row(self, table_row: int) -> bool:
        return table_row >= self._data_row_offset()

    def _schedule_filter_apply(self) -> None:
        if self._filter_visible:
            self._filter_apply_timer.start()

    def _filtered_source_rows(self) -> list[dict[str, Any]]:
        return filter_dict_rows_by_column_edits(
            self._source_rows,
            self.table,
            self._column_spec,
            self._filter_visible,
            _value_for_column,
            _format_cell,
        )

    def _write_data_rows(self, data_rows: list[dict[str, Any]]) -> None:
        off = self._data_row_offset()
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
                len(self._column_spec),
                on_text_changed=self._schedule_filter_apply,
            )
        for r, row in enumerate(data_rows):
            tr = off + r
            for col, (_, keys) in enumerate(self._column_spec):
                value, key_used = _value_for_column(row, keys)
                item = QTableWidgetItem(_format_cell(value, key_used, keys))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(tr, col, item)
        sync_vertical_header_labels(
            self.table,
            filter_visible=self._filter_visible,
            data_row_count=len(data_rows),
        )
        resize_data_table_columns_to_content(
            self.table,
            self._column_spec,
            self._source_rows,
            _value_for_column,
            _format_cell,
        )
        self.table.setSortingEnabled(not self._filter_visible)

    def _apply_column_filters_refresh(self) -> None:
        if not self._filter_visible or not self._column_spec or not self._source_rows:
            return
        try:
            filtered = self._filtered_source_rows()
            self._write_data_rows(filtered)
        except Exception:
            traceback.print_exc()

    def _on_filter_toggle(self, checked: bool) -> None:
        self._filter_visible = checked
        if not checked:
            self._filter_apply_timer.stop()
            clear_filter_row_widgets(self.table)
        if self._column_spec and self._source_rows:
            try:
                to_show = self._filtered_source_rows() if checked else list(self._source_rows)
                self._write_data_rows(to_show)
            except Exception:
                traceback.print_exc()
        elif not self._source_rows:
            self._show_empty_table()

    def _show_empty_table(self) -> None:
        self._source_rows = []
        self._column_spec = []
        self.table.setSortingEnabled(False)
        clear_filter_row_widgets(self.table)
        self.table.setRowCount(0)
        self.table.setColumnCount(0)

    def _populate_table(self, rows: list[dict[str, Any]]) -> None:
        if not rows:
            self._show_empty_table()
            return
        try:
            self._source_rows = [dict(r) for r in rows if isinstance(r, dict)]
            self._column_spec = list(_API_COLUMN_SPEC)
            self.table.setSortingEnabled(False)
            headers = [spec[0] for spec in self._column_spec]
            self.table.setColumnCount(len(self._column_spec))
            self.table.setHorizontalHeaderLabels(headers)
            hh = self.table.horizontalHeader()
            hh.setStretchLastSection(False)
            for col in range(self.table.columnCount()):
                hh.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            hh.setMinimumSectionSize(MIN_DATA_COL_WIDTH_PX)
            filtered = self._filtered_source_rows() if self._filter_visible else list(self._source_rows)
            self._write_data_rows(filtered)
        except Exception:
            traceback.print_exc()
            self._show_empty_table()

    def refresh(self) -> None:
        if self._loading:
            self._pending_refresh = True
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        self._loading = True
        cancel_auto_hide_message(self, self._message_label)
        self._message_label.setStyleSheet(MODAL_FIELD_LABEL_STYLE)
        self._message_label.setText("Loading APIs...")
        self._message_label.setVisible(True)
        self._load_thread = QThread(self)
        self._load_worker = _ApisLoadWorker(token)
        self._load_worker.moveToThread(self._load_thread)
        self._load_thread.started.connect(self._load_worker.run)
        self._load_worker.finished.connect(self._on_apis_loaded)
        self._load_worker.finished.connect(self._load_thread.quit)
        self._load_thread.finished.connect(self._cleanup_loader)
        self._load_thread.start()

    @Slot()
    def _on_apis_loaded(self, success: bool, rows: object, message: str) -> None:
        self._loading = False
        if not success:
            self._show_message(message or "Failed to load APIs.", error=True)
            self._show_empty_table()
        else:
            show_auto_hiding_message(self, self._message_label, "")
            data = list(rows) if isinstance(rows, list) else []
            self._populate_table([r for r in data if isinstance(r, dict)])
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

    def _get_token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _show_message(self, text: str, *, error: bool) -> None:
        show_auto_hiding_message(self, self._message_label, text, error=error)

    def _has_data_row_selection(self) -> bool:
        for it in self.table.selectedItems():
            if self._is_data_table_row(it.row()):
                return True
        return False

    def _selected_api_row(self) -> dict[str, Any] | None:
        items = self.table.selectedItems()
        if not items:
            return None
        r = items[0].row()
        if not self._is_data_table_row(r):
            return None
        item = self.table.item(r, 0)
        if item is None:
            return None
        data = item.data(Qt.ItemDataRole.UserRole)
        return data if isinstance(data, dict) else None

    def _on_table_context_menu(self, pos: QPoint) -> None:
        clicked_item = self.table.itemAt(pos)
        if clicked_item is not None and self._is_data_table_row(clicked_item.row()):
            self.table.setCurrentCell(clicked_item.row(), clicked_item.column())
            self.table.selectRow(clicked_item.row())
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Add API")
        edit_action = menu.addAction("Edit Selected API")
        remove_action = menu.addAction("Remove Selected API")
        has_selected_row = self._has_data_row_selection() or (
            clicked_item is not None and self._is_data_table_row(clicked_item.row())
        )
        edit_action.setEnabled(has_selected_row)
        remove_action.setEnabled(has_selected_row)
        action = menu.exec(QCursor.pos())
        if action == add_action:
            self._show_add_api_dialog()
        elif action == remove_action:
            self._remove_selected_api()
        elif action == edit_action:
            self._edit_selected_api()

    def _on_table_row_double_clicked(self, item: QTableWidgetItem) -> None:
        if not self._is_data_table_row(item.row()):
            return
        row_item = self.table.item(item.row(), 0)
        if row_item is None:
            return
        rec = row_item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(rec, dict):
            return
        if _api_catalog_id(rec) is None:
            return
        self._run_edit_api_dialog(rec)

    def _run_edit_api_dialog(self, row: dict[str, Any]) -> None:
        token = self._get_token()
        if not token:
            self._show_message("Session expired. Please log in again.", error=True)
            return
        load = api_get_all_app_id(token=token)
        if not load.get("success"):
            self._show_message(load.get("message", "Failed to load app ids."), error=True)
            return
        raw = load.get("data") or []
        app_rows = [r for r in raw if isinstance(r, dict)]
        dlg = _EditApiDialog(self, row, app_rows=app_rows)
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        self._show_message(dlg.success_message, error=False)
        self.refresh()

    def _edit_selected_api(self) -> None:
        rec = self._selected_api_row()
        if not rec:
            self._show_message("Select an API to edit.", error=True)
            return
        if _api_catalog_id(rec) is None:
            self._show_message("Cannot edit: missing API id.", error=True)
            return
        self._run_edit_api_dialog(rec)

    def _remove_selected_api(self) -> None:
        rec = self._selected_api_row()
        if not rec:
            self._show_message("Select an API to remove.", error=True)
            return
        api_id = _api_catalog_id(rec)
        if api_id is None:
            self._show_message("Cannot remove: missing API id.", error=True)
            return
        reply = QMessageBox.question(
            self,
            "Remove API",
            "Remove this API from the catalog?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        token = self._get_token()
        if not token:
            self._show_message("Session expired. Please log in again.", error=True)
            return
        result = api_delete_api_by_id(api_id, token=token)
        if result.get("success"):
            self._show_message(result.get("message", "API removed."), error=False)
            self.refresh()
            return
        self._show_message(result.get("message", "Failed to remove API."), error=True)

    def _show_add_api_dialog(self) -> None:
        token = self._get_token()
        if not token:
            self._show_message("Session expired. Please log in again.", error=True)
            return
        load = api_get_all_app_id(token=token)
        if not load.get("success"):
            self._show_message(load.get("message", "Failed to load app ids."), error=True)
            return
        raw = load.get("data") or []
        app_rows = [r for r in raw if isinstance(r, dict)]
        dlg = _CreateApiDialog(self, app_rows=app_rows, token=token)
        if dlg.exec() != int(QDialog.DialogCode.Accepted):
            return
        self._show_message(dlg.creation_success_message(), error=False)
        self.refresh()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.refresh()
