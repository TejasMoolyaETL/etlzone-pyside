"""Map GET api-access/get-app-id-step-id-list to left-panel section and sub-item visibility.

Each API row may include ``appIdDescription``. Rows with a missing or empty
``appIdDescription`` are ignored.

* **Sections** (collapsible headers) show if at least one child sub-item is allowed.
* **Sub-items** show if ``allowed`` intersects :data:`LEFT_PANEL_NAV_ITEM_APP_ID_KEYS` for that label.

Each tuple lists accepted ``appIdDescription`` values (OR). Values match the App Id → Desc
table from ``getAppStepList`` (one primary code per nav item; no coarse section fallbacks).

If the step list is ``None`` (**SADMIN** only), gated nav is not filtered (everything allowed).

If the step list is a ``list`` (including ``[]`` from getAppStepList failure or an empty grant),
each gated submenu is shown only when its configured ``appIdDescription`` value appears in at
least one step row; otherwise it is hidden.

SADMIN bypass is applied in :func:`app.login_window` via ``set_nav_access_steps(None)`` and
skipping the get-app-id-step-id-list call.

Print a sectioned tag list: ``print(core.nav_access.format_nav_app_id_descriptions_by_section())``
or use :func:`all_distinct_nav_app_id_descriptions` for a flat sorted tuple.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from core.left_panel_nav_items import (
    API_MANAGEMENT_SUB_OPTIONS,
    API_SUB_OPTIONS,
    APP_CONFIG_SUB_OPTIONS,
    DATA_MIGRATION_ADMIN_SUB_OPTIONS,
    DATA_MIGRATION_ONBOARDING_SUB_OPTIONS,
    LEAD_MANAGEMENT_SUB_OPTIONS,
    OBJECT_TRACKER_SUB_OPTIONS,
    ORG_MANAGEMENT_SUB_OPTIONS,
    USER_MANAGEMENT_SUB_OPTIONS,
)

# Exact nav label (as emitted by the left panel) → appIdDescription values that show that item.
# Backend returns ``appIdDescription`` matching the App Id → Desc reference table (OR within tuple).
LEFT_PANEL_NAV_ITEM_APP_ID_KEYS: dict[str, tuple[str, ...]] = {
    # Organization Management
    "Organizations": ("ORG_MGMT_ORGANIZATIONS",),
    "Business Units": ("ORG_MGMT_BUSINESS_UNITS",),
    "Departments": ("ORG_MGMT_DEPARTMENTS",),
    "Positions": ("ORG_MGMT_POSITIONS",),
    "Roles": ("ORG_MGMT_ROLES",),
    # User Management
    "Users": ("USER",),
    "Reporting Manager": ("USER_REPORTING_MANAGER",),
    "User-Roles Assignment": ("USER_ROLES_ASSIGNMENT",),
    "Reset User Password": ("USER_RESET_PASSWORD",),
    # API Management
    "API: App Id": ("API_MGMT_APP_ID",),
    "API: List": ("API_MGMT_API_LIST",),
    "API: API-Role Assignment": ("API_MGMT_API_TO_ROLE_ASSIGNMENT",),
    "API: Role-API Assignment": ("API_MGMT_ROLE_TO_API_ASSIGNMENT",),
    "API: Audit Logs": ("API_MGMT_AUDIT_LOGS",),
    # DB Design (single top-level item)
    "DB Design Project": ("DB_DESIGN_PROJECT",),
    # API Development
    "API: Projects": ("API_DEV_PROJECTS", "API_DEV_PROJECT"),
    "API: User Involved": ("API_DEV_USER_INVOLVED",),
    "API: Details": ("API_DEV_DETAILS",),
    "API: Validations": ("API_DEV_VALIDATIONS",),
    "API: Tasks": ("API_DEV_TASKS", "API_DEV_TASK"),
    "API: All in One": ("API_DEV_ALL_IN_ONE",),
    # Lead Management (align appIdDescription with backend getAppStepList when available)
    "Lead: Company": ("LEAD_MGMT_COMPANY",),
    "Lead: Contact Person": ("LEAD_MGMT_CONTACT_PERSON",),
    "Lead: Company Contact Assignment": ("LEAD_MGMT_COMPANY_CONTACT_ASSIGNMENT",),
    "Leads": ("LEAD_MGMT_LEAD",),
    # Data Migration Setup (align appIdDescription with backend getAppStepList when available)
    "DM: Company": ("DM_COMPANY",),
    "DM: Contact Person": ("DM_CONTACT_PERSON",),
    "DM: Company Contact Assignment": ("DM_COMPANY_CONTACT_ASSIGNMENT",),
    "DM: Project": ("DM_PROJECT",),
    "DM: User": ("DMT_USERS",),
    "DM: User Project Mapping": ("DM_USER_PROJECT_MAPPING",),
    # DMT Tracker (align appIdDescription with backend getAppStepList when available)
    "DMT - Category": ("DMT_CATEGORY",),
    "DMT - Module": ("DMT_MODULE",),
    "DMT: User Module Assignment": ("DMT_USER_MODULE_ASSIGNMENT",),
    "DMT - Object": ("DMT_OBJECT",),
    "DMT - Object List Tracker": ("DMT_OBJECT_LIST_TRACKER",),
    "DMT - Issue Tracker": ("DMT_ISSUE_TRACKER",),
    # App Config (align appIdDescription with backend getAppStepList when available)
    "Master Setup Key": ("MASTER_SETUP_KEY",),
    "Master Setup Value": ("MASTER_SETUP_VALUE",),
    "Master Setup Config": ("MASTER_SETUP_CONFIG",),
}

# Per-submenu actions (step-level) keyed by action name -> accepted stepIdDescription/apiName values.
# The backend currently sends these action codes via ``apiName`` in getAppStepList rows.
LEFT_PANEL_ACTION_STEP_ID_KEYS: dict[str, dict[str, tuple[str, ...]]] = {
    "API: Projects": {
        "create": ("api-dev-projects-create",),
        "edit": ("api-dev-projects-edit",),
        "delete": ("api-dev-projects-delete",),
    },
    "API: User Involved": {
        "create": ("api-dev-user-involved-create",),
        "edit": ("api-dev-user-involved-edit",),
        "delete": ("api-dev-user-involved-delete",),
    },
    "API: Details": {
        "create": ("api-dev-details-create",),
        "edit": ("api-dev-details-edit",),
        "delete": ("api-dev-details-delete",),
    },
    "API: Validations": {
        "create": ("api-dev-validations-create",),
        "edit": ("api-dev-validations-edit",),
        "delete": ("api-dev-validations-delete",),
    },
    "API: Tasks": {
        "create": ("api-dev-tasks-create",),
        "edit": ("api-dev-tasks-edit",),
        "delete": ("api-dev-tasks-delete",),
    },
    "API: All in One": {
        "display": ("api-dev-all-in-one-display",),
        "comment_create": ("api-dev-comment-create",),
        "comment_display": ("api-dev-comment-display",),
        "comment_edit": ("api-dev-comment-edit",),
        "comment_delete": ("api-dev-comment-delete",),
    },
    "Lead: Company": {
        "create": ("lead-company-create",),
        "display": ("lead-company-display",),
        "edit": ("lead-company-edit",),
        "delete": ("lead-company-delete",),
    },
    "DM: Company": {
        "create": ("dm-company-create",),
        "display": ("dm-company-display",),
        "edit": ("dm-company-edit",),
        "delete": ("dm-company-delete",),
    },
    "DM: Contact Person": {
        "create": ("dm-contact-person-create",),
        "display": ("dm-contact-person-display",),
        "edit": ("dm-contact-person-edit",),
        "delete": ("dm-contact-person-delete",),
    },
    "DM: Company Contact Assignment": {
        "create": ("dm-company-contact-assignment-create",),
        "display": ("dm-company-contact-assignment-display",),
        "edit": (
            "dm-company-contact-assignment-edit",
            "dm-company-contact-assignment-update",
        ),
        "delete": ("dm-company-contact-assignment-delete",),
    },
    "DM: Project": {
        "create": ("dm-project-create",),
        "display": ("dm-project-display",),
        "edit": ("dm-project-edit",),
        "delete": ("dm-project-delete",),
    },
    "Lead: Contact Person": {
        "create": ("lead-contact-person-create",),
        "display": ("lead-contact-person-display",),
        "edit": ("lead-contact-person-edit",),
        "delete": ("lead-contact-person-delete",),
    },
    "Lead: Company Contact Assignment": {
        "create": ("lead-company-contact-assignment-create",),
        "display": ("lead-company-contact-assignment-display",),
        "edit": (
            "lead-company-contact-assignment-edit",
            "lead-company-contact-assignment-update",
        ),
        "delete": ("lead-company-contact-assignment-delete",),
    },
    "Leads": {
        "create": ("lead-create",),
        "display": ("lead-display",),
        "edit": ("lead-edit",),
        "delete": ("lead-delete",),
        "comment_create": ("lead-comment-create",),
        "comment_display": ("lead-comment-display",),
        "comment_edit": ("lead-comment-edit",),
        "comment_delete": ("lead-comment-delete",),
    },
    "DMT: User Module Assignment": {
        "create": ("dmt-user-module-assign",),
        "display": ("dmt-user-module-display",),
        "edit": ("dmt-user-module-edit",),
        "change_status": ("dmt-user-module-change-status",),
        "delete": ("dmt-user-module-remove",),
    },
}


def all_distinct_nav_app_id_descriptions() -> tuple[str, ...]:
    """Sorted unique ``appIdDescription`` strings referenced for left-nav items (for docs / API)."""
    s: set[str] = set()
    for tup in LEFT_PANEL_NAV_ITEM_APP_ID_KEYS.values():
        s.update(tup)
    return tuple(sorted(s))


def format_nav_app_id_descriptions_by_section() -> str:
    """Human-readable reference: section → menu label → accepted ``appIdDescription`` values (OR)."""
    lines: list[str] = []
    groups: list[tuple[str, list[str]]] = [
        ("Org Management", list(ORG_MANAGEMENT_SUB_OPTIONS)),
        ("User Management", list(USER_MANAGEMENT_SUB_OPTIONS)),
        ("API Management", list(API_MANAGEMENT_SUB_OPTIONS)),
        ("API Development", list(API_SUB_OPTIONS)),
        ("DB Design Project", ["DB Design Project"]),
        ("Lead Management", list(LEAD_MANAGEMENT_SUB_OPTIONS)),
        ("Data Migration Onboarding", list(DATA_MIGRATION_ONBOARDING_SUB_OPTIONS)),
        ("Data Migration - Admin", list(DATA_MIGRATION_ADMIN_SUB_OPTIONS)),
        ("Data Migration Tracker", list(OBJECT_TRACKER_SUB_OPTIONS)),
        ("App Config", list(APP_CONFIG_SUB_OPTIONS)),
    ]
    for section_title, labels in groups:
        lines.append(f"[{section_title}]")
        for lbl in labels:
            keys = LEFT_PANEL_NAV_ITEM_APP_ID_KEYS.get(lbl, ())
            key_str = ", ".join(keys) if keys else "(none)"
            lines.append(f"  - {lbl}")
            lines.append(f"      {key_str}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _row_description(row: Any) -> str | None:
    if not isinstance(row, dict):
        return None
    d = row.get("appIdDescription") or row.get("app_id_description")
    if d is None:
        return None
    s = str(d).strip()
    return s if s else None


def _row_action_name(row: Any) -> str | None:
    """Action code from step rows (e.g. ``apiName``/``stepIdDescription``)."""
    if not isinstance(row, dict):
        return None
    v = (
        row.get("apiName")
        or row.get("api_name")
        or row.get("stepIdDescription")
        or row.get("step_id_description")
    )
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None


def collect_allowed_descriptions(steps: Iterable[Any]) -> set[str]:
    """Unique non-empty ``appIdDescription`` values from the step list."""
    out: set[str] = set()
    for row in steps:
        s = _row_description(row)
        if s:
            out.add(s)
    return out


def collect_allowed_action_names(steps: Iterable[Any]) -> set[str]:
    """Unique non-empty action names (apiName / stepIdDescription) from the step list."""
    out: set[str] = set()
    for row in steps:
        s = _row_action_name(row)
        if s:
            out.add(s)
    return out


def nav_item_visible(label: str, allowed: set[str]) -> bool:
    """True if this nav label should show given the allowed ``appIdDescription`` set."""
    keys = LEFT_PANEL_NAV_ITEM_APP_ID_KEYS.get(label)
    if not keys:
        return True
    return bool(allowed.intersection(keys))


def nav_action_visible(label: str, action: str, allowed_actions: set[str]) -> bool:
    """True if a submenu action should be enabled for given step action codes."""
    action_map = LEFT_PANEL_ACTION_STEP_ID_KEYS.get(label, {})
    keys = action_map.get(action, ())
    if not keys:
        return True
    return bool(allowed_actions.intersection(keys))


def nav_action_visible_from_steps(label: str, action: str, steps: Iterable[Any]) -> bool:
    """True when at least one step row matches both submenu appIdDescription and action apiName.

    This enforces row-level pairing: the same ``getAppStepList`` row must carry
    the submenu's ``appIdDescription`` and the action code (``apiName`` / step id).
    """
    app_keys = LEFT_PANEL_NAV_ITEM_APP_ID_KEYS.get(label, ())
    action_map = LEFT_PANEL_ACTION_STEP_ID_KEYS.get(label, {})
    action_keys = action_map.get(action, ())
    if not action_keys:
        return True
    if not app_keys:
        return False
    for row in steps:
        app_desc = _row_description(row)
        action_name = _row_action_name(row)
        if not app_desc or not action_name:
            continue
        if app_desc in app_keys and action_name in action_keys:
            return True
    return False


@dataclass(frozen=True)
class LeftPanelAccessState:
    show_org_management: bool
    show_user_management: bool
    show_api_management: bool
    show_db_design_project: bool
    show_api_development: bool
    show_lead_management: bool
    show_data_migration_onboarding: bool
    show_data_migration_admin: bool
    show_dmt_tracker: bool
    show_app_config: bool
    api_development_title: str
    unrestricted: bool
    """When True, ignore ``visible_gated_nav_labels`` and show every sub-item."""
    visible_gated_nav_labels: frozenset[str]
    """When not unrestricted, sub-item ``label`` is shown iff ``label in visible_gated_nav_labels``."""


def build_left_panel_access_state(steps: list[dict[str, Any]] | None) -> LeftPanelAccessState:
    """``steps is None`` → unrestricted. Otherwise filter sections and sub-items by descriptions."""
    default_title = "API Development"
    empty_visible: frozenset[str] = frozenset()
    if steps is None:
        return LeftPanelAccessState(
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            True,
            default_title,
            True,
            empty_visible,
        )

    allowed = collect_allowed_descriptions(steps)
    gated_labels = tuple(LEFT_PANEL_NAV_ITEM_APP_ID_KEYS.keys())
    visible = frozenset(lbl for lbl in gated_labels if nav_item_visible(lbl, allowed))

    show_org = any(nav_item_visible(lbl, allowed) for lbl in ORG_MANAGEMENT_SUB_OPTIONS)
    show_user = any(nav_item_visible(lbl, allowed) for lbl in USER_MANAGEMENT_SUB_OPTIONS)
    show_api_mgmt = any(nav_item_visible(lbl, allowed) for lbl in API_MANAGEMENT_SUB_OPTIONS)
    show_db = nav_item_visible("DB Design Project", allowed)
    show_api_dev = any(nav_item_visible(lbl, allowed) for lbl in API_SUB_OPTIONS)
    show_lead_mgmt = any(nav_item_visible(lbl, allowed) for lbl in LEAD_MANAGEMENT_SUB_OPTIONS)
    show_dm_onboarding = any(nav_item_visible(lbl, allowed) for lbl in DATA_MIGRATION_ONBOARDING_SUB_OPTIONS)
    show_dm_admin = any(nav_item_visible(lbl, allowed) for lbl in DATA_MIGRATION_ADMIN_SUB_OPTIONS)
    show_dmt = any(nav_item_visible(lbl, allowed) for lbl in OBJECT_TRACKER_SUB_OPTIONS)
    show_app_cfg = any(nav_item_visible(lbl, allowed) for lbl in APP_CONFIG_SUB_OPTIONS)

    return LeftPanelAccessState(
        show_org,
        show_user,
        show_api_mgmt,
        show_db,
        show_api_dev,
        show_lead_mgmt,
        show_dm_onboarding,
        show_dm_admin,
        show_dmt,
        show_app_cfg,
        default_title,
        False,
        visible,
    )
