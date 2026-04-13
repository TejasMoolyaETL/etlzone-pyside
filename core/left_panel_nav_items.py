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
    "API: Audit Logs",
    "API: Login History",
]

# Org Management sub-options
ORG_MANAGEMENT_SUB_OPTIONS = [
    "Organizations",
    "Business Units",
    "Departments",
    "Positions",
    "Roles",
]

# App Access Control sub-options
APP_ACCESS_CONTROL_SUB_OPTIONS = [
    "App: Permissions",
    "App: Role-Permission Assignment",
]

# API Development sub-options
API_SUB_OPTIONS = [
    "API: Projects",
    "API: User Involved",
    "API: Details",
    "API: Validations",
    "API: All in One",
]
