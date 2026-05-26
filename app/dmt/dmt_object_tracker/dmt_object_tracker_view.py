"""View/edit Object List Tracker record."""

from __future__ import annotations

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
    api_get_all_modules,
    api_get_all_objects,
    api_update_object_tracker,
    master_key_row_seq_value,
)
from core.app_preferences import to_utc_iso
from app.dmt.dmt_object_tracker.dmt_object_tracker_create import _DateTimePickerField
from core.user_context import get_user_profile
from ui.auto_hide_message import cancel_auto_hide_message, show_auto_hiding_message
from ui.form_combobox_style import apply_form_combobox_field
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
    MODAL_FIELD_HEIGHT_PX,
    placeholder_example,
)
from ui.post_save_navigation import navigate_after_no_changes, schedule_after_success
from ui.strict_completer import strict_list_selection_message
from ui.searchable_form_combo import (
    combo_resolved_master_key_seq,
    master_key_invalid_typed_text,
    master_key_seq_for_payload,
    require_master_key_seq_for_payload,
    populate_master_key_by_field_name,
    reset_searchable_combo,
    set_searchable_combo_by_user_data,
    wire_searchable_master_key_combo,
)
from ui.widgets.required_label import field_caption_label, labeled_field_block

_TRACKER_ID_KEYS = ("objectTrackerId", "trackerId", "id")

_FIELD_STATUS = "dmt_object_list_tracker_status"
_FIELD_BUSINESS_OBJECT_TYPE = "dmt_business_object_type"
_FIELD_SCOPE = "dmt_scope"
_FIELD_LOAD_APPROACH = "dmt_load_approach"
_FIELD_UPLOAD_TOOL = "dmt_upload_tool"
_FIELD_CUSTOMIZATION_STATUS = "dmt_customization_status"
_FIELD_BUILD_STATUS = "dmt_buildStatus"
_FIELD_FUNCTIONAL_UNIT_TESTING_STATUS = "dmt_functionalUnitTestingStatus"
_FIELD_BUSINESS_UNIT_TESTING_STATUS = "dmt_businessUnitTestingStatus"


def _seq_from_record(rec: dict[str, Any], *keys: str) -> Any | None:
    for key in keys:
        v = rec.get(key)
        if v is None:
            continue
        if isinstance(v, dict):
            seq = master_key_row_seq_value(v)
            if seq is not None:
                return seq
            continue
        if isinstance(v, bool):
            continue
        if isinstance(v, int):
            return v
        if isinstance(v, float) and v == int(v):
            return int(v)
        s = str(v).strip()
        if s.isdigit():
            return int(s)
    return None


