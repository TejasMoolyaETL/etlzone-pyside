"""Shared constants for Data Transformation UI."""

from __future__ import annotations

SECTION_LABELS: tuple[str, ...] = (
    "Object",
    "Job",
    "Work Flow",
    "Flow",
    "Step",
)

SECTION_HINTS: tuple[str, ...] = (
    "Define business objects that group related transformation jobs.",
    "Manage jobs per object that group related work flows.",
    "Compose work flows as ordered sequences of flows for each job.",
    "Select a work flow and manage the flows defined for that work flow.",
    "Use Switch Flow to choose a work flow and flow, then complete the step-by-step setup.",
)

NAV_SECTION_OBJECT = 0
NAV_SECTION_JOB = 1
NAV_SECTION_WORKFLOW = 2
NAV_SECTION_FLOW = 3
NAV_SECTION_STEP = 4

NAV_ITEM_TO_SECTION: dict[str, int] = {
    "DT: Object": NAV_SECTION_OBJECT,
    "DT: Job": NAV_SECTION_JOB,
    "DT: Work Flow": NAV_SECTION_WORKFLOW,
    "DT: Flow": NAV_SECTION_FLOW,
    "DT: Step": NAV_SECTION_STEP,
}

# Backward-compatible alias used by dashboard_window
NAV_ITEM_TO_TAB = NAV_ITEM_TO_SECTION

# Legacy step labels (flow workspace sub-steps)
TAB_LABELS: tuple[str, ...] = (
    "Source tables",
    "Target table",
    "Field mapping",
)

STEP_HINTS: tuple[str, ...] = (
    "Choose a connection and select one or more imported tables as transformation sources.",
    "Select the target connection, table, and load columns that will receive mapped output.",
    "Map source fields to target columns and define expressions for the transformation output.",
)

MAPPING_TABLE_HEADERS: tuple[str, ...] = (
    "Target column",
    "Source table",
    "Source column",
    "Expression",
    "Output name",
)

CARD_STYLE = (
    "QFrame#dtCard { background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; }"
)

SUMMARY_BAR_STYLE = (
    "QFrame#dtSummary { background: #f8fafc; border: 1px solid #e2e8f0; "
    "border-radius: 8px; padding: 4px; }"
)

PANEL_TITLE_STYLE = "font-size: 11px; font-weight: 600; color: #334155;"
PANEL_HINT_STYLE = "font-size: 11px; color: #64748b;"

STEP_SETUP_LABELS: tuple[str, ...] = (
    "Source",
    "Target",
    "Column",
    "Join",
    "Transform",
)

STEP_SETUP_HINTS: tuple[str, ...] = (
    "Add one or more source tables. Each needs a connection, table, alias, and sequence.",
    "Choose the connection and target table where transformed data will be loaded.",
    "Select a source alias, check the columns to map, then click Save.",
    "If you have multiple sources, define how they are joined. Skip when using one source.",
    "Add transformation rules (trim, replace, etc.) on mapped columns.",
)
