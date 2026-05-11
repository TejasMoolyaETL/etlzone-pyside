"""View / edit Master Setup page."""

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

from core.api import (
    api_get_all_master_setup_key_entries,
    api_update_master_key_value,
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

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})


def _get_value(rec: dict[str, Any], keys: tuple[str, ...]) -> Any:
    flat = {k: v for k, v in rec.items() if k not in _HIDDEN_KEYS}
    for key in keys:
        if key in flat:
            return flat[key]
    return None


def _format_category_value_for_display(value: Any) -> str:
    """Plain category text for nested ``category`` objects (same idea as list / create combo)."""
    if is_blank_display_value(value):
        return ""
    if isinstance(value, dict):
        inner = value.get("category")
        if isinstance(inner, dict):
            leaf = inner.get("category")
            if leaf is not None:
                return str(leaf).strip()
            return ""
        if inner is not None:
            return str(inner).strip()
        for alt in ("categoryName", "category_name", "name"):
            v = value.get(alt)
            if v is not None and not isinstance(v, (dict, list)):
                return str(v).strip()
        return ""
    return str(value).strip()


def _format_value(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
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


def _get_master_key_id(rec: dict[str, Any]) -> int | str | None:
    return rec.get("id") or rec.get("masterKeyValueId") or rec.get("master_key_value_id")


def _resolve_master_key_value_category_id(rec: dict[str, Any]) -> int | None:
    """Master key value row → category id for the Master Setup Key combo (root keys, then nested ``category``)."""
    if not isinstance(rec, dict):
        return None
    for k in (
        "categoryId",
        "category_id",
        "masterKeyCategoryId",
        "master_key_category_id",
    ):
        if k not in rec or rec.get(k) is None:
            continue
        try:
            return int(rec[k])
        except (TypeError, ValueError):
            continue
    cat = rec.get("category")
    if isinstance(cat, dict):
        for k in ("id", "categoryId", "category_id", "masterKeyId", "master_key_id"):
            if k not in cat or cat.get(k) is None:
                continue
            try:
                return int(cat[k])
            except (TypeError, ValueError):
                continue
    return None


def _category_id_pipe_name_display(rec: dict[str, Any]) -> str:
    """``categoryId | categoryName`` using the same shape as master key value GET-all rows."""
    if not isinstance(rec, dict):
        return ""
    cid = _resolve_master_key_value_category_id(rec)
    name = ""
    for k in ("categoryName", "category_name"):
        v = rec.get(k)
        if v is not None and not isinstance(v, (dict, list)):
            name = str(v).strip()
            break
    if not name:
        raw = _get_value(rec, ("category", "categoryName", "category_name"))
        if isinstance(raw, str):
            s = raw.strip()
            if "|" in s:
                name = s.split("|", 1)[1].strip()
            elif s:
                name = s
        else:
            name = _format_category_value_for_display(raw).strip()
    if cid is not None:
        try:
            i = int(cid)
        except (TypeError, ValueError):
            return name
        return f"{i} | {name}" if name else f"{i} |"
    return name


def _apply_get_all_category_label_to_combo(combo: QComboBox, rec: dict[str, Any]) -> None:
    """Replace the selected combo row label with GET-all style ``id | name`` (keeps ``UserRole``)."""
    idx = combo.currentIndex()
    if idx < 0:
        return
    pipe = _category_id_pipe_name_display(rec)
    if pipe:
        combo.setItemText(idx, pipe)


def _set_category_combo_current_by_id(combo: QComboBox, category_id: int | None) -> None:
    """Pick the row whose ``UserRole`` matches ``category_id`` (int-coerced); -1 if unknown (never default to row 0)."""
    if category_id is None:
        combo.setCurrentIndex(-1)
        return
    target = int(category_id)
    for i in range(combo.count()):
        data = combo.itemData(i, Qt.ItemDataRole.UserRole)
        if data is None:
            continue
        try:
            if int(data) == target:
                combo.setCurrentIndex(i)
                return
        except (TypeError, ValueError):
            continue
    combo.setCurrentIndex(-1)


def _parse_category_id_from_label_text(text: str) -> int | None:
    """Parse only a leading integer id from a combo label (e.g. ``12 | Name`` → ``12``). Never uses the name segment."""
    t = (text or "").strip()
    if not t:
        return None
    if "|" in t:
        prefix = t.split("|", 1)[0].strip()
        if prefix.isdigit():
            try:
                return int(prefix)
            except ValueError:
                return None
        return None
    if t.isdigit():
        try:
            return int(t)
        except ValueError:
            return None
    return None


def category_id_from_master_setup_category_combo(combo: QComboBox) -> int | None:
    """Integer ``categoryId`` for master key value create/update API bodies only.

    Prefer ``UserRole`` on the current row (always the numeric id). If missing, parse
    only a leading integer from the visible text (``id | name`` → ``id``). Display
    names are never sent to the API — only this int is passed as ``categoryId``.
    """
    idx = combo.currentIndex()
    for raw in (
        combo.currentData(Qt.ItemDataRole.UserRole),
        combo.itemData(idx, Qt.ItemDataRole.UserRole) if idx >= 0 else None,
    ):
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return _parse_category_id_from_label_text(combo.currentText())


_MASTER_SETUP_COL1 = (
    ("Id", ("id", "masterKeyValueId", "master_key_value_id")),
    ("Category*", ("category", "categoryName", "category_name")),
    ("Seq*", ("seq",)),
    ("Key Value*", ("keyValue", "key_value")),
    ("Description", ("description", "desc")),
)
_MASTER_SETUP_COL2 = (
    ("Created By", ("createdBy", "createBy", "created_by", "create_by")),
    ("Created On", ("createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified On", ("modifiedAt", "modified_at")),
)
_MASTER_SETUP_FIELD_GROUPS = _MASTER_SETUP_COL1 + _MASTER_SETUP_COL2

_READONLY_KEYS = frozenset({
    "id",
    "masterKeyValueId",
    "master_key_value_id",
    "createdBy", "createBy", "created_by", "create_by",
    "createdAt", "created_at",
    "modifiedBy", "modified_by",
    "modifiedAt", "modified_at",
})


class ViewMasterSetupPage(QWidget):
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
        self._editable_keys: list[str] = []
        self._allowed_category_ids: set[int] = set()
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
        title = QLabel("Master Setup Value Details")
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
        card.setMaximumWidth(860)
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
            if canonical == "category":
                value_edit = QComboBox()
                value_edit.setEditable(False)
                apply_form_combobox_field(
                    value_edit,
                    height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX,
                    min_width=240,
                )
                value_edit.setEnabled(False)
            else:
                value_edit = QLineEdit()
                value_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
                value_edit.setMinimumWidth(240)
                value_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                value_edit.setReadOnly(canonical in _READONLY_KEYS)
                value_edit.setStyleSheet(READONLY_INPUT_STYLE if canonical in _READONLY_KEYS else INPUT_STYLE)
                value_edit.setText("")
                if canonical == "seq":
                    value_edit.setPlaceholderText(placeholder_example("1"))
                elif canonical == "keyValue":
                    value_edit.setPlaceholderText(placeholder_example("In Scope"))
                elif canonical == "description":
                    value_edit.setPlaceholderText(placeholder_example("Added from app"))
            self._field_edits[canonical] = value_edit
            grid.addWidget(labeled_field_block(label_widget, value_edit), idx, col)

        for idx, (label_text, keys) in enumerate(_MASTER_SETUP_COL1):
            add_field(0, idx, label_text, keys)
        for idx, (label_text, keys) in enumerate(_MASTER_SETUP_COL2):
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
        display_btns_layout = QHBoxLayout(display_btns)
        display_btns_layout.setContentsMargins(0, 0, 0, 0)
        display_btns_layout.setSpacing(12)
        display_btns_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        display_btns_layout.addWidget(self._edit_btn)
        display_btns_layout.addWidget(self._back_btn)

        edit_btns = QWidget()
        edit_btns.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        edit_btns.setStyleSheet("background: transparent;")
        edit_btns_layout = QHBoxLayout(edit_btns)
        edit_btns_layout.setContentsMargins(0, 0, 0, 0)
        edit_btns_layout.setSpacing(12)
        edit_btns_layout.addWidget(self._save_btn)
        edit_btns_layout.addWidget(self._cancel_btn)

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

        btn_row = max(len(_MASTER_SETUP_COL1), len(_MASTER_SETUP_COL2))
        grid.addWidget(self._error_label, btn_row, 0, 1, 2)
        grid.addWidget(
            self._btn_stack,
            btn_row + 1,
            0,
            1,
            2,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        grid.setRowMinimumHeight(btn_row + 1, 52)

        card_layout.addLayout(grid)
        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        self._switch_to_view_mode()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._record or self.is_edit_mode():
            return
        cid = _resolve_master_key_value_category_id(self._record)
        self._load_category_options(selected_category_id=cid)

    def set_record(self, record: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._record = dict(record) if record else {}
        selected_cid = _resolve_master_key_value_category_id(self._record)
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
            pipe = _category_id_pipe_name_display(self._record)
            combo.addItem(pipe if pipe else f"{sid} |", sid)
            self._allowed_category_ids.add(sid)
        _set_category_combo_current_by_id(combo, sid)
        _apply_get_all_category_label_to_combo(combo, self._record)
        combo.blockSignals(False)

    def _refresh_values(self) -> None:
        for _label_text, keys in _MASTER_SETUP_FIELD_GROUPS:
            canonical = keys[0]
            value = _get_value(self._record, keys)
            text = _format_value(value, keys[0], keys)
            edit = self._field_edits.get(canonical)
            if edit:
                if isinstance(edit, QComboBox) and canonical == "category":
                    cid = _resolve_master_key_value_category_id(self._record)
                    pipe_display = _category_id_pipe_name_display(self._record)
                    text = pipe_display or text
                    if cid is not None:
                        _set_category_combo_current_by_id(edit, cid)
                        if edit.currentIndex() >= 0:
                            _apply_get_all_category_label_to_combo(edit, self._record)
                            continue
                    if text and edit.findText(text) < 0:
                        role_id = cid if cid is not None else _parse_category_id_from_label_text(text)
                        edit.addItem(text, role_id)
                    if text:
                        edit.setCurrentText(text)
                elif isinstance(edit, QComboBox):
                    if edit.findText(text) < 0 and text:
                        edit.addItem(text)
                    edit.setCurrentText(text)
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
        for _label_text, keys in _MASTER_SETUP_FIELD_GROUPS:
            canonical = keys[0]
            if canonical not in self._editable_keys:
                continue
            if canonical == "category":
                edit = self._field_edits.get("category")
                if isinstance(edit, QComboBox):
                    orig_id = _resolve_master_key_value_category_id(self._record)
                    cur = category_id_from_master_setup_category_combo(edit)
                    try:
                        if orig_id is not None and cur is not None and int(orig_id) == int(cur):
                            continue
                    except (TypeError, ValueError):
                        pass
                orig_str = _category_id_pipe_name_display(self._record)
                current = self._get_edit_value(canonical)
                if orig_str.strip() != (current or "").strip():
                    return True
                continue
            original = _get_value(self._record, keys)
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

        category_edit = self._field_edits.get("category")
        if not isinstance(category_edit, QComboBox):
            self._show_error("Category is required.")
            return
        # API body uses integer categoryId only (see api_update_master_key_value).
        category_id = category_id_from_master_setup_category_combo(category_edit)
        if category_id is None:
            self._show_error("Category is required.")
            category_edit.setFocus()
            return
        if category_id not in self._allowed_category_ids:
            self._show_error("Category must be selected from the available list.")
            category_edit.setFocus()
            return
        seq_text = self._get_edit_value("seq")
        if not seq_text:
            self._show_error("Seq is required.")
            seq_edit = self._field_edits.get("seq")
            if seq_edit:
                seq_edit.setFocus()
            return
        key_value = self._get_edit_value("keyValue", "key_value")
        if not key_value:
            self._show_error("Key value is required.")
            key_value_edit = self._field_edits.get("keyValue")
            if key_value_edit:
                key_value_edit.setFocus()
            return
        description = self._get_edit_value("description", "desc")

        master_key_id = _get_master_key_id(self._record)
        if master_key_id is None:
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

        result = api_update_master_key_value(
            master_key_id,
            category_id=category_id,
            seq=seq_text,
            key_value=key_value,
            description=description,
            token=token,
        )
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Failed to update master setup entry."))
            return

        self._record["categoryId"] = category_id
        self._record["category_id"] = category_id
        if isinstance(category_edit, QComboBox):
            ct = category_edit.currentText().strip()
            self._record["category"] = ct
            if "|" in ct:
                tail = ct.split("|", 1)[1].strip()
                if tail:
                    self._record["categoryName"] = tail
        self._record["seq"] = seq_text
        self._record["keyValue"] = key_value
        self._record["description"] = description
        self._show_success(str(result.get("message") or "Master setup entry updated successfully."))

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
