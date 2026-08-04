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
    "API: Tasks",
    "API: All in One",
]

# Lead Management sub-options
LEAD_MANAGEMENT_SUB_OPTIONS = [
    "Lead: Company",
    "Lead: Contact Person",
    "Lead: Company Contact Assignment",
    "Leads",
]

# Data Migration Onboarding sub-options
DATA_MIGRATION_ONBOARDING_SUB_OPTIONS = [
    "DM: Company",
    "DM: Contact Person",
    "DM: Company Contact Assignment",
    "DM: Project",
]

# Data Migration - Admin sub-options
DATA_MIGRATION_ADMIN_SUB_OPTIONS = [
    "DM: User",
    "DM: User Project Mapping",
]

# DMT Tracker sub-options
OBJECT_TRACKER_SUB_OPTIONS = [
    "DMT - Category",
    "DMT - Module",
    "DMT: User Module Assignment",
    "DMT - Object",
    "DMT - Object List Tracker",
    "DMT - Issue Tracker",
]

# ETL sub-options
ETL_SUB_OPTIONS = [
    "Connections",
    "Scan",
    "Import Metadata",
    "Extraction",
    "Job Logs",
]

# Excel (below ETL)
EXCEL_SUB_OPTIONS = [
    "Import State",
    "Upload File",
    "Extract File",
]

# Data Transformation (below Excel)
DATA_TRANSFORMATION_SUB_OPTIONS = [
    "DT: Object",
    "DT: Job",
    "DT: Work Flow",
    "DT: Flow",
    "DT: Step",
]

MASTER_SETUP_ITEM = "Master Setup Value"
MASTER_SETUP_CONFIG_ITEM = "Master Setup Config"
MASTER_SETUP_KEY_ITEM = "Master Setup Key"
APP_CONFIG_SUB_OPTIONS = [MASTER_SETUP_KEY_ITEM, MASTER_SETUP_ITEM, MASTER_SETUP_CONFIG_ITEM]