def _ids_equal(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return False
    sa, sb = str(a).strip(), str(b).strip()
    if sa == sb:
        return True
    try:
        return int(sa) == int(sb)
    except ValueError:
        return False


class ViewDmtObjectTrackerPage(QWidget):
    def __init__(
        self,
        on_back: Callable[[], None] | None = None,
        on_update_success: Callable[[], None] | None = None,
    ) -> None:
        super().__init__()
        self.on_back = on_back
        self.on_update_success = on_update_success
        self._record: dict[str, Any] = {}
        self._all_object_rows: list[dict[str, Any]] = []
        self._loading_refs = False
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
        title = QLabel("Object List Tracker Details")
        header_layout.addWidget(title)
        header_layout.addStretch()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedWidth(100)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self._load_reference_data)
        header_layout.addWidget(self._refresh_btn)
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        scroll_content = QWidget()
        content_layout = QVBoxLayout(scroll_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        card = QWidget()
        card.setObjectName("profileCard")
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        card.setMinimumWidth(720)
        card.setMaximumWidth(1080)
        card.setStyleSheet(
            "#profileCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; }"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 16, 20, 20)
        card_layout.setSpacing(12)

        field_h = MODAL_FIELD_HEIGHT_PX
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)

        self.module_combo = QComboBox()
        self.object_combo = QComboBox()
        self.business_object_type_combo = QComboBox()
        self.status_combo = QComboBox()
        self.scope_combo = QComboBox()
        self.load_approach_combo = QComboBox()
        self.upload_tool_combo = QComboBox()
        self.customization_status_combo = QComboBox()
        self.build_status_combo = QComboBox()
        self.functional_unit_testing_status_combo = QComboBox()
        self.business_unit_testing_status_combo = QComboBox()
        self.uploaded_to_sharepoint_combo = QComboBox()

        combo_specs = (
            self.module_combo,
            self.object_combo,
            self.business_object_type_combo,
            self.status_combo,
            self.scope_combo,
            self.load_approach_combo,
            self.upload_tool_combo,
            self.customization_status_combo,
            self.build_status_combo,
            self.functional_unit_testing_status_combo,
            self.business_unit_testing_status_combo,
            self.uploaded_to_sharepoint_combo,
        )
        for c in combo_specs:
            apply_form_combobox_field(c, height_px=field_h, min_width=260)
        for combo, label in (
            (self.status_combo, "Status"),
            (self.business_object_type_combo, "Business object type"),
            (self.scope_combo, "Scope"),
            (self.load_approach_combo, "Load approach"),
            (self.upload_tool_combo, "Upload tool"),
            (self.customization_status_combo, "Customization status"),
            (self.build_status_combo, "Build status"),
            (self.functional_unit_testing_status_combo, "Functional unit testing status"),
            (self.business_unit_testing_status_combo, "Business unit testing status"),
        ):
            wire_searchable_master_key_combo(combo, search_field_label=label)

        self.module_combo.currentIndexChanged.connect(self._on_module_selection_changed)

        self.tcode_edit = QLineEdit()
        self.tcode_edit.setPlaceholderText(placeholder_example("VA01"))
        self.tcode_edit.setStyleSheet(INPUT_STYLE)
        self.tcode_edit.setFixedHeight(field_h)

        self.estimated_prod_count_edit = QLineEdit()
        self.estimated_prod_count_edit.setPlaceholderText(placeholder_example("100"))
        self.estimated_prod_count_edit.setStyleSheet(INPUT_STYLE)
        self.estimated_prod_count_edit.setFixedHeight(field_h)

        self.dmc_program_name_edit = QLineEdit()
        self.dmc_program_name_edit.setPlaceholderText(placeholder_example("Data Migration"))
        self.dmc_program_name_edit.setStyleSheet(INPUT_STYLE)
        self.dmc_program_name_edit.setFixedHeight(field_h)

        self.build_completion_datetime = _DateTimePickerField(field_h)
        self.functional_unit_testing_completion_datetime = _DateTimePickerField(field_h)
        self.business_unit_testing_completion_datetime = _DateTimePickerField(field_h)

        self.functional_spoc_edit = QLineEdit()
        self.functional_spoc_edit.setPlaceholderText(placeholder_example("Ali"))
        self.functional_spoc_edit.setStyleSheet(INPUT_STYLE)
        self.functional_spoc_edit.setFixedHeight(field_h)

        self.uploaded_to_sharepoint_combo.addItem("Yes", True)
        self.uploaded_to_sharepoint_combo.addItem("No", False)

        def add_separator(row: int) -> None:
            wrap = QWidget()
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(0, 8, 0, 8)
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setFrameShadow(QFrame.Shadow.Plain)
            line.setFixedHeight(1)
            line.setStyleSheet("background-color: #e5e7eb; border: none;")
            wl.addWidget(line)
            grid.addWidget(wrap, row, 0, 1, 3)

        grid.addWidget(labeled_field_block(field_caption_label("Module*", LABEL_STYLE), self.module_combo), 0, 0)
        grid.addWidget(labeled_field_block(field_caption_label("Object*", LABEL_STYLE), self.object_combo), 0, 1)
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Business Object Type*", LABEL_STYLE), self.business_object_type_combo
            ),
            0,
            2,
        )
        grid.addWidget(labeled_field_block(field_caption_label("TCode", LABEL_STYLE), self.tcode_edit), 1, 0)
        grid.addWidget(
            labeled_field_block(field_caption_label("Status*", LABEL_STYLE), self.status_combo),
            1,
            1,
            1,
            2,
        )

        add_separator(2)
        grid.addWidget(labeled_field_block(field_caption_label("Scope*", LABEL_STYLE), self.scope_combo), 3, 0)
        grid.addWidget(
            labeled_field_block(field_caption_label("Load Approach*", LABEL_STYLE), self.load_approach_combo),
            3,
            1,
        )
        grid.addWidget(
            labeled_field_block(field_caption_label("Upload Tool*", LABEL_STYLE), self.upload_tool_combo),
            3,
            2,
        )
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Customization Status*", LABEL_STYLE), self.customization_status_combo
            ),
            4,
            0,
        )
        grid.addWidget(
            labeled_field_block(field_caption_label("Estimated Prod Count", LABEL_STYLE), self.estimated_prod_count_edit),
            4,
            1,
        )
        grid.addWidget(
            labeled_field_block(field_caption_label("DMC Program Name", LABEL_STYLE), self.dmc_program_name_edit),
            4,
            2,
        )

        add_separator(5)
        grid.addWidget(
            labeled_field_block(field_caption_label("Build Status*", LABEL_STYLE), self.build_status_combo), 6, 0
        )
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Functional Unit Testing Status*", LABEL_STYLE),
                self.functional_unit_testing_status_combo,
            ),
            6,
            1,
        )
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Business Unit Testing Status*", LABEL_STYLE),
                self.business_unit_testing_status_combo,
            ),
            6,
            2,
        )
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Build Completion Date & time", LABEL_STYLE),
                self.build_completion_datetime,
            ),
            7,
            0,
        )
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Functional Unit Testing Completion Date & time", LABEL_STYLE),
                self.functional_unit_testing_completion_datetime,
            ),
            7,
            1,
        )
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Business Unit Testing Completion Date & time", LABEL_STYLE),
                self.business_unit_testing_completion_datetime,
            ),
            7,
            2,
        )

        add_separator(8)
        grid.addWidget(
            labeled_field_block(field_caption_label("Functional SPOC", LABEL_STYLE), self.functional_spoc_edit),
            9,
            0,
        )
        grid.addWidget(
            labeled_field_block(
                field_caption_label("Uploaded to SharePoint*", LABEL_STYLE), self.uploaded_to_sharepoint_combo
            ),
            9,
            1,
        )

        self._id_label = QLabel("")
        self._id_label.setStyleSheet(LABEL_STYLE)
        grid.addWidget(self._id_label, 9, 2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)

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
        display_btns.setStyleSheet("background: transparent; border: none;")
        dbl = QHBoxLayout(display_btns)
        dbl.setContentsMargins(0, 0, 0, 0)
        dbl.setSpacing(12)
        dbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        dbl.addWidget(self._edit_btn)
        dbl.addWidget(self._back_btn)

        edit_btns = QWidget()
        edit_btns.setStyleSheet("background: transparent; border: none;")
        ebl = QHBoxLayout(edit_btns)
        ebl.setContentsMargins(0, 0, 0, 0)
        ebl.setSpacing(12)
        ebl.addWidget(self._save_btn)
        ebl.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
        self._btn_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")
        self._btn_stack.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self._btn_stack.addWidget(display_btns)
        self._btn_stack.addWidget(edit_btns)

        self._error_label = QLabel()
        self._error_label.setStyleSheet(FORM_ERROR_LABEL_STYLE)
        self._error_label.setWordWrap(True)
        self._error_label.setVisible(False)

        grid.addWidget(self._error_label, 10, 0, 1, 3)
        grid.addWidget(self._btn_stack, 11, 0, 1, 3, Qt.AlignmentFlag.AlignLeft)

        card_layout.addLayout(grid)
        content_layout.addWidget(card)
        content_layout.addStretch()
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)
        self._switch_to_view_mode()

    def _token(self) -> str | None:
        profile = get_user_profile()
        token = profile.get("token") or profile.get("accessToken") or profile.get("access_token") or profile.get("jwt")
        return str(token) if token else None

    def _tracker_id(self) -> int | str | None:
        for key in _TRACKER_ID_KEYS:
            value = self._record.get(key)
            if value is not None:
                return value
        return None

    def _set_combo_by_data(self, combo: QComboBox, value: Any, *, fallback_text: str = "") -> None:
        idx = combo.findData(value)
        if idx < 0 and value is not None:
            for i in range(combo.count()):
                if _ids_equal(combo.itemData(i), value):
                    idx = i
                    break
        if idx >= 0:
            combo.setCurrentIndex(idx)
            return
        if fallback_text:
            combo.addItem(fallback_text, value)
            combo.setCurrentIndex(combo.count() - 1)
            return
        combo.setCurrentIndex(0)

    def _populate_tracker_master_field_combos(self) -> None:
        tk = self._token()
        specs: tuple[tuple[QComboBox, str], ...] = (
            (self.status_combo, _FIELD_STATUS),
            (self.business_object_type_combo, _FIELD_BUSINESS_OBJECT_TYPE),
            (self.scope_combo, _FIELD_SCOPE),
            (self.load_approach_combo, _FIELD_LOAD_APPROACH),
            (self.upload_tool_combo, _FIELD_UPLOAD_TOOL),
            (self.customization_status_combo, _FIELD_CUSTOMIZATION_STATUS),
            (self.build_status_combo, _FIELD_BUILD_STATUS),
            (self.functional_unit_testing_status_combo, _FIELD_FUNCTIONAL_UNIT_TESTING_STATUS),
            (self.business_unit_testing_status_combo, _FIELD_BUSINESS_UNIT_TESTING_STATUS),
        )
        for combo, field_name in specs:
            populate_master_key_by_field_name(
                combo,
                field_name,
                token=tk,
                include_placeholder=False,
            )

    def _load_reference_data(self) -> None:
        if self._loading_refs:
            return
        self._loading_refs = True
        self._refresh_btn.setEnabled(False)

        self.module_combo.blockSignals(True)
        self.object_combo.blockSignals(True)
        self.module_combo.clear()
        self.object_combo.clear()
        self.module_combo.addItem("— Select module —", None)
        self.object_combo.addItem("— Select object —", None)

        modules_result = api_get_all_modules(token=self._token())
        if modules_result.get("success"):
            for row in modules_result.get("data") or []:
                if not isinstance(row, dict):
                    continue
                module_id = row.get("moduleId") or row.get("id")
                if module_id is None:
                    continue
                name = str(row.get("moduleName") or row.get("name") or module_id)
                self.module_combo.addItem(name, module_id)

        objects_result = api_get_all_objects(token=self._token())
        self._all_object_rows = [r for r in (objects_result.get("data") or []) if isinstance(r, dict)] if objects_result.get("success") else []

        self._populate_tracker_master_field_combos()

        self.module_combo.blockSignals(False)
        self.object_combo.blockSignals(False)
        self._loading_refs = False
        self._refresh_btn.setEnabled(True)
        self._on_module_selection_changed()

    def _repopulate_object_combo_for_module(self) -> None:
        self.object_combo.clear()
        self.object_combo.addItem("— Select object —", None)
        module_id = self.module_combo.currentData()
        if module_id is None:
            return
        for row in self._all_object_rows:
            object_id = row.get("objectId") or row.get("id")
            row_module_id = row.get("moduleId") or row.get("module_id")
            if object_id is None or row_module_id is None or not _ids_equal(row_module_id, module_id):
                continue
            name = str(row.get("objectName") or row.get("name") or object_id)
            self.object_combo.addItem(name, object_id)

    def _on_module_selection_changed(self, *_unused: int) -> None:
        has_module = self.module_combo.currentData() is not None
        self.object_combo.blockSignals(True)
        if has_module:
            self._repopulate_object_combo_for_module()
        else:
            self.object_combo.clear()
            self.object_combo.addItem("— Select object —", None)
        self.object_combo.blockSignals(False)
        self.object_combo.setEnabled(has_module and self.is_edit_mode())

    def _apply_record_to_fields(self) -> None:
        self._set_combo_by_data(self.module_combo, self._record.get("moduleId"), fallback_text=str(self._record.get("moduleName") or ""))
        self._on_module_selection_changed()
        self._set_combo_by_data(self.object_combo, self._record.get("objectId"), fallback_text=str(self._record.get("objectName") or ""))
        for combo, keys in (
            (self.status_combo, ("status", "statusSeq", "status_seq", "dmt_object_list_tracker_status")),
            (
                self.business_object_type_combo,
                (
                    "businessObjectType",
                    "businessObjectTypeSeq",
                    "dmt_business_object_type",
                ),
            ),
            (self.scope_combo, ("scope", "scopeSeq", "dmt_scope")),
            (self.load_approach_combo, ("loadApproach", "loadApproachSeq", "dmt_load_approach")),
            (self.upload_tool_combo, ("uploadTool", "uploadToolSeq", "dmt_upload_tool")),
            (
                self.customization_status_combo,
                ("customizationStatus", "customizationStatusSeq", "dmt_customization_status"),
            ),
            (self.build_status_combo, ("buildStatus", "buildStatusSeq", "dmt_buildStatus")),
            (
                self.functional_unit_testing_status_combo,
                (
                    "functionalUnitTestingStatus",
                    "functionalUnitTestingStatusSeq",
                    "dmt_functionalUnitTestingStatus",
                ),
            ),
            (
                self.business_unit_testing_status_combo,
                (
                    "businessUnitTestingStatus",
                    "businessUnitTestingStatusSeq",
                    "dmt_businessUnitTestingStatus",
                ),
            ),
        ):
            seq = _seq_from_record(self._record, *keys)
            if seq is not None:
                set_searchable_combo_by_user_data(combo, seq)
            else:
                reset_searchable_combo(combo)
        self._set_combo_by_data(self.uploaded_to_sharepoint_combo, bool(self._record.get("uploadedToSharePoint")), fallback_text="")
        self.tcode_edit.setText(str(self._record.get("tcode") or ""))
        self.estimated_prod_count_edit.setText(str(self._record.get("estimatedProdCount") or ""))
        self.dmc_program_name_edit.setText(str(self._record.get("dmcProgramName") or ""))
        self.build_completion_datetime.set_iso_timestamp(self._record.get("buildCompletionDate"))
        self.functional_unit_testing_completion_datetime.set_iso_timestamp(
            self._record.get("functionalUnitTestingCompletionDate")
        )
        self.business_unit_testing_completion_datetime.set_iso_timestamp(
            self._record.get("businessUnitTestingCompletionDate")
        )
        self.functional_spoc_edit.setText(str(self._record.get("functionalSPOC") or ""))
        tid = self._tracker_id()
        self._id_label.setText(f"Tracker Id: {tid}" if tid is not None else "")

    def set_record(self, record: dict[str, Any] | None, *, edit_mode: bool = False) -> None:
        self._record = dict(record) if record else {}
        self._load_reference_data()
        self._apply_record_to_fields()
        if edit_mode and self._record:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._record:
            return
        self._load_reference_data()
        self._apply_record_to_fields()

    def _show_error(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=True)

    def _show_success(self, message: str) -> None:
        show_auto_hiding_message(self, self._error_label, message, error=False)

    def _clear_error(self) -> None:
        cancel_auto_hide_message(self, self._error_label)
        self._error_label.setText("")
        self._error_label.setVisible(False)

    def _current_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "moduleId": self.module_combo.currentData(),
            "objectId": self.object_combo.currentData(),
            "status": master_key_seq_for_payload(self.status_combo),
            "businessObjectType": master_key_seq_for_payload(self.business_object_type_combo),
            "scope": master_key_seq_for_payload(self.scope_combo),
            "loadApproach": master_key_seq_for_payload(self.load_approach_combo),
            "uploadTool": master_key_seq_for_payload(self.upload_tool_combo),
            "customizationStatus": master_key_seq_for_payload(self.customization_status_combo),
            "buildStatus": master_key_seq_for_payload(self.build_status_combo),
            "functionalUnitTestingStatus": master_key_seq_for_payload(
                self.functional_unit_testing_status_combo
            ),
            "businessUnitTestingStatus": master_key_seq_for_payload(
                self.business_unit_testing_status_combo
            ),
            "uploadedToSharePoint": bool(self.uploaded_to_sharepoint_combo.currentData()),
        }
        for key, edit in (
            ("tcode", self.tcode_edit),
            ("functionalSPOC", self.functional_spoc_edit),
            ("dmcProgramName", self.dmc_program_name_edit),
        ):
            val = edit.text().strip()
            if val:
                payload[key] = val
        build_iso = self.build_completion_datetime.iso_timestamp()
        payload["buildCompletionDate"] = to_utc_iso(build_iso) or build_iso
        fut_iso = self.functional_unit_testing_completion_datetime.iso_timestamp()
        payload["functionalUnitTestingCompletionDate"] = to_utc_iso(fut_iso) or fut_iso
        but_iso = self.business_unit_testing_completion_datetime.iso_timestamp()
        payload["businessUnitTestingCompletionDate"] = to_utc_iso(but_iso) or but_iso
        est = self.estimated_prod_count_edit.text().strip()
        if est:
            payload["estimatedProdCount"] = int(est) if est.isdigit() else est
        return payload

    def _original_payload(self) -> dict[str, Any]:
        return {
            "moduleId": self._record.get("moduleId"),
            "objectId": self._record.get("objectId"),
            "status": _seq_from_record(
                self._record, "status", "statusSeq", "status_seq", "dmt_object_list_tracker_status"
            ),
            "businessObjectType": _seq_from_record(
                self._record,
                "businessObjectType",
                "businessObjectTypeSeq",
                "dmt_business_object_type",
            ),
            "scope": _seq_from_record(self._record, "scope", "scopeSeq", "dmt_scope"),
            "loadApproach": _seq_from_record(
                self._record, "loadApproach", "loadApproachSeq", "dmt_load_approach"
            ),
            "uploadTool": _seq_from_record(self._record, "uploadTool", "uploadToolSeq", "dmt_upload_tool"),
            "customizationStatus": _seq_from_record(
                self._record, "customizationStatus", "customizationStatusSeq", "dmt_customization_status"
            ),
            "buildStatus": _seq_from_record(self._record, "buildStatus", "buildStatusSeq", "dmt_buildStatus"),
            "functionalUnitTestingStatus": _seq_from_record(
                self._record,
                "functionalUnitTestingStatus",
                "functionalUnitTestingStatusSeq",
                "dmt_functionalUnitTestingStatus",
            ),
            "businessUnitTestingStatus": _seq_from_record(
                self._record,
                "businessUnitTestingStatus",
                "businessUnitTestingStatusSeq",
                "dmt_businessUnitTestingStatus",
            ),
            "uploadedToSharePoint": bool(self._record.get("uploadedToSharePoint")),
            "tcode": str(self._record.get("tcode") or ""),
            "buildCompletionDate": self._normalize_iso(self._record.get("buildCompletionDate")),
            "functionalUnitTestingCompletionDate": self._normalize_iso(self._record.get("functionalUnitTestingCompletionDate")),
            "businessUnitTestingCompletionDate": self._normalize_iso(self._record.get("businessUnitTestingCompletionDate")),
            "functionalSPOC": str(self._record.get("functionalSPOC") or ""),
            "dmcProgramName": str(self._record.get("dmcProgramName") or ""),
            "estimatedProdCount": self._record.get("estimatedProdCount") if self._record.get("estimatedProdCount") is not None else "",
        }

    def _has_unsaved_changes(self) -> bool:
        return self._current_payload() != self._original_payload()

    def _validate_required(self) -> bool:
        if self.module_combo.currentData() is None:
            self._show_error("Please select module.")
            return False
        if self.object_combo.currentData() is None:
            self._show_error("Please select object.")
            return False
        for combo, caption, phrase in (
            (self.status_combo, "Status", "a status"),
            (self.business_object_type_combo, "Business object type", "a business object type"),
            (self.scope_combo, "Scope", "a scope"),
            (self.load_approach_combo, "Load approach", "a load approach"),
            (self.upload_tool_combo, "Upload tool", "an upload tool"),
            (self.customization_status_combo, "Customization status", "a customization status"),
            (self.build_status_combo, "Build status", "a build status"),
            (self.functional_unit_testing_status_combo, "Functional unit testing status", "a functional unit testing status"),
            (self.business_unit_testing_status_combo, "Business unit testing status", "a business unit testing status"),
        ):
            _, err = require_master_key_seq_for_payload(
                combo, field_caption=caption, strict_phrase=phrase
            )
            if err:
                self._show_error(err)
                combo.setFocus()
                return False
        return True

    def _set_editable(self, editable: bool) -> None:
        for c in (
            self.module_combo,
            self.object_combo,
            self.status_combo,
            self.business_object_type_combo,
            self.scope_combo,
            self.load_approach_combo,
            self.upload_tool_combo,
            self.customization_status_combo,
            self.build_status_combo,
            self.functional_unit_testing_status_combo,
            self.business_unit_testing_status_combo,
            self.uploaded_to_sharepoint_combo,
        ):
            c.setEnabled(editable)
        for edit in (
            self.tcode_edit,
            self.estimated_prod_count_edit,
            self.dmc_program_name_edit,
            self.functional_spoc_edit,
        ):
            edit.setReadOnly(not editable)
            edit.setStyleSheet(INPUT_STYLE if editable else READONLY_INPUT_STYLE)
        for dt_widget in (
            self.build_completion_datetime,
            self.functional_unit_testing_completion_datetime,
            self.business_unit_testing_completion_datetime,
        ):
            dt_widget.setEnabled(editable)
        if not editable:
            self.object_combo.setEnabled(False)
        else:
            self.object_combo.setEnabled(self.module_combo.currentData() is not None)

    def _handle_back(self) -> None:
        if self.on_back:
            self.on_back()

    def _handle_edit(self) -> None:
        self._clear_error()
        self._set_editable(True)
        self._btn_stack.setCurrentIndex(1)

    def _handle_cancel(self) -> None:
        if self._has_unsaved_changes():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "You have unsaved changes. Discard and leave?",
                QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Discard:
                return
        self._clear_error()
        self._apply_record_to_fields()
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
        if not self._validate_required():
            return
        tracker_id = self._tracker_id()
        if tracker_id is None:
            self._show_error("Object tracker ID is missing.")
            return
        payload = self._current_payload()
        result = api_update_object_tracker(tracker_id, payload, token=self._token())
        if not result.get("success"):
            self._show_error(str(result.get("message") or "Failed to update object tracker record."))
            return
        self._record.update(payload)
        self._show_success(str(result.get("message") or "Object tracker record updated successfully."))
        schedule_after_success(
            delay_ms=800,
            clear_error=self._clear_error,
            on_back=self.on_back,
            on_success=self.on_update_success,
        )

    def _switch_to_view_mode(self) -> None:
        self._set_editable(False)
        self._btn_stack.setCurrentIndex(0)

    def is_edit_mode(self) -> bool:
        return self._btn_stack.currentIndex() == 1

    def _normalize_iso(self, value: Any) -> str:
        s = str(value or "").strip()
        if not s:
            return ""
        s_iso = s.replace(" ", "T").replace("Z", "")
        return s_iso[:19]
