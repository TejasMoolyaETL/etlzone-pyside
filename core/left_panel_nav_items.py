"""Left navigation labels (exact strings used in :class:`ui.widgets.app_left_panel.AppLeftPanel`).

Single place to edit menu item text so :mod:`core.nav_access` stays in sync.
"""

from __future__ import annotations

# User Management sub-options
USER_MANAGEMENT_SUB_OPTIONS = [
    "Users",
    "Reporting Manager",
    "User-Roles Assignment",
    "Reset User Password",
]

# API Management sub-options
API_MANAGEMENT_SUB_OPTIONS = [
    "API: App Id",
    "API: List",
    "API: API-Role Assignment",
    "API: Role-API Assignment",
    "API: Audit Logs",
]

# Org Management sub-options
ORG_MANAGEMENT_SUB_OPTIONS = [
    "Organizations",
    "Business Units",
    "Departments",
    "Positions",
    "Roles",
]

# API Development sub-options
API_SUB_OPTIONS = [
    "API: Projects",
    "API: User Involved",
    "API: Details",
    "API: Validations",
    "API: All in One",
]

# DMT Tracker sub-options
OBJECT_TRACKER_SUB_OPTIONS = [
    "DMT - Category",
    "DMT - Module",
]
