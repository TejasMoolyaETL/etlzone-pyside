"""View / edit Position — PUT api/positions/update-position-by-id/{position_id}."""

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
    api_get_master_key_by_app_id_field_name,
    api_update_position,
    master_key_row_display_label,
    master_key_row_seq_value,
)
from core.app_preferences import format_datetime_display, is_datetime_field
from ui.blank_display import is_blank_display_value
from core.user_context import get_user_profile
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
    placeholder_example,
)
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success
from ui.widgets.required_label import field_caption_label, labeled_field_block

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})

_POSITION_STATUS_FIELD_NAME = "position_status"


def _coerce_master_seq_to_int(seq_val: Any) -> int:
    """Send master-key seq as integer in JSON payload."""
    if isinstance(seq_val, bool):
        return int(seq_val)
    if isinstance(seq_val, int):
        return seq_val
    if isinstance(seq_val, float) and seq_val == int(seq_val):
        return int(seq_val)
    s = str(seq_val).strip()
    if s.isdigit():
        return int(s)
    raise ValueError(f"Not a whole number: {seq_val!r}")


def _position_status_nested(pos: dict[str, Any]) -> dict[str, Any] | None:
    flat = {k: v for k, v in pos.items() if k not in _HIDDEN_KEYS}
    nested = flat.get("status") or flat.get("positionStatus") or flat.get("position_status")
    return nested if isinstance(nested, dict) else None


def _position_status_seq(pos: dict[str, Any]) -> Any | None:
    nested = _position_status_nested(pos)
    if nested is not None:
        return master_key_row_seq_value(nested)
    flat = {k: v for k, v in pos.items() if k not in _HIDDEN_KEYS}
    for k in ("status", "statusSeq", "status_seq"):
        v = flat.get(k)
        if v is not None and not isinstance(v, dict) and str(v).strip() != "":
            return v
    return None


def _combo_status_key_value(combo: QComboBox) -> str:
    if combo.currentIndex() <= 0 or combo.itemData(combo.currentIndex()) is None:
        return ""
    t = combo.currentText().strip()
    if " | " in t:
        return t.split(" | ", 1)[-1].strip().upper()
    return t.upper()


def _get_position_id(pos: dict[str, Any]) -> int | str | None:
    """Prefer API ``positionId`` (and common aliases); only then generic ``id``."""
    for k in ("positionId", "position_id", "positionID", "PositionId", "PositionID"):
        if k in pos:
            return pos.get(k)
    nested = pos.get("position")
    if isinstance(nested, dict):
        for k in ("positionId", "position_id", "positionID", "PositionId", "PositionID", "id"):
            if k in nested:
                return nested.get(k)
    if "id" in pos:
        return pos.get("id")
    return None


def _get_value(pos: dict[str, Any], keys: tuple[str, ...]) -> Any:
    flat = {k: v for k, v in pos.items() if k not in _HIDDEN_KEYS}
    if keys and keys[0] in (
        "positionId",
        "position_id",
        "positionID",
        "PositionId",
        "PositionID",
        "id",
    ):
        return _get_position_id(pos)
    if keys and "status" in keys:
        flat = {k: v for k, v in pos.items() if k not in _HIDDEN_KEYS}
        nested = flat.get("status") or flat.get("positionStatus") or flat.get("position_status")
        if isinstance(nested, dict):
            if nested.get("keyValue") is not None:
                return nested.get("keyValue")
            if nested.get("key_value") is not None:
                return nested.get("key_value")
        for key in ("status", "statusSeq", "status_seq"):
            if key in flat:
                v = flat[key]
                if not isinstance(v, dict) and v is not None:
                    return v
        return None
    for key in keys:
        if key in flat:
            return flat[key]
    return None


def _format_value(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    # is_datetime_field() matches substring "on" — "positionId" is wrongly treated as a date field.
    if key == "positionId":
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, (dict, list)):
            return json.dumps(value, default=str)
        return str(value)
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return str(value)


_POSITION_COL1 = (
    ("Position Id", ("positionId", "position_id", "positionID", "PositionId", "PositionID", "id")),
    ("Position Name*", ("positionName", "position_name", "name")),
    ("Hierarchy Level*", ("hierarchyLevel", "hierarchy_level", "level")),
    ("Status*", ("status",)),
)
_POSITION_COL2 = (
    ("Created By", ("createdBy", "created_by")),
    ("Created At", ("createdAt", "created_at", "createdOn", "created_on")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified At", ("modifiedAt", "modified_at", "updatedAt", "updated_at", "modifiedOn", "modified_on")),
)
_POSITION_FIELD_GROUPS = _POSITION_COL1 + _POSITION_COL2

_READONLY_KEYS = frozenset({
    "positionId", "position_id", "positionID", "PositionId", "PositionID", "id",
    "createdBy", "created_by", "createdAt", "created_at", "createdOn", "created_on",
    "modifiedBy", "modified_by", "modifiedAt", "modified_at", "updatedAt", "updated_at", "modifiedOn", "modified_on",
})


class ViewPositionPage(QWidget):
    """Display position details; editable name and hierarchy level."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._position: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit | QComboBox] = {}
        self._editable_keys: list[str] = []
        self._hierarchy_values = [str(i) for i in range(1, 31)]
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
        title = QLabel("Position Details")
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

            if canonical in ("hierarchyLevel", "hierarchy_level", "level"):
                # Use hierarchyLevel as single canonical widget key
                wkey = "hierarchyLevel"
                value_edit = QComboBox()
                value_edit.addItems(self._hierarchy_values)
                value_edit.setCurrentText("1")
                apply_form_combobox_field(
                    value_edit, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX, min_width=240
                )
                ro = canonical in _READONLY_KEYS
                value_edit.setEnabled(not ro)
                value_edit.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                self._field_edits[wkey] = value_edit
            elif canonical == "status":
                value_edit = QComboBox()
                apply_form_combobox_field(
                    value_edit, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX, min_width=240
                )
                value_edit.setEnabled(canonical not in _READONLY_KEYS)
                self._field_edits[canonical] = value_edit
            else:
                value_edit = QLineEdit()
                value_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
                value_edit.setMinimumWidth(240)
                value_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                value_edit.setReadOnly(canonical in _READONLY_KEYS)
                value_edit.setStyleSheet(READONLY_INPUT_STYLE if canonical in _READONLY_KEYS else INPUT_STYLE)
                value_edit.setText("")
                if canonical == "positionName":
                    value_edit.setPlaceholderText(placeholder_example("Developer"))
                self._field_edits[canonical] = value_edit

            grid.addWidget(labeled_field_block(label_widget, value_edit), idx, col)

        for idx, (label_text, keys) in enumerate(_POSITION_COL1):
            add_field(0, idx, label_text, keys)
        for idx, (label_text, keys) in enumerate(_POSITION_COL2):
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
        display_btns_layout = QHBoxLayout(display_btns)
        display_btns_layout.setContentsMargins(0, 0, 0, 0)
        display_btns_layout.setSpacing(12)
        display_btns_layout.addWidget(self._edit_btn)
        display_btns_layout.addWidget(self._back_btn)

        edit_btns = QWidget()
        edit_btns_layout = QHBoxLayout(edit_btns)
        edit_btns_layout.setContentsMargins(0, 0, 0, 0)
        edit_btns_layout.setSpacing(12)
        edit_btns_layout.addWidget(self._save_btn)
        edit_btns_layout.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
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

        btn_row = max(len(_POSITION_COL1), len(_POSITION_COL2))
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
        if self.is_edit_mode():
            return
        combo = self._field_edits.get("status")
        if isinstance(combo, QComboBox):
            self._populate_master_key_seq_combo(combo, _POSITION_STATUS_FIELD_NAME, "Select status…")
            self._sync_status_combo_from_position()

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        return str(token) if token else None

    def _populate_master_key_seq_combo(
        self,
        combo: QComboBox | None,
        field_name: str,
        placeholder: str,
    ) -> None:
        if combo is None:
            return
        result = api_get_master_key_by_app_id_field_name(
            field_name=field_name,
            token=self._token(),
        )
        rows = result.get("data") if result.get("success") else []
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(placeholder, None)
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                seq_val = master_key_row_seq_value(row)
                if seq_val is None:
                    continue
                label = master_key_row_display_label(row).strip()
                if not label:
                    continue
                combo.addItem(label, seq_val)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _sync_status_combo_from_position(self) -> None:
        combo = self._field_edits.get("status")
        if not isinstance(combo, QComboBox) or combo.count() == 0:
            return
        seq = _position_status_seq(self._position)
        if seq is not None:
            for i in range(combo.count()):
                data = combo.itemData(i)
                if data is None:
                    continue
                try:
                    if int(data) == int(seq):  # type: ignore[arg-type]
                        combo.setCurrentIndex(i)
                        return
                except (TypeError, ValueError):
                    if str(data).strip() == str(seq).strip():
                        combo.setCurrentIndex(i)
                        return
        kv = _get_value(self._position, ("status",))
        if kv is not None and str(kv).strip():
            kv_up = str(kv).strip().upper()
            for i in range(combo.count()):
                if combo.itemData(i) is None:
                    continue
                label_up = combo.itemText(i).strip().upper()
                if kv_up == label_up or kv_up in label_up or label_up.endswith(kv_up) or f"| {kv_up}" in label_up:
                    combo.setCurrentIndex(i)
                    return
        combo.setCurrentIndex(0)

    def set_position(self, pos: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._position = dict(pos) if pos else {}
        combo = self._field_edits.get("status")
        if isinstance(combo, QComboBox):
            self._populate_master_key_seq_combo(combo, _POSITION_STATUS_FIELD_NAME, "Select status…")
        self._refresh_values()
        if edit_mode and self._position:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _refresh_values(self) -> None:
        for _label_text, keys in _POSITION_FIELD_GROUPS:
            canonical = keys[0]
            if canonical == "status":
                continue
            value = _get_value(self._position, keys)

            if canonical in ("hierarchyLevel", "hierarchy_level", "level"):
                combo = self._field_edits.get("hierarchyLevel")
                if isinstance(combo, QComboBox):
                    lo = int(self._hierarchy_values[0])
                    hi = int(self._hierarchy_values[-1])
                    target = str(lo)
                    if value is not None:
                        try:
                            ivalue = int(float(value))
                            target = str(min(hi, max(lo, ivalue)))
                        except (TypeError, ValueError):
                            target = str(lo)
                    combo.setCurrentText(target)
                continue

            edit = self._field_edits.get(canonical)
            if isinstance(edit, QLineEdit):
                text = _format_value(value, keys[0], keys)
                edit.setText(text)
        self._sync_status_combo_from_position()

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

    def _get_edit_text(self, key: str) -> str:
        w = self._field_edits.get(key)
        if isinstance(w, QComboBox):
            return w.currentText().strip()
        if isinstance(w, QLineEdit):
            return w.text().strip()
        return ""

    def _get_hierarchy_value(self) -> int:
        w = self._field_edits.get("hierarchyLevel")
        if isinstance(w, QComboBox):
            try:
                return int(w.currentText())
            except (TypeError, ValueError):
                return 1
        return 1

    def _handle_edit(self) -> None:
        self._clear_error()
        for key in self._editable_keys:
            if key in ("hierarchyLevel", "hierarchy_level", "level"):
                combo = self._field_edits.get("hierarchyLevel")
                if isinstance(combo, QComboBox):
                    combo.setEnabled(True)
                    combo.setStyleSheet(FORM_COMBOBOX_STYLE)
            elif key == "status":
                combo = self._field_edits.get("status")
                if isinstance(combo, QComboBox):
                    combo.setEnabled(True)
                    combo.setStyleSheet(FORM_COMBOBOX_STYLE)
            else:
                edit = self._field_edits.get(key)
                if isinstance(edit, QLineEdit):
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
        for _label_text, keys in _POSITION_FIELD_GROUPS:
            canonical = keys[0]
            if canonical not in self._editable_keys and canonical not in (
                "hierarchyLevel",
                "hierarchy_level",
                "level",
            ):
                continue
            if canonical in ("hierarchyLevel", "hierarchy_level", "level"):
                orig = _get_value(self._position, ("hierarchyLevel", "hierarchy_level", "level"))
                try:
                    orig_int = int(orig) if orig is not None else 0
                except (TypeError, ValueError):
                    orig_int = 0
                if self._get_hierarchy_value() != orig_int:
                    return True
                continue
            if canonical == "status":
                combo = self._field_edits.get("status")
                if not isinstance(combo, QComboBox):
                    continue
                orig_seq = _position_status_seq(self._position)
                cur_data = combo.currentData()
                if orig_seq is not None and cur_data is not None:
                    try:
                        if int(orig_seq) != int(cur_data):  # type: ignore[arg-type]
                            return True
                    except (TypeError, ValueError):
                        if str(orig_seq).strip() != str(cur_data).strip():
                            return True
                    continue
                orig_kv = str(_get_value(self._position, ("status",)) or "").strip().upper()
                cur_kv = _combo_status_key_value(combo)
                if orig_kv != cur_kv:
                    return True
                continue
            original = _get_value(self._position, keys)
            orig_str = _format_value(original, keys[0], keys)
            current = self._get_edit_text(canonical)
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
        name = self._get_edit_text("positionName")
        if not name.strip():
            self._show_error("Position name is required.")
            return

        pid = _get_position_id(self._position)
        if pid is None:
            self._show_error("Position Id is missing.")
            return

        status_combo = self._field_edits.get("status")
        if isinstance(status_combo, QComboBox):
            if status_combo.currentIndex() <= 0 or status_combo.currentData() is None:
                self._show_error("Status is required.")
                status_combo.setFocus()
                return
            try:
                status_seq = _coerce_master_seq_to_int(status_combo.currentData())
            except ValueError:
                self._show_error("Status must be a valid selection.")
                status_combo.setFocus()
                return
        else:
            status_seq = None

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_update_position(
            pid,
            position_name=name,
            hierarchy_level=self._get_hierarchy_value(),
            status=status_seq,
            token=token,
        )

        if not result.get("success"):
            self._show_error(result.get("message", "Failed to update position."))
            return

        self._position["positionName"] = name
        self._position["hierarchyLevel"] = self._get_hierarchy_value()
        if status_seq is not None:
            kv = (
                _combo_status_key_value(status_combo)
                if isinstance(status_combo, QComboBox)
                else str(status_seq).strip().upper()
            )
            nested_st = _position_status_nested(self._position)
            if isinstance(nested_st, dict) and isinstance(status_combo, QComboBox):
                nested_st = dict(nested_st)
                nested_st["seq"] = status_seq
                if kv:
                    nested_st["keyValue"] = kv
                self._position["status"] = nested_st
            elif isinstance(status_combo, QComboBox) and kv:
                self._position["status"] = {"keyValue": kv, "seq": status_seq}
            else:
                self._position["status"] = kv or str(status_seq)

        self._show_success(result.get("message", "Position updated successfully."))

        schedule_after_success(
            delay_ms=800,
            clear_error=self._clear_error,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )

    def _switch_to_view_mode(self) -> None:
        for key in self._editable_keys:
            if key in ("hierarchyLevel", "hierarchy_level", "level"):
                combo = self._field_edits.get("hierarchyLevel")
                if isinstance(combo, QComboBox):
                    combo.setEnabled(False)
                    combo.setStyleSheet(FORM_COMBOBOX_STYLE)
            elif key == "status":
                combo = self._field_edits.get("status")
                if isinstance(combo, QComboBox):
                    combo.setEnabled(False)
                    combo.setStyleSheet(FORM_COMBOBOX_STYLE)
            else:
                edit = self._field_edits.get(key)
                if isinstance(edit, QLineEdit):
                    edit.setReadOnly(True)
                    edit.setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1
