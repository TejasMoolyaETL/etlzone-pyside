"""Central configuration.

Change **only** `API_BASE_URL` to point the whole app to a different backend.
You can also override it without code changes using the env var `ETL_API_BASE_URL`.
"""

from __future__ import annotations

import os

# Single source of truth for backend base URL.
API_BASE_URL = os.getenv("ETL_API_BASE_URL", "http://72.62.74.158:9091").rstrip("/")


def _http_base_to_ws_base(http_base: str) -> str:
    b = (http_base or "").strip().rstrip("/")
    if b.startswith("https://"):
        return "wss://" + b[len("https://") :]
    if b.startswith("http://"):
        return "ws://" + b[len("http://") :]
    return b


# App push WebSocket (plain WebSocket, not STOMP).
# Prefer ETL_WS_URL / ETL_WS_PATH; ETL_WS_STOMP_* still work for older setups.
_WS_PATH = (
    os.getenv("ETL_WS_PATH", os.getenv("ETL_WS_STOMP_PATH", "/ws")).strip() or "/ws"
)
_WS_URL_OVERRIDE = os.getenv(
    "ETL_WS_URL", os.getenv("ETL_WS_STOMP_URL", "")
).strip()


def app_updates_websocket_url() -> str:
    """Full WebSocket URL (e.g. ws://host:port/ws)."""
    if _WS_URL_OVERRIDE:
        return _WS_URL_OVERRIDE.rstrip("/")
    base = _http_base_to_ws_base(API_BASE_URL)
    path = _WS_PATH if _WS_PATH.startswith("/") else f"/{_WS_PATH}"
    return f"{base}{path}"


def app_updates_websocket_origin() -> str:
    """Origin header for WebSocket handshake (CORS / security filters)."""
    o = os.getenv("ETL_WS_ORIGIN", "").strip()
    return o if o else API_BASE_URL


def app_updates_websocket_connect_message_template() -> str:
    """If non-empty, sent as the first text frame after connect; `{token}` is replaced."""
    return os.getenv("ETL_WS_CONNECT_MESSAGE", "").strip()


def app_updates_websocket_use_auth_header() -> bool:
    """Send Authorization: Bearer on the handshake (default true). Set ETL_WS_AUTH_HEADER=0 to skip."""
    return os.getenv("ETL_WS_AUTH_HEADER", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def app_updates_websocket_enabled() -> bool:
    """When false, the dashboard does not open the app-updates WebSocket. Set ETL_WS_ENABLED=0 to skip."""
    return os.getenv("ETL_WS_ENABLED", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )

# Login auth endpoint (full path).
LOGIN_URL = f"{API_BASE_URL}/api/auth/login"

# After login: left-nav access from app/step list (GET, Bearer JWT).
GET_APP_STEP_LIST_PATH = os.getenv(
    "ETL_GET_APP_STEP_LIST_PATH", "api-access/get-app-id-step-id-list"
).strip().lstrip("/")

# Profile update endpoint path (override if backend uses different path).
UPDATE_PROFILE_PATH = os.getenv("ETL_UPDATE_PROFILE_PATH", "api/update-profile").strip()

# User list / create / update / delete (override with ETL_* env vars if backend differs).
GET_ALL_USERS_PATH = os.getenv("ETL_GET_ALL_USERS_PATH", "api/user/get-all-user").strip()
CREATE_USER_PATH = os.getenv("ETL_CREATE_USER_PATH", "api/user/create-user").strip()
# UPDATE_USER_PATH also used for profile update.
UPDATE_USER_PATH = os.getenv("ETL_UPDATE_USER_PATH", "api/user/update-user-by-id").strip()
DELETE_USER_PATH = os.getenv("ETL_DELETE_USER_PATH", "api/user/delete-user-by-id").strip()
RESET_USER_PASSWORD_PATH = os.getenv(
    "ETL_RESET_USER_PASSWORD_PATH", "api/user/reset-user-password"
).strip()
UPDATE_USER_STATUS_PATH = os.getenv(
    "ETL_UPDATE_USER_STATUS_PATH", "api/update-user-status-by-id"
).strip()
UPDATE_USER_ROLE_STATUS_PATH = os.getenv(
    "ETL_UPDATE_USER_ROLE_STATUS_PATH", "api/update-user-role-status-by-id"
).strip()

# DMT User (override with ETL_DMT_USER_* env vars if backend differs).
DMT_USER_GET_ALL_PATH = os.getenv(
    "ETL_DMT_USER_GET_ALL_PATH", "api/dm-project/user/get-all-user"
).strip().lstrip("/")
DMT_USER_GET_BY_ID_PREFIX = os.getenv(
    "ETL_DMT_USER_GET_BY_ID_PREFIX", "api/dmt/user/get-user-by-id"
).strip().lstrip("/").rstrip("/")
DMT_USER_CREATE_PATH = os.getenv(
    "ETL_DMT_USER_CREATE_PATH", "api/dm-project/user/create"
).strip().lstrip("/")
DMT_USER_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_DMT_USER_UPDATE_BY_ID_PREFIX", "api/dm-project/user/update-user-by-id"
).strip().lstrip("/").rstrip("/")
DMT_USER_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_DMT_USER_DELETE_BY_ID_PREFIX", "api/dm-project/user/delete-user-by-id"
).strip().lstrip("/").rstrip("/")
# POST copy-from-app-user: JSON array of IDs. Override with ETL_DMT_USER_COPY_FROM_USER_PATH or legacy ETL_DMT_USER_COPY_FROM_APPUSER_PATH.
DMT_USER_COPY_FROM_APPUSER_PATH = os.getenv(
    "ETL_DMT_USER_COPY_FROM_USER_PATH",
    os.getenv(
        "ETL_DMT_USER_COPY_FROM_APPUSER_PATH",
        "api/dm-project/user/copy-from-app-user",
    ),
).strip().lstrip("/")
DMT_USER_UPLOAD_PATH = os.getenv(
    "ETL_DMT_USER_UPLOAD_PATH", "api/dm-project/user/upload-users"
).strip().lstrip("/")

