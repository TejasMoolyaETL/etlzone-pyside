"""Create Business Unit — POST api/bu/create-bu."""

from __future__ import annotations

import re
from typing import Any, Callable

from PySide6.QtCore import QEvent, QStringListModel, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.org_management.bu.bu_utils import (
    get_bu_id,
    get_bu_name,
    get_organization_name_from_bu,
)
from core.api import (
    api_create_bu,
    api_get_all_bu,
    api_get_all_orgs,
    api_get_master_key_by_app_id_field_name,
    master_key_row_display_label,
    master_key_row_seq_value,
)
from core.user_context import get_user_profile
from ui.auto_hide_message import (
    cancel_auto_hide_message,
    show_api_result_message,
    show_auto_hiding_message,
)
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
    placeholder_auto_filled,
    placeholder_enter,
    placeholder_example,
    placeholder_search_select,
)
from ui.post_save_navigation import schedule_after_success
from ui.strict_completer import strict_list_selection_message
from ui.widgets.required_label import field_caption_label, labeled_field_block

# Master setup field for BU status (GET …/get-by-field-name?fieldName=bu_status).
_BU_STATUS_FIELD_NAME = "bu_status"


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


class CreateBuPage(QWidget):
    """Form: organization id/name + buName + optional parent BU."""

    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._bus: list[dict[str, Any]] = []
        self._org_completions: list[tuple[str, int | str]] = []
        self._parent_bu_completions: list[tuple[str, int | str]] = []
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
        title = QLabel("Create Business Unit")
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
        card.setMaximumWidth(520)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; "
            "border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        label_name = field_caption_label("Business Unit Name*", LABEL_STYLE)
        self.bu_name_edit = QLineEdit()
        self.bu_name_edit.setPlaceholderText(
            f"{placeholder_enter('BU name')} ({placeholder_example('HR')})"
        )
        self.bu_name_edit.setStyleSheet(INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_name, self.bu_name_edit))

        label_org_id = QLabel("Organization Id:")
        label_org_id.setStyleSheet(LABEL_STYLE)
        self.org_id_edit = QLineEdit()
        self.org_id_edit.setReadOnly(True)
        self.org_id_edit.setPlaceholderText(placeholder_auto_filled("Organization Name"))
        self.org_id_edit.setStyleSheet(READONLY_INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_org_id, self.org_id_edit))

        label_org_name = field_caption_label("Organization*", LABEL_STYLE)
        self.org_name_edit = QLineEdit()
        self.org_name_edit.setPlaceholderText(placeholder_search_select("orgID", "orgName"))
        self.org_name_edit.setStyleSheet(INPUT_STYLE)
        self.org_name_edit.installEventFilter(self)
        self.org_name_edit.textChanged.connect(self._on_org_name_text_changed)
        card_layout.addWidget(labeled_field_block(label_org_name, self.org_name_edit))

        label_parent_id = QLabel("Parent BU Id:")
        label_parent_id.setStyleSheet(LABEL_STYLE)
        self.parent_bu_id_edit = QLineEdit()
        self.parent_bu_id_edit.setReadOnly(True)
        self.parent_bu_id_edit.setPlaceholderText(placeholder_auto_filled("Parent BU Name"))
        self.parent_bu_id_edit.setStyleSheet(READONLY_INPUT_STYLE)
        card_layout.addWidget(labeled_field_block(label_parent_id, self.parent_bu_id_edit))

        label_parent = QLabel("Parent BU:")
        label_parent.setStyleSheet(LABEL_STYLE)
        self.parent_bu_edit = QLineEdit()
        self.parent_bu_edit.setPlaceholderText(placeholder_search_select("BU Id", "BU Name", "Org Name"))
        self.parent_bu_edit.setStyleSheet(INPUT_STYLE)
        self.parent_bu_edit.installEventFilter(self)
        self.parent_bu_edit.textChanged.connect(self._on_parent_bu_text_changed)
        parent_completer = QCompleter(self.parent_bu_edit)
        parent_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        parent_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        parent_completer.setMaxVisibleItems(10)
        self.parent_bu_edit.setCompleter(parent_completer)
        card_layout.addWidget(labeled_field_block(label_parent, self.parent_bu_edit))

        label_status = field_caption_label("Status*", LABEL_STYLE)
        self.status_combo = QComboBox()
        apply_form_combobox_field(self.status_combo, height_px=FORM_SINGLELINE_FIELD_HEIGHT_PX)
        card_layout.addWidget(labeled_field_block(label_status, self.status_combo))

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
        btn_layout.addWidget(create_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self._handle_back)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addStretch()
        card_layout.addLayout(btn_layout)

        content_layout.addWidget(card)
        content_layout.addStretch()
        layout.addWidget(content)

    def _setup_organization_completer(self) -> None:
        """Load organizations and setup searchable completer."""
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_orgs(token=token)
        self._org_completions = []
        orgs = result.get("data", []) if result.get("success") else []
        for org in orgs:
            if not isinstance(org, dict):
                continue
            oid = org.get("orgID") or org.get("orgId") or org.get("org_id") or org.get("id")
            if oid is None or str(oid).strip() == "":
                continue
            org_name = str(org.get("orgName") or org.get("org_name") or "").strip()
            display = f"{oid} | {org_name}" if org_name else f"{oid} |"
            self._org_completions.append((display, oid))

        completer = QCompleter([d for d, _ in self._org_completions])
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(10)

        def on_activated(text: str) -> None:
            for disp, oid in self._org_completions:
                if disp == text:
                    self.org_id_edit.setText(str(oid))
                    self.org_name_edit.setText(disp)
                    break

        completer.activated.connect(on_activated)
        self.org_name_edit.setCompleter(completer)

    def _load_parent_bus(self) -> None:
        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None
        result = api_get_all_bu(token=token)

        self._bus = []
        self._parent_bu_completions = []

        if result.get("success"):
            data = result.get("data") or []
            self._bus = [b for b in data if isinstance(b, dict)]
            self._bus.sort(key=lambda b: (get_bu_name(b) or "").lower())
            for bu in self._bus:
                bu_id = get_bu_id(bu)
                if bu_id is None:
                    continue
                bu_name = get_bu_name(bu) or ""
                org_name = get_organization_name_from_bu(bu) or ""
                display = f"{bu_id} | {bu_name} | Org: {org_name}"
                self._parent_bu_completions.append((display, bu_id))

        completer = QCompleter([d for d, _ in self._parent_bu_completions])
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setMaxVisibleItems(10)

        def on_activated(text: str) -> None:
            self.parent_bu_edit.setText(text)
            for disp, bid in self._parent_bu_completions:
                if disp == text:
                    self.parent_bu_id_edit.setText(str(bid))
                    break

        completer.activated.connect(on_activated)
        self.parent_bu_edit.setCompleter(completer)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._setup_organization_completer()
        self._load_parent_bus()
        self._populate_master_key_seq_combo(
            self.status_combo,
            _BU_STATUS_FIELD_NAME,
            "Select status…",
        )

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

    def eventFilter(self, obj, event) -> bool:
        if obj == self.org_name_edit and event.type() == QEvent.Type.FocusIn:
            self._setup_organization_completer()
        parent_edit = getattr(self, "parent_bu_edit", None)
        if parent_edit is not None and obj == parent_edit and event.type() == QEvent.Type.FocusIn:
            self._load_parent_bus()
        return super().eventFilter(obj, event)

    def _on_org_name_text_changed(self, text: str) -> None:
        if not text.strip():
            self.org_id_edit.clear()

    def _on_parent_bu_text_changed(self, text: str) -> None:
        if not text.strip():
            self.parent_bu_id_edit.clear()
            return
        for disp, bid in self._parent_bu_completions:
            if disp == text:
                self.parent_bu_id_edit.setText(str(bid))
                return
        self.parent_bu_id_edit.clear()

    def _parse_org_id(self, text: str) -> str:
        # Kept only for backward compatibility with old display values.
        text = text.strip()
        if not text:
            return ""
        match = re.search(r"\(ID:\s*([^)]+)\)", text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return self.org_id_edit.text().strip()

    def _is_valid_org_selection(self) -> bool:
        text = self.org_name_edit.text().strip()
        if not text:
            return False
        return text in {disp for disp, _ in self._org_completions}

    def _is_valid_parent_bu_selection(self) -> bool:
        text = self.parent_bu_edit.text().strip()
        return text in {disp for disp, _ in self._parent_bu_completions}

    def _resolve_parent_bu_id(self) -> int | None:
        text = self.parent_bu_edit.text().strip()
        if not text:
            return None
        for disp, bid in self._parent_bu_completions:
            if disp == text:
                try:
                    return int(bid)
                except (TypeError, ValueError):
                    return None
        return None

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self.error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)

    def is_dirty(self) -> bool:
        if self.org_id_edit.text().strip():
            return True
        if self.org_name_edit.text().strip():
            return True
        if self.bu_name_edit.text().strip():
            return True
        if self.parent_bu_id_edit.text().strip():
            return True
        if self.parent_bu_edit.text().strip():
            return True
        if self.status_combo.currentIndex() > 0:
            return True
        return False

    def reset_to_default(self) -> None:
        self.org_id_edit.clear()
        self.org_name_edit.clear()
        self.bu_name_edit.clear()
        self.parent_bu_id_edit.clear()
        self.parent_bu_edit.clear()
        self.status_combo.setCurrentIndex(0)

    def _handle_back(self) -> None:
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

    def _handle_create(self) -> None:
        self._clear_error()
        org_name_text = self.org_name_edit.text().strip()
        if not org_name_text:
            self._show_error("Please select an organization from Organization field.")
            return
        if not self._is_valid_org_selection():
            self._show_error(strict_list_selection_message("an organization"))
            return
        organization_id_raw = self.org_id_edit.text().strip() or self._parse_org_id(org_name_text)
        if not organization_id_raw:
            self._show_error("Please select an organization from Organization field.")
            return

        bu_name = self.bu_name_edit.text().strip()
        if not bu_name:
            self._show_error("Business unit name is required.")
            return

        try:
            organization_id = int(organization_id_raw)
        except ValueError:
            organization_id = organization_id_raw
        if organization_id is None or str(organization_id).strip() == "":
            self._show_error("Organization Id is invalid.")
            return

        if self.parent_bu_edit.text().strip():
            if not self._is_valid_parent_bu_selection():
                self._show_error(strict_list_selection_message("a parent BU"))
                return
        parent_bu = self._resolve_parent_bu_id()

        if self.status_combo.currentIndex() <= 0:
            self._show_error("Status is required.")
            self.status_combo.setFocus()
            return
        status_raw = self.status_combo.currentData()
        if status_raw is None:
            self._show_error("Status is required.")
            self.status_combo.setFocus()
            return
        try:
            status_val = _coerce_master_seq_to_int(status_raw)
        except ValueError:
            self._show_error("Status must be a valid selection.")
            self.status_combo.setFocus()
            return

        profile = get_user_profile()
        token = (
            profile.get("token")
            or profile.get("accessToken")
            or profile.get("access_token")
            or profile.get("jwt")
        )
        token = str(token) if token else None

        result = api_create_bu(
            organization_id=organization_id,
            bu_name=bu_name,
            parent_bu=parent_bu,
            status=status_val,
            token=token,
        )

        ok = show_api_result_message(
            self,
            self.error_label,
            result,
            error_fallback="Failed to create business unit.",
            success_fallback="Business unit created successfully.",
        )
        if ok:

            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )
