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

# Login auth endpoint (full path).
LOGIN_URL = f"{API_BASE_URL}/api/auth/login"

# After login: left-nav access from app/step list (GET, Bearer JWT).
GET_APP_STEP_LIST_PATH = os.getenv(
    "ETL_GET_APP_STEP_LIST_PATH", "api-access/getAppStepList"
).strip().lstrip("/")

# Profile update endpoint path (override if backend uses different path).
UPDATE_PROFILE_PATH = os.getenv("ETL_UPDATE_PROFILE_PATH", "api/update-profile").strip()

# User update path: api/update-user-by-id/{user_id} (used for profile update)
UPDATE_USER_PATH = os.getenv("ETL_UPDATE_USER_PATH", "api/update-user-by-id").strip()
DELETE_USER_PATH = os.getenv("ETL_DELETE_USER_PATH", "api/delete-user-by-id").strip()
RESET_USER_PASSWORD_PATH = os.getenv(
    "ETL_RESET_USER_PASSWORD_PATH", "api/reset-user-password"
).strip()
UPDATE_USER_STATUS_PATH = os.getenv(
    "ETL_UPDATE_USER_STATUS_PATH", "api/update-user-status-by-id"
).strip()
UPDATE_USER_ROLE_STATUS_PATH = os.getenv(
    "ETL_UPDATE_USER_ROLE_STATUS_PATH", "api/update-user-role-status-by-id"
).strip()

# Combined API details + validations (API: All in One page).
API_DETAILS_ALL_IN_ONE_PATH = os.getenv(
    "ETL_API_DETAILS_ALL_IN_ONE_PATH", "api/get-all-api-details/all-in-one"
).strip()

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
