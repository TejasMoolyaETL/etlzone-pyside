"""View/edit Object List Tracker record."""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
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
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.api import (
    api_get_all_modules,
    api_get_all_objects,
    api_get_master_key_category_entries,
    api_update_object_tracker,
)
from core.app_preferences import to_utc_iso
from app.dmt.dmt_object_tracker.dmt_object_tracker_comment_panel import ObjectTrackerCommentPanel
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
from ui.widgets.required_label import field_caption_label, labeled_field_block

_TRACKER_ID_KEYS = ("objectTrackerId", "trackerId", "id")
_MASTER_KEY_BUSINESS_OBJECT_TYPE = "BUSINESS_OBJECT_TYPE"
_MASTER_KEY_SCOPE = "SCOPE"
_MASTER_KEY_LOAD_APPROACH = "LOAD_APPROACH"
_MASTER_KEY_UPLOAD_TOOL = "UPLOAD_TOOL"
_MASTER_KEY_CUSTOMIZATION_STATUS = "CUSTOMIZATION_STATUS"
_MASTER_KEY_STATUS1 = "STATUS1"


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


def _seq_sort_key(row: dict[str, Any]) -> tuple[int, Any]:
    s = row.get("seq")
    try:
        return (0, int(s))
    except (TypeError, ValueError):
        return (1, s or "")


def _label_for_master_key_row(row: dict[str, Any]) -> str:
    seq = row.get("seq")
    kv = str(row.get("keyValue") or row.get("key_value") or "").strip()
    desc = str(row.get("description") or row.get("desc") or "").strip()
    parts: list[str] = []
    if kv:
        parts.append(kv)
    if desc:
        parts.append(desc)
    if parts:
        return f"{seq} — {' — '.join(parts)}" if seq is not None else " — ".join(parts)
    return str(seq) if seq is not None else ""


