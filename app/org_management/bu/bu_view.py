"""View / edit Business Unit — PUT api/bu/update-bu-by-id/{bu_id}."""

from __future__ import annotations

import json
from typing import Any, Callable

from PySide6.QtCore import QStringListModel, Qt
from PySide6.QtWidgets import (
    QCompleter,
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

from app.org_management.bu.bu_utils import (
    get_bu_id,
    get_bu_name,
    get_organization_id_from_bu,
    get_organization_name_from_bu,
    get_parent_bu_id_from_bu,
    get_parent_bu_name_from_bu,
)
from core.api import api_get_all_bu, api_get_all_orgs, api_update_bu
from core.app_preferences import format_datetime_display, is_datetime_field
from ui.blank_display import is_blank_display_value
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
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
    placeholder_search_select,
)
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label, labeled_field_block

_HIDDEN_KEYS = frozenset({"password", "token", "accessToken", "access_token", "jwt"})


def _get_value(bu: dict[str, Any], keys: tuple[str, ...]) -> Any:
    flat = {k: v for k, v in bu.items() if k not in _HIDDEN_KEYS}

    if keys and keys[0] in ("organizationId", "organization_id", "orgId"):
        for key in keys:
            if key in flat:
                v = flat[key]
                if not isinstance(v, dict) and v is not None:
                    return v
        return get_organization_id_from_bu(bu)

    if keys and keys[0] in ("parentBu", "parent_bu", "parentBuId", "parent_bu_id"):
        for key in keys:
            if key in flat:
                v = flat[key]
                if not isinstance(v, dict) and v is not None:
                    return v
        return get_parent_bu_id_from_bu(bu)

    if keys and keys[0] in ("organizationName", "organization_name", "orgName", "org_name"):
        return get_organization_name_from_bu(bu)

    if keys and keys[0] in ("parentBuName", "parent_bu_name", "parentName", "parent_name"):
        return get_parent_bu_name_from_bu(bu)

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


def _get_bu_id(bu: dict[str, Any]) -> int | str | None:
    for k in ("buId", "bu_id", "id"):
        v = bu.get(k)
        if v is not None:
            return v
    return None


_BU_COL1 = (
    ("BU Id", ("buId", "bu_id", "id")),
    ("BU Name*", ("buName", "bu_name")),
    ("Organization Id", ("organizationId", "organization_id", "orgId")),
    ("Organization Name*", ("organizationName", "organization_name", "orgName", "org_name")),
    ("Parent BU Id", ("parentBu", "parent_bu", "parentBuId", "parent_bu_id")),
    ("Parent BU Name", ("parentBuName", "parent_bu_name", "parentName", "parent_name")),
)
_BU_COL2 = (
    ("Created By", ("createdBy", "created_by")),
    ("Created On", ("createdOn", "created_on", "createdAt", "created_at")),
    ("Modified By", ("modifiedBy", "modified_by")),
    ("Modified On", ("modifiedOn", "modified_on", "modifiedAt", "modified_at", "updatedAt", "updated_at")),
)
_BU_FIELD_GROUPS = _BU_COL1 + _BU_COL2

_READONLY_KEYS = frozenset({
    "buId", "bu_id", "id",
    "organizationId", "organization_id", "orgId",
    "parentBu", "parent_bu", "parentBuId", "parent_bu_id",
    "createdBy", "created_by", "createdOn", "created_on", "createdAt", "created_at",
    "modifiedBy", "modified_by", "modifiedOn", "modified_on", "modifiedAt", "modified_at", "updatedAt", "updated_at",
})


