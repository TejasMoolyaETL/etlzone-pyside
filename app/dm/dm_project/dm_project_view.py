"""View / edit DM: Project page."""

from __future__ import annotations

import ast
import json
from typing import Any, Callable

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.dm.dm_project.dm_project_fields import (
    COMPANY_COMBO_STRICT_PHRASE,
    DM_COMPANY_COMBO_KEYS,
    MASTER_KEY_FIELD_BY_PAYLOAD_KEY,
    _company_rows,
    apply_combo_from_record,
    auth_token,
    bool_from_record,
    COMPANY_COMBO_RECORD_ID_KEYS,
    format_master_display,
    id_from_record,
    prepare_dm_project_api_payload,
    parse_date_ymd,
    populate_dm_company_combo,
    populate_master_key_combo,
    resolved_combo_id,
    seq_from_record,
)
from app.dm.dm_project.dm_project_form_layout import (
    DATE_KEYS,
    ENTITY_COMBO_KEYS,
    FORM_FIELD_CAPTIONS,
    MASTER_COMBO_KEYS,
    PROJECT_RECORD_KEYS,
    READONLY_KEYS,
    SCOPE_BOOL_KEYS,
    SCOPE_GATED_OWNERSHIP_KEYS,
    apply_scope_gated_ownership_defaults,
    build_dm_project_form_scroll,
    collect_scope_gated_ownership_masters,
    scope_gated_ownership_seq,
    sync_scope_gated_ownership,
)
from app.user_management.users.user_create import _DatePickerEdit
from core.api import api_get_dm_project_by_id, api_update_dm_project
from core.app_preferences import (
    format_date_display,
    format_datetime_display,
    is_date_only_field,
    is_datetime_field,
)
from core.nav_access import collect_allowed_action_names, nav_action_visible
from core.user_context import get_nav_access_steps
from ui.auto_hide_message import (
    cancel_auto_hide_message,
    show_api_result_message,
    show_auto_hiding_message,
)
from ui.blank_display import is_blank_display_value
from ui.form_page_styles import (
    FORM_ERROR_LABEL_STYLE,
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_PAGE_HEADER_STYLESHEET,
    FORM_PRIMARY_BUTTON_STYLESHEET,
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    FORM_SECONDARY_BUTTON_STYLESHEET,
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
)
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success
from ui.searchable_form_combo import (
    combo_resolved_master_key_seq,
    master_key_invalid_typed_text,
    master_key_seq_for_payload,
    require_master_key_seq_for_payload,
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


def _project_id(rec: dict[str, Any]) -> Any:
    return id_from_record(rec, "id", "projectId")


def _get_value(rec: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in rec:
            return rec[key]
    return None


def _format_value(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    if is_blank_display_value(value):
        return ""
    if is_date_only_field(key, key_candidates):
        return format_date_display(value)
    if isinstance(value, dict):
        text = format_master_display(value)
        if text:
            return text
    if isinstance(value, str) and (
        key in MASTER_COMBO_KEYS or key in key_candidates
    ):
        s = value.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                parsed = ast.literal_eval(s)
            except (ValueError, SyntaxError):
                try:
                    parsed = json.loads(s)
                except (ValueError, TypeError):
                    parsed = None
            if isinstance(parsed, dict):
                text = format_master_display(parsed)
                if text:
                    return text
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, dict):
        return format_master_display(value)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


class ViewDmProjectPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._project: dict[str, Any] = {}
        self._field_edits: dict[str, QLineEdit] = {}
        self._entity_combo_by_key: dict[str, QComboBox] = {}
        self._master_combo_by_key: dict[str, QComboBox] = {}
        self._date_by_key: dict[str, _DatePickerEdit] = {}
        self._project_id_edit: QLineEdit | None = None
        self._editable_keys: list[str] = []
        self._can_edit_action = True
        self._form_scroll = None
        self._reference_data_loaded = False
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
        hl.addWidget(QLabel("DM: Project Details"))
        hl.addStretch()
        back_hdr = QPushButton("Back")
        back_hdr.setFixedWidth(100)
        back_hdr.setCursor(Qt.CursorShape.PointingHandCursor)
        back_hdr.clicked.connect(self._handle_back)
        hl.addWidget(back_hdr)
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

        scroll, form = build_dm_project_form_scroll(
            include_project_id=True, start_readonly=True
        )
        self._form_scroll = scroll
        self._field_edits = form.field_edits
        self._entity_combo_by_key = form.entity_combo_by_key
        self._master_combo_by_key = form.master_combo_by_key
        self._date_by_key = form.date_by_key
        self._scope_check_by_key = form.scope_check_by_key
        self._project_id_edit = form.project_id_edit
        self._editable_keys = list(form.editable_keys)
        card_layout.addWidget(scroll, 1)

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
        display_btns.setStyleSheet("background: transparent; border: none;")
        db = QHBoxLayout(display_btns)
        db.setContentsMargins(0, 0, 0, 0)
        db.setSpacing(12)
        db.setAlignment(Qt.AlignmentFlag.AlignLeft)
        db.addWidget(self._edit_btn)
        db.addWidget(self._back_btn)

        edit_btns = QWidget()
        edit_btns.setStyleSheet("background: transparent; border: none;")
        eb = QHBoxLayout(edit_btns)
        eb.setContentsMargins(0, 0, 0, 0)
        eb.setSpacing(12)
        eb.setAlignment(Qt.AlignmentFlag.AlignLeft)
        eb.addWidget(self._save_btn)
        eb.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
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

        card_layout.addWidget(self._error_label)
        card_layout.addWidget(self._btn_stack, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        cl.addWidget(card, 1)
        layout.addWidget(content, 1)

        self._switch_to_view_mode()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._form_scroll is not None:
            self._form_scroll.sync_body_geometry()
        if self._project:
            self._populate_reference_combos()
            self._apply_form_from_project()

    def _populate_reference_combos(self, *, force: bool = False) -> None:
        """Load company/master dropdown choices from API on every page show."""
        del force
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
            if field_name:
                populate_master_key_combo(combo, field_name, token=tk)
        self._reference_data_loaded = True

    def _apply_form_from_project(self) -> None:
        self._refresh_values()
        self._apply_combos_from_record()

    def _apply_combos_from_record(self) -> None:
        p = self._project
        for keys in PROJECT_RECORD_KEYS:
            canonical = keys[0]
            if canonical in ENTITY_COMBO_KEYS:
                id_keys = COMPANY_COMBO_RECORD_ID_KEYS.get(canonical, keys)
                apply_combo_from_record(
                    self._entity_combo_by_key.get(canonical),
                    id_from_record(p, *id_keys),
                )
                continue
            if canonical not in MASTER_COMBO_KEYS:
                continue
            apply_combo_from_record(
                self._master_combo_by_key.get(canonical),
                seq_from_record(p, *keys),
            )
        apply_scope_gated_ownership_defaults(
            self._scope_check_by_key, self._master_combo_by_key
        )

    def set_project(self, project: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._project = dict(project) if project else {}
        self._refresh_edit_action_access()
        self._populate_reference_combos()
        self._apply_form_from_project()
        if edit_mode and self._project and self._can_edit_action:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def _refresh_edit_action_access(self) -> None:
        steps = get_nav_access_steps()
        if steps is None:
            self._can_edit_action = True
        else:
            allowed = collect_allowed_action_names(steps)
            self._can_edit_action = nav_action_visible("DM: Project", "edit", allowed)
        self._edit_btn.setEnabled(self._can_edit_action)
        self._edit_btn.setToolTip("" if self._can_edit_action else "Require Permission.")

    def _refresh_values(self) -> None:
        if self._project_id_edit is not None:
            self._project_id_edit.setText(str(_project_id(self._project) or ""))
        for keys in PROJECT_RECORD_KEYS:
            canonical = keys[0]
            if canonical in ENTITY_COMBO_KEYS or canonical in MASTER_COMBO_KEYS:
                continue
            if canonical in DATE_KEYS:
                raw = _get_value(self._project, keys)
                parsed = parse_date_ymd(raw)
                picker = self._date_by_key.get(canonical)
                if picker is not None:
                    if parsed is not None:
                        picker.setDate(QDate(parsed.year, parsed.month, parsed.day))
                    else:
                        picker.setDate(QDate.currentDate())
                continue
            if canonical in SCOPE_BOOL_KEYS:
                check = self._scope_check_by_key.get(canonical)
                if check is not None:
                    check.blockSignals(True)
                    check.setChecked(bool_from_record(self._project, *keys))
                    check.blockSignals(False)
                continue
            value = _get_value(self._project, keys)
            text = _format_value(value, keys[0], keys)
            edit = self._field_edits.get(canonical)
            if edit is not None:
                edit.setText(text)

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(
            self, self._error_label, message, error=True, clear_on_user_activity=False
        )

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _handle_edit(self) -> None:
        if not self._can_edit_action:
            self._show_error("Require Permission.")
            return
        self._clear_error()
        for key in self._editable_keys:
            edit = self._field_edits.get(key)
            if edit is not None:
                edit.setReadOnly(False)
                edit.setStyleSheet(INPUT_STYLE)
        for combo in self._entity_combo_by_key.values():
            combo.setEnabled(True)
        for key, combo in self._master_combo_by_key.items():
            if key in SCOPE_GATED_OWNERSHIP_KEYS:
                continue
            combo.setEnabled(True)
        for picker in self._date_by_key.values():
            picker.setEnabled(True)
        for check in self._scope_check_by_key.values():
            check.setEnabled(True)
        sync_scope_gated_ownership(
            self._scope_check_by_key,
            self._master_combo_by_key,
            form_enabled=True,
        )
        self._btn_stack.setCurrentIndex(1)

    def _handle_cancel(self) -> None:
        if not self._has_unsaved_changes():
            self._clear_error()
            self._apply_form_from_project()
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
            self._apply_form_from_project()
            self._switch_to_view_mode()

    def _switch_to_view_mode(self) -> None:
        for edit in self._field_edits.values():
            edit.setReadOnly(True)
            edit.setStyleSheet(READONLY_INPUT_STYLE)
        for combo in self._entity_combo_by_key.values():
            combo.setEnabled(False)
        for combo in self._master_combo_by_key.values():
            combo.setEnabled(False)
        for picker in self._date_by_key.values():
            picker.setEnabled(False)
        for check in self._scope_check_by_key.values():
            check.setEnabled(False)
        sync_scope_gated_ownership(
            self._scope_check_by_key,
            self._master_combo_by_key,
            form_enabled=False,
        )
        self._btn_stack.setCurrentIndex(0)

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1

    def _scalar_from_record(self, keys: tuple[str, ...]) -> str:
        for key in keys:
            v = self._project.get(key)
            if v is None:
                continue
            if isinstance(v, dict):
                return format_master_display(v).strip()
            return str(v).strip()
        return ""

    def _entity_id_from_record(self, keys: tuple[str, ...]) -> Any:
        return id_from_record(self._project, *keys)

    def _master_seq_from_record(self, keys: tuple[str, ...]) -> Any:
        return seq_from_record(self._project, *keys)

    def _has_unsaved_changes(self) -> bool:
        for keys in PROJECT_RECORD_KEYS:
            canonical = keys[0]
            if canonical in READONLY_KEYS:
                continue
            if canonical in ENTITY_COMBO_KEYS:
                combo = self._entity_combo_by_key.get(canonical)
                cur = resolved_combo_id(combo) if combo is not None else None
                prev = self._entity_id_from_record(keys)
                if str(cur) != str(prev) if (cur is not None or prev is not None) else False:
                    return True
                continue
            if canonical in MASTER_COMBO_KEYS:
                combo = self._master_combo_by_key.get(canonical)
                cur = combo_resolved_master_key_seq(combo) if combo is not None else None
                prev = self._master_seq_from_record(keys)
                if str(cur) != str(prev) if (cur is not None or prev is not None) else False:
                    return True
                continue
            if canonical in DATE_KEYS:
                picker = self._date_by_key.get(canonical)
                if picker is None:
                    continue
                orig = parse_date_ymd(_get_value(self._project, keys))
                cur = picker.date()
                if orig is None and cur is not None:
                    return True
                if orig is not None and cur != orig:
                    return True
                continue
            if canonical in SCOPE_BOOL_KEYS:
                check = self._scope_check_by_key.get(canonical)
                if check is None:
                    continue
                if check.isChecked() != bool_from_record(self._project, *keys):
                    return True
                continue
            edit = self._field_edits.get(canonical)
            current = edit.text().strip() if edit is not None else ""
            original = self._scalar_from_record(keys)
            if current != original:
                return True
        return False

    def _text_field_value(self, key: str) -> str | None:
        edit = self._field_edits.get(key)
        if edit is None:
            return None
        text = edit.text().strip()
        return text if text else None

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

    def _handle_save(self) -> None:
        if not self._has_unsaved_changes():
            navigate_after_no_changes(
                show_non_error_message=self._show_success,
                clear_message=self._clear_error,
                on_back=self.on_back,
            )
            return

        pid = _project_id(self._project)
        if pid is None:
            self._show_error("Project is missing.")
            return

        name_edit = self._field_edits.get("projectName")
        name = name_edit.text().strip() if name_edit is not None else ""
        if not name:
            self._show_error("Project Name is required.")
            if name_edit is not None:
                name_edit.setFocus()
            return

        delivery_combo = self._master_combo_by_key.get("deliveryModel")
        delivery = self._required_master(
            delivery_combo, field_caption="Delivery Model", strict_phrase="a delivery model"
        )
        if delivery is None:
            return

        entity_values: dict[str, Any | None] = {}
        for key in DM_COMPANY_COMBO_KEYS:
            combo = self._entity_combo_by_key.get(key)
            phrase = COMPANY_COMBO_STRICT_PHRASE.get(key, f"a {key}")
            val = self._optional_combo(combo, phrase)
            if val is None and combo and (combo.currentText() or "").strip():
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

        try:
            payload = prepare_dm_project_api_payload(
                project_name=name,
                delivery_model=delivery,
                entity_values=entity_values,
                optional_masters=optional_masters,
                start_date=start_picker.date().isoformat() if start_picker else None,
                go_live_date=go_live_picker.date().isoformat() if go_live_picker else None,
                region=self._text_field_value("region"),
                comment_at_etlzone=self._text_field_value("commentAtEtlzone"),
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

        result = api_update_dm_project(pid, payload, token=auth_token())
        ok = show_api_result_message(
            self,
            self._error_label,
            result,
            error_fallback="Failed to update project.",
            success_fallback="Project updated successfully.",
        )
        if not ok:
            return

        detail = api_get_dm_project_by_id(pid, token=auth_token())
        if detail.get("success") and isinstance(detail.get("data"), dict):
            self._project = detail["data"]
        else:
            data = result.get("data")
            if isinstance(data, dict):
                self._project.update(data)
            else:
                self._project.update(payload)
        self._apply_form_from_project()
        self._switch_to_view_mode()
        schedule_after_success(
            delay_ms=600,
            clear_error=self._clear_error,
            reset=lambda: None,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )
