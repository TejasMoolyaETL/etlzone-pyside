"""View / edit Master Setup Config page."""

from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
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

from app.master_setup.master_setup_view import (
    _format_category_value_for_display,
    _parse_category_id_from_label_text,
    _resolve_master_key_value_category_id,
    _set_category_combo_current_by_id,
    category_id_from_master_setup_category_combo,
)
from core.api import (
    api_get_all_master_setup_key_entries,
    api_update_master_setup_config,
    master_setup_key_entry_category_combo_options,
)
from core.app_preferences import format_datetime_display, is_datetime_field
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.blank_display import is_blank_display_value
from ui.form_combobox_style import FORM_COMBOBOX_STYLE, apply_form_combobox_field
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    FORM_SINGLELINE_FIELD_HEIGHT_PX,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    placeholder_example,
)
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success
from ui.widgets.required_label import field_caption_label, labeled_field_block

_CATEGORY_ROW_KEYS: tuple[str, ...] = ("category", "categoryName", "category_name")

_COL1 = (
    ("Id", ("id",)),
    ("Field*", ("field",)),
    ("Category*", _CATEGORY_ROW_KEYS),
)
_COL2 = (
    ("Created By", ("createdBy", "created_by")),
    ("Created On", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified On", ("modifiedAt", "modified_at")),
)
_ALL = _COL1 + _COL2
_READONLY = {"id", "createdBy", "created_by", "createdAt", "created_at", "modifiedBy", "modified_by", "modifiedAt", "modified_at"}


def _resolve_master_setup_config_category_id(rec: dict[str, Any]) -> int | None:
    """Config row → category id (root keys, ``category`` object, or ``masterSetupCategory``)."""
    base = _resolve_master_key_value_category_id(rec)
    if base is not None:
        return base
    if not isinstance(rec, dict):
        return None
    for nk in ("masterSetupCategory", "master_setup_category"):
        cat = rec.get(nk)
        if isinstance(cat, dict):
            for k in ("id", "categoryId", "category_id", "masterKeyId", "master_key_id"):
                if k not in cat or cat.get(k) is None:
                    continue
                try:
                    return int(cat[k])
                except (TypeError, ValueError):
                    continue
    return None


def _config_category_id_pipe_name(rec: dict[str, Any]) -> str:
    """``categoryId | categoryName`` from the config line (GET-all style)."""
    if not isinstance(rec, dict):
        return ""
    cid = _resolve_master_setup_config_category_id(rec)
    name = ""
    for k in ("categoryName", "category_name"):
        v = rec.get(k)
        if v is not None and not isinstance(v, (dict, list)):
            name = str(v).strip()
            break
    if not name:
        for k in ("category", "masterSetupCategory", "master_setup_category"):
            if k not in rec:
                continue
            raw = rec[k]
            if isinstance(raw, str):
                s = raw.strip()
                if "|" in s:
                    name = s.split("|", 1)[1].strip()
                elif s:
                    name = s
            else:
                name = _format_category_value_for_display(raw).strip()
            if name:
                break
    if cid is not None:
        try:
            i = int(cid)
        except (TypeError, ValueError):
            return name
        return f"{i} | {name}" if name else f"{i} |"
    return name


def _apply_config_category_pipe_label(combo: QComboBox, rec: dict[str, Any]) -> None:
    idx = combo.currentIndex()
    if idx < 0:
        return
    pipe = _config_category_id_pipe_name(rec)
    if pipe:
        combo.setItemText(idx, pipe)


def _get(rec: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for k in keys:
        if k in rec:
            return rec[k]
    return None


def _fmt(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, dict) and key in ("category", "categoryName", "category_name"):
        return _format_category_value_for_display(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


class ViewMasterSetupConfigPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._record: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit | QComboBox] = {}
        self._editable_keys = ["field", "category"]
        self._allowed_category_ids: set[int] = set()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QWidget()
        header.setStyleSheet(FORM_PAGE_HEADER_STYLESHEET)
        header.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        hl.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        hl.addWidget(QLabel("Master Setup Config Details"))
        hl.addStretch()
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
        card.setMaximumWidth(860)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }"
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
            lbl = field_caption_label(label_text, LABEL_STYLE)
            if canonical == "category":
                ed = QComboBox()
                ed.setEditable(False)
                apply_form_combobox_field(
                    ed,
                    height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX,
                    min_width=240,
                )
                ed.setEnabled(False)
            else:
                ed = QLineEdit()
                ed.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
                ed.setMinimumWidth(240)
                ro = canonical in _READONLY
                ed.setReadOnly(ro)
                ed.setStyleSheet(READONLY_INPUT_STYLE if ro else INPUT_STYLE)
                if canonical == "field":
                    ed.setPlaceholderText(placeholder_example("api_status"))
            self._field_edits[canonical] = ed
            grid.addWidget(labeled_field_block(lbl, ed), idx, col)

        for idx, (label_text, keys) in enumerate(_COL1):
            add_field(0, idx, label_text, keys)
        for idx, (label_text, keys) in enumerate(_COL2):
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
        self._error_label.setVisible(False)
        btn_row = max(len(_COL1), len(_COL2))
        grid.addWidget(self._error_label, btn_row, 0, 1, 2)
        grid.addWidget(
            self._btn_stack,
            btn_row + 1,
            0,
            1,
            2,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        card_layout.addLayout(grid)
        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)
        self._switch_to_view_mode()

    def showEvent(self, event: QShowEvent) -> None:  # type: ignore[override]
        super().showEvent(event)
        if not self._record or self.is_edit_mode():
            return
        cid = _resolve_master_setup_config_category_id(self._record)
        self._load_category_options(selected_category_id=cid)

    def set_record(self, record: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._record = dict(record) if record else {}
        selected_cid = _resolve_master_setup_config_category_id(self._record)
        self._load_category_options(selected_category_id=selected_cid)
        self._refresh_values()
        if edit_mode and self._record:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _load_category_options(self, *, selected_category_id: Any = None) -> None:
        combo = self._field_edits.get("category")
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
        result = api_get_all_master_setup_key_entries(token=token)
        rows = result.get("data") or [] if result.get("success") else []
        self._allowed_category_ids.clear()
        combo.blockSignals(True)
        combo.clear()
        for label, cid in master_setup_key_entry_category_combo_options(rows):
            combo.addItem(label, cid)
            self._allowed_category_ids.add(cid)
        sid: int | None = None
        if selected_category_id is not None:
            try:
                sid = int(selected_category_id)
            except (TypeError, ValueError):
                sid = None
        if sid is not None and sid not in self._allowed_category_ids:
            pipe = _config_category_id_pipe_name(self._record)
            combo.addItem(pipe if pipe else f"{sid} |", sid)
            self._allowed_category_ids.add(sid)
        _set_category_combo_current_by_id(combo, sid)
        _apply_config_category_pipe_label(combo, self._record)
        combo.blockSignals(False)

    def _refresh_values(self) -> None:
        for _label, keys in _ALL:
            canonical = keys[0]
            value = _get(self._record, keys)
            text = _fmt(value, keys[0], keys)
            ed = self._field_edits.get(canonical)
            if ed is not None:
                if isinstance(ed, QComboBox) and canonical == "category":
                    cid = _resolve_master_setup_config_category_id(self._record)
                    pipe_display = _config_category_id_pipe_name(self._record)
                    text = pipe_display or _fmt(value, keys[0], keys)
                    if cid is not None:
                        _set_category_combo_current_by_id(ed, cid)
                        if ed.currentIndex() >= 0:
                            _apply_config_category_pipe_label(ed, self._record)
                            continue
                    if text and ed.findText(text) < 0:
                        role_id = cid if cid is not None else _parse_category_id_from_label_text(text)
                        ed.addItem(text, role_id)
                    if text:
                        ed.setCurrentText(text)
                elif isinstance(ed, QComboBox):
                    idx = ed.findData(text)
                    if idx >= 0:
                        ed.setCurrentIndex(idx)
                    elif ed.count() > 0:
                        ed.setCurrentIndex(0)
                else:
                    ed.setText(text)

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

    def _get_edit(self, key: str) -> str:
        return self._get_edit_value(key)

    def _handle_edit(self) -> None:
        self._clear_error()
        for key in self._editable_keys:
            ed = self._field_edits.get(key)
            if ed:
                if isinstance(ed, QComboBox):
                    ed.setEnabled(True)
                    ed.setStyleSheet(FORM_COMBOBOX_STYLE)
                else:
                    ed.setReadOnly(False)
                    ed.setStyleSheet(INPUT_STYLE)
        self._btn_stack.setCurrentIndex(1)

    def _has_unsaved_changes(self) -> bool:
        for key in self._editable_keys:
            if key == "category":
                edit = self._field_edits.get("category")
                if isinstance(edit, QComboBox):
                    orig_id = _resolve_master_setup_config_category_id(self._record)
                    cur = category_id_from_master_setup_category_combo(edit)
                    try:
                        if orig_id is not None and cur is not None and int(orig_id) == int(cur):
                            continue
                    except (TypeError, ValueError):
                        pass
                orig_str = _config_category_id_pipe_name(self._record)
                current = self._get_edit_value("category")
                if orig_str.strip() != (current or "").strip():
                    return True
                continue
            if _fmt(self._record.get(key)).strip() != self._get_edit_value(key).strip():
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

    def _handle_save(self) -> None:
        self._clear_error()
        if not self._has_unsaved_changes():
            navigate_after_no_changes(
                show_non_error_message=self._show_success,
                clear_message=self._clear_error,
                on_back=self.on_back,
            )
            return
        field = self._get_edit_value("field")
        if not field:
            self._show_error("Field is required.")
            field_edit = self._field_edits.get("field")
            if isinstance(field_edit, QLineEdit):
                field_edit.setFocus()
            return
        category_edit = self._field_edits.get("category")
        if not isinstance(category_edit, QComboBox):
            self._show_error("Category is required.")
            return
        category_id = category_id_from_master_setup_category_combo(category_edit)
        if category_id is None:
            self._show_error("Category is required.")
            category_edit.setFocus()
            return
        if category_id not in self._allowed_category_ids:
            self._show_error("Category must be selected from the available list.")
            category_edit.setFocus()
            return
        rid = self._record.get("id")
        if rid is None:
            self._show_error("ID is missing.")
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_update_master_setup_config(
            rid,
            field=field,
            category_id=category_id,
            token=token,
        )
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Failed to update master setup config."))
            return
        self._record["field"] = field
        self._record["categoryId"] = category_id
        self._record["category_id"] = category_id
        ct = category_edit.currentText().strip()
        self._record["category"] = ct
        if "|" in ct:
            tail = ct.split("|", 1)[1].strip()
            if tail:
                self._record["categoryName"] = tail
        self._show_success(str(result.get("message") or "Master setup config updated successfully."))
        schedule_after_success(
            delay_ms=800,
            clear_error=self._clear_error,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )

    def _switch_to_view_mode(self) -> None:
        for key in self._editable_keys:
            ed = self._field_edits.get(key)
            if ed:
                if isinstance(ed, QComboBox):
                    ed.setEnabled(False)
                    ed.setStyleSheet(FORM_COMBOBOX_STYLE)
                else:
                    ed.setReadOnly(True)
                    ed.setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1
