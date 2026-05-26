"""Shared scroll form layout for DM: Project create/update (Leads-style)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.dm.dm_project.dm_project_fields import (
    DM_COMPANY_COMBO_KEYS,
    MASTER_KEY_FIELD_BY_PAYLOAD_KEY,
    wire_master_key_combo,
)
from app.user_management.users.user_create import _DatePickerEdit
from ui.form_combobox_style import apply_form_combobox_field
from ui.form_page_styles import (
    FORM_INPUT_STYLE as INPUT_STYLE,
    FORM_LABEL_STYLE as LABEL_STYLE,
    FORM_READONLY_INPUT_STYLE as READONLY_INPUT_STYLE,
    MODAL_FIELD_HEIGHT_PX,
    placeholder_example,
)
from ui.theme import Theme
from ui.widgets.required_label import field_caption_label, labeled_field_block

FORM_FIELD_CAPTIONS: dict[str, str] = {
    "projectId": "Project ID",
    "projectName": "Project Name*",
    "deliveryModel": "Delivery Model*",
    "clientCompanyId": "Client Company",
    "region": "Region",
    "status": "Status",
    "srcLandscape": "Source Landscape",
    "tgtLandscape": "Target Landscape",
    "migrationType": "Migration Type",
    "startDate": "Start Date",
    "goLiveDate": "Go-Live Date",
    "implementationPartnerId": "Implementation Partner",
    "source": "Source",
    "laptopOwnership": "Laptop Ownership",
    "accommodationOwnership": "Accommodation Ownership",
    "travelExpenseOwnership": "Travel Expense Ownership",
    "perDiemOwnership": "Per Diem Ownership",
    "extractionOwnership": "Extraction Ownership",
    "transformationOwnership": "Transformation Ownership",
    "loadingOwnership": "Loading Ownership",
    "extractionScope": "Extraction Scope",
    "transformationScope": "Transformation Scope",
    "loadScope": "Load Scope",
    "endClientName": "End Client Name",
    "intermediateClient1": "Intermediate Client 1",
    "intermediateClient2": "Intermediate Client 2",
    "intermediateClient3": "Intermediate Client 3",
    "intermediateClient4": "Intermediate Client 4",
    "commentAtEtlzone": "Comment At ETLZone",
}

ENTITY_COMBO_KEYS: frozenset[str] = DM_COMPANY_COMBO_KEYS

MASTER_COMBO_KEYS: frozenset[str] = frozenset(MASTER_KEY_FIELD_BY_PAYLOAD_KEY.keys())

DATE_KEYS: frozenset[str] = frozenset({"startDate", "goLiveDate"})

SCOPE_BOOL_KEYS: frozenset[str] = frozenset(
    {"extractionScope", "transformationScope", "loadScope"}
)

SCOPE_OWNERSHIP_PAIRS: dict[str, str] = {
    "extractionScope": "extractionOwnership",
    "transformationScope": "transformationOwnership",
    "loadScope": "loadingOwnership",
}

SCOPE_GATED_OWNERSHIP_KEYS: frozenset[str] = frozenset(SCOPE_OWNERSHIP_PAIRS.values())

SCOPE_UNCHECKED_OWNERSHIP_SEQ = 4


def apply_scope_unchecked_ownership_default(combo: QComboBox | None) -> None:
    """When scope is off, ownership master-key selection defaults to seq 4."""
    from ui.searchable_form_combo import set_searchable_combo_by_user_data

    set_searchable_combo_by_user_data(combo, SCOPE_UNCHECKED_OWNERSHIP_SEQ)


def clear_scope_checked_ownership(combo: QComboBox | None) -> None:
    """When scope is on, clear the unchecked default (4) so the user picks a value."""
    from ui.searchable_form_combo import combo_resolved_master_key_seq, reset_searchable_combo

    if combo is None:
        return
    if combo_resolved_master_key_seq(combo) == SCOPE_UNCHECKED_OWNERSHIP_SEQ:
        reset_searchable_combo(combo)


def apply_scope_gated_ownership_defaults(
    scope_check_by_key: dict[str, QCheckBox],
    master_combo_by_key: dict[str, QComboBox],
) -> None:
    for scope_key, ownership_key in SCOPE_OWNERSHIP_PAIRS.items():
        check = scope_check_by_key.get(scope_key)
        if check is not None and check.isChecked():
            continue
        apply_scope_unchecked_ownership_default(master_combo_by_key.get(ownership_key))


def scope_gated_ownership_seq(*, scope_checked: bool, resolved_seq: int | None) -> int:
    from ui.searchable_form_combo import coerce_master_key_payload_int

    if not scope_checked:
        return SCOPE_UNCHECKED_OWNERSHIP_SEQ
    return coerce_master_key_payload_int(resolved_seq)


def collect_scope_gated_ownership_masters(
    scope_check_by_key: dict[str, QCheckBox],
    master_combo_by_key: dict[str, QComboBox],
    *,
    on_error: Callable[[str, str | None], None],
) -> dict[str, int] | None:
    """Resolve ownership master-key seq for each scope row.

    When scope is unchecked, uses :data:`SCOPE_UNCHECKED_OWNERSHIP_SEQ` (4).
    When scope is checked, ownership must be chosen from the list (not blank / not seq 4).
    """
    from ui.searchable_form_combo import (
        MASTER_KEY_BLANK_SEQ_DEFAULT,
        require_master_key_seq_for_payload,
    )

    out: dict[str, int] = {}
    for scope_key, ownership_key in SCOPE_OWNERSHIP_PAIRS.items():
        check = scope_check_by_key.get(scope_key)
        scope_on = bool(check.isChecked()) if check is not None else False
        combo = master_combo_by_key.get(ownership_key)
        if not scope_on:
            out[ownership_key] = SCOPE_UNCHECKED_OWNERSHIP_SEQ
            continue
        caption = FORM_FIELD_CAPTIONS.get(ownership_key, ownership_key).replace("*", "").strip()
        seq, err = require_master_key_seq_for_payload(
            combo,
            field_caption=caption,
            strict_phrase=f"an {caption.lower()}",
        )
        if err:
            on_error(err, ownership_key)
            return None
        if seq in (SCOPE_UNCHECKED_OWNERSHIP_SEQ, MASTER_KEY_BLANK_SEQ_DEFAULT):
            scope_caption = FORM_FIELD_CAPTIONS.get(scope_key, scope_key)
            on_error(
                f"When {scope_caption} is selected, {caption} is required.",
                ownership_key,
            )
            return None
        out[ownership_key] = int(seq)
    return out


def sync_scope_gated_ownership(
    scope_check_by_key: dict[str, QCheckBox],
    master_combo_by_key: dict[str, QComboBox],
    *,
    form_enabled: bool,
) -> None:
    """Ownership combos are enabled only when the form is editable and scope is checked."""
    for scope_key, ownership_key in SCOPE_OWNERSHIP_PAIRS.items():
        check = scope_check_by_key.get(scope_key)
        combo = master_combo_by_key.get(ownership_key)
        if combo is None:
            continue
        scope_on = bool(check.isChecked()) if check is not None else False
        if not scope_on:
            apply_scope_unchecked_ownership_default(combo)
        combo.setEnabled(form_enabled and scope_on)

READONLY_KEYS: frozenset[str] = frozenset({"projectId", "id"})

PROJECT_RECORD_KEYS: tuple[tuple[str, ...], ...] = (
    ("projectId", "id"),
    ("projectName",),
    ("deliveryModel", "delivery_model"),
    ("clientCompanyId", "client_company_id"),
    ("region",),
    ("status",),
    ("srcLandscape", "src_landscape"),
    ("tgtLandscape", "tgt_landscape"),
    ("migrationType", "migration_type"),
    ("startDate",),
    ("goLiveDate", "go_live_date"),
    ("implementationPartnerId", "implementation_partner_id"),
    ("source", "leadSource"),
    ("laptopOwnership",),
    ("accommodationOwnership", "accomadationOwnership"),
    ("travelExpenseOwnership",),
    ("perDiemOwnership",),
    ("extractionOwnership",),
    ("transformationOwnership",),
    ("loadingOwnership",),
    ("extractionScope",),
    ("transformationScope",),
    ("loadScope",),
    ("endClientName",),
    ("intermediateClient1",),
    ("intermediateClient2",),
    ("intermediateClient3",),
    ("intermediateClient4",),
    ("commentAtEtlzone", "commentAtEtlZone"),
)

FIELD_PLACEHOLDERS: dict[str, str] = {
    "projectName": placeholder_example("SAP Migration Project"),
    "region": placeholder_example("APAC"),
    "commentAtEtlzone": placeholder_example("Migration phase initiated"),
}


def horizontal_rule_block() -> QWidget:
    wrap = QWidget()
    lay = QVBoxLayout(wrap)
    lay.setContentsMargins(0, 10, 0, 10)
    lay.setSpacing(0)
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Plain)
    line.setFixedHeight(1)
    line.setStyleSheet(
        f"QFrame {{ background-color: {Theme.BORDER_DEFAULT}; border: none; }}"
    )
    lay.addWidget(line)
    return wrap


class DmProjectFormScrollArea(QScrollArea):
    """Preserve natural form height so fields do not compress; scroll vertically when needed."""

    def __init__(self, body: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._body = body
        self.setWidgetResizable(False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setWidget(body)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        vp = self.viewport()
        vp.setAutoFillBackground(True)
        vpal = vp.palette()
        vpal.setColor(QPalette.ColorRole.Window, QColor(Theme.BG_WHITE))
        vp.setPalette(vpal)
        self.setStyleSheet(
            f"QScrollArea {{ background: {Theme.BG_WHITE}; border: none; }}"
            f"QScrollArea > QWidget > QWidget {{ background: {Theme.BG_WHITE}; }}"
        )

    def sync_body_geometry(self) -> None:
        lay = self._body.layout()
        if lay is not None:
            lay.activate()
            min_h = lay.minimumSize().height()
            if min_h > 0:
                self._body.setMinimumHeight(min_h)
        vw = self.viewport().width()
        if vw > 0:
            self._body.setFixedWidth(vw)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self.sync_body_geometry()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.sync_body_geometry()


@dataclass
class DmProjectFormWidgets:
    field_edits: dict[str, QLineEdit] = field(default_factory=dict)
    entity_combo_by_key: dict[str, QComboBox] = field(default_factory=dict)
    master_combo_by_key: dict[str, QComboBox] = field(default_factory=dict)
    date_by_key: dict[str, _DatePickerEdit] = field(default_factory=dict)
    scope_check_by_key: dict[str, QCheckBox] = field(default_factory=dict)
    project_id_edit: QLineEdit | None = None
    scroll_area: QScrollArea | None = None
    editable_keys: list[str] = field(default_factory=list)


def build_dm_project_form_scroll(
    *,
    include_project_id: bool,
    start_readonly: bool = False,
) -> tuple[QScrollArea, DmProjectFormWidgets]:
    """Build Leads-style scrollable two-column form; return scroll area and widget refs."""
    ctx = DmProjectFormWidgets()
    field_h = MODAL_FIELD_HEIGHT_PX
    field_min_w = 260
    field_by_key = FORM_FIELD_CAPTIONS

    def new_section_grid() -> QGridLayout:
        section_grid = QGridLayout()
        section_grid.setHorizontalSpacing(24)
        section_grid.setVerticalSpacing(10)
        section_grid.setColumnStretch(0, 1)
        section_grid.setColumnStretch(1, 1)
        return section_grid

    def add_section(grid: QGridLayout) -> None:
        section = QWidget()
        section.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        section.setLayout(grid)
        scroll_layout.addWidget(section)

    def add_line_field(
        grid: QGridLayout, key: str, row: int, col: int, col_span: int = 1
    ) -> None:
        caption = field_by_key.get(key, key)
        if key not in READONLY_KEYS and key != "projectId":
            ctx.editable_keys.append(key)

        if key == "projectId":
            edit = QLineEdit()
            edit.setReadOnly(True)
            edit.setFixedHeight(field_h)
            edit.setStyleSheet(READONLY_INPUT_STYLE)
            edit.setMinimumWidth(field_min_w)
            edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            ctx.project_id_edit = edit
            grid.addWidget(
                labeled_field_block(field_caption_label(caption, LABEL_STYLE), edit),
                row,
                col,
                1,
                col_span,
            )
            return

        if key in DATE_KEYS:
            picker = _DatePickerEdit()
            picker.setFixedHeight(field_h)
            picker.setMinimumWidth(field_min_w)
            picker.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            if start_readonly:
                picker.setEnabled(False)
            ctx.date_by_key[key] = picker
            grid.addWidget(
                labeled_field_block(field_caption_label(caption, LABEL_STYLE), picker),
                row,
                col,
                1,
                col_span,
            )
            return

        if key in ENTITY_COMBO_KEYS:
            combo = QComboBox()
            combo.setMinimumWidth(field_min_w)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            apply_form_combobox_field(combo, height_px=field_h)
            if start_readonly:
                combo.setEnabled(False)
            ctx.entity_combo_by_key[key] = combo
            grid.addWidget(
                labeled_field_block(field_caption_label(caption, LABEL_STYLE), combo),
                row,
                col,
                1,
                col_span,
            )
            return

        if key in SCOPE_BOOL_KEYS or key in SCOPE_GATED_OWNERSHIP_KEYS:
            return

        if key in MASTER_COMBO_KEYS:
            combo = QComboBox()
            combo.setMinimumWidth(field_min_w)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            cap = caption.replace("*", "").strip()
            wire_master_key_combo(combo, label=cap)
            if start_readonly:
                combo.setEnabled(False)
            ctx.master_combo_by_key[key] = combo
            grid.addWidget(
                labeled_field_block(field_caption_label(caption, LABEL_STYLE), combo),
                row,
                col,
                1,
                col_span,
            )
            return

        edit = QLineEdit()
        edit.setFixedHeight(field_h)
        edit.setMinimumWidth(field_min_w)
        edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        ph = FIELD_PLACEHOLDERS.get(key)
        if ph:
            edit.setPlaceholderText(ph)
        if start_readonly or key in READONLY_KEYS:
            edit.setReadOnly(True)
            edit.setStyleSheet(READONLY_INPUT_STYLE)
        else:
            edit.setStyleSheet(INPUT_STYLE)
        ctx.field_edits[key] = edit
        grid.addWidget(
            labeled_field_block(field_caption_label(caption, LABEL_STYLE), edit),
            row,
            col,
            1,
            col_span,
        )

    def add_scope_ownership_row(
        grid: QGridLayout, scope_key: str, ownership_key: str, row: int
    ) -> None:
        if ownership_key not in READONLY_KEYS:
            ctx.editable_keys.append(ownership_key)

        row_widget = QWidget()
        row_widget.setFixedHeight(field_h)
        row_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        row_lay = QHBoxLayout(row_widget)
        row_lay.setContentsMargins(0, 0, 0, 0)
        row_lay.setSpacing(12)
        row_lay.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        scope_caption = field_by_key.get(scope_key, scope_key)
        check = QCheckBox(scope_caption)
        check.setStyleSheet("QCheckBox { color: #0f172a; }")
        if start_readonly:
            check.setEnabled(False)
        ctx.scope_check_by_key[scope_key] = check
        row_lay.addWidget(check, 0, Qt.AlignmentFlag.AlignVCenter)

        own_caption = field_by_key.get(ownership_key, ownership_key)
        own_label = field_caption_label(own_caption, LABEL_STYLE)
        own_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row_lay.addWidget(own_label, 0, Qt.AlignmentFlag.AlignVCenter)

        combo = QComboBox()
        combo.setFixedHeight(field_h)
        combo.setMinimumWidth(field_min_w)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        cap = own_caption.replace("*", "").strip()
        wire_master_key_combo(combo, label=cap)
        combo.setEnabled(False)
        ctx.master_combo_by_key[ownership_key] = combo
        row_lay.addWidget(combo, 1, Qt.AlignmentFlag.AlignVCenter)

        def on_scope_changed(_state: int, *, sk: str = scope_key, ok: str = ownership_key) -> None:
            scope_check = ctx.scope_check_by_key.get(sk)
            own_combo = ctx.master_combo_by_key.get(ok)
            if scope_check is None or own_combo is None:
                return
            if scope_check.isChecked():
                clear_scope_checked_ownership(own_combo)
            else:
                apply_scope_unchecked_ownership_default(own_combo)
            sync_scope_gated_ownership(
                ctx.scope_check_by_key,
                ctx.master_combo_by_key,
                form_enabled=scope_check.isEnabled(),
            )

        check.stateChanged.connect(on_scope_changed)
        grid.addWidget(row_widget, row, 0, 1, 2)

    scroll_body = QWidget()
    scroll_body.setStyleSheet(f"background-color: {Theme.BG_WHITE};")
    scroll_body.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    scroll_layout = QVBoxLayout(scroll_body)
    scroll_layout.setContentsMargins(0, 0, 0, 0)
    scroll_layout.setSpacing(0)

    core_grid = new_section_grid()
    core_row = 0
    if include_project_id:
        add_line_field(core_grid, "projectId", core_row, 0)
        add_line_field(core_grid, "status", core_row, 1)
        core_row += 1
    add_line_field(core_grid, "projectName", core_row, 0)
    add_line_field(core_grid, "deliveryModel", core_row, 1)
    core_row += 1
    add_line_field(core_grid, "clientCompanyId", core_row, 0)
    add_line_field(core_grid, "region", core_row, 1)
    core_row += 1
    if not include_project_id:
        add_line_field(core_grid, "status", core_row, 0)
        core_row += 1
    core_grid.addWidget(horizontal_rule_block(), core_row, 0, 1, 2)
    core_row += 1
    add_line_field(core_grid, "srcLandscape", core_row, 0)
    add_line_field(core_grid, "tgtLandscape", core_row, 1)
    core_row += 1
    add_line_field(core_grid, "migrationType", core_row, 0)
    add_line_field(core_grid, "startDate", core_row, 1)
    core_row += 1
    add_line_field(core_grid, "goLiveDate", core_row, 0)
    core_row += 1
    core_grid.addWidget(horizontal_rule_block(), core_row, 0, 1, 2)
    core_row += 1
    add_line_field(core_grid, "implementationPartnerId", core_row, 0, col_span=2)
    core_row += 1
    core_grid.addWidget(horizontal_rule_block(), core_row, 0, 1, 2)
    core_row += 1
    add_section(core_grid)

    own_grid = new_section_grid()
    add_line_field(own_grid, "source", 0, 0)
    add_line_field(own_grid, "laptopOwnership", 0, 1)
    add_line_field(own_grid, "accommodationOwnership", 1, 0)
    add_line_field(own_grid, "travelExpenseOwnership", 1, 1)
    add_line_field(own_grid, "perDiemOwnership", 2, 0)
    own_grid.addWidget(horizontal_rule_block(), 3, 0, 1, 2)
    add_scope_ownership_row(own_grid, "extractionScope", "extractionOwnership", 4)
    add_scope_ownership_row(own_grid, "transformationScope", "transformationOwnership", 5)
    add_scope_ownership_row(own_grid, "loadScope", "loadingOwnership", 6)
    apply_scope_gated_ownership_defaults(ctx.scope_check_by_key, ctx.master_combo_by_key)
    own_grid.addWidget(horizontal_rule_block(), 7, 0, 1, 2)
    add_section(own_grid)

    client_grid = new_section_grid()
    add_line_field(client_grid, "endClientName", 0, 0, col_span=2)
    for row, left_key, right_key in (
        (1, "intermediateClient1", "intermediateClient2"),
        (2, "intermediateClient3", "intermediateClient4"),
    ):
        add_line_field(client_grid, left_key, row, 0)
        add_line_field(client_grid, right_key, row, 1)
    client_grid.addWidget(horizontal_rule_block(), 3, 0, 1, 2)
    add_section(client_grid)

    notes_grid = new_section_grid()
    add_line_field(notes_grid, "commentAtEtlzone", 0, 0, col_span=2)
    add_section(notes_grid)

    scroll = DmProjectFormScrollArea(scroll_body)
    scroll.sync_body_geometry()
    ctx.scroll_area = scroll
    return scroll, ctx
