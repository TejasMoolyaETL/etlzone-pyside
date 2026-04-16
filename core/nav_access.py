"""Map GET api-access/getAppStepList to left-panel section and sub-item visibility.

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
skipping the getAppStepList call.

Print a sectioned tag list: ``print(core.nav_access.format_nav_app_id_descriptions_by_section())``
or use :func:`all_distinct_nav_app_id_descriptions` for a flat sorted tuple.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from core.left_panel_nav_items import (
    API_MANAGEMENT_SUB_OPTIONS,
    API_SUB_OPTIONS,
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
    "API: All in One": ("API_DEV_ALL_IN_ONE",),
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
    "API: All in One": {
        "display": ("api-dev-all-in-one-display",),
        "comment_create": ("api-dev-comment-create",),
        "comment_display": ("api-dev-comment-display",),
        "comment_edit": ("api-dev-comment-edit",),
        "comment_delete": ("api-dev-comment-delete",),
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

    return LeftPanelAccessState(
        show_org,
        show_user,
        show_api_mgmt,
        show_db,
        show_api_dev,
        default_title,
        False,
        visible,
    )
