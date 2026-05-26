"""Create DM: Project page."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.dm.dm_project.dm_project_fields import (
    COMPANY_COMBO_STRICT_PHRASE,
    DM_COMPANY_COMBO_KEYS,
    MASTER_KEY_FIELD_BY_PAYLOAD_KEY,
    _company_rows,
    auth_token,
    prepare_dm_project_api_payload,
    populate_dm_company_combo,
    populate_master_key_combo,
    resolved_combo_id,
)
from app.dm.dm_project.dm_project_form_layout import (
    FORM_FIELD_CAPTIONS,
    MASTER_COMBO_KEYS,
    SCOPE_GATED_OWNERSHIP_KEYS,
    apply_scope_gated_ownership_defaults,
    build_dm_project_form_scroll,
    collect_scope_gated_ownership_masters,
    scope_gated_ownership_seq,
    sync_scope_gated_ownership,
)
from core.api import api_create_dm_project
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps
from ui.auto_hide_message import (
    cancel_auto_hide_message,
    show_api_result_message,
    show_auto_hiding_message,
)
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
)
from ui.post_save_navigation import schedule_after_success
from ui.searchable_form_combo import (
    combo_resolved_master_key_seq,
    master_key_invalid_typed_text,
    master_key_seq_for_payload,
    require_master_key_seq_for_payload,
    reset_searchable_combo,
)
from ui.strict_completer import strict_list_selection_message
from ui.theme import Theme

_STRICT_MASTER_PHRASE: dict[str, str] = {
    "source": "a source",
    "laptopOwnership": "a laptop ownership",
    "accommodationOwnership": "an accommodation ownership",
    "travelExpenseOwnership": "a travel expense ownership",
    "perDiemOwnership": "a per diem ownership",
    "extractionOwnership": "an extraction ownership",
    "transformationOwnership": "a transformation ownership",
    "loadingOwnership": "a loading ownership",
    "deliveryModel": "a delivery model",
    "status": "a status",
    "srcLandscape": "a source landscape",
    "tgtLandscape": "a target landscape",
    "migrationType": "a migration type",
}


class CreateDmProjectPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_create_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_create_success = on_create_success
        self._field_edits: dict[str, Any] = {}
        self._entity_combo_by_key: dict[str, QComboBox] = {}
        self._master_combo_by_key: dict[str, QComboBox] = {}
        self._date_by_key: dict[str, Any] = {}
        self._scope_check_by_key: dict[str, QCheckBox] = {}
        self._start_date_touched = False
        self._go_live_date_touched = False
        self._can_create_project = True
        self._form_scroll = None
        self._build_ui()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._refresh_create_access()
        if self._form_scroll is not None:
            self._form_scroll.sync_body_geometry()
        tk = auth_token()
        company_rows = _company_rows(tk)
        for key in DM_COMPANY_COMBO_KEYS:
            label = FORM_FIELD_CAPTIONS.get(key, key).replace("*", "").strip()
            populate_dm_company_combo(
                self._entity_combo_by_key.get(key),
                search_field_label=label,
                token=tk,
                rows=company_rows,
            )
        for key, combo in self._master_combo_by_key.items():
            field_name = MASTER_KEY_FIELD_BY_PAYLOAD_KEY.get(key)
            if field_name and combo is not None:
                populate_master_key_combo(combo, field_name, token=tk)
        apply_scope_gated_ownership_defaults(
            self._scope_check_by_key, self._master_combo_by_key
        )

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
        hl.addWidget(QLabel("DM: Create Project"))
        hl.addStretch()
        back_btn = QPushButton("Back")
        back_btn.setFixedWidth(100)
        back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        back_btn.clicked.connect(self._handle_back)
        hl.addWidget(back_btn)
        layout.addWidget(header)

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(12)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        card.setMaximumWidth(980)
        card.setStyleSheet(
            f"#profileCard {{ background: {Theme.BG_WHITE}; border: 1px solid {Theme.BORDER_DEFAULT}; "
            "border-radius: 10px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        scroll, form = build_dm_project_form_scroll(include_project_id=False)
        self._form_scroll = scroll
        self._field_edits = form.field_edits
        self._entity_combo_by_key = form.entity_combo_by_key
        self._master_combo_by_key = form.master_combo_by_key
        self._date_by_key = form.date_by_key
        self._scope_check_by_key = form.scope_check_by_key
        self._wire_date_pickers()
        card_layout.addWidget(scroll, 1)

        self.error_label = QLabel()
        self.error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self.error_label.setWordWrap(True)
        self.error_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.error_label.setVisible(False)
        card_layout.addWidget(self.error_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self._create_btn = QPushButton("Create")
        self._create_btn.setFixedWidth(100)
        self._create_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._create_btn.setStyleSheet(
            FORM_PRIMARY_BUTTON_STYLESHEET
            + " QPushButton:disabled {"
            + " background-color: #e5e7eb;"
            + " color: #6b7280;"
            + " border: 1px solid #cbd5e1;"
            + "}"
        )
        self._create_btn.clicked.connect(self._handle_create)
        btn_row.addWidget(self._create_btn)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(100)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(FORM_SECONDARY_BUTTON_STYLESHEET)
        cancel_btn.clicked.connect(self._handle_back)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        card_layout.addLayout(btn_row)

        cl.addWidget(card, 1)
        layout.addWidget(content, 1)

    def _wire_date_pickers(self) -> None:
        start_picker = self._date_by_key.get("startDate")
        go_live_picker = self._date_by_key.get("goLiveDate")
        if start_picker is not None:
            original_open = start_picker._open_picker

            def _open_start(event: object = None) -> None:
                self._start_date_touched = True
                original_open(event)

            start_picker._open_picker = _open_start  # type: ignore[method-assign]
        if go_live_picker is not None:
            original_open = go_live_picker._open_picker

            def _open_go_live(event: object = None) -> None:
                self._go_live_date_touched = True
                original_open(event)

            go_live_picker._open_picker = _open_go_live  # type: ignore[method-assign]

    def _refresh_create_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_create_project = True
        else:
            allowed = collect_allowed_action_names(steps)
            self._can_create_project = nav_action_visible("DM: Project", "create", allowed)
        self._create_btn.setEnabled(self._can_create_project)
        self._create_btn.setToolTip("" if self._can_create_project else "Require Permission.")

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(
            self, self.error_label, message, error=True, clear_on_user_activity=False
        )

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self.error_label)
        self.error_label.setText("")
        self.error_label.setVisible(False)

    def _optional_combo(self, combo: QComboBox | None, label: str) -> Any | None:
        val = resolved_combo_id(combo) if combo is not None else None
        if val is not None and str(val).strip() != "":
            return val
        typed = (combo.currentText() or "").strip() if combo else ""
        if typed:
            self._show_error(strict_list_selection_message(label))
            if combo is not None:
                combo.setFocus()
        return None

    def _required_master(
        self, combo: QComboBox | None, *, field_caption: str, strict_phrase: str
    ) -> int | None:
        seq, err = require_master_key_seq_for_payload(
            combo, field_caption=field_caption, strict_phrase=strict_phrase
        )
        if err:
            self._show_error(err)
            if combo is not None:
                combo.setFocus()
            return None
        return seq

    def _optional_master(self, combo: QComboBox | None, label: str) -> int | None:
        if master_key_invalid_typed_text(combo):
            self._show_error(strict_list_selection_message(label))
            if combo is not None:
                combo.setFocus()
            return None
        return master_key_seq_for_payload(combo)

    def _scope_checked(self, key: str) -> bool:
        check = self._scope_check_by_key.get(key)
        return bool(check.isChecked()) if check is not None else False

    def _report_scope_ownership_error(self, message: str, ownership_key: str | None) -> None:
        self._show_error(message)
        if ownership_key:
            combo = self._master_combo_by_key.get(ownership_key)
            if combo is not None:
                combo.setFocus()

    def _reset_date_picker(self, key: str) -> None:
        from PySide6.QtCore import QDate

        picker = self._date_by_key.get(key)
        if picker is not None:
            picker.setDate(QDate.currentDate())

    def is_dirty(self) -> bool:
        if any(edit.text().strip() for edit in self._field_edits.values()):
            return True
        if self._start_date_touched or self._go_live_date_touched:
            return True
        for combo in self._entity_combo_by_key.values():
            if resolved_combo_id(combo) is not None:
                return True
        for combo in self._master_combo_by_key.values():
            if combo_resolved_master_key_seq(combo) is not None:
                return True
        for check in self._scope_check_by_key.values():
            if check.isChecked():
                return True
        return False

    def reset_to_default(self) -> None:
        for edit in self._field_edits.values():
            edit.clear()
        self._start_date_touched = False
        self._go_live_date_touched = False
        self._reset_date_picker("startDate")
        self._reset_date_picker("goLiveDate")
        for combo in self._entity_combo_by_key.values():
            reset_searchable_combo(combo)
        for combo in self._master_combo_by_key.values():
            reset_searchable_combo(combo)
        for check in self._scope_check_by_key.values():
            check.setChecked(False)
        sync_scope_gated_ownership(
            self._scope_check_by_key,
            self._master_combo_by_key,
            form_enabled=True,
        )
        self._clear_error()

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
        if not self._can_create_project:
            self._show_error("Create disabled: missing step access dm-project-create.")
            return
        self._clear_error()

        name = self._field_edits["projectName"].text().strip()
        if not name:
            self._show_error("Project Name is required.")
            self._field_edits["projectName"].setFocus()
            return

        delivery_combo = self._master_combo_by_key.get("deliveryModel")
        delivery = self._required_master(
            delivery_combo, field_caption="Delivery Model", strict_phrase="a delivery model"
        )
        if delivery is None:
            return

        def _combo_has_typed(key: str) -> bool:
            combo = self._entity_combo_by_key.get(key)
            return bool(combo and (combo.currentText() or "").strip())

        entity_values: dict[str, Any | None] = {}
        for key in DM_COMPANY_COMBO_KEYS:
            combo = self._entity_combo_by_key.get(key)
            phrase = COMPANY_COMBO_STRICT_PHRASE.get(key, f"a {key}")
            val = self._optional_combo(combo, phrase)
            if val is None and _combo_has_typed(key):
                return
            entity_values[key] = val

        scope_ownerships = collect_scope_gated_ownership_masters(
            self._scope_check_by_key,
            self._master_combo_by_key,
            on_error=self._report_scope_ownership_error,
        )
        if scope_ownerships is None:
            return

        optional_masters: dict[str, Any | None] = {}
        for key in MASTER_COMBO_KEYS:
            if key == "deliveryModel" or key in SCOPE_GATED_OWNERSHIP_KEYS:
                continue
            combo = self._master_combo_by_key.get(key)
            val = self._optional_master(combo, _STRICT_MASTER_PHRASE.get(key, f"a {key}"))
            if val is None:
                return
            optional_masters[key] = val
        optional_masters.update(scope_ownerships)

        start_picker = self._date_by_key.get("startDate")
        go_live_picker = self._date_by_key.get("goLiveDate")
        start_date = start_picker.date().isoformat() if start_picker is not None else None
        go_live_date = go_live_picker.date().isoformat() if go_live_picker is not None else None

        try:
            payload = prepare_dm_project_api_payload(
                project_name=name,
                delivery_model=delivery,
                entity_values=entity_values,
                optional_masters=optional_masters,
                start_date=start_date,
                go_live_date=go_live_date,
                region=self._text_value("region"),
                comment_at_etlzone=self._text_value("commentAtEtlzone"),
                extraction_scope=self._scope_checked("extractionScope"),
                transformation_scope=self._scope_checked("transformationScope"),
                load_scope=self._scope_checked("loadScope"),
                extraction_ownership=scope_gated_ownership_seq(
                    scope_checked=self._scope_checked("extractionScope"),
                    resolved_seq=optional_masters.get("extractionOwnership"),
                ),
                transformation_ownership=scope_gated_ownership_seq(
                    scope_checked=self._scope_checked("transformationScope"),
                    resolved_seq=optional_masters.get("transformationOwnership"),
                ),
                loading_ownership=scope_gated_ownership_seq(
                    scope_checked=self._scope_checked("loadScope"),
                    resolved_seq=optional_masters.get("loadingOwnership"),
                ),
            )
        except ValueError as exc:
            self._show_error(str(exc))
            return

        result = api_create_dm_project(payload, token=auth_token())
        ok = show_api_result_message(
            self,
            self.error_label,
            result,
            error_fallback="Failed to create project.",
            success_fallback="Project created successfully.",
        )
        if ok:
            schedule_after_success(
                delay_ms=800,
                clear_error=self._clear_error,
                reset=self.reset_to_default,
                on_back=self.on_back,
                on_success=self.on_create_success,
            )

    def _text_value(self, key: str) -> str | None:
        edit = self._field_edits.get(key)
        if edit is None:
            return None
        text = edit.text().strip()
        return text if text else None