# DM Project (override with ETL_DM_PROJECT_* env vars if backend differs).
DM_PROJECT_GET_ALL_PATH = os.getenv(
    "ETL_DM_PROJECT_GET_ALL_PATH",
    "api/dm-project/get-all",
).strip().lstrip("/")
DM_PROJECT_GET_BY_ID_PREFIX = os.getenv(
    "ETL_DM_PROJECT_GET_BY_ID_PREFIX",
    "api/dm-project",
).strip().lstrip("/").rstrip("/")
DM_PROJECT_CREATE_PATH = os.getenv(
    "ETL_DM_PROJECT_CREATE_PATH",
    "api/dm-project/create",
).strip().lstrip("/")
DM_PROJECT_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_DM_PROJECT_UPDATE_BY_ID_PREFIX",
    "api/dm-project/update",
).strip().lstrip("/").rstrip("/")
DM_PROJECT_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_DM_PROJECT_DELETE_BY_ID_PREFIX",
    "api/dm-project/delete",
).strip().lstrip("/").rstrip("/")
DM_PROJECT_GET_CONTACT_ASSIGNED_PREFIX = os.getenv(
    "ETL_DM_PROJECT_GET_CONTACT_ASSIGNED_PREFIX",
    "api/dm-project/get-contact-assigned",
).strip().lstrip("/").rstrip("/")

# DM User–Project mapping (override with ETL_DM_USER_PROJECT_* env vars if backend differs).
DM_USER_PROJECT_GET_BY_PROJECT_ID_PREFIX = os.getenv(
    "ETL_DM_USER_PROJECT_GET_BY_PROJECT_ID_PREFIX",
    "api/dm-user-project/get-user-by-project-id",
).strip().lstrip("/").rstrip("/")
DM_USER_PROJECT_ASSIGN_PATH = os.getenv(
    "ETL_DM_USER_PROJECT_ASSIGN_PATH",
    "api/dm-user-project/assign",
).strip().lstrip("/")
DM_USER_PROJECT_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_DM_USER_PROJECT_DELETE_BY_ID_PREFIX",
    "api/dm-user-project/delete-by-id",
).strip().lstrip("/").rstrip("/")
DM_USER_PROJECT_CHANGE_STATUS_BY_ID_PREFIX = os.getenv(
    "ETL_DM_USER_PROJECT_CHANGE_STATUS_BY_ID_PREFIX",
    "api/dm-user-project/change-status-by-id",
).strip().lstrip("/").rstrip("/")

# DMT User–Module assignment (override with ETL_DMT_USER_MODULE_* env vars if backend differs).
DMT_USER_MODULE_ASSIGN_PATH = os.getenv(
    "ETL_DMT_USER_MODULE_ASSIGN_PATH",
    "api/dmt/user-module/assign",
).strip().lstrip("/")
DMT_USER_MODULE_CHANGE_STATUS_BY_ID_PREFIX = os.getenv(
    "ETL_DMT_USER_MODULE_CHANGE_STATUS_BY_ID_PREFIX",
    "api/dmt/user-module/change-status-by-id",
).strip().lstrip("/").rstrip("/")
DMT_USER_MODULE_REMOVE_ASSIGNMENT_PATH = os.getenv(
    "ETL_DMT_USER_MODULE_REMOVE_ASSIGNMENT_PATH",
    "api/dmt/user-module/remove-assignment",
).strip().lstrip("/")
DMT_USER_MODULE_GET_BY_USER_ID_PREFIX = os.getenv(
    "ETL_DMT_USER_MODULE_GET_BY_USER_ID_PREFIX",
    "api/dm-project/user/get-user-modules",
).strip().lstrip("/").rstrip("/")

# DMT Object List Tracker (override with ETL_DMT_OBJECT_TRACKER_* if backend differs).
DMT_OBJECT_TRACKER_GET_ALL_PATH = os.getenv(
    "ETL_DMT_OBJECT_TRACKER_GET_ALL_PATH",
    "api/dmt/object-tracker/get-all-object-tracker",
).strip().lstrip("/")
DMT_OBJECT_TRACKER_CREATE_PATH = os.getenv(
    "ETL_DMT_OBJECT_TRACKER_CREATE_PATH",
    "api/dmt/object-tracker/create",
).strip().lstrip("/")
DMT_OBJECT_TRACKER_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_DMT_OBJECT_TRACKER_UPDATE_BY_ID_PREFIX",
    "api/dmt/object-tracker/update-by-id",
).strip().lstrip("/").rstrip("/")
DMT_OBJECT_TRACKER_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_DMT_OBJECT_TRACKER_DELETE_BY_ID_PREFIX",
    "api/dmt/object-tracker/delete-by-id",
).strip().lstrip("/").rstrip("/")

# DMT Issue Tracker (override with ETL_DMT_ISSUE_TRACKER_* if backend differs).
DMT_ISSUE_TRACKER_GET_ALL_PATH = os.getenv(
    "ETL_DMT_ISSUE_TRACKER_GET_ALL_PATH",
    "api/dmt/issue-tracker/get-all-issue-tracker",
).strip().lstrip("/")
DMT_ISSUE_TRACKER_CREATE_PATH = os.getenv(
    "ETL_DMT_ISSUE_TRACKER_CREATE_PATH",
    "api/dmt/issue-tracker/create",
).strip().lstrip("/")
DMT_ISSUE_TRACKER_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_DMT_ISSUE_TRACKER_UPDATE_BY_ID_PREFIX",
    "api/dmt/issue-tracker/update-by-id",
).strip().lstrip("/").rstrip("/")
DMT_ISSUE_TRACKER_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_DMT_ISSUE_TRACKER_DELETE_BY_ID_PREFIX",
    "api/dmt/issue-tracker/delete-by-id",
).strip().lstrip("/").rstrip("/")

# DMT object-tracker comments (override with ETL_DMT_COMMENT_* if backend differs).
# Legacy ``ETL_DMT_COMMENT_GET_BY_ISSUE_ID_PREFIX`` still applies if the new var is unset.
DMT_COMMENT_GET_BY_OBJECT_ID_PREFIX = (
    os.getenv("ETL_DMT_COMMENT_GET_BY_OBJECT_ID_PREFIX")
    or os.getenv("ETL_DMT_COMMENT_GET_BY_ISSUE_ID_PREFIX")
    or "api/dmt/comment/get-comment-by-object-id"
).strip().lstrip("/").rstrip("/")
DMT_COMMENT_CREATE_PATH = os.getenv(
    "ETL_DMT_COMMENT_CREATE_PATH",
    "api/dmt/comment/create",
).strip().lstrip("/")
DMT_COMMENT_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_DMT_COMMENT_UPDATE_BY_ID_PREFIX",
    "api/dmt/comment/update-by-id",
).strip().lstrip("/").rstrip("/")
DMT_COMMENT_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_DMT_COMMENT_DELETE_BY_ID_PREFIX",
    "api/dmt/comment/delete-by-id",
).strip().lstrip("/").rstrip("/")

# User role assignment — assign / update-by-id / delete-by-id (override with ETL_* if backend differs).
USER_ROLE_ASSIGN_PATH = os.getenv(
    "ETL_USER_ROLE_ASSIGN_PATH", "api/user-role-assignment/assign"
).strip()
USER_ROLE_ASSIGNMENT_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_USER_ROLE_ASSIGNMENT_UPDATE_BY_ID_PREFIX",
    "api/user-role-assignment/update-by-id",
).strip().rstrip("/")
USER_ROLE_ASSIGNMENT_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_USER_ROLE_ASSIGNMENT_DELETE_BY_ID_PREFIX",
    "api/user-role-assignment/delete-by-id",
).strip().rstrip("/")

# User hierarchy / reporting (override with ETL_* if backend differs).
USER_HIERARCHY_GET_ALL_PATH = os.getenv(
    "ETL_USER_HIERARCHY_GET_ALL_PATH", "api/user-hierarchy/get-all"
).strip()
USER_HIERARCHY_ASSIGN_PATH = os.getenv(
    "ETL_USER_HIERARCHY_ASSIGN_PATH", "api/user-hierarchy/assign"
).strip()
USER_HIERARCHY_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_USER_HIERARCHY_UPDATE_BY_ID_PREFIX", "api/user-hierarchy/update-by-id"
).strip().rstrip("/")
USER_HIERARCHY_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_USER_HIERARCHY_DELETE_BY_ID_PREFIX", "api/user-hierarchy/delete-by-id"
).strip().rstrip("/")

# Combined API details + validations (API: All in One page).
API_DETAILS_ALL_IN_ONE_PATH = os.getenv(
    "ETL_API_DETAILS_ALL_IN_ONE_PATH", "api/get-all-api-details/all-in-one"
).strip()

# API Management — API list
API_MGMT_API_LIST_GET_ALL_PATH = os.getenv(
    "ETL_API_MGMT_API_LIST_GET_ALL_PATH", "api/api-mgmt/api-list/get-all-api"
).strip()
API_MGMT_API_LIST_CREATE_PATH = os.getenv(
    "ETL_API_MGMT_API_LIST_CREATE_PATH", "api/api-mgmt/api-list/create"
).strip()
API_MGMT_API_LIST_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_API_MGMT_API_LIST_UPDATE_BY_ID_PREFIX", "api/api-mgmt/api-list/update-api-by-id"
).strip().rstrip("/")
API_MGMT_API_LIST_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_API_MGMT_API_LIST_DELETE_BY_ID_PREFIX", "api/api-mgmt/api-list/delete-api-by-id"
).strip().rstrip("/")
API_MGMT_APP_ID_GET_ALL_PATH = os.getenv(
    "ETL_API_MGMT_APP_ID_GET_ALL_PATH", "api/api-mgmt/app-id/get-all-app-id"
).strip()
API_MGMT_APP_ID_CREATE_PATH = os.getenv(
    "ETL_API_MGMT_APP_ID_CREATE_PATH", "api/api-mgmt/app-id/create"
).strip()
API_MGMT_APP_ID_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_API_MGMT_APP_ID_UPDATE_BY_ID_PREFIX", "api/api-mgmt/app-id/update-by-app-id"
).strip().rstrip("/")
API_MGMT_APP_ID_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_API_MGMT_APP_ID_DELETE_BY_ID_PREFIX", "api/api-mgmt/app-id/delete-by-app-id"
).strip().rstrip("/")

# API detail delete path: api/delete-api-detail-by-id/{id} where id is internal API Id
DELETE_API_DETAIL_PATH = os.getenv(
    "ETL_DELETE_API_DETAIL_PATH", "api/delete-api-detail-by-id"
).strip()

# API validation delete path: api/delete-api-validation-by-id/{api_validation_id}
DELETE_API_VALIDATION_PATH = os.getenv(
    "ETL_DELETE_API_VALIDATION_PATH", "api/delete-api-validation-by-id"
).strip()

# Comment API (path prefix + id): {COMMENT_ADD_PATH}/{api_validation_id}
COMMENT_ADD_PATH = os.getenv("ETL_COMMENT_ADD_PATH", "comment/add-comment").strip().rstrip("/")
COMMENT_GET_BY_ID_PATH = os.getenv(
    "ETL_COMMENT_GET_BY_ID_PATH", "comment/get-comment-by-id"
).strip().rstrip("/")
COMMENT_GET_ALL_BY_VALIDATION_ID_PATH = os.getenv(
    "ETL_COMMENT_GET_ALL_BY_VALIDATION_ID_PATH", "comment/get-comment-by-id"
).strip().rstrip("/")
COMMENT_UPDATE_BY_ID_PATH = os.getenv(
    "ETL_COMMENT_UPDATE_BY_ID_PATH", "comment/update-by-id"
).strip().rstrip("/")
COMMENT_DELETE_BY_ID_PATH = os.getenv(
    "ETL_COMMENT_DELETE_BY_ID_PATH", "comment/delete-by-id"
).strip().rstrip("/")

# Lead Management — company API path segments (under ``API_BASE_URL``).
LEAD_MGMT_COMPANY_CREATE_PATH = os.getenv(
    "ETL_LEAD_MGMT_COMPANY_CREATE_PATH", "api/lead-mgmt/company/create"
).strip().lstrip("/")
LEAD_MGMT_COMPANY_GET_ALL_PATH = os.getenv(
    "ETL_LEAD_MGMT_COMPANY_GET_ALL_PATH", "api/lead-mgmt/company/get-all-company"
).strip().lstrip("/")
LEAD_MGMT_COMPANY_DELETE_PATH_PREFIX = os.getenv(
    "ETL_LEAD_MGMT_COMPANY_DELETE_PATH_PREFIX", "api/lead-mgmt/company/delete-company-by-id"
).strip().lstrip("/")
LEAD_MGMT_COMPANY_UPDATE_PATH_PREFIX = os.getenv(
    "ETL_LEAD_MGMT_COMPANY_UPDATE_PATH_PREFIX", "api/lead-mgmt/company/update-company-by-id"
).strip().lstrip("/")
LEAD_MGMT_COMPANY_CONTACT_GET_BY_COMPANY_PREFIX = os.getenv(
    "ETL_LEAD_MGMT_COMPANY_CONTACT_GET_BY_COMPANY_PREFIX",
    "api/lead-mgmt/company-contact/get-contact-by-company-id",
).strip().lstrip("/").rstrip("/")

# Data Migration — company API path segments (under ``API_BASE_URL``).
DM_COMPANY_CREATE_PATH = os.getenv(
    "ETL_DM_COMPANY_CREATE_PATH", "api/dm/company/create"
).strip().lstrip("/")
DM_COMPANY_GET_ALL_PATH = os.getenv(
    "ETL_DM_COMPANY_GET_ALL_PATH", "api/dm/company/get-all-company"
).strip().lstrip("/")
DM_COMPANY_DELETE_PATH_PREFIX = os.getenv(
    "ETL_DM_COMPANY_DELETE_PATH_PREFIX", "api/dm/company/delete-company-by-id"
).strip().lstrip("/")
DM_COMPANY_UPDATE_PATH_PREFIX = os.getenv(
    "ETL_DM_COMPANY_UPDATE_PATH_PREFIX", "api/dm/company/update-company-by-id"
).strip().lstrip("/")

# Data Migration — contact person API path segments (under ``API_BASE_URL``).
DM_CONTACT_PERSON_GET_ALL_PATH = os.getenv(
    "ETL_DM_CONTACT_PERSON_GET_ALL_PATH",
    "api/dm/contact-person/get-all-contact-person",
).strip().lstrip("/")
DM_CONTACT_PERSON_CREATE_PATH = os.getenv(
    "ETL_DM_CONTACT_PERSON_CREATE_PATH",
    "api/dm/contact-person/create",
).strip().lstrip("/")
DM_CONTACT_PERSON_UPDATE_PATH_PREFIX = os.getenv(
    "ETL_DM_CONTACT_PERSON_UPDATE_PATH_PREFIX",
    "api/dm/contact-person/update-contact-person-by-id",
).strip().lstrip("/")
DM_CONTACT_PERSON_DELETE_PATH_PREFIX = os.getenv(
    "ETL_DM_CONTACT_PERSON_DELETE_PATH_PREFIX",
    "api/dm/contact-person/delete-contact-person-by-id",
).strip().lstrip("/")