def _seq_payload_value(seq: Any) -> Any:
    if seq is None:
        return seq
    s = str(seq).strip()
    return int(s) if s.isdigit() else seq


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
        self._comment_context_listeners: list[Callable[[], None]] = []
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

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(6)

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
        dbl = QHBoxLayout(display_btns)
        dbl.setContentsMargins(0, 0, 0, 0)
        dbl.setSpacing(12)
        dbl.setAlignment(Qt.AlignmentFlag.AlignLeft)
        dbl.addWidget(self._edit_btn)
        dbl.addWidget(self._back_btn)

        edit_btns = QWidget()
        ebl = QHBoxLayout(edit_btns)
        ebl.setContentsMargins(0, 0, 0, 0)
        ebl.setSpacing(12)
        ebl.addWidget(self._save_btn)
        ebl.addWidget(self._cancel_btn)

        self._btn_stack = QStackedWidget()
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
        splitter.addWidget(scroll)
        self._comment_panel = ObjectTrackerCommentPanel(self)
        splitter.addWidget(self._comment_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([700, 300])
        layout.addWidget(splitter, 1)
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

    def get_selected_row(self) -> dict[str, Any] | None:
        return self._record if self._record else None

    def register_comment_context_listener(self, listener: Callable[[], None]) -> None:
        if listener not in self._comment_context_listeners:
            self._comment_context_listeners.append(listener)

    def _notify_comment_context_changed(self) -> None:
        for listener in self._comment_context_listeners:
            try:
                listener()
            except Exception:
                continue

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

    def _populate_master_key_combo(self, combo: QComboBox, category: str, placeholder: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(placeholder, None)
        result = api_get_master_key_category_entries(category, token=self._token())
        if result.get("success"):
            rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
            rows.sort(key=_seq_sort_key)
            for row in rows:
                seq = row.get("seq")
                if seq is None:
                    continue
                label = _label_for_master_key_row(row) or str(seq)
                seq_str = str(seq).strip()
                seq_data: int | str = int(seq_str) if seq_str.isdigit() else seq_str
                combo.addItem(label, seq_data)
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

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

        self._populate_master_key_combo(
            self.business_object_type_combo, _MASTER_KEY_BUSINESS_OBJECT_TYPE, "— Select business object type —"
        )
        self._populate_master_key_combo(self.scope_combo, _MASTER_KEY_SCOPE, "— Select scope —")
        self._populate_master_key_combo(self.load_approach_combo, _MASTER_KEY_LOAD_APPROACH, "— Select load approach —")
        self._populate_master_key_combo(self.upload_tool_combo, _MASTER_KEY_UPLOAD_TOOL, "— Select upload tool —")
        self._populate_master_key_combo(
            self.customization_status_combo, _MASTER_KEY_CUSTOMIZATION_STATUS, "— Select customization status —"
        )
        self._populate_master_key_combo(self.build_status_combo, _MASTER_KEY_STATUS1, "— Select build status —")
        self._populate_master_key_combo(
            self.functional_unit_testing_status_combo, _MASTER_KEY_STATUS1, "— Select functional unit testing status —"
        )
        self._populate_master_key_combo(
            self.business_unit_testing_status_combo, _MASTER_KEY_STATUS1, "— Select business unit testing status —"
        )

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
        self._set_combo_by_data(self.business_object_type_combo, self._record.get("businessObjectTypeSeq"), fallback_text=str(self._record.get("businessObjectTypeName") or ""))
        self._set_combo_by_data(self.scope_combo, self._record.get("scopeSeq"), fallback_text=str(self._record.get("scopeName") or ""))
        self._set_combo_by_data(self.load_approach_combo, self._record.get("loadApproachSeq"), fallback_text=str(self._record.get("loadApproachName") or ""))
        self._set_combo_by_data(self.upload_tool_combo, self._record.get("uploadToolSeq"), fallback_text=str(self._record.get("uploadToolName") or ""))
        self._set_combo_by_data(
            self.customization_status_combo,
            self._record.get("customizationStatusSeq"),
            fallback_text=str(self._record.get("customizationStatusName") or ""),
        )
        self._set_combo_by_data(
            self.build_status_combo,
            self._record.get("buildStatusSeq"),
            fallback_text=str(self._record.get("buildStatusName") or ""),
        )
        self._set_combo_by_data(
            self.functional_unit_testing_status_combo,
            self._record.get("functionalUnitTestingStatusSeq"),
            fallback_text=str(self._record.get("functionalUnitTestingStatusName") or ""),
        )
        self._set_combo_by_data(
            self.business_unit_testing_status_combo,
            self._record.get("businessUnitTestingStatusSeq"),
            fallback_text=str(self._record.get("businessUnitTestingStatusName") or ""),
        )
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
        self._notify_comment_context_changed()
        if edit_mode and self._record:
            self._handle_edit()
        else:
            self._switch_to_view_mode()

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
            "businessObjectTypeSeq": _seq_payload_value(self.business_object_type_combo.currentData()),
            "scopeSeq": _seq_payload_value(self.scope_combo.currentData()),
            "loadApproachSeq": _seq_payload_value(self.load_approach_combo.currentData()),
            "uploadToolSeq": _seq_payload_value(self.upload_tool_combo.currentData()),
            "customizationStatusSeq": _seq_payload_value(self.customization_status_combo.currentData()),
            "buildStatusSeq": _seq_payload_value(self.build_status_combo.currentData()),
            "functionalUnitTestingStatusSeq": _seq_payload_value(self.functional_unit_testing_status_combo.currentData()),
            "businessUnitTestingStatusSeq": _seq_payload_value(self.business_unit_testing_status_combo.currentData()),
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
            "businessObjectTypeSeq": self._record.get("businessObjectTypeSeq"),
            "scopeSeq": self._record.get("scopeSeq"),
            "loadApproachSeq": self._record.get("loadApproachSeq"),
            "uploadToolSeq": self._record.get("uploadToolSeq"),
            "customizationStatusSeq": self._record.get("customizationStatusSeq"),
            "buildStatusSeq": self._record.get("buildStatusSeq"),
            "functionalUnitTestingStatusSeq": self._record.get("functionalUnitTestingStatusSeq"),
            "businessUnitTestingStatusSeq": self._record.get("businessUnitTestingStatusSeq"),
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
        required = (
            ("module", self.module_combo.currentData()),
            ("object", self.object_combo.currentData()),
            ("business object type", self.business_object_type_combo.currentData()),
            ("scope", self.scope_combo.currentData()),
            ("load approach", self.load_approach_combo.currentData()),
            ("upload tool", self.upload_tool_combo.currentData()),
            ("customization status", self.customization_status_combo.currentData()),
            ("build status", self.build_status_combo.currentData()),
            ("functional unit testing status", self.functional_unit_testing_status_combo.currentData()),
            ("business unit testing status", self.business_unit_testing_status_combo.currentData()),
        )
        for label, value in required:
            if value is None:
                self._show_error(f"Please select {label}.")
                return False
        return True

    def _set_editable(self, editable: bool) -> None:
        for c in (
            self.module_combo,
            self.object_combo,
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
