"""Map GET api-access/getAppStepList to left-panel section and sub-item visibility.

Each API row may include ``appIdDescription``. Rows with a missing or empty
``appIdDescription`` are ignored.

* **Sections** (collapsible headers) show if at least one child sub-item is allowed.
* **Sub-items** show if ``allowed`` intersects :data:`LEFT_PANEL_NAV_ITEM_APP_ID_KEYS` for that label.

Each tuple lists accepted ``appIdDescription`` values (OR). Include parent section codes as
fallbacks so a single broad row (e.g. ``API_DEV_PROJECT``) can still unlock all API Dev subs
until the backend sends finer-grained codes.

If the step list is ``None`` (API error / not loaded, or **SADMIN** after login), nothing is
filtered. If the step list is ``[]`` or no descriptions match, gated UI hides.

SADMIN bypass is applied in :func:`app.login_window` by leaving ``set_nav_access_steps(None)`` and
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
# Backend can return any one of the tuple entries. Sub-specific codes are listed first; section
# fallbacks last so coarse grants still work.
LEFT_PANEL_NAV_ITEM_APP_ID_KEYS: dict[str, tuple[str, ...]] = {
    # Org Management
    "Organizations": (
        "ORG_ORGANIZATIONS",
        "ORG_MANAGEMENT",
        "ORG_MGMT",
        "ORGANIZATION_MANAGEMENT",
    ),
    "Business Units": (
        "ORG_BUSINESS_UNITS",
        "ORG_MANAGEMENT",
        "ORG_MGMT",
        "ORGANIZATION_MANAGEMENT",
    ),
    "Departments": (
        "ORG_DEPARTMENTS",
        "ORG_MANAGEMENT",
        "ORG_MGMT",
        "ORGANIZATION_MANAGEMENT",
    ),
    "Positions": (
        "ORG_POSITIONS",
        "ORG_MANAGEMENT",
        "ORG_MGMT",
        "ORGANIZATION_MANAGEMENT",
    ),
    "Roles": (
        "ORG_ROLES",
        "ORG_MANAGEMENT",
        "ORG_MGMT",
        "ORGANIZATION_MANAGEMENT",
    ),
    # User Management
    "Users": (
        "USER_USERS",
        "USER_MANAGEMENT",
        "USER_MGMT",
    ),
    "Reporting Manager": (
        "USER_REPORTING_MANAGER",
        "USER_MANAGEMENT",
        "USER_MGMT",
    ),
    "User-Roles Assignment": (
        "USER_ROLES_ASSIGNMENT",
        "USER_MANAGEMENT",
        "USER_MGMT",
    ),
    "Reset User Password": (
        "USER_RESET_PASSWORD",
        "USER_MANAGEMENT",
        "USER_MGMT",
    ),
    # API Management
    "API: App Id": (
        "API_MGMT_APP_ID",
        "API_MANAGEMENT",
        "API_MGMT",
    ),
    "API: List": (
        "API_MGMT_LIST",
        "API_MANAGEMENT",
        "API_MGMT",
    ),
    "API: API-Role Assignment": (
        "API_MGMT_ROLE_ASSIGNMENT",
        "API_MANAGEMENT",
        "API_MGMT",
    ),
    "API: Role-API Assignment": (
        "API_MGMT_ROLE_API_ASSIGNMENT",
        "API_MANAGEMENT",
        "API_MGMT",
    ),
    "API: Audit Logs": (
        "API_MGMT_AUDIT_LOGS",
        "API_MANAGEMENT",
        "API_MGMT",
    ),
    # DB Design (single top-level item)
    "DB Design Project": (
        "DB_DESIGN_PROJECT",
        "DB_DESIGN",
    ),
    # API Development
    "API: Projects": (
        "API_DEV_PROJECTS",
        "API_DEV_PROJECT",
        "API_DEVELOPMENT",
    ),
    "API: User Involved": (
        "API_DEV_USER_INVOLVED",
        "API_DEV_PROJECT",
        "API_DEVELOPMENT",
    ),
    "API: Details": (
        "API_DEV_DETAILS",
        "API_DEV_PROJECT",
        "API_DEVELOPMENT",
    ),
    "API: Validations": (
        "API_DEV_VALIDATIONS",
        "API_DEV_PROJECT",
        "API_DEVELOPMENT",
    ),
    "API: All in One": (
        "API_DEV_ALL_IN_ONE",
        "API_DEV_PROJECT",
        "API_DEVELOPMENT",
    ),
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


def collect_allowed_descriptions(steps: Iterable[Any]) -> set[str]:
    """Unique non-empty ``appIdDescription`` values from the step list."""
    out: set[str] = set()
    for row in steps:
        s = _row_description(row)
        if s:
            out.add(s)
    return out


def nav_item_visible(label: str, allowed: set[str]) -> bool:
    """True if this nav label should show given the allowed ``appIdDescription`` set."""
    keys = LEFT_PANEL_NAV_ITEM_APP_ID_KEYS.get(label)
    if not keys:
        return True
    return bool(allowed.intersection(keys))


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