# Data Migration — company–contact assignment API path segments (under ``API_BASE_URL``).
DM_COMPANY_CONTACT_ASSIGN_PATH = os.getenv(
    "ETL_DM_COMPANY_CONTACT_ASSIGN_PATH",
    "api/dm/company-contact/assign",
).strip().lstrip("/")
DM_COMPANY_CONTACT_UPDATE_STATUS_PATH_PREFIX = os.getenv(
    "ETL_DM_COMPANY_CONTACT_UPDATE_STATUS_PATH_PREFIX",
    "api/dm/company-contact/update-status-by-id",
).strip().lstrip("/")
DM_COMPANY_CONTACT_DELETE_PATH_PREFIX = os.getenv(
    "ETL_DM_COMPANY_CONTACT_DELETE_PATH_PREFIX",
    "api/dm/company-contact/delete-by-id",
).strip().lstrip("/")

# Lead Management — contact person API path segments (under ``API_BASE_URL``).
LEAD_MGMT_CONTACT_PERSON_GET_ALL_PATH = os.getenv(
    "ETL_LEAD_MGMT_CONTACT_PERSON_GET_ALL_PATH",
    "api/lead-mgmt/contact-person/get-all-contact-person",
).strip().lstrip("/")
LEAD_MGMT_CONTACT_PERSON_CREATE_PATH = os.getenv(
    "ETL_LEAD_MGMT_CONTACT_PERSON_CREATE_PATH",
    "api/lead-mgmt/contact-person/create",
).strip().lstrip("/")
LEAD_MGMT_CONTACT_PERSON_UPDATE_PATH_PREFIX = os.getenv(
    "ETL_LEAD_MGMT_CONTACT_PERSON_UPDATE_PATH_PREFIX",
    "api/lead-mgmt/contact-person/update-contact-person-by-id",
).strip().lstrip("/")
LEAD_MGMT_CONTACT_PERSON_DELETE_PATH_PREFIX = os.getenv(
    "ETL_LEAD_MGMT_CONTACT_PERSON_DELETE_PATH_PREFIX",
    "api/lead-mgmt/contact-person/delete-contact-person-by-id",
).strip().lstrip("/")

# Lead Management — lead API path segments (under ``API_BASE_URL``).
LEAD_MGMT_LEAD_GET_ALL_PATH = os.getenv(
    "ETL_LEAD_MGMT_LEAD_GET_ALL_PATH",
    "api/lead-mgmt/lead/get-all-lead",
).strip().lstrip("/")
LEAD_MGMT_LEAD_CREATE_PATH = os.getenv(
    "ETL_LEAD_MGMT_LEAD_CREATE_PATH",
    "api/lead-mgmt/lead/create",
).strip().lstrip("/")
LEAD_MGMT_LEAD_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_LEAD_MGMT_LEAD_UPDATE_BY_ID_PREFIX",
    "api/lead-mgmt/lead/update-lead-by-id",
).strip().lstrip("/").rstrip("/")
LEAD_MGMT_LEAD_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_LEAD_MGMT_LEAD_DELETE_BY_ID_PREFIX",
    "api/lead-mgmt/lead/delete-lead-by-id",
).strip().lstrip("/").rstrip("/")
LEAD_MGMT_LEAD_CONTACT_PERSON_BY_LEAD_ID_PREFIX = os.getenv(
    "ETL_LEAD_MGMT_LEAD_CONTACT_PERSON_BY_LEAD_ID_PREFIX",
    "api/lead-mgmt/lead/get-lead-contact-person",
).strip().lstrip("/").rstrip("/")
LEAD_MGMT_COMMENT_GET_BY_LEAD_ID_PREFIX = os.getenv(
    "ETL_LEAD_MGMT_COMMENT_GET_BY_LEAD_ID_PREFIX",
    "api/lead-mgmt/comment/get-lead-comment-by-id",
).strip().lstrip("/").rstrip("/")
LEAD_MGMT_COMMENT_ADD_BY_LEAD_ID_PREFIX = os.getenv(
    "ETL_LEAD_MGMT_COMMENT_ADD_BY_LEAD_ID_PREFIX",
    "api/lead-mgmt/comment/add-lead-comment",
).strip().lstrip("/").rstrip("/")
LEAD_MGMT_COMMENT_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_LEAD_MGMT_COMMENT_UPDATE_BY_ID_PREFIX",
    "api/lead-mgmt/comment/update-by-id",
).strip().lstrip("/").rstrip("/")
LEAD_MGMT_COMMENT_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_LEAD_MGMT_COMMENT_DELETE_BY_ID_PREFIX",
    "api/lead-mgmt/comment/delete-by-id",
).strip().lstrip("/").rstrip("/")