class ViewBuPage(QWidget):
    """Display business unit details; editable organizationId, buName, parentBu."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._bu: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit] = {}
        self._editable_keys: list[str] = []
        self._all_bus: list[dict[str, Any]] = []
        self._all_orgs: list[dict[str, Any]] = []
        self._org_completions: list[tuple[str, Any]] = []
        self._parent_bu_completions: list[tuple[str, Any]] = []
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
        title = QLabel("Business Unit Details")
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

            value_edit = QLineEdit()
            value_edit.setFixedHeight(FORM_SINGLELINE_FIELD_HEIGHT_PX)
            value_edit.setMinimumWidth(240)
            value_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            value_edit.setReadOnly(canonical in _READONLY_KEYS)
            value_edit.setStyleSheet(READONLY_INPUT_STYLE if canonical in _READONLY_KEYS else INPUT_STYLE)
            if canonical in ("organizationName", "parentBuName"):
                if canonical == "organizationName":
                    value_edit.setPlaceholderText(
                        placeholder_search_select("Org Id", "Org Name", "Code", "Industry")
                    )
                    value_edit.textChanged.connect(self._on_organization_name_changed)
                else:
                    value_edit.setPlaceholderText(
                        placeholder_search_select("BU Id", "BU Name", "Org Name")
                    )
                    value_edit.textChanged.connect(self._on_parent_name_changed)
                completer = QCompleter(value_edit)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
                completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
                value_edit.setCompleter(completer)
            else:
                value_edit.setText("")

            self._field_edits[canonical] = value_edit
            grid.addWidget(labeled_field_block(label_widget, value_edit), idx, col)

        for idx, (label_text, keys) in enumerate(_BU_COL1):
            add_field(0, idx, label_text, keys)
        for idx, (label_text, keys) in enumerate(_BU_COL2):
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

        btn_row = max(len(_BU_COL1), len(_BU_COL2))
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

    def set_bu(self, bu: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._bu = dict(bu) if bu else {}
        self._load_organization_options()
        self._load_parent_bu_options()
        self._refresh_values()
        if edit_mode and self._bu:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _refresh_values(self) -> None:
        for _label_text, keys in _BU_FIELD_GROUPS:
            canonical = keys[0]
            value = _get_value(self._bu, keys)
            key_used = keys[0]
            text = _format_value(value, keys[0], keys)
            edit = self._field_edits.get(canonical)
            if edit:
                if canonical == "organizationName":
                    self._set_organization_combo_from_value(value)
                elif canonical == "parentBuName":
                    self._set_parent_combo_from_value(value)
                else:
                    edit.setText(text)

    def _load_organization_options(self) -> None:
        org_combo = self._field_edits.get("organizationName")
        if not isinstance(org_combo, QLineEdit):
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_orgs(token=token)
        org_combo.blockSignals(True)
        self._all_orgs = []
        self._org_completions = []
        if result.get("success"):
            data = result.get("data") or []
            self._all_orgs = [o for o in data if isinstance(o, dict)]
            self._all_orgs.sort(key=lambda o: str(get_organization_name_from_bu({"organization": o}) or "").lower())
            for org in self._all_orgs:
                oid = org.get("orgId") or org.get("org_id") or org.get("id")
                if oid is None:
                    continue
                name = str(org.get("orgName") or org.get("org_name") or "").strip()
                code = str(org.get("orgCode") or org.get("org_code") or "").strip()
                industry = str(org.get("industry") or "").strip()
                display = (
                    f"{oid} | {name} | Code: {code} | Industry: {industry}"
                    if (name or code or industry)
                    else f"Organization {oid}"
                )
                self._org_completions.append((display, oid))
        names = [d for d, _ in self._org_completions]
        c = org_combo.completer()
        if c is not None:
            c.setModel(QStringListModel(names))
        org_combo.blockSignals(False)

    def _set_organization_combo_from_value(self, value: Any) -> None:
        org_combo = self._field_edits.get("organizationName")
        if not isinstance(org_combo, QLineEdit):
            return
        target = get_organization_id_from_bu(self._bu)
        if target is None:
            name = get_organization_name_from_bu(self._bu)
            if name:
                org_combo.setText(name)
            else:
                org_combo.clear()
            self._set_id_field("organizationId", None)
            return
        target_str = str(target).strip()
        for disp, oid in self._org_completions:
            if str(oid).strip() == target_str:
                org_combo.setText(disp)
                self._set_id_field("organizationId", oid)
                return
        org_combo.setText(target_str)
        self._set_id_field("organizationId", target)

    def _load_parent_bu_options(self) -> None:
        parent_combo = self._field_edits.get("parentBuName")
        if not isinstance(parent_combo, QLineEdit):
            return
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_bu(token=token)
        parent_combo.blockSignals(True)
        self._all_bus = []
        self._parent_bu_completions = []
        if result.get("success"):
            data = result.get("data") or []
            self._all_bus = [b for b in data if isinstance(b, dict)]
            current_bu_id = _get_bu_id(self._bu)
            self._all_bus = [b for b in self._all_bus if get_bu_id(b) != current_bu_id]
            self._all_bus.sort(key=lambda b: str(get_bu_name(b) or "").lower())
            for bu in self._all_bus:
                bid = get_bu_id(bu)
                if bid is None:
                    continue
                bu_name = get_bu_name(bu) or ""
                org_name = get_organization_name_from_bu(bu) or ""
                display = f"{bid} | {bu_name} | Org: {org_name}"
                self._parent_bu_completions.append((display, bid))
        names = [d for d, _ in self._parent_bu_completions]
        c = parent_combo.completer()
        if c is not None:
            c.setModel(QStringListModel(names))
        parent_combo.blockSignals(False)

    def _set_parent_combo_from_value(self, value: Any) -> None:
        parent_combo = self._field_edits.get("parentBuName")
        if not isinstance(parent_combo, QLineEdit):
            return
        target = get_parent_bu_id_from_bu(self._bu)
        target_name = get_parent_bu_name_from_bu(self._bu)
        if target is None:
            if target_name:
                parent_combo.setText(target_name)
            else:
                parent_combo.clear()
            self._set_id_field("parentBu", None)
            return
        target_str = str(target).strip()
        for disp, bid in self._parent_bu_completions:
            if str(bid).strip() == target_str:
                parent_combo.setText(disp)
                self._set_id_field("parentBu", bid)
                return
        parent_combo.setText(target_str)
        self._set_id_field("parentBu", target)

    def _set_id_field(self, key: str, value: Any) -> None:
        edit = self._field_edits.get(key)
        if isinstance(edit, QLineEdit):
            if value is None and key in ("organizationId", "parentBu"):
                edit.clear()
            else:
                edit.setText("" if value is None else str(value))

    def _on_organization_name_changed(self, _text: str) -> None:
        edit = self._field_edits.get("organizationName")
        if not isinstance(edit, QLineEdit):
            return
        text = edit.text().strip()
        if not text:
            self._set_id_field("organizationId", None)
            return
        for disp, oid in self._org_completions:
            if disp == text:
                self._set_id_field("organizationId", oid)
                return
        self._set_id_field("organizationId", None)

    def _on_parent_name_changed(self, _text: str) -> None:
        edit = self._field_edits.get("parentBuName")
        if not isinstance(edit, QLineEdit):
            return
        text = edit.text().strip()
        if not text:
            self._set_id_field("parentBu", None)
            return
        for disp, bid in self._parent_bu_completions:
            if disp == text:
                self._set_id_field("parentBu", bid)
                return
        self._set_id_field("parentBu", None)

    def _is_valid_org_selection(self) -> bool:
        edit = self._field_edits.get("organizationName")
        if not isinstance(edit, QLineEdit):
            return False
        text = edit.text().strip()
        if not text:
            return False
        return text in {disp for disp, _ in self._org_completions}

    def _is_valid_parent_bu_selection(self) -> bool:
        edit = self._field_edits.get("parentBuName")
        if not isinstance(edit, QLineEdit):
            return False
        text = edit.text().strip()
        return text in {disp for disp, _ in self._parent_bu_completions}

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
                return edit.text().strip()
        return ""

    def _resolve_parent_bu_id_from_ui(self) -> int | None:
        edit = self._field_edits.get("parentBuName")
        if not isinstance(edit, QLineEdit):
            return None
        text = edit.text().strip()
        if not text:
            return None
        for disp, bid in self._parent_bu_completions:
            if disp == text:
                try:
                    return int(bid)
                except (TypeError, ValueError):
                    return None
        return None

    def _resolve_organization_id_from_ui(self) -> int | None:
        edit = self._field_edits.get("organizationName")
        if not isinstance(edit, QLineEdit):
            return None
        text = edit.text().strip()
        if not text:
            return None
        for disp, oid in self._org_completions:
            if disp == text:
                try:
                    return int(oid)
                except (TypeError, ValueError):
                    return None
        return None

    def _handle_edit(self) -> None:
        self._clear_error()
        for key in self._editable_keys:
            edit = self._field_edits.get(key)
            if edit:
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

    def _original_display_for_editable(self, canonical: str, keys: tuple[str, ...]) -> str:
        original = _get_value(self._bu, keys)
        if original is None:
            return ""
        return str(original).strip()

    def _has_unsaved_changes(self) -> bool:
        for _label_text, keys in _BU_FIELD_GROUPS:
            canonical = keys[0]
            if canonical not in self._editable_keys:
                continue
            if canonical == "organizationName":
                original_org = get_organization_id_from_bu(self._bu)
                current_org = self._resolve_organization_id_from_ui()
                if ("" if original_org is None else str(original_org)) != (
                    "" if current_org is None else str(current_org)
                ):
                    return True
                continue
            if canonical == "parentBuName":
                original_parent = get_parent_bu_id_from_bu(self._bu)
                current_parent = self._resolve_parent_bu_id_from_ui()
                if ("" if original_parent is None else str(original_parent)) != (
                    "" if current_parent is None else str(current_parent)
                ):
                    return True
                continue
            orig_str = self._original_display_for_editable(canonical, keys)
            current = self._get_edit_value(canonical)
            if orig_str != (current or "").strip():
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
        bu_name = self._get_edit_value("buName", "bu_name")

        if not bu_name:
            self._show_error("Business unit name is required.")
            return

        org_text = self._get_edit_value("organizationName", "organization_name", "orgName", "org_name")
        if not org_text:
            self._show_error("Please select an organization from Organization field.")
            return
        if not self._is_valid_org_selection():
            self._show_error(strict_list_selection_message("an organization"))
            return
        organization_id = self._resolve_organization_id_from_ui()
        if organization_id is None:
            self._show_error("Please select an organization from Organization field.")
            return
        if organization_id is None or str(organization_id).strip() == "":
            self._show_error("Organization Id is invalid.")
            return

        parent_text = self._get_edit_value("parentBuName", "parent_bu_name", "parentName", "parent_name")
        if parent_text and not self._is_valid_parent_bu_selection():
            self._show_error(strict_list_selection_message("a parent BU"))
            return
        parent_bu = self._resolve_parent_bu_id_from_ui()

        bu_id = _get_bu_id(self._bu)
        if bu_id is None:
            self._show_error("BU Id is missing.")
            return

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_update_bu(
            bu_id,
            organization_id=organization_id,
            bu_name=bu_name,
            parent_bu=parent_bu,
            token=token,
        )

        if not result.get("success"):
            self._show_error(result.get("message", "Failed to update business unit."))
            return

        self._bu["organizationId"] = organization_id
        org_name = self._get_edit_value("organizationName", "organization_name", "orgName", "org_name")
        if org_name.strip():
            self._bu["organizationName"] = org_name
        self._bu["buName"] = bu_name
        if parent_bu is not None:
            self._bu["parentBu"] = parent_bu
            parent_name = self._get_edit_value("parentBuName", "parent_bu_name", "parentName", "parent_name")
            if parent_name.strip():
                self._bu["parentBuName"] = parent_name
        else:
            self._bu.pop("parentBu", None)
            self._bu.pop("parentBuName", None)
        org = self._bu.get("organization")
        if isinstance(org, dict):
            org["orgId"] = organization_id
        self._show_success(result.get("message", "Business unit updated successfully."))

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
                edit.setReadOnly(True)
                edit.setStyleSheet(READONLY_INPUT_STYLE)
        self._btn_stack.setCurrentIndex(0)

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1