# App Config — Master Setup Key (api/master-setup/master-key/… under ``API_BASE_URL``).
MASTER_SETUP_KEY_GET_ALL_PATH = os.getenv(
    "ETL_MASTER_SETUP_KEY_GET_ALL_PATH",
    "api/master-setup/master-key/get-all-master-key",
).strip().lstrip("/")
MASTER_SETUP_KEY_CREATE_PATH = os.getenv(
    "ETL_MASTER_SETUP_KEY_CREATE_PATH",
    "api/master-setup/master-key/create",
).strip().lstrip("/")
MASTER_SETUP_KEY_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_MASTER_SETUP_KEY_UPDATE_BY_ID_PREFIX",
    "api/master-setup/master-key/update-by-id",
).strip().lstrip("/").rstrip("/")
MASTER_SETUP_KEY_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_MASTER_SETUP_KEY_DELETE_BY_ID_PREFIX",
    "api/master-setup/master-key/delete-by-id",
).strip().lstrip("/").rstrip("/")

# Master Setup Value — master key value CRUD (under ``API_BASE_URL``).
MASTER_SETUP_KEY_VALUE_GET_ALL_PATH = os.getenv(
    "ETL_MASTER_SETUP_KEY_VALUE_GET_ALL_PATH",
    "api/master-setup/master-key-value/get-by-category/ALL",
).strip().lstrip("/")
MASTER_SETUP_KEY_VALUE_CREATE_PATH = os.getenv(
    "ETL_MASTER_SETUP_KEY_VALUE_CREATE_PATH",
    "api/master-setup/master-key-value/create",
).strip().lstrip("/")
MASTER_SETUP_KEY_VALUE_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_MASTER_SETUP_KEY_VALUE_UPDATE_BY_ID_PREFIX",
    "api/master-setup/master-key-value/update-by-id",
).strip().lstrip("/").rstrip("/")
MASTER_SETUP_KEY_VALUE_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_MASTER_SETUP_KEY_VALUE_DELETE_BY_ID_PREFIX",
    "api/master-setup/master-key-value/delete-by-id",
).strip().lstrip("/").rstrip("/")

# Master Setup Config (api/master-setup/master-config/… under ``API_BASE_URL``).
MASTER_SETUP_CONFIG_GET_ALL_PATH = os.getenv(
    "ETL_MASTER_SETUP_CONFIG_GET_ALL_PATH",
    "api/master-setup/master-config/get-all-config",
).strip().lstrip("/")
MASTER_SETUP_CONFIG_CREATE_PATH = os.getenv(
    "ETL_MASTER_SETUP_CONFIG_CREATE_PATH",
    "api/master-setup/master-config/create",
).strip().lstrip("/")
MASTER_SETUP_CONFIG_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_MASTER_SETUP_CONFIG_UPDATE_BY_ID_PREFIX",
    "api/master-setup/master-config/update-config-by-id",
).strip().lstrip("/").rstrip("/")
MASTER_SETUP_CONFIG_DELETE_BY_ID_PREFIX = os.getenv(
    "ETL_MASTER_SETUP_CONFIG_DELETE_BY_ID_PREFIX",
    "api/master-setup/master-config/delete-config-by-id",
).strip().lstrip("/").rstrip("/")

# ETL — database connections (``api/etl/connection/*``).
ETL_CONNECTIONS_LIST_PATH = os.getenv(
    "ETL_CONNECTIONS_LIST_PATH", "api/etl/connection/get-all"
).strip().lstrip("/")
ETL_CONNECTIONS_TEST_PATH = os.getenv(
    "ETL_CONNECTIONS_TEST_PATH", "api/etl/connection/test"
).strip().lstrip("/")
ETL_CONNECTIONS_SAVE_PATH = os.getenv(
    "ETL_CONNECTIONS_SAVE_PATH", "api/etl/connection/save"
).strip().lstrip("/")
ETL_CONNECTIONS_UPDATE_BY_ID_PREFIX = os.getenv(
    "ETL_CONNECTIONS_UPDATE_BY_ID_PREFIX", "api/etl/connection/update-by-id"
).strip().lstrip("/").rstrip("/")
ETL_CONNECTIONS_REMOVE_BY_ID_PREFIX = os.getenv(
    "ETL_CONNECTIONS_REMOVE_BY_ID_PREFIX", "api/etl/connection/remove-by-id"
).strip().lstrip("/").rstrip("/")

# ETL — import metadata (connection id in path / body; table name as query where noted).
ETL_METADATA_SCAN_TABLES_PATH_PREFIX = os.getenv(
    "ETL_METADATA_SCAN_TABLES_PATH_PREFIX",
    "api/etl/scan-connection/get-scanned-table-by-id",
).strip().lstrip("/").rstrip("/")
ETL_SCAN_CONNECTION_SOURCE_TABLES_PATH_PREFIX = os.getenv(
    "ETL_SCAN_CONNECTION_SOURCE_TABLES_PATH_PREFIX",
    "api/etl/scan-connection/table",
).strip().lstrip("/").rstrip("/")
ETL_METADATA_SCAN_FIELDS_PATH_PREFIX = os.getenv(
    "ETL_METADATA_SCAN_FIELDS_PATH_PREFIX",
    "api/etl/scan-connection/get-scanned-table-detail",
).strip().lstrip("/").rstrip("/")
ETL_METADATA_IMPORT_TABLE_DETAILS_PATH = os.getenv(
    "ETL_METADATA_IMPORT_TABLE_DETAILS_PATH",
    "api/etl/import-metadata/import-table-detail",
).strip().lstrip("/").rstrip("/")
ETL_METADATA_CHECK_FIELD_PATH_PREFIX = os.getenv(
    "ETL_METADATA_CHECK_FIELD_PATH_PREFIX",
    "api/etl/import-metadata/check-field",
).strip().lstrip("/").rstrip("/")
ETL_METADATA_SCAN_ALL_PATH = os.getenv(
    "ETL_METADATA_SCAN_ALL_PATH", "api/etl/scan-connection/scan-all"
).strip().lstrip("/")
ETL_METADATA_SCAN_BY_FILTER_PATH_PREFIX = os.getenv(
    "ETL_METADATA_SCAN_BY_FILTER_PATH_PREFIX",
    os.getenv(
        "ETL_METADATA_SCAN_BY_FILTER_PATH",
        "api/etl/scan-connection/scan-all-by-filter",
    ),
).strip().lstrip("/").rstrip("/")

# ETL — extraction (imported tables, column selection, jobs).
ETL_METADATA_IMPORTED_TABLES_PATH_PREFIX = os.getenv(
    "ETL_METADATA_IMPORTED_TABLES_PATH_PREFIX",
    "api/etl/import-metadata/imported-table-by-id",
).strip().lstrip("/").rstrip("/")
ETL_METADATA_IMPORTED_REMOVE_PATH_PREFIX = os.getenv(
    "ETL_METADATA_IMPORTED_REMOVE_PATH_PREFIX", "api/metadata/imported-remove"
).strip().lstrip("/").rstrip("/")
ETL_METADATA_SCAN_EXTRACTED_FIELDS_PATH_PREFIX = os.getenv(
    "ETL_METADATA_SCAN_EXTRACTED_FIELDS_PATH_PREFIX", "api/metadata/scan-extracted-feilds"
).strip().lstrip("/").rstrip("/")
ETL_METADATA_UPDATE_EXTRACTED_FIELDS_PATH_PREFIX = os.getenv(
    "ETL_METADATA_UPDATE_EXTRACTED_FIELDS_PATH_PREFIX", "api/metadata/update-extracted-feilds"
).strip().lstrip("/").rstrip("/")
ETL_JOB_START_PATH = os.getenv("ETL_JOB_START_PATH", "etl/jobs/start").strip().lstrip("/")
ETL_JOBS_ALL_PATH = os.getenv("ETL_JOBS_ALL_PATH", "etl/jobs/all").strip().lstrip("/")
ETL_LOGS_BY_TYPE_PATH = os.getenv(
    "ETL_LOGS_BY_TYPE_PATH", "api/etl/logs/type"
).strip().lstrip("/").rstrip("/")
ETL_LOGS_BY_CONNECTION_AND_OPERATION_TYPE_PATH = os.getenv(
    "ETL_LOGS_BY_CONNECTION_AND_OPERATION_TYPE_PATH",
    "api/etl/logs/connection/name-and-operation-type",
).strip().lstrip("/").rstrip("/")
