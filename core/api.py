"""API client for login and sign out.

HTTP helpers log requests/responses to stderr as ``[API] ...`` (see ``_log_api``).
Environment:

- ``ETL_API_HTTP_LOG=0`` — disable API console logging.
- ``ETL_API_LOG_STDOUT=1`` — mirror the same lines to stdout (e.g. if your runner hides stderr).
- ``ETL_API_LOG_URL_MAX`` — max characters for the ``[API] URL`` line (default ``120``); avoids ultra-wide lines in narrow terminals.

All ``urllib.request.Request`` / ``urlopen`` usage in this module goes through
:func:`_http_urlopen_logged` so request/response lines are consistent (see ``_log_api``).
"""

from __future__ import annotations

import base64
import io
import json
import os
import mimetypes
import re
import sys
import time
from pathlib import Path
from uuid import uuid4
from contextlib import contextmanager
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlparse
from urllib.request import Request, urlopen as _urllib_urlopen

from core.config import (
    API_BASE_URL,
    API_MGMT_APP_ID_CREATE_PATH,
    API_MGMT_APP_ID_DELETE_BY_ID_PREFIX,
    API_MGMT_APP_ID_GET_ALL_PATH,
    API_MGMT_APP_ID_UPDATE_BY_ID_PREFIX,
    API_MGMT_API_LIST_CREATE_PATH,
    API_MGMT_API_LIST_DELETE_BY_ID_PREFIX,
    API_MGMT_API_LIST_GET_ALL_PATH,
    API_MGMT_API_LIST_UPDATE_BY_ID_PREFIX,
    API_DETAILS_ALL_IN_ONE_PATH,
    GET_APP_STEP_LIST_PATH,
    LEAD_MGMT_COMPANY_CREATE_PATH,
    LEAD_MGMT_COMPANY_DELETE_PATH_PREFIX,
    LEAD_MGMT_COMPANY_GET_ALL_PATH,
    LEAD_MGMT_COMPANY_CONTACT_GET_BY_COMPANY_PREFIX,
    LEAD_MGMT_COMPANY_UPDATE_PATH_PREFIX,
    DM_COMPANY_CREATE_PATH,
    DM_COMPANY_DELETE_PATH_PREFIX,
    DM_COMPANY_GET_ALL_PATH,
    DM_COMPANY_UPDATE_PATH_PREFIX,
    DM_CONTACT_PERSON_CREATE_PATH,
    DM_CONTACT_PERSON_DELETE_PATH_PREFIX,
    DM_CONTACT_PERSON_GET_ALL_PATH,
    DM_CONTACT_PERSON_UPDATE_PATH_PREFIX,
    DM_COMPANY_CONTACT_ASSIGN_PATH,
    DM_COMPANY_CONTACT_DELETE_PATH_PREFIX,
    DM_COMPANY_CONTACT_UPDATE_STATUS_PATH_PREFIX,
    DM_PROJECT_CREATE_PATH,
    DM_PROJECT_DELETE_BY_ID_PREFIX,
    DM_PROJECT_GET_ALL_PATH,
    DM_PROJECT_GET_BY_ID_PREFIX,
    DM_PROJECT_GET_CONTACT_ASSIGNED_PREFIX,
    DM_PROJECT_UPDATE_BY_ID_PREFIX,
    DM_USER_PROJECT_ASSIGN_PATH,
    DM_USER_PROJECT_CHANGE_STATUS_BY_ID_PREFIX,
    DM_USER_PROJECT_DELETE_BY_ID_PREFIX,
    DM_USER_PROJECT_GET_BY_PROJECT_ID_PREFIX,
    DMT_USER_MODULE_ASSIGN_PATH,
    DMT_USER_MODULE_CHANGE_STATUS_BY_ID_PREFIX,
    DMT_USER_MODULE_GET_BY_USER_ID_PREFIX,
    DMT_USER_MODULE_REMOVE_ASSIGNMENT_PATH,
    LEAD_MGMT_CONTACT_PERSON_CREATE_PATH,
    LEAD_MGMT_CONTACT_PERSON_DELETE_PATH_PREFIX,
    LEAD_MGMT_CONTACT_PERSON_GET_ALL_PATH,
    LEAD_MGMT_CONTACT_PERSON_UPDATE_PATH_PREFIX,
    LEAD_MGMT_COMMENT_ADD_BY_LEAD_ID_PREFIX,
    LEAD_MGMT_COMMENT_DELETE_BY_ID_PREFIX,
    LEAD_MGMT_COMMENT_GET_BY_LEAD_ID_PREFIX,
    LEAD_MGMT_COMMENT_UPDATE_BY_ID_PREFIX,
    LEAD_MGMT_LEAD_CREATE_PATH,
    LEAD_MGMT_LEAD_CONTACT_PERSON_BY_LEAD_ID_PREFIX,
    LEAD_MGMT_LEAD_DELETE_BY_ID_PREFIX,
    LEAD_MGMT_LEAD_GET_ALL_PATH,
    LEAD_MGMT_LEAD_UPDATE_BY_ID_PREFIX,
    MASTER_SETUP_KEY_CREATE_PATH,
    MASTER_SETUP_KEY_DELETE_BY_ID_PREFIX,
    MASTER_SETUP_KEY_GET_ALL_PATH,
    MASTER_SETUP_CONFIG_CREATE_PATH,
    MASTER_SETUP_CONFIG_DELETE_BY_ID_PREFIX,
    MASTER_SETUP_CONFIG_GET_ALL_PATH,
    MASTER_SETUP_CONFIG_UPDATE_BY_ID_PREFIX,
    MASTER_SETUP_KEY_VALUE_CREATE_PATH,
    MASTER_SETUP_KEY_VALUE_DELETE_BY_ID_PREFIX,
    MASTER_SETUP_KEY_VALUE_GET_ALL_PATH,
    MASTER_SETUP_KEY_VALUE_UPDATE_BY_ID_PREFIX,
    MASTER_SETUP_KEY_UPDATE_BY_ID_PREFIX,
    COMMENT_ADD_PATH,
    COMMENT_DELETE_BY_ID_PATH,
    COMMENT_GET_ALL_BY_VALIDATION_ID_PATH,
    COMMENT_GET_BY_ID_PATH,
    COMMENT_UPDATE_BY_ID_PATH,
    DELETE_API_DETAIL_PATH,
    DELETE_API_VALIDATION_PATH,
    DMT_USER_COPY_FROM_APPUSER_PATH,
    DMT_USER_UPLOAD_PATH,
    DMT_USER_CREATE_PATH,
    DMT_USER_DELETE_BY_ID_PREFIX,
    DMT_USER_GET_ALL_PATH,
    DMT_USER_GET_BY_ID_PREFIX,
    DMT_USER_UPDATE_BY_ID_PREFIX,
    DMT_OBJECT_TRACKER_CREATE_PATH,
    DMT_OBJECT_TRACKER_DELETE_BY_ID_PREFIX,
    DMT_OBJECT_TRACKER_GET_ALL_PATH,
    DMT_OBJECT_TRACKER_UPDATE_BY_ID_PREFIX,
    DMT_ISSUE_TRACKER_CREATE_PATH,
    DMT_ISSUE_TRACKER_DELETE_BY_ID_PREFIX,
    DMT_ISSUE_TRACKER_GET_ALL_PATH,
    DMT_ISSUE_TRACKER_UPDATE_BY_ID_PREFIX,
    DMT_COMMENT_CREATE_PATH,
    DMT_COMMENT_DELETE_BY_ID_PREFIX,
    DMT_COMMENT_GET_BY_OBJECT_ID_PREFIX,
    DMT_COMMENT_UPDATE_BY_ID_PREFIX,
    CREATE_USER_PATH,
    DELETE_USER_PATH,
    GET_ALL_USERS_PATH,
    LOGIN_URL,
    RESET_USER_PASSWORD_PATH,
    UPDATE_USER_ROLE_STATUS_PATH,
    USER_ROLE_ASSIGN_PATH,
    USER_ROLE_ASSIGNMENT_DELETE_BY_ID_PREFIX,
    USER_ROLE_ASSIGNMENT_UPDATE_BY_ID_PREFIX,
    USER_HIERARCHY_ASSIGN_PATH,
    USER_HIERARCHY_DELETE_BY_ID_PREFIX,
    USER_HIERARCHY_GET_ALL_PATH,
    USER_HIERARCHY_UPDATE_BY_ID_PREFIX,
    UPDATE_USER_STATUS_PATH,
    UPDATE_PROFILE_PATH,
    UPDATE_USER_PATH,
    ETL_CONNECTIONS_LIST_PATH,
    ETL_CONNECTIONS_TEST_PATH,
    ETL_CONNECTIONS_SAVE_PATH,
    ETL_CONNECTIONS_UPDATE_BY_ID_PREFIX,
    ETL_CONNECTIONS_REMOVE_BY_ID_PREFIX,
    IMPORTS_CREATE_PATH,
    IMPORTS_GET_ALL_SESSION_ID_PATH,
    IMPORTS_UPLOAD_PATH_PREFIX,
    IMPORTS_ANALYZE_PATH_PREFIX,
    IMPORTS_ANALYZE_IF_PRESENT_PATH_PREFIX,
    IMPORTS_MAPPING_PATH_PREFIX,
    IMPORTS_GET_ALL_IMPORT_SHEET_PATH,
    IMPORTS_GET_IMPORT_SHEET_BY_UUID_PREFIX,
    IMPORTS_EXECUTE_PATH_PREFIX,
    IMPORTS_VALIDATE_PATH_PREFIX,
    ETL_METADATA_SCAN_TABLES_PATH_PREFIX,
    ETL_SCAN_CONNECTION_SOURCE_TABLES_PATH_PREFIX,
    ETL_METADATA_SCAN_FIELDS_PATH_PREFIX,
    ETL_METADATA_IMPORT_TABLE_DETAILS_PATH,
    ETL_METADATA_CHECK_FIELD_PATH_PREFIX,
    ETL_SCAN_CONNECTION_CHECK_FIELD_PATH_PREFIX,
    ETL_METADATA_SCAN_ALL_PATH,
    ETL_METADATA_SCAN_BY_FILTER_PATH_PREFIX,
    ETL_SCAN_UPDATE_TGT_TABLE_NAME_PATH_PREFIX,
    ETL_IMPORT_METADATA_UPDATE_WHERE_CLAUSE_PATH_PREFIX,
    ETL_EXTRACTION_PATH,
    ETL_EXTRACTION_BY_CONNECTION_PATH_PREFIX,
    ETL_EXTRACTION_UPDATE_TARGET_TABLE_PATH_PREFIX,
    ETL_EXTRACTION_UPDATE_WHERE_CLAUSE_PATH_PREFIX,
    ETL_METADATA_IMPORTED_TABLES_PATH_PREFIX,
    ETL_EXTRACT_METADATA_EXTRACTED_TABLE_BY_ID_PATH_PREFIX,
    ETL_METADATA_IMPORTED_REMOVE_PATH_PREFIX,
    ETL_METADATA_SCAN_EXTRACTED_FIELDS_PATH_PREFIX,
    ETL_METADATA_UPDATE_EXTRACTED_FIELDS_PATH_PREFIX,
    ETL_METADATA_GET_TABLE_NAME_FROM_ETL_DETAILS_PATH_PREFIX,
    ETL_EXTRACT_GROUP_PATH,
    ETL_EXTRACT_GROUP_UPDATE_TGT_TABLE_PATH,
    ETL_GROUP_TABLE_ADD_WHERE_CLAUSE_PATH,
    ETL_GROUP_VALIDATE_WHERE_CLAUSE_PATH,
    ETL_JOB_START_PATH,
    ETL_GROUP_JOB_START_PATH,
    ETL_JOBS_ALL_PATH,
    ETL_LOG_BY_ID_PATH_PREFIX,
    ETL_LOGS_BY_TYPE_PATH,
    ETL_LOGS_BY_CONNECTION_AND_OPERATION_TYPE_PATH,
    ETL_TRANSFORMATION_OBJECT_PATH,
    ETL_TRANSFORMATION_JOB_PATH,
    ETL_TRANSFORMATION_WORKFLOW_PATH,
    ETL_TRANSFORMATION_FLOW_PATH,
    ETL_TRANSFORMATION_SOURCE_PATH,
    ETL_TRANSFORMATION_TARGET_PATH,
    ETL_TRANSFORMATION_COLUMN_PATH,
    ETL_TRANSFORMATION_JOIN_PATH,
    ETL_TRANSFORMATION_STEP_PATH,
    ETL_TRANSFORMATION_STEP_MASTER_PATH,
)

_LOG_ZAP_INVISIBLE = re.compile(r"[\u200b-\u200f\u202f\u2060-\u2064\ufeff\x00-\x08\x0b\x0c\x0e-\x1f]")
_LOG_COLLAPSE_WS = re.compile(r"\s+", re.UNICODE)


def _sanitize_log_text(s: str) -> str:
    t = _LOG_ZAP_INVISIBLE.sub("", s or "")
    t = _LOG_COLLAPSE_WS.sub(" ", t)
    return t.strip()


def _clip_log_text(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    if max_len < 8:
        return s[:max_len]
    keep = max_len - 1
    left = keep // 2
    right = keep - left
    return s[:left] + "…" + s[-right:]


def _log_api(method: str, url: str, body: Any = None, response: Any = None, status: int | None = None) -> None:
    """Log API request and response to console (not in app). Redacts password in body.

    Set ``ETL_API_HTTP_LOG=0`` to disable. Set ``ETL_API_LOG_STDOUT=1`` to mirror logs to stdout
    (default is stderr only).

    Log request lines use a short ``[API] REQUEST <method>`` line plus ``[API] URL …`` (clipped
    to ``ETL_API_LOG_URL_MAX``) so integrated terminals do not soft-wrap one huge ``http://…`` line
    into a fake “blank gap”. Invisible / control characters in the URL are stripped before print.
    """
    if os.environ.get("ETL_API_HTTP_LOG", "1").lower() in ("0", "false", "no", "off"):
        return
    streams = [sys.stderr]
    if os.environ.get("ETL_API_LOG_STDOUT", "").lower() in ("1", "true", "yes"):
        streams.append(sys.stdout)

    def _emit(msg: str) -> None:
        for stream in streams:
            print(msg, file=stream, flush=True)

    method_s = _sanitize_log_text(method)
    url_s = _sanitize_log_text(url)
    req_key = f"{method_s} {url_s}"
    if not hasattr(_log_api, "_pending"):
        _log_api._pending = {}  # type: ignore[attr-defined]
    pending = _log_api._pending  # type: ignore[attr-defined]
    if response is None:
        pending.setdefault(req_key, []).append(time.perf_counter())
        # Two short lines avoid one ultra-wide line (bad soft-wrap / linkifier gaps in some terminals).
        _emit(f"[API] REQUEST {method_s}")
        try:
            max_u = int(os.environ.get("ETL_API_LOG_URL_MAX", "120"))
        except ValueError:
            max_u = 120
        max_u = max(40, min(max_u, 4096))
        _emit(f"[API] URL {_clip_log_text(url_s, max_u)}")
    if body is not None:
        # Avoid printing the same JSON twice when helpers call _log_api once for the request
        # (response is None) and again with the response (body repeated on the second call).
        _pend_for_key = pending.get(req_key) if isinstance(pending, dict) else None
        _had_request_phase = isinstance(_pend_for_key, list) and len(_pend_for_key) > 0
        _print_body = response is None or (response is not None and not _had_request_phase)
        if _print_body:
            try:
                safe_body = body
                if isinstance(body, dict) and "password" in body:
                    safe_body = {k: ("***" if k == "password" else v) for k, v in body.items()}
                s = json.dumps(safe_body, indent=2) if isinstance(safe_body, dict) else str(safe_body)
                _emit(f"[API] REQUEST BODY:\n{s}")
            except Exception:
                _emit("[API] REQUEST BODY: (non-serializable)")
    if response is not None:
        try:
            s = json.dumps(response, indent=2) if isinstance(response, (dict, list)) else str(response)
            elapsed_suffix = ""
            starts = pending.get(req_key) if isinstance(pending, dict) else None
            if isinstance(starts, list) and starts:
                started_at = starts.pop(0)
                elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                elapsed_suffix = f" [{elapsed_ms}ms]"
            status_str = f" [HTTP {status}]" if status is not None else ""
            _emit(f"[API] RESPONSE{status_str}{elapsed_suffix}:\n{s}")
        except Exception:
            _emit("[API] RESPONSE: (non-serializable)")


def _request_body_for_log(req: Request) -> Any:
    data = getattr(req, "data", None)
    if not data:
        return None
    if isinstance(data, bytes):
        try:
            parsed: Any = json.loads(data.decode("utf-8"))
        except Exception:
            s = data.decode("utf-8", errors="replace")
            if len(s) > 4000:
                return s[:4000] + "…"
            return s
        if isinstance(parsed, dict) and "password" in parsed:
            return {k: ("***" if k == "password" else v) for k, v in parsed.items()}
        return parsed
    return str(data)


def _response_obj_for_log(raw: bytes) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        s = raw.decode("utf-8", errors="replace")
        if len(s) > 8000:
            return s[:8000] + "…"
        return s


def _rewind_http_error(exc: HTTPError, body: bytes) -> None:
    """Re-seed ``HTTPError`` so callers can ``exc.read()`` again after we log the body."""
    exc.fp = io.BytesIO(body)
    try:
        exc.length = len(body)
    except Exception:
        pass


class _BufferedHttpResponse:
    """Minimal stand-in for ``http.client.HTTPResponse`` after the real socket is closed."""

    __slots__ = ("_buf", "_pos", "status")

    def __init__(self, body: bytes, status_code: int) -> None:
        self._buf = body
        self._pos = 0
        self.status = status_code

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            out = self._buf[self._pos :]
            self._pos = len(self._buf)
            return out
        end = min(self._pos + n, len(self._buf))
        out = self._buf[self._pos : end]
        self._pos = end
        return out

    def getcode(self) -> int:
        return int(self.status)


@contextmanager
def _http_urlopen_logged(*args: Any, **kwargs: Any):
    """Like :func:`urllib.request.urlopen`, but logs one request + one response via :func:`_log_api`."""
    if os.environ.get("ETL_API_HTTP_LOG", "1").lower() in ("0", "false", "no", "off"):
        with _urllib_urlopen(*args, **kwargs) as resp:
            yield resp
        return

    req0 = args[0] if args else None
    if not isinstance(req0, Request):
        with _urllib_urlopen(*args, **kwargs) as resp:
            yield resp
        return

    req: Request = req0
    method = (req.get_method() or "GET").upper()
    url = req.full_url
    body_log = _request_body_for_log(req)
    _log_api(method, url, body=body_log)

    try:
        raw_resp = _urllib_urlopen(*args, **kwargs)
    except HTTPError as exc:
        err_raw = exc.read()
        _rewind_http_error(exc, err_raw)
        _log_api(
            method,
            url,
            body=body_log,
            response=_response_obj_for_log(err_raw),
            status=getattr(exc, "code", None),
        )
        raise

    with raw_resp:
        raw = raw_resp.read()
        stat = getattr(raw_resp, "status", None)
        code = raw_resp.getcode()
    status_int = int(stat if stat is not None else (code if code is not None else 200))
    _log_api(method, url, body=body_log, response=_response_obj_for_log(raw), status=status_int)
    yield _BufferedHttpResponse(raw, status_int)


def _api_url(path: str) -> str:
    return f"{API_BASE_URL}/{path.lstrip('/')}"


def _normalize_bearer_token(token: str | None) -> str | None:
    """Return raw JWT (no ``Bearer `` prefix) for a safe ``Authorization: Bearer …`` header."""
    if token is None:
        return None
    t = str(token).strip()
    if not t:
        return None
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return t if t else None


def _api_path_id_segment(value: Any) -> str:
    """Build a stable URL path segment for numeric REST ids (avoids ``16.0``, whitespace)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        n = int(value)
        return str(n) if value == n else str(value)
    s = str(value).strip()
    if not s:
        return ""
    try:
        f = float(s)
        if f == int(f):
            return str(int(f))
    except ValueError:
        pass
    return s


def _http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout_s: float = 8.0,
) -> Any:
    """HTTP GET returning parsed JSON (or {} if empty)."""
    hdrs: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
    }
    if headers:
        hdrs.update(headers)
    req = Request(url, headers=hdrs, method="GET")
    with _http_urlopen_logged(req, timeout=timeout_s) as resp:
        raw = resp.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _http_post_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_s: float = 8.0,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    """HTTP POST JSON returning parsed JSON (or {} if empty)."""
    data = json.dumps(payload).encode("utf-8")
    hdrs: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
    }
    if extra_headers:
        hdrs.update(extra_headers)
    req = Request(
        url,
        data=data,
        headers=hdrs,
        method="POST",
    )
    with _http_urlopen_logged(req, timeout=timeout_s) as resp:
        raw = resp.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _http_put_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_s: float = 8.0,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """HTTP PUT JSON. Returns ``(http_status, parsed body or {})``."""
    data = json.dumps(payload).encode("utf-8")
    hdrs: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
    }
    if extra_headers:
        hdrs.update(extra_headers)
    req = Request(
        url,
        data=data,
        headers=hdrs,
        method="PUT",
    )
    with _http_urlopen_logged(req, timeout=timeout_s) as resp:
        raw = resp.read()
        status = int(getattr(resp, "status", 200) or 200)
    if not raw:
        return status, {}
    try:
        result = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        result = {}
    return status, result


def _http_patch(url: str, *, headers: dict[str, str] | None = None, timeout_s: float = 8.0) -> Any:
    """HTTP PATCH (no body) returning parsed JSON (or {} if empty)."""
    hdrs: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
    }
    if headers:
        hdrs.update(headers)
    req = Request(url, headers=hdrs, method="PATCH")
    with _http_urlopen_logged(req, timeout=timeout_s) as resp:
        raw = resp.read()
    if not raw:
        return {}
    result = json.loads(raw.decode("utf-8"))
    return result


def _http_delete(url: str, *, headers: dict[str, str] | None = None, timeout_s: float = 8.0) -> Any:
    """HTTP DELETE returning parsed JSON (or {} if empty)."""
    hdrs: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
    }
    if headers:
        hdrs.update(headers)
    req = Request(url, headers=hdrs, method="DELETE")
    with _http_urlopen_logged(req, timeout=timeout_s) as resp:
        raw = resp.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _http_delete_json(
    url: str,
    body: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout_s: float = 8.0,
) -> Any:
    """HTTP DELETE with JSON body, returning parsed JSON (or {} if empty)."""
    hdrs: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
    }
    if headers:
        hdrs.update(headers)
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers=hdrs, method="DELETE")
    with _http_urlopen_logged(req, timeout=timeout_s) as resp:
        raw = resp.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _normalize_role(role: Any) -> str:
    """Normalize role string, e.g. ROLE_SADMIN -> SADMIN."""
    if role is None:
        return ""
    r = str(role).strip()
    return r.replace("ROLE_", "", 1) if r.startswith("ROLE_") else r


def _decode_jwt_payload(token: str) -> dict[str, Any] | None:
    """Decode JWT payload (middle segment) to a dict; returns None on failure."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        raw = json.loads(payload_bytes.decode("utf-8"))
        return raw if isinstance(raw, dict) else None
    except Exception:
        return None


def _decode_jwt_role(token: str) -> str | None:
    """Extract role from JWT payload. Supports 'role' or 'roles' (array). Returns None on failure."""
    payload = _decode_jwt_payload(token)
    if not payload:
        return None
    role = payload.get("role") or payload.get("userType") or payload.get("user_type")
    if not role and "roles" in payload:
        roles = payload["roles"]
        if isinstance(roles, list) and roles:
            role = roles[0]
        elif isinstance(roles, str) and roles.strip():
            role = roles.strip()
    return _normalize_role(role) if role else None


def collect_normalized_roles_from_login_session(login_result: dict[str, Any]) -> set[str]:
    """All role strings from login JSON + JWT ``roles`` / ``role`` (``ROLE_*`` normalized to ``*``)."""
    out: set[str] = set()

    def add_role(x: Any) -> None:
        if x is None:
            return
        if isinstance(x, dict):
            r = x.get("role") or x.get("roleName") or x.get("name")
            if r is not None and str(r).strip():
                n = _normalize_role(str(r).strip())
                if n:
                    out.add(n)
            return
        if str(x).strip():
            n = _normalize_role(str(x).strip())
            if n:
                out.add(n)

    dr = login_result.get("defaultRole") or login_result.get("default_role")
    if isinstance(dr, str) and dr.strip():
        add_role(dr.strip())

    rv = login_result.get("roles")
    if isinstance(rv, list):
        for item in rv:
            add_role(item)
    elif isinstance(rv, str) and rv.strip():
        s = rv.strip()
        if s.startswith("["):
            inner = s[1:-1].strip()
            for part in inner.split(","):
                p = part.strip().strip('"').strip("'")
                if p:
                    add_role(p)
        else:
            for part in s.split(","):
                if part.strip():
                    add_role(part.strip())

    r1 = login_result.get("role")
    if isinstance(r1, str) and r1.strip():
        add_role(r1.strip())

    tok = (
        login_result.get("token")
        or login_result.get("accessToken")
        or login_result.get("access_token")
        or login_result.get("jwt")
        or login_result.get("idToken")
        or login_result.get("id_token")
    )
    if isinstance(tok, str) and tok.strip():
        payload = _decode_jwt_payload(tok.strip())
        if payload:
            jr = payload.get("roles")
            if isinstance(jr, list):
                for x in jr:
                    add_role(x)
            elif isinstance(jr, str) and jr.strip():
                add_role(jr.strip())
            one = payload.get("role") or payload.get("userType") or payload.get("user_type")
            if one is not None and str(one).strip():
                add_role(str(one).strip())

    return out


def session_has_sadmin_role(login_result: dict[str, Any]) -> bool:
    """True if any session role is SADMIN (including JWT ``ROLE_SADMIN`` after normalization)."""
    return any(r.upper() == "SADMIN" for r in collect_normalized_roles_from_login_session(login_result))


def _role_from_login_payload(payload: dict[str, Any], token: str | None) -> str:
    """Derive role from login response: payload['roles'] (string or list) or JWT."""
    dr = payload.get("defaultRole") or payload.get("default_role")
    if isinstance(dr, str) and dr.strip():
        return _normalize_role(dr.strip())
    roles_val = payload.get("roles")
    if isinstance(roles_val, list) and roles_val:
        first = roles_val[0]
        if isinstance(first, dict):
            r = first.get("role") or first.get("roleName") or first.get("name")
            if r is not None and str(r).strip():
                return _normalize_role(str(r).strip())
        return _normalize_role(str(first))
    if isinstance(roles_val, str) and roles_val.strip():
        s = roles_val.strip()
        if s.startswith("["):
            s = s[1:-1].strip()
            parts = [p.strip() for p in s.split(",") if p.strip()]
            if parts:
                return _normalize_role(parts[0])
        return _normalize_role(s)
    if token:
        decoded = _decode_jwt_role(token)
        if decoded:
            return decoded
    return "user"


def _extract_error_message(payload: Any, fallback: str) -> str:
    def _coerce_message_fragment(value: Any) -> str | None:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and not isinstance(value, (dict, list)) and str(value).strip():
            return str(value).strip()
        return None

    if isinstance(payload, dict):
        for key in (
            "message",
            "error",
            "detail",
            "msg",
            "errorMessage",
            "error_message",
            "reason",
            "statusMessage",
            "description",
            "title",
        ):
            value = payload.get(key)
            frag = _coerce_message_fragment(value)
            if frag is not None:
                return frag
            if isinstance(value, list) and value:
                first = value[0]
                frag = _coerce_message_fragment(first)
                if frag is not None:
                    return frag
                if isinstance(first, dict):
                    nested = _extract_error_message(first, "")
                    if nested.strip():
                        return nested.strip()
        errors = payload.get("errors")
        if isinstance(errors, list) and errors:
            first = errors[0]
            frag = _coerce_message_fragment(first)
            if frag is not None:
                return frag
            if isinstance(first, dict):
                nested = _extract_error_message(first, "")
                if nested.strip():
                    return nested.strip()
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    out = (fallback or "").strip()
    if out:
        return out
    if fallback == "":
        return ""
    return "Something went wrong."


def _unwrap_api_row_list(data: Any) -> list[dict[str, Any]] | None:
    """Normalize list endpoints that return a bare array or ``{ companies: [...] }`` under ``data``."""
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in (
            "companies",
            "companyList",
            "company_list",
            "content",
            "items",
            "records",
            "data",
            "rows",
            "result",
        ):
            nested = data.get(key)
            if isinstance(nested, list):
                return [row for row in nested if isinstance(row, dict)]
    return None


def _dict_has_api_failure_markers(d: dict[str, Any]) -> bool:
    """True when one dict (root or nested ``data``) marks failure: ``success: false`` or ``status: FAILURE`` / etc."""
    if not isinstance(d, dict):
        return False
    if d.get("success") is False:
        return True
    raw_s = d.get("success")
    if isinstance(raw_s, str) and raw_s.strip().lower() in ("false", "0", "no", "fail", "failed", "error"):
        return True
    st = str(d.get("status", "")).strip().upper()
    return st in ("FAILURE", "FAILED", "FAIL", "ERROR", "FALSE", "0")


def _json_payload_indicates_business_failure(payload: Any) -> bool:
    """True when JSON marks business failure at root or under ``data``; HTTP may be 2xx."""
    if not isinstance(payload, dict):
        return False
    if _dict_has_api_failure_markers(payload):
        return True
    data = payload.get("data")
    if isinstance(data, dict) and _dict_has_api_failure_markers(data):
        return True
    return False


# Backward-compatible name (API catalog create/update/delete).
_api_catalog_body_indicates_failure = _json_payload_indicates_business_failure


def _reject_json_business_failure(
    payload: Any,
    *,
    message_fallback: str,
    **extra: Any,
) -> dict[str, Any] | None:
    """If payload is a failure envelope, return {success: False, message, ...}; else None."""
    if not isinstance(payload, dict) or not _json_payload_indicates_business_failure(payload):
        return None
    msg = _extract_error_message(payload, message_fallback)
    if not (msg or "").strip():
        msg = (message_fallback or "").strip() or "Something went wrong."
    out: dict[str, Any] = {
        "success": False,
        "message": msg,
    }
    for k, v in extra.items():
        if v is not None:
            out[k] = v
    return out


def _merge_login_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten common API wrappers so ``token`` / user fields nested under ``data`` are visible.

    Examples::

        {"status":"SUCCESS","data":{"token":"...","user":{...}}}
        {"success":true,"result":{"accessToken":"..."}}
    """
    merged = dict(payload)
    for key in ("data", "result", "payload", "body", "content"):
        inner = payload.get(key)
        if isinstance(inner, dict):
            merged = {**inner, **merged}
    return merged


def _login_http_body_is_success(payload: dict[str, Any]) -> bool:
    """True when the auth JSON indicates a successful login (not only HTTP 200).

    The UI previously required ``status == "SUCCESS"`` exactly; many backends use
    ``success: true``, case-variant status strings, or return a token without ``status``.
    """
    if _json_payload_indicates_business_failure(payload):
        return False
    succ = payload.get("success")
    if succ is True:
        return True
    if isinstance(succ, str) and succ.strip().lower() in ("true", "1", "yes"):
        return True
    raw = payload.get("status")
    if raw is None:
        raw = payload.get("Status")
    st = str(raw).strip().upper()
    if st in ("SUCCESS", "OK", "SUCCEEDED", "200", "201"):
        return True
    if raw in (0, "0") and payload.get("success") is not False:
        return True
    tok = (
        payload.get("token")
        or payload.get("accessToken")
        or payload.get("access_token")
        or payload.get("jwt")
        or payload.get("idToken")
        or payload.get("id_token")
    )
    if isinstance(tok, str) and tok.strip():
        return True
    return False


def api_login(user_name: str, password: str) -> dict[str, Any]:
    """Login via POST /api/auth/login with userName and password.

    Expects response: status, email, username, roles, token, ...
    Returns normalized dict with success, role, message, and full profile.
    """
    user_name = user_name.strip()
    try:
        payload = _http_post_json(
            LOGIN_URL,
            {"userName": user_name, "password": password},
        )

        if not isinstance(payload, dict):
            return {"success": False, "message": "Login failed: unexpected response."}

        merged = _merge_login_envelope(payload)
        if not _login_http_body_is_success(merged):
            message = _extract_error_message(payload, "Invalid username or password.")
            return {"success": False, "message": message}

        token = (
            merged.get("token")
            or merged.get("accessToken")
            or merged.get("access_token")
            or merged.get("jwt")
            or merged.get("idToken")
            or merged.get("id_token")
        )
        role = _role_from_login_payload(merged, token if isinstance(token, str) else None)
        message = _extract_error_message(payload, "Login successful.")

        email_guess = (
            merged.get("email")
            or merged.get("userEmail")
            or merged.get("user_email")
        )
        if not email_guess and isinstance(merged.get("user"), dict):
            u = merged["user"]
            email_guess = u.get("email") or u.get("userEmail")
        if not email_guess:
            email_guess = user_name

        uname_guess = merged.get("username") or merged.get("userName") or user_name
        if not uname_guess and isinstance(merged.get("user"), dict):
            u = merged["user"]
            uname_guess = u.get("username") or u.get("userName") or user_name

        result: dict[str, Any] = {
            "success": True,
            "role": role,
            "message": message,
            "email": email_guess,
            "userName": uname_guess,
        }
        for k, v in merged.items():
            if k != "password" and v is not None and k not in result:
                result[k] = v
        if "roles" not in result and result.get("role"):
            result["roles"] = result["role"]
        return result

    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Login failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_sign_out() -> dict[str, bool]:
    """Sign out / invalidate session."""
    time.sleep(0.05)
    return {"success": True}


def api_get_app_step_list(token: str | None = None) -> dict[str, Any]:
    """GET api-access/get-app-id-step-id-list — left-nav access. Requires Bearer JWT.

    Returns ``success``, ``message``, and ``steps`` (list of dicts). On failure, ``steps`` is
    ``[]`` so callers can apply strict left-nav filtering (no matching descriptions).
    """
    tok = _normalize_bearer_token(token)
    if not tok:
        return {"success": False, "message": "Not authenticated.", "steps": []}
    url = _api_url(GET_APP_STEP_LIST_PATH)
    headers: dict[str, str] = {"Authorization": f"Bearer {tok}"}
    try:
        data = _http_get_json(url, headers=headers, timeout_s=12.0)
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "steps": [],
        }
    except (URLError, TimeoutError, ValueError):
        _log_api("GET", url, response={"error": "Backend not reachable."})
        return {"success": False, "message": "Backend not reachable.", "steps": []}

    steps: list[Any]
    if isinstance(data, list):
        steps = data
    elif isinstance(data, dict):
        inner = (
            data.get("data")
            or data.get("steps")
            or data.get("content")
            or data.get("result")
        )
        steps = inner if isinstance(inner, list) else []
    else:
        steps = []

    out_steps: list[dict[str, Any]] = [x for x in steps if isinstance(x, dict)]
    return {"success": True, "message": "", "steps": out_steps}


def _do_update_profile_request(
    url: str, body: dict[str, Any], headers: dict[str, str], method: str
) -> tuple[dict[str, Any] | None, HTTPError | None]:
    """Execute profile update request. Returns (payload, None) on success or (None, exc) on HTTPError."""
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        return (payload, None)
    except HTTPError as exc:
        return (None, exc)


def api_update_profile(profile: dict[str, Any], token: str | None = None) -> dict[str, Any]:
    """Update profile via POST api/update-profile (or PUT if POST returns 403). Requires JWT.

    Returns dict with success, message. On success, may include updated user data.
    """
    token = str(token or "").strip()
    if not token:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(UPDATE_PROFILE_PATH)
    country_code = (profile.get("countryCode") or "+91").strip()
    mobile_raw = profile.get("mobileNumber") or profile.get("mobile_number")
    mobile_number = None
    if mobile_raw:
        num = str(mobile_raw).replace(" ", "").strip()
        mobile_number = f"{country_code}{num}" if num else None

    body = {
        "email": profile.get("email"),
        "firstName": profile.get("firstName") or profile.get("first_name"),
        "lastName": profile.get("lastName") or profile.get("last_name"),
        "mobileNumber": mobile_number,
    }
    body = {k: v for k, v in body.items() if v is not None}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }

    def _handle_success(payload: dict[str, Any]) -> dict[str, Any]:
        rej = _reject_json_business_failure(payload, message_fallback="Profile update failed.")
        if rej is not None:
            return rej
        ok = payload.get("success", payload.get("status") == "SUCCESS")
        if ok:
            updated = payload.get("user") or payload.get("data") or payload
            return {
                "success": True,
                "message": payload.get("message", "Profile updated."),
                "data": updated,
            }
        return {
            "success": False,
            "message": _extract_error_message(payload, "Profile update failed."),
        }

    def _handle_http_error(exc: HTTPError) -> dict[str, Any]:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        code = getattr(exc, "code", None)
        backend_msg = _extract_error_message(err_payload, "")
        base = f"Profile update failed (HTTP {code})."
        if backend_msg:
            base = f"{base} {backend_msg}"
        return {"success": False, "message": base}

    # Try POST first
    payload, exc = _do_update_profile_request(url, body, headers, "POST")
    if exc is not None and getattr(exc, "code", None) == 403:
        # Backend may expect PUT for updates; retry with PUT
        payload, exc = _do_update_profile_request(url, body, headers, "PUT")
    if exc is not None:
        return _handle_http_error(exc)
    if isinstance(payload, dict):
        return _handle_success(payload)
    return {"success": False, "message": "Profile update failed: unexpected server response."}


def api_get_all_users(token: str | None = None) -> dict[str, Any]:
    """Fetch all users from GET (default: api/user/get-all-user). Requires JWT.

    Returns dict with:
    - success: bool
    - data: list of user dicts (when success=True)
    - message: str (when success=False)
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url(GET_ALL_USERS_PATH)
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load users.", data=[]
            )
            if rej is not None:
                return rej
            data = payload.get("data") or payload.get("users") or payload.get("result")
            if data is not None:
                items = data if isinstance(data, list) else [data]
                return {"success": True, "data": items}
            return {"success": True, "data": [payload]}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_get_all_orgs(token: str | None = None) -> dict[str, Any]:
    """Fetch all organizations from GET api/org-mgmt/org/get-all-org. Requires JWT.

    Returns dict with:
    - success: bool
    - data: list of org dicts (when success=True)
    - message: str (when success=False)
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("api/org-mgmt/org/get-all-org")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load organizations.", data=[]
            )
            if rej is not None:
                return rej
            data = payload.get("data") or payload.get("orgs") or payload.get("organizations") or payload.get("result")
            if data is not None:
                items = data if isinstance(data, list) else [data]
                return {"success": True, "data": items}
            return {"success": True, "data": [payload]}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_create_org(
    org_name: str,
    org_code: str,
    industry: str,
    status: Any,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Create organization via POST api/org-mgmt/org/create-org. Requires JWT.

    Request body: orgName, orgCode, industry, status.
    Returns dict with success, message. On success, may include created org data.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/org-mgmt/org/create-org")
    if isinstance(status, bool):
        status_payload: Any = int(status)
    elif isinstance(status, (int, float)) and not isinstance(status, bool):
        status_payload = int(status) if isinstance(status, float) and status == int(status) else status
    else:
        status_text = str(status or "").strip()
        status_payload = status_text.upper() if status_text else "ACTIVE"
    body: dict[str, Any] = {
        "orgName": (org_name or "").strip(),
        "orgCode": (org_code or "").strip(),
        "industry": (industry or "").strip(),
        "status": status_payload,
    }
    try:
        payload = _http_post_json(
            url,
            body,
            timeout_s=8.0,
            extra_headers={"Authorization": f"Bearer {token}"},
        )
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to create organization."
            )
            if rej is not None:
                return rej
            ok = (
                payload.get("success") is True
                or payload.get("status") == "SUCCESS"
                or "orgId" in payload
                or "orgid" in payload
                or "id" in payload
            )
            if ok:
                return {"success": True, "message": payload.get("message", "Organization created."), "data": payload}
        return {"success": False, "message": _extract_error_message(payload, "Failed to create organization.")}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_org(
    org_id: int | str,
    org_name: str,
    org_code: str,
    industry: str,
    status: Any,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Update organization via PUT api/org-mgmt/org/update-org-by-id/{org_id}. Requires JWT.

    Request body: orgName, orgCode, industry, status (same rules as create-org: int seq, bool, or string).
    Returns dict with success, message. On success, may include updated org data.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/org-mgmt/org/update-org-by-id/{org_id}")
    if isinstance(status, bool):
        status_payload: Any = int(status)
    elif isinstance(status, (int, float)) and not isinstance(status, bool):
        status_payload = int(status) if isinstance(status, float) and status == int(status) else status
    else:
        status_text = str(status or "").strip()
        status_payload = status_text.upper() if status_text else "ACTIVE"
    body: dict[str, Any] = {
        "orgName": (org_name or "").strip(),
        "orgCode": (org_code or "").strip(),
        "industry": (industry or "").strip(),
        "status": status_payload,
    }
    try:
        _, payload = _http_put_json(
            url,
            body,
            timeout_s=8.0,
            extra_headers={"Authorization": f"Bearer {token}"},
        )
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to update organization."
            )
            if rej is not None:
                return rej
            ok = (
                payload.get("success") is True
                or payload.get("status") == "SUCCESS"
                or "orgId" in payload
                or "orgid" in payload
                or "id" in payload
            )
            if ok:
                return {"success": True, "message": payload.get("message", "Organization updated."), "data": payload}
        return {"success": False, "message": _extract_error_message(payload, "Failed to update organization.")}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_org(org_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """Delete organization via DELETE api/org-mgmt/org/delete-org-by-id/{org_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/org-mgmt/org/delete-org-by-id/{org_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_delete(url, headers=headers)
        if isinstance(payload, dict):
            if not payload:
                return {"success": True, "message": "Organization deleted successfully."}
            status = str(payload.get("status", "")).strip().upper()
            ok = payload.get("success") is True or status == "SUCCESS"
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "Organization deleted successfully."),
                }
            if status in ("FAILURE", "FAILED", "ERROR"):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete organization failed."),
                }
            if (
                payload.get("success") is False
                or payload.get("message")
                or payload.get("msg")
                or payload.get("error")
            ):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete organization failed."),
                }
            return {"success": True, "message": "Organization deleted successfully."}
        return {"success": True, "message": "Organization deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete organization failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_bu(token: str | None = None) -> dict[str, Any]:
    """Fetch all business units from GET api/org-mgmt/bu/get-all-bu. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("api/org-mgmt/bu/get-all-bu")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load business units.", data=[]
            )
            if rej is not None:
                return rej
            data = (
                payload.get("data")
                or payload.get("businessUnits")
                or payload.get("business_units")
                or payload.get("bus")
                or payload.get("result")
                or payload.get("content")
                or payload.get("items")
                or payload.get("records")
            )
            if data is not None:
                items = data if isinstance(data, list) else [data]
                return {"success": True, "data": items}
            return {"success": True, "data": [payload]}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_get_all_depts(token: str | None = None) -> dict[str, Any]:
    """Fetch all departments from GET api/org-mgmt/dept/get-all-dept. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("api/org-mgmt/dept/get-all-dept")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load departments.", data=[]
            )
            if rej is not None:
                return rej
            data = (
                payload.get("data")
                or payload.get("departments")
                or payload.get("department")
                or payload.get("depts")
                or payload.get("result")
                or payload.get("content")
                or payload.get("items")
                or payload.get("records")
            )
            if data is not None:
                items = data if isinstance(data, list) else [data]
                return {"success": True, "data": items}
            return {"success": True, "data": [payload]}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_create_dept(
    bu_id: int | str,
    dept_name: str,
    *,
    parent_dept_id: int | str | None = None,
    status: Any | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Create department via POST api/org-mgmt/dept/create-dept. Body: buId, deptName; parentDeptId, status if set."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/org-mgmt/dept/create-dept")
    body: dict[str, Any] = {
        "buId": int(bu_id),
        "deptName": (dept_name or "").strip(),
    }
    if parent_dept_id is not None:
        body["parentDeptId"] = int(parent_dept_id)
    if status is not None:
        if isinstance(status, bool):
            body["status"] = int(status)
        elif isinstance(status, (int, float)) and not isinstance(status, bool):
            body["status"] = int(status) if isinstance(status, float) and status == int(status) else status
        else:
            st = str(status or "").strip()
            body["status"] = st.upper() if st else "ACTIVE"
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to create department."
            )
            if rej is not None:
                return rej
            ok = (
                payload.get("success") is True
                or payload.get("status") == "SUCCESS"
                or "deptId" in payload
                or "dept_id" in payload
                or "departmentId" in payload
                or "id" in payload
            )
            if ok:
                return {"success": True, "message": payload.get("message", "Department created."), "data": payload}
        return {"success": False, "message": _extract_error_message(payload, "Failed to create department.")}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_dept(
    dept_id: int | str,
    *,
    bu_id: int | str,
    dept_name: str,
    parent_dept_id: int | str | None = None,
    status: Any | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Update department via PUT api/org-mgmt/dept/update-dept-by-id/{dept_id}. Body: buId, deptName; parentDeptId, status if set."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/org-mgmt/dept/update-dept-by-id/{dept_id}")
    body: dict[str, Any] = {
        "buId": int(bu_id),
        "deptName": (dept_name or "").strip(),
    }
    if parent_dept_id is not None:
        body["parentDeptId"] = int(parent_dept_id)
    if status is not None:
        if isinstance(status, bool):
            body["status"] = int(status)
        elif isinstance(status, (int, float)) and not isinstance(status, bool):
            body["status"] = int(status) if isinstance(status, float) and status == int(status) else status
        else:
            st = str(status or "").strip()
            body["status"] = st.upper() if st else "ACTIVE"
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None) or resp.getcode() or 200

        if not raw or not str(raw).strip():
            return {"success": True, "message": "Department updated successfully."}

        try:
            payload: Any = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            if 200 <= int(status) < 300:
                return {"success": True, "message": "Department updated successfully."}
            return {"success": False, "message": "Invalid response from server."}

        if payload is True:
            return {"success": True, "message": "Department updated successfully."}

        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to update department."),
                }
            if payload.get("error") is not None or payload.get("errors") is not None:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to update department."),
                }
            ok = (
                payload.get("success") is True
                or str(payload.get("status", "")).upper() in ("SUCCESS", "OK")
                or "deptId" in payload
                or "dept_id" in payload
                or "departmentId" in payload
            )
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "Department updated."),
                    "data": payload,
                }
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to update department."
            )
            if rej is not None:
                return rej
            if 200 <= int(status) < 300:
                return {
                    "success": True,
                    "message": payload.get("message", "Department updated."),
                    "data": payload,
                }

        return {
            "success": False,
            "message": _extract_error_message(
                payload if isinstance(payload, dict) else {},
                "Failed to update department.",
            ),
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_dept(dept_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """Delete department via DELETE api/org-mgmt/dept/delete-dept-by-id/{dept_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/org-mgmt/dept/delete-dept-by-id/{dept_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_delete(url, headers=headers)
        if isinstance(payload, dict):
            if not payload:
                return {"success": True, "message": "Department deleted successfully."}
            status = str(payload.get("status", "")).strip().upper()
            ok = payload.get("success") is True or status == "SUCCESS"
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "Department deleted successfully."),
                }
            if status in ("FAILURE", "FAILED", "ERROR"):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete department failed."),
                }
            if (
                payload.get("success") is False
                or payload.get("message")
                or payload.get("msg")
                or payload.get("error")
            ):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete department failed."),
                }
            return {"success": True, "message": "Department deleted successfully."}
        return {"success": True, "message": "Department deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete department failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_positions(token: str | None = None) -> dict[str, Any]:
    """Fetch all positions from GET api/org-mgmt/position/get-all-position. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("api/org-mgmt/position/get-all-position")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load positions.", data=[]
            )
            if rej is not None:
                return rej
            data = (
                payload.get("data")
                or payload.get("positions")
                or payload.get("position")
                or payload.get("result")
                or payload.get("content")
                or payload.get("items")
            )
            if data is not None:
                items = data if isinstance(data, list) else [data]
                return {"success": True, "data": items}
            return {"success": True, "data": [payload]}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_create_position(
    position_name: str,
    hierarchy_level: int,
    *,
    status: Any | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Create position via POST api/org-mgmt/position/create-position. Body: positionName, hierarchyLevel; status (seq) if set."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/org-mgmt/position/create-position")
    body: dict[str, Any] = {
        "positionName": (position_name or "").strip(),
        "hierarchyLevel": int(hierarchy_level),
    }
    if status is not None:
        if isinstance(status, bool):
            body["status"] = int(status)
        elif isinstance(status, (int, float)) and not isinstance(status, bool):
            body["status"] = int(status) if isinstance(status, float) and status == int(status) else status
        else:
            st = str(status or "").strip()
            body["status"] = st.upper() if st else "ACTIVE"
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            biz_status = str(payload.get("status", "")).strip().upper()
            if biz_status in ("FAILURE", "FAILED", "ERROR"):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to create position."),
                }
            ok = (
                payload.get("success") is True
                or biz_status == "SUCCESS"
                or "positionId" in payload
                or "position_id" in payload
                or "id" in payload
            )
            if ok:
                return {"success": True, "message": payload.get("message", "Position created."), "data": payload}
        return {"success": False, "message": "Unexpected response from server."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_position(
    position_id: int | str,
    *,
    position_name: str,
    hierarchy_level: int,
    status: Any | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Update position via PUT api/org-mgmt/position/update-position-by-id/{position_id}. Body: positionName, hierarchyLevel; status (seq) if set."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/org-mgmt/position/update-position-by-id/{position_id}")
    body: dict[str, Any] = {
        "positionName": (position_name or "").strip(),
        "hierarchyLevel": int(hierarchy_level),
    }
    if status is not None:
        if isinstance(status, bool):
            body["status"] = int(status)
        elif isinstance(status, (int, float)) and not isinstance(status, bool):
            body["status"] = int(status) if isinstance(status, float) and status == int(status) else status
        else:
            st = str(status or "").strip()
            body["status"] = st.upper() if st else "ACTIVE"
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
            http_status = getattr(resp, "status", None) or resp.getcode() or 200

        if not raw or not str(raw).strip():
            return {"success": True, "message": "Position updated successfully."}

        try:
            payload: Any = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            if 200 <= int(http_status) < 300:
                return {"success": True, "message": "Position updated successfully."}
            return {"success": False, "message": "Invalid response from server."}

        if isinstance(payload, dict):
            st = str(payload.get("status", "")).strip().upper()
            if st in ("FAILURE", "FAILED", "ERROR"):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to update position."),
                }
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to update position."),
                }
            ok = (
                payload.get("success") is True
                or st == "SUCCESS"
                or "positionId" in payload
                or "position_id" in payload
            )
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "Position updated."),
                    "data": payload,
                }
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to update position."
            )
            if rej is not None:
                return rej
            if 200 <= int(http_status) < 300:
                return {
                    "success": True,
                    "message": payload.get("message", "Position updated."),
                    "data": payload,
                }

        return {
            "success": False,
            "message": _extract_error_message(
                payload if isinstance(payload, dict) else {},
                "Failed to update position.",
            ),
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_position(position_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """Delete position via DELETE api/org-mgmt/position/delete-position-by-id/{position_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/org-mgmt/position/delete-position-by-id/{position_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_delete(url, headers=headers)
        if isinstance(payload, dict):
            if not payload:
                return {"success": True, "message": "Position deleted successfully."}
            status = str(payload.get("status", "")).strip().upper()
            ok = payload.get("success") is True or status == "SUCCESS"
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "Position deleted successfully."),
                }
            if status in ("FAILURE", "FAILED", "ERROR"):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete position failed."),
                }
            if (
                payload.get("success") is False
                or payload.get("message")
                or payload.get("msg")
                or payload.get("error")
            ):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete position failed."),
                }
            return {"success": True, "message": "Position deleted successfully."}
        return {"success": True, "message": "Position deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete position failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_roles(token: str | None = None) -> dict[str, Any]:
    """Fetch all roles from GET api/org-mgmt/role/get-all-role. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("api/org-mgmt/role/get-all-role")
    headers: dict[str, str] = {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load roles.", data=[]
            )
            if rej is not None:
                return rej
            data = (
                payload.get("data")
                or payload.get("roles")
                or payload.get("role")
                or payload.get("result")
                or payload.get("content")
                or payload.get("items")
            )
            if data is not None:
                items = data if isinstance(data, list) else [data]
                return {"success": True, "data": items}
            return {"success": True, "data": [payload]}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_create_role(role_name: str, *, token: str | None = None) -> dict[str, Any]:
    """Create role via POST api/org-mgmt/role/create-role?roleName=<name> (query param, no body). Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    name = (role_name or "").strip()
    if not name:
        return {"success": False, "message": "Role name is required."}
    base = _api_url("api/org-mgmt/role/create-role")
    url = f"{base}?{urlencode({'roleName': name})}"
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        # POST with empty body; roleName is only in the query string (matches backend / Postman).
        req = Request(url, data=b"", headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, list):
            return {"success": True, "message": "Role created.", "data": payload}
        if isinstance(payload, dict):
            status = str(payload.get("status", "")).strip().upper()
            if status in ("FAILURE", "FAILED", "ERROR"):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to create role."),
                }
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to create role."),
                }
            ok = (
                payload.get("success") is True
                or status == "SUCCESS"
                or "roleId" in payload
                or "role_id" in payload
                or "id" in payload
            )
            if ok:
                return {"success": True, "message": payload.get("message", "Role created."), "data": payload}
        if payload == {}:
            return {"success": True, "message": "Role created successfully."}
        return {"success": False, "message": "Unexpected response from server."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_role(
    role_id: int | str,
    role_name: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Update role via PUT api/org-mgmt/role/update-role-by-id/{role_id}?roleName=<name> (query param, no body). Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    name = (role_name or "").strip()
    if not name:
        return {"success": False, "message": "Role name is required."}
    base = _api_url(f"api/org-mgmt/role/update-role-by-id/{role_id}")
    url = f"{base}?{urlencode({'roleName': name})}"
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            status = str(payload.get("status", "")).strip().upper()
            if status in ("FAILURE", "FAILED", "ERROR"):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Update role failed."),
                }
            ok = (
                payload.get("success") is True
                or status == "SUCCESS"
                or "roleId" in payload
                or "role_id" in payload
            )
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "Role updated successfully."),
                    "data": payload,
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Update role failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update role failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_role(role_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """Delete role via DELETE api/org-mgmt/role/delete-role-by-id/{role_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/org-mgmt/role/delete-role-by-id/{role_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_delete(url, headers=headers)
        if isinstance(payload, dict):
            if not payload:
                return {"success": True, "message": "Role deleted successfully."}
            status = str(payload.get("status", "")).strip().upper()
            ok = payload.get("success") is True or status == "SUCCESS"
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "Role deleted successfully."),
                }
            if status in ("FAILURE", "FAILED", "ERROR"):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete role failed."),
                }
            if (
                payload.get("success") is False
                or payload.get("message")
                or payload.get("msg")
                or payload.get("error")
            ):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete role failed."),
                }
            return {"success": True, "message": "Role deleted successfully."}
        return {"success": True, "message": "Role deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete role failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_bu(
    organization_id: int,
    bu_name: str,
    parent_bu: int | None = None,
    *,
    status: Any | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Create business unit via POST api/org-mgmt/bu/create-bu. Body: organizationId, buName, parentBu (optional), status (optional)."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/org-mgmt/bu/create-bu")
    body: dict[str, Any] = {
        "organizationId": int(organization_id),
        "buName": (bu_name or "").strip(),
    }
    if parent_bu is not None:
        body["parentBu"] = int(parent_bu)
    if status is not None:
        if isinstance(status, bool):
            body["status"] = int(status)
        elif isinstance(status, (int, float)) and not isinstance(status, bool):
            body["status"] = int(status) if isinstance(status, float) and status == int(status) else status
        else:
            st = str(status or "").strip()
            body["status"] = st.upper() if st else "ACTIVE"
    try:
        payload = _http_post_json(
            url,
            body,
            timeout_s=8.0,
            extra_headers={"Authorization": f"Bearer {token}"},
        )
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to create business unit."
            )
            if rej is not None:
                return rej
            ok = (
                payload.get("success") is True
                or payload.get("status") == "SUCCESS"
                or "buId" in payload
                or "bu_id" in payload
                or "id" in payload
            )
            if ok:
                return {"success": True, "message": payload.get("message", "Business unit created."), "data": payload}
        return {"success": False, "message": _extract_error_message(payload, "Failed to create business unit.")}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_bu(
    bu_id: int | str,
    organization_id: int,
    bu_name: str,
    parent_bu: int | None = None,
    *,
    status: Any | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Update business unit via PUT api/org-mgmt/bu/update-bu-by-id/{bu_id}. Body: organizationId, buName; parentBu and status if set."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/org-mgmt/bu/update-bu-by-id/{bu_id}")
    body: dict[str, Any] = {
        "organizationId": int(organization_id),
        "buName": (bu_name or "").strip(),
    }
    if parent_bu is not None:
        body["parentBu"] = int(parent_bu)
    if status is not None:
        if isinstance(status, bool):
            body["status"] = int(status)
        elif isinstance(status, (int, float)) and not isinstance(status, bool):
            body["status"] = int(status) if isinstance(status, float) and status == int(status) else status
        else:
            st = str(status or "").strip()
            body["status"] = st.upper() if st else "ACTIVE"
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None) or resp.getcode() or 200

        # Many backends return 200/204 with empty body or minimal JSON on success.
        if not raw or not str(raw).strip():
            return {"success": True, "message": "Business unit updated successfully."}

        try:
            payload: Any = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            if 200 <= int(status) < 300:
                return {"success": True, "message": "Business unit updated successfully."}
            return {"success": False, "message": "Invalid response from server."}

        if payload is True:
            return {"success": True, "message": "Business unit updated successfully."}

        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to update business unit."),
                }
            if payload.get("error") is not None or payload.get("errors") is not None:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to update business unit."),
                }

            inner = payload.get("data")
            if isinstance(inner, dict) and ("buId" in inner or "bu_id" in inner):
                return {
                    "success": True,
                    "message": payload.get("message", "Business unit updated."),
                    "data": payload,
                }

            ok = (
                payload.get("success") is True
                or str(payload.get("status", "")).upper() in ("SUCCESS", "OK")
                or "buId" in payload
                or "bu_id" in payload
            )
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "Business unit updated."),
                    "data": payload,
                }

            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to update business unit."
            )
            if rej is not None:
                return rej

            # 2xx with JSON but no explicit markers — treat as success (entity-only responses).
            if 200 <= int(status) < 300:
                return {
                    "success": True,
                    "message": payload.get("message", "Business unit updated."),
                    "data": payload,
                }

        return {
            "success": False,
            "message": _extract_error_message(
                payload if isinstance(payload, dict) else {},
                "Failed to update business unit.",
            ),
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_bu(bu_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """Delete business unit via DELETE api/org-mgmt/bu/delete-bu-by-id/{bu_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/org-mgmt/bu/delete-bu-by-id/{bu_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_delete(url, headers=headers)
        if isinstance(payload, dict):
            if not payload:
                return {"success": True, "message": "Business unit deleted successfully."}
            status = str(payload.get("status", "")).strip().upper()
            ok = payload.get("success") is True or status == "SUCCESS"
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "Business unit deleted successfully."),
                }
            if status in ("FAILURE", "FAILED", "ERROR"):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete business unit failed."),
                }
            if (
                payload.get("success") is False
                or payload.get("message")
                or payload.get("msg")
                or payload.get("error")
            ):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete business unit failed."),
                }
            return {"success": True, "message": "Business unit deleted successfully."}
        return {"success": True, "message": "Business unit deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete business unit failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_business_units(token: str | None = None) -> dict[str, Any]:
    """Fetch all business units from GET api/orgs/get-all-business-units. Requires JWT.

    Returns dict with:
    - success: bool
    - data: list of business unit dicts (when success=True)
    - message: str (when success=False)
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("api/orgs/get-all-business-units")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load business units.", data=[]
            )
            if rej is not None:
                return rej
            data = (
                payload.get("data")
                or payload.get("businessUnits")
                or payload.get("business_units")
                or payload.get("result")
            )
            if data is not None:
                items = data if isinstance(data, list) else [data]
                return {"success": True, "data": items}
            return {"success": True, "data": [payload]}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_get_all_user_type_in_api_project(*, token: str | None = None) -> dict[str, Any]:
    """Fetch projects from GET api/get-all-api-user-types. Requires JWT.

    No request body or query params.
    Returns dict with success, data, message.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("api/get-all-api-user-types")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load API user types.", data=[]
            )
            if rej is not None:
                return rej
            data_list = payload.get("data") or payload.get("projects") or payload.get("result")
            if data_list is not None:
                items = data_list if isinstance(data_list, list) else [data_list]
                return {"success": True, "data": items}
            return {"success": True, "data": [payload]}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        code = getattr(exc, "code", None)
        base_msg = _extract_error_message(
            err_payload, f"Request failed ({code or 'HTTP error'})."
        )
        return {"success": False, "message": base_msg, "data": []}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_delete_user_type_in_api_project_by_id(
    internal_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Delete user type via DELETE api/delete-api-user-type-by-id/{id}.

    Path param {id} is the user type Id (Internal).
    No request body.
    Returns dict with success, message.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/delete-api-user-type-by-id/{internal_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_delete(url, headers=headers)
        if isinstance(payload, dict):
            status = str(payload.get("status", "")).strip().upper()
            ok = (
                status == "SUCCESS"
                or status == "OK"
                or status == "200"
                or payload.get("success") is True
            )
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "User type deleted successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Delete user type failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete user type failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_user_type_in_api_project(
    project_id: int | str,
    role: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Create user type in API project via POST api/create-api-user-type/{project_id}. Requires JWT.

    Request body: { projectId, userType }
    Returns dict with success, message.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/create-api-user-type/{project_id}")
    body = {
        "projectId": project_id,
        "userType": (role or "USER").strip().upper(),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            ok = payload.get("success") is True or payload.get("status") == "SUCCESS"
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "User type added successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Create user type failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create user type failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_user_type_in_api_project_by_id(
    internal_id: int | str,
    role: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Update user type via PUT api/update-api-user-type-by-id/{id}.

    Path param {id} is the user type Id (Internal).
    Request body: { "userType": "SADMIN" }
    Returns dict with success, message.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/update-api-user-type-by-id/{internal_id}")
    body = {"userType": (role or "").strip().upper()}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            status = str(payload.get("status", "")).strip().upper()
            ok = (
                status == "SUCCESS"
                or status == "OK"
                or status == "200"
                or payload.get("success") is True
            )
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "User type updated successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Update user type failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update user type failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_projects(token: str | None = None) -> dict[str, Any]:
    """Fetch all projects from GET /api/get-all-api-projects. Requires JWT.

    Returns dict with:
    - success: bool
    - data: list of project dicts (when success=True)
    - message: str (when success=False)
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("/api/get-all-api-projects")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load projects.", data=[]
            )
            if rej is not None:
                return rej
            data = (
                payload.get("data")
                or payload.get("projects")
                or payload.get("result")
                or payload.get("content")
                or payload.get("items")
                or payload.get("body")
            )
            if data is not None:
                items = data if isinstance(data, list) else [data]
                return {"success": True, "data": items}
            return {"success": True, "data": [payload]}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_create_project(
    project_name: str,
    *,
    token: str | None = None,
    project_desc: str | None = None,
    project_owner_user_id: str | None = None,
    project_status: str | None = None,
    project_server: str | None = None,
    project_port: str | int | None = None,
) -> dict[str, Any]:
    """Create project via POST /api/create-api-project. Requires JWT.

    Request body: projectName, projectDesc, projectOwnerUserId, projectStatus,
    projectServer, projectPort.
    Returns dict with success, message. On success, may include created project data.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("/api/create-api-project")

    # projectPort as integer (API expects number)
    port_val: int = 0
    if project_port is not None and str(project_port).strip():
        try:
            port_val = int(str(project_port).strip())
        except ValueError:
            port_val = 0

    body: dict[str, Any] = {
        "projectName": (project_name or "").strip(),
        "projectDesc": (project_desc or "").strip(),
        "projectOwnerUserId": (project_owner_user_id or "").strip(),
        "projectStatus": (project_status or "ACTIVE").strip().upper(),
        "projectServer": (project_server or "").strip(),
        "projectPort": port_val,
    }

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Create project failed."
            )
            if rej is not None:
                return rej
            # Success: explicit success, status SUCCESS, or has projectId/projectid
            ok = (
                payload.get("success") is True
                or payload.get("status") == "SUCCESS"
                or "projectId" in payload
                or "projectid" in payload
            )
            if ok:
                created = payload.get("project") or payload.get("data") or payload
                return {
                    "success": True,
                    "message": payload.get("message", "Project created successfully."),
                    "data": created,
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Create project failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create project failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_project(
    project_id: int | str,
    project_name: str,
    *,
    token: str | None = None,
    project_desc: str | None = None,
    project_owner_user_id: str | None = None,
    project_status: str | None = None,
    project_server: str | None = None,
    project_port: str | int | None = None,
) -> dict[str, Any]:
    """Update project via PUT /api/update-api-project-by-id/{id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"/api/update-api-project-by-id/{project_id}")

    port_val: int | str = 0
    if project_port is not None and str(project_port).strip():
        try:
            port_val = int(str(project_port).strip())
        except ValueError:
            port_val = 0

    body: dict[str, Any] = {
        "projectName": (project_name or "").strip(),
        "projectDesc": (project_desc or "").strip(),
        "projectOwnerUserId": (project_owner_user_id or "").strip(),
        "projectStatus": (project_status or "ACTIVE").strip(),
        "projectServer": (project_server or "").strip(),
        "projectPort": port_val,
    }

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Update project failed."
            )
            if rej is not None:
                return rej
            ok = (
                payload.get("success") is True
                or payload.get("status") == "SUCCESS"
                or "projectId" in payload
                or "projectid" in payload
            )
            if ok:
                updated = payload.get("project") or payload.get("data") or payload
                return {
                    "success": True,
                    "message": payload.get("message", "Project updated successfully."),
                    "data": updated,
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Update project failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update project failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_project(project_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """Delete project via DELETE /api/delete-api-project-by-id/{id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"/api/delete-api-project-by-id/{project_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_delete(url, headers=headers)
        if isinstance(payload, dict):
            ok = payload.get("success") is True or payload.get("status") == "SUCCESS"
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "Project deleted successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Delete project failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete project failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_user(
    email: str,
    password: str,
    *,
    token: str | None = None,
    firstName: str | None = None,
    lastName: str | None = None,
    mobileNumber: str | None = None,
    status: str | None = None,
    orgId: str | int | None = None,
    deptId: str | int | None = None,
    positionId: str | int | None = None,
) -> dict[str, Any]:
    """Create user via POST (default: api/user/create-user). Requires JWT (only api/auth/login is unauthenticated).

    Request body: firstName, lastName, email, mobileNumber, password, status, orgId, deptId, positionId.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(CREATE_USER_PATH)
    body: dict[str, Any] = {
        "firstName": (firstName or "").strip() or None,
        "lastName": (lastName or "").strip() or None,
        "email": email.strip(),
        "mobileNumber": (mobileNumber or "").strip() or None,
        "password": password,
        "status": (status or "ACTIVE").strip().upper(),
        "positionId": positionId,
        "deptId": deptId,
        "orgId": orgId,
    }

    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            ok = payload.get("success", payload.get("status") == "SUCCESS")
            if ok:
                created = payload.get("user") or payload.get("data") or payload
                return {
                    "success": True,
                    "message": payload.get("message", "User created successfully."),
                    "data": created,
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Create user failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create user failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_user(
    user_id: int | str,
    *,
    token: str | None = None,
    firstName: str | None = None,
    lastName: str | None = None,
    email: str | None = None,
    mobileNumber: str | None = None,
    orgId: int | None = None,
    deptId: int | None = None,
    positionId: int | None = None,
) -> dict[str, Any]:
    """Update user via PUT (default: api/user/update-user-by-id/{user_id}; or POST if PUT returns 403). Requires JWT.

    Request body: email, firstName, lastName, mobileNumber (country code + national digits),
    orgId, deptId, positionId.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"{UPDATE_USER_PATH.rstrip('/')}/{user_id}")
    body: dict[str, Any] = {
        "email": (email or "").strip(),
        "firstName": (firstName or "").strip(),
        "lastName": (lastName or "").strip(),
        "mobileNumber": (mobileNumber or "").strip(),
        "orgId": orgId,
        "deptId": deptId,
        "positionId": positionId,
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        for method in ("PUT", "POST"):
            req = Request(url, data=data, headers=headers, method=method)
            try:
                with _http_urlopen_logged(req, timeout=8.0) as resp:
                    raw = resp.read()
            except HTTPError as exc:
                if exc.code == 403 and method == "PUT":
                    continue
                raise
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            if isinstance(payload, dict):
                ok = payload.get("success") is True or payload.get("status") in ("SUCCESS", "OK")
                if ok:
                    data = payload.get("user") or payload.get("data")
                    if data is None:
                        data = {k: v for k, v in payload.items()
                                if k not in ("success", "status", "message")}
                    return {
                        "success": True,
                        "message": payload.get("message", "User updated successfully."),
                        "data": data,
                    }
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Update user failed."),
                }
            return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update user failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_user(user_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """Delete user via DELETE (default: api/user/delete-user-by-id/{user_id}). Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"{DELETE_USER_PATH.rstrip('/')}/{user_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            ok = payload.get("success") is True or payload.get("status") in ("SUCCESS", "OK")
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "User deleted successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Delete user failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete user failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_reset_user_password(
    user_name: str,
    password: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST (default: api/user/reset-user-password) with JSON { userName, password }. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    uname = (user_name or "").strip()
    if not uname:
        return {"success": False, "message": "Username is required."}
    pw = password or ""
    if not pw:
        return {"success": False, "message": "Password is required."}
    url = _api_url(RESET_USER_PASSWORD_PATH.strip())
    body = {"userName": uname, "password": pw}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            ok = payload.get("success") is True or str(payload.get("status", "")).upper() in (
                "SUCCESS",
                "OK",
            )
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "Password reset successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Reset password failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload,
                f"Reset password failed ({getattr(exc, 'code', 'HTTP error')}).",
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_user_status_by_id(
    user_id: int | str,
    status: str,
    *,
    valid_from: str | None = None,
    valid_to: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """POST api/update-user-status-by-id/{id}. validFrom/validTo are sent for ACTIVE only."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    status_value = (status or "").strip().upper()
    # Backend user-status endpoint expects DEACTIVE for inactive users.
    if status_value == "INACTIVE":
        status_value = "DEACTIVE"
    if not status_value:
        return {"success": False, "message": "Status is required."}
    uid = str(user_id).strip()
    if not uid:
        return {"success": False, "message": "User Id is required."}

    body: dict[str, Any] = {"status": status_value}
    if status_value == "ACTIVE":
        vf_raw = (valid_from or "").strip()
        vt_raw = (valid_to or "").strip()
        if not vf_raw or not vt_raw:
            return {
                "success": False,
                "message": "Valid From and Valid To are required when status is ACTIVE.",
            }
        vf_date = vf_raw.split("T", 1)[0]
        vt_date = vt_raw.split("T", 1)[0]
        body["validFrom"] = f"{vf_date}T00:00:00"
        body["validTo"] = f"{vt_date}T23:59:59"
    url = _api_url(f"{UPDATE_USER_STATUS_PATH.rstrip('/')}/{uid}")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            ok = payload.get("success") is True or str(payload.get("status", "")).upper() in ("SUCCESS", "OK")
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "User status updated successfully."),
                    "data": payload.get("data") or payload.get("user") or payload,
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Update user status failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload,
                f"Update user status failed ({getattr(exc, 'code', 'HTTP error')}).",
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_user_role_status_by_id(
    user_id: int | str,
    role: str,
    status: str,
    *,
    valid_from: str | None = None,
    valid_to: str | None = None,
    default_role: bool | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """POST api/update-user-role-status-by-id/{id}. validFrom/validTo are sent for ACTIVE only."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    uid = str(user_id).strip()
    role_value = (role or "").strip()
    status_value = (status or "").strip().upper()
    if not uid:
        return {"success": False, "message": "User Id is required."}
    if not role_value:
        return {"success": False, "message": "Role is required."}
    if not status_value:
        return {"success": False, "message": "Status is required."}

    body: dict[str, Any] = {"role": role_value, "status": status_value}
    if default_role is not None:
        body["defaultRole"] = bool(default_role)
    if status_value == "ACTIVE":
        vf_raw = (valid_from or "").strip()
        vt_raw = (valid_to or "").strip()
        if not vf_raw or not vt_raw:
            return {
                "success": False,
                "message": "Valid From and Valid To are required when status is ACTIVE.",
            }
        vf_date = vf_raw.split("T", 1)[0]
        vt_date = vt_raw.split("T", 1)[0]
        body["validFrom"] = f"{vf_date}T00:00:00"
        body["validTo"] = f"{vt_date}T23:59:59"

    url = _api_url(f"{UPDATE_USER_ROLE_STATUS_PATH.rstrip('/')}/{uid}")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            ok = payload.get("success") is True or str(payload.get("status", "")).upper() in ("SUCCESS", "OK")
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "User role status updated successfully."),
                    "data": payload.get("data") or payload.get("user") or payload,
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Update user role status failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload,
                f"Update user role status failed ({getattr(exc, 'code', 'HTTP error')}).",
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_assign_user_role(
    *,
    user_id: int | str,
    role_id: int | str,
    valid_from: str,
    valid_to: str,
    default_role: bool = True,
    status: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """Assign role to user via POST (default: api/user-role-assignment/assign). Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(USER_ROLE_ASSIGN_PATH)
    vf_raw = (valid_from or "").strip()
    vt_raw = (valid_to or "").strip()
    # Enforce API payload format:
    # validFrom -> YYYY-MM-DDT00:00:00
    # validTo   -> YYYY-MM-DDT23:59:59
    vf_date = vf_raw.split("T", 1)[0] if vf_raw else ""
    vt_date = vt_raw.split("T", 1)[0] if vt_raw else ""
    vf = f"{vf_date}T00:00:00" if vf_date else ""
    vt = f"{vt_date}T23:59:59" if vt_date else ""
    body: dict[str, Any] = {
        "userId": user_id,
        "roleId": role_id,
        "validFrom": vf,
        "validTo": vt,
        "defaultRole": bool(default_role),
    }
    if status is not None and str(status).strip():
        body["status"] = str(status).strip().upper()
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            ok = payload.get("success") is True or str(payload.get("status", "")).upper() == "SUCCESS"
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "Role assigned successfully."),
                    "data": payload.get("data") or payload,
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Assign role failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Assign role failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_user_role_assignment_by_id(
    assignment_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    """Delete user-role assignment via DELETE (default: api/user-role-assignment/delete-by-id/{id}). Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"{USER_ROLE_ASSIGNMENT_DELETE_BY_ID_PREFIX.rstrip('/')}/{assignment_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            ok = payload.get("success") is True or str(payload.get("status", "")).upper() == "SUCCESS"
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "User role assignment deleted successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Delete user role assignment failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete user role assignment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_user_role_assignment_by_id(
    assignment_id: int | str,
    *,
    user_id: int | str,
    role_id: int | str,
    valid_from: str,
    valid_to: str,
    default_role: bool = True,
    status: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT (default: api/user-role-assignment/update-by-id/{id}) — JSON body (userId, roleId, validFrom, validTo, defaultRole, status)."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}

    def _json_int_id(v: int | str) -> int | str:
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v
        s = str(v).strip()
        return int(s) if s.isdigit() else v

    url = _api_url(f"{USER_ROLE_ASSIGNMENT_UPDATE_BY_ID_PREFIX.rstrip('/')}/{assignment_id}")
    vf_raw = (valid_from or "").strip()
    vt_raw = (valid_to or "").strip()
    vf_out = ""
    vt_out = ""
    if vf_raw:
        vf_out = vf_raw if "T" in vf_raw else f"{vf_raw.split('T', 1)[0]}T00:00:00"
    if vt_raw:
        vt_out = vt_raw if "T" in vt_raw else f"{vt_raw.split('T', 1)[0]}T23:59:59"
    status_out = str(status).strip().upper() if status is not None and str(status).strip() else "ACTIVE"
    body: dict[str, Any] = {
        "userId": _json_int_id(user_id),
        "roleId": _json_int_id(role_id),
        "validFrom": vf_out,
        "validTo": vt_out,
        "defaultRole": bool(default_role),
        "status": status_out,
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        print(f"[UPDATE USER ROLE] URL: {url}", flush=True)
        print(f"[UPDATE USER ROLE] REQUEST BODY: {json.dumps(body)}", flush=True)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        print(f"[UPDATE USER ROLE] RESPONSE: {json.dumps(payload)}", flush=True)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Update role assignment failed."
            )
            if rej is not None:
                return rej
            ok = payload.get("success") is True or str(payload.get("status", "")).upper() == "SUCCESS"
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "Role assignment updated successfully."),
                    "data": payload.get("data") or payload,
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Update role assignment failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        print(f"[UPDATE USER ROLE] URL: {url}", flush=True)
        print(f"[UPDATE USER ROLE] ERROR RESPONSE: {json.dumps(err_payload)}", flush=True)
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update role assignment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        print(f"[UPDATE USER ROLE] URL: {url}", flush=True)
        print("[UPDATE USER ROLE] ERROR RESPONSE: Backend not reachable.", flush=True)
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_api_details(
    *,
    token: str | None = None,
    app_id: int | str | None = None,
) -> dict[str, Any]:
    """Fetch all API details from GET api/get-all-api-details. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    # Keep app_id arg for backward compatibility at call sites, but do not
    # send it as request param for this endpoint.
    _ = app_id
    url = _api_url("api/get-all-api-details")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load API details.", data=[]
            )
            if rej is not None:
                return rej
            data_list = payload.get("data") or payload.get("apiDetails") or payload.get("result")
            if data_list is not None:
                items = data_list if isinstance(data_list, list) else [data_list]
                return {"success": True, "data": items}
            return {"success": True, "data": [payload]}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_get_api_detail_by_id(
    api_id: int | str,
    *,
    token: str | None = None,
    app_id: int | str | None = None,
) -> dict[str, Any]:
    """Fetch one API detail by id. Sends optional ``appId`` query param when available."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": {}}
    api_id_text = str(api_id).strip()
    if not api_id_text:
        return {"success": False, "message": "API id is required.", "data": {}}
    base = f"api/get-api-detail-by-id/{_api_path_id_segment(api_id_text)}"
    app_id_text = str(app_id).strip() if app_id is not None else ""
    url = _api_url(f"{base}?{urlencode({'appId': app_id_text})}") if app_id_text else _api_url(base)
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load API detail.", data={}
            )
            if rej is not None:
                return rej
            data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {"success": True, "data": data_obj}
        return {"success": False, "message": "Unexpected response format.", "data": {}}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": {},
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": {}}


def api_get_etl_logs_by_type(
    log_type: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET ETL logs filtered by type (e.g. ``SCAN``) from ``api/etl/logs/type?type=``."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    kind = (log_type or "").strip().upper()
    if not kind:
        return {"success": False, "message": "Log type is required.", "data": []}
    base = _api_url(ETL_LOGS_BY_TYPE_PATH)
    sep = "&" if "?" in base else "?"
    url = f"{base}{sep}type={quote(kind, safe='')}"
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=15.0)
        if isinstance(payload, list):
            rows = [r for r in payload if isinstance(r, dict)]
            return {"success": True, "data": rows, "message": ""}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load ETL logs.", data=[]
            )
            if rej is not None:
                return rej
            rows = payload.get("data")
            if isinstance(rows, list):
                return {
                    "success": True,
                    "data": [r for r in rows if isinstance(r, dict)],
                    "message": str(payload.get("message") or ""),
                }
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_get_etl_logs_by_connection_and_operation_type(
    connection_id: int | str,
    operation_type: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET ETL logs for one connection and operation (e.g. ``SCAN``).

    Default path: ``api/etl/logs/connection/name-and-operation-type?type=SCAN&connectionId=1``.
    """
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    seg = _api_path_id_segment(connection_id)
    if not seg:
        return {"success": False, "message": "Connection ID is required.", "data": []}
    kind = (operation_type or "").strip().upper()
    if not kind:
        return {"success": False, "message": "Operation type is required.", "data": []}
    base = _api_url(ETL_LOGS_BY_CONNECTION_AND_OPERATION_TYPE_PATH)
    sep = "&" if "?" in base else "?"
    url = (
        f"{base}{sep}type={quote(kind, safe='')}"
        f"&connectionId={quote(seg, safe='')}"
    )
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=15.0)
        if isinstance(payload, list):
            rows = [r for r in payload if isinstance(r, dict)]
            return {"success": True, "data": rows, "message": ""}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load ETL logs.", data=[]
            )
            if rej is not None:
                return rej
            rows = payload.get("data")
            if isinstance(rows, list):
                return {
                    "success": True,
                    "data": [r for r in rows if isinstance(r, dict)],
                    "message": str(payload.get("message") or ""),
                }
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def _flatten_all_in_one_nested_validations(
    details: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a flat validation list from detail rows that carry nested ``validations`` arrays."""
    out: list[dict[str, Any]] = []
    for detail in details:
        nested = detail.get("validations")
        if not isinstance(nested, list):
            continue
        for val in nested:
            if not isinstance(val, dict):
                continue
            merged = dict(val)
            for parent_key in (
                "apiId",
                "api_id",
                "apiName",
                "api_name",
                "projectId",
                "projectid",
                "project_id",
                "projectName",
                "project_name",
            ):
                if parent_key not in merged and parent_key in detail:
                    merged[parent_key] = detail[parent_key]
            out.append(merged)
    return out


def _parse_all_in_one_details_validations(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Extract detail rows and validation rows from combined All-in-One JSON."""
    details: list[dict[str, Any]] = []
    validations: list[dict[str, Any]] = []

    inner = payload.get("data")
    if isinstance(inner, dict):
        for key in ("apiDetails", "details", "api_details", "apiDetailList", "result"):
            d = inner.get(key)
            if isinstance(d, list):
                details = [x for x in d if isinstance(x, dict)]
                break
        if not details:
            nested = inner.get("data")
            if isinstance(nested, list):
                details = [x for x in nested if isinstance(x, dict)]
        for key in ("validations", "apiValidations", "api_validations"):
            v = inner.get(key)
            if isinstance(v, list):
                validations = [x for x in v if isinstance(x, dict)]
                break
    elif isinstance(inner, list):
        details = [x for x in inner if isinstance(x, dict)]

    if not details:
        for key in ("apiDetails", "details", "api_details"):
            d = payload.get(key)
            if isinstance(d, list):
                details = [x for x in d if isinstance(x, dict)]
                break

    if not validations:
        for key in ("validations", "apiValidations", "api_validations"):
            v = payload.get(key)
            if isinstance(v, list):
                validations = [x for x in v if isinstance(x, dict)]
                break

    # Common backend shape for all-in-one:
    #   [ { ...detail..., "validations": [ {...}, ... ] }, ... ]
    # Flatten nested detail.validations when top-level validations are absent.
    if not validations and details:
        validations = _flatten_all_in_one_nested_validations(details)

    return details, validations


def api_get_all_api_details_all_in_one(*, token: str | None = None) -> dict[str, Any]:
    """GET combined API details + validations (All in One). Requires JWT."""
    if not token or not str(token).strip():
        return {
            "success": False,
            "message": "Session expired. Please log in again.",
            "details": [],
            "validations": [],
        }
    path = (API_DETAILS_ALL_IN_ONE_PATH or "api/get-all-api-details/all-in-one").strip().lstrip(
        "/"
    )
    url = _api_url(path)
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            details = [x for x in payload if isinstance(x, dict)]
            validations = _flatten_all_in_one_nested_validations(details)
            return {
                "success": True,
                "details": details,
                "validations": validations,
                "message": "",
            }
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload,
                message_fallback="Failed to load All in One data.",
                details=[],
                validations=[],
            )
            if rej is not None:
                return rej
            details, validations = _parse_all_in_one_details_validations(payload)
            return {
                "success": True,
                "details": details,
                "validations": validations,
                "message": "",
            }
        return {
            "success": False,
            "message": "Unexpected response format.",
            "details": [],
            "validations": [],
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "details": [],
            "validations": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {
            "success": False,
            "message": "Backend not reachable.",
            "details": [],
            "validations": [],
        }


def api_get_all_apis(*, token: str | None = None) -> dict[str, Any]:
    """GET API management API catalog list. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url((API_MGMT_API_LIST_GET_ALL_PATH or "api/api-mgmt/api-list/get-all-api").lstrip("/"))
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load APIs.", data=[]
            )
            if rej is not None:
                return rej
            for key in ("data", "content", "result", "records", "items", "apis"):
                data = payload.get(key)
                if isinstance(data, list):
                    return {"success": True, "data": data}
            return {"success": False, "message": "Unexpected response format.", "data": []}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_replicate_api_dev_to_mgmt(
    app_id: int | str,
    api_detail_ids: list[int | str],
    *,
    token: str | None = None,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """POST replicate/api-dev-to-mgmt — copy selected dev APIs into management."""
    norm = _normalize_bearer_token(token)
    if not norm:
        return {"success": False, "message": "Session expired. Please log in again."}
    ids = [x for x in (api_detail_ids or []) if x is not None and str(x).strip() != ""]
    if not ids:
        return {"success": False, "message": "Select at least one API to replicate."}
    base = _api_url("replicate/api-dev-to-mgmt")
    pairs: list[tuple[str, str]] = [("appId", str(app_id).strip())]
    for aid in ids:
        pairs.append(("apiDetailsIds", str(aid).strip()))
    url = f"{base}?{urlencode(pairs)}"
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {norm}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=timeout_s) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            status = str(payload.get("status", "")).strip().upper()
            if status in ("FAILURE", "FAILED", "ERROR"):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Replication failed."),
                }
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Replication failed."),
                }
            ok = payload.get("success") is True or status in ("SUCCESS", "OK")
            if ok or payload.get("data") is not None:
                return {
                    "success": True,
                    "message": str(payload.get("message") or "Replication completed."),
                    "data": payload.get("data"),
                }
        if payload == {}:
            return {"success": True, "message": "Replication completed.", "data": None}
        if isinstance(payload, list):
            return {"success": True, "message": "Replication completed.", "data": payload}
        return {"success": False, "message": "Unexpected response from server."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _flatten_app_version_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Merge nested ``data`` / ``result`` / ``content`` so version + download fields are visible."""
    cur: dict[str, Any] = dict(payload)
    for _ in range(6):
        nested_key: str | None = None
        nested: dict[str, Any] | None = None
        for key in ("data", "result", "content", "payload", "body", "response"):
            blk = cur.get(key)
            if isinstance(blk, dict):
                nested_key = key
                nested = blk
                break
        if nested is None or nested_key is None:
            break
        cur = {**cur, **nested}
        cur.pop(nested_key, None)
    return cur


def _pick_non_empty_str(*values: Any) -> str:
    for v in values:
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def _server_version_string(d: dict[str, Any]) -> str:
    return _pick_non_empty_str(
        d.get("version"),
        d.get("latestVersion"),
        d.get("latest_version"),
        d.get("newVersion"),
        d.get("new_version"),
        d.get("targetVersion"),
        d.get("target_version"),
        d.get("appVersion"),
        d.get("app_version"),
        d.get("remoteVersion"),
        d.get("remote_version"),
    )


def _version_tuple_cmp(ver: str) -> tuple[int, ...]:
    s = str(ver or "").strip().lstrip("vV")
    if not s:
        return (0,)
    parts: list[int] = []
    for segment in s.split("."):
        buf = ""
        for ch in segment.strip():
            if ch.isdigit():
                buf += ch
            else:
                break
        parts.append(int(buf) if buf else 0)
    return tuple(parts)


def _is_version_newer(latest: str, current: str) -> bool:
    return _version_tuple_cmp(latest) > _version_tuple_cmp(current)


def _truthy_flag(v: Any) -> bool:
    if v is True:
        return True
    if isinstance(v, str) and v.strip().lower() in ("true", "1", "yes", "y"):
        return True
    if isinstance(v, (int, float)) and v == 1:
        return True
    return False


def _normalize_download_url_candidate(raw: Any) -> str:
    """Return absolute http(s) URL; join relative paths to ``API_BASE_URL``."""
    s = str(raw).strip() if raw is not None else ""
    if not s:
        return ""
    if s.startswith(("http://", "https://")):
        return s
    if s.startswith("//"):
        return "https:" + s
    base = API_BASE_URL.rstrip("/")
    if s.startswith("/"):
        return f"{base}{s}"
    return f"{base}/{s}"


def _resolve_app_update_package_type(payload: dict[str, Any], dl_url: Any) -> str:
    """Return ``\"setup\"`` (Inno-style .exe), ``\"zip\"`` (onedir archive), or ``\"dmg\"`` (macOS disk image).

    Server may send ``packageType`` / ``package_type`` / ``artifact`` / ``downloadType``
    with values like ``setup``, ``inno``, ``installer``, ``zip``, ``archive``, ``portable``, ``dmg``.
    If omitted, the download URL path ending in ``.zip`` or ``.dmg`` implies that type; otherwise ``setup``.
    """
    raw = (
        payload.get("packageType")
        or payload.get("package_type")
        or payload.get("artifact")
        or payload.get("downloadType")
        or payload.get("download_type")
        or payload.get("updatePackage")
        or payload.get("update_package")
    )
    if raw is not None:
        s = str(raw).strip().lower()
        if s in ("zip", "archive", "portable", "onedir"):
            return "zip"
        if s in ("dmg", "diskimage", "macos", "mac"):
            return "dmg"
        if s in ("setup", "inno", "installer"):
            return "setup"
        if s == "auto":
            pass
        else:
            return "setup"
    u = str(dl_url or "").strip()
    try:
        path = urlparse(u).path.lower()
    except ValueError:
        path = ""
    if path.endswith(".zip"):
        return "zip"
    if path.endswith(".dmg"):
        return "dmg"
    return "setup"


def api_check_app_version(*, current_version: str, token: str | None = None) -> dict[str, Any]:
    """GET app/version?currentVersion=... — latest build info. Requires JWT.

    The client flattens one level of nesting from ``data``, ``result``, ``content``,
    ``payload``, ``body``, or ``response`` so fields can live inside those objects.

    Expected JSON fields (typical):

    - ``version`` / ``latestVersion`` / ``newVersion`` / ``targetVersion`` / …: latest semver
    - ``downloadUrl`` / ``download_url`` / ``downloadURL`` / ``fileUrl`` / ``installerUrl`` / …
    - ``downloadWindowsUrl`` / ``download_windows_url`` and
      ``downloadMacUrl`` / ``download_mac_url``: platform-specific URLs
    - Relative download paths are resolved against :data:`core.config.API_BASE_URL`
    - ``updateAvailable`` / ``update_available``: optional bool
    - ``checksum`` / ``sha256`` / …: optional hex SHA-256 of the **downloaded** file
    - ``packageType`` / … — see :func:`_resolve_app_update_package_type`

    If the server version is newer than ``currentVersion`` but no download URL is present,
    the result includes ``needsUpdateNoDownloadUrl: True`` (UI shows an error instead of
    falsely reporting up to date).
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Please sign in to check for updates."}
    ver = (current_version or "").strip()
    query = urlencode({"currentVersion": ver})
    url = _api_url(f"app/version?{query}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload: Any = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(payload, dict):
            return {"success": False, "message": "Unexpected response from server."}
        flat = _flatten_app_version_envelope(payload)
        chk = (
            flat.get("checksum")
            or flat.get("sha256")
            or flat.get("sha256sum")
            or flat.get("hash")
        )
        chk_str = str(chk).strip() if chk is not None else ""
        legacy_s = _normalize_download_url_candidate(
            _pick_non_empty_str(
                flat.get("downloadUrl"),
                flat.get("download_url"),
                flat.get("downloadURL"),
                flat.get("fileUrl"),
                flat.get("file_url"),
                flat.get("installerUrl"),
                flat.get("installer_url"),
                flat.get("setupUrl"),
                flat.get("setup_url"),
                flat.get("exeUrl"),
                flat.get("exe_url"),
                flat.get("windowsDownloadUrl"),
                flat.get("windows_download_url"),
                flat.get("artifactUrl"),
                flat.get("artifact_url"),
            )
        )
        win_u = _normalize_download_url_candidate(
            _pick_non_empty_str(
                flat.get("downloadWindowsUrl"),
                flat.get("download_windows_url"),
                flat.get("windowsInstallerUrl"),
                flat.get("windows_installer_url"),
            )
        )
        mac_u = _normalize_download_url_candidate(
            _pick_non_empty_str(
                flat.get("downloadMacUrl"),
                flat.get("download_mac_url"),
                flat.get("macDownloadUrl"),
                flat.get("dmgUrl"),
                flat.get("dmg_url"),
            )
        )
        # Prefer platform-specific URL when present; fall back to legacy downloadUrl.
        if sys.platform == "darwin":
            dl_effective = mac_u or legacy_s or win_u
        else:
            dl_effective = win_u or legacy_s or mac_u
        dl_url = dl_effective if dl_effective else None
        package_type = _resolve_app_update_package_type(flat, dl_url)
        has_dl = bool(dl_url)
        server_ver = _server_version_string(flat) or _pick_non_empty_str(flat.get("version"))
        msg = str(flat.get("message") or "").strip()
        cv = (current_version or "").strip()
        newer = bool(server_ver and _is_version_newer(server_ver, cv))
        same_strings = (
            server_ver.strip("vV").lower() == cv.strip("vV").lower() if server_ver and cv else True
        )
        explicit_update = _truthy_flag(flat.get("updateAvailable")) or _truthy_flag(
            flat.get("update_available")
        )
        needs_no_download = False
        if not has_dl:
            if newer:
                needs_no_download = True
            elif explicit_update and server_ver and not same_strings:
                needs_no_download = True
            elif explicit_update and not server_ver:
                needs_no_download = True
        return {
            "success": True,
            "version": server_ver or flat.get("version"),
            "downloadUrl": dl_url,
            "downloadWindowsUrl": win_u or None,
            "downloadMacUrl": mac_u or None,
            "message": msg,
            "checksum": chk_str or None,
            "packageType": package_type,
            "needsUpdateNoDownloadUrl": needs_no_download,
            "updateAvailable": bool(
                explicit_update
                or has_dl
                or bool(win_u or mac_u)
                or newer
                or needs_no_download,
            ),
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        _log_api("GET", url, response={"error": "Backend not reachable."})
        return {"success": False, "message": "Backend not reachable."}


def api_create_api(
    *,
    api_name: str,
    api_endpoint: str,
    method: str,
    app_id: int | str,
    token: str | None = None,
) -> dict[str, Any]:
    """POST API management api-list/create — create API catalog entry. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url((API_MGMT_API_LIST_CREATE_PATH or "api/api-mgmt/api-list/create").lstrip("/"))
    aid = str(app_id).strip()
    app_id_json: int | str = int(aid) if aid.isdigit() else aid
    body: dict[str, Any] = {
        "appId": app_id_json,
        "apiName": (api_name or "").strip(),
        "apiEndpoint": (api_endpoint or "").strip(),
        "method": (method or "").strip().upper(),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            if _api_catalog_body_indicates_failure(payload):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to create API."),
                    "data": payload if isinstance(payload, dict) else {},
                }
            return {
                "success": True,
                "message": _extract_error_message(payload, "API created successfully."),
                "data": payload,
            }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        _log_api("POST", url, body=body, response={"error": "Backend not reachable."})
        return {"success": False, "message": "Backend not reachable."}


def api_update_api_by_id(
    api_id: int | str,
    *,
    api_name: str,
    api_endpoint: str,
    method: str,
    app_id: int | str,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT API management api-list/update-api-by-id/{api_id} — update API catalog entry. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    base = (API_MGMT_API_LIST_UPDATE_BY_ID_PREFIX or "api/api-mgmt/api-list/update-api-by-id").lstrip("/").rstrip("/")
    url = _api_url(f"{base}/{api_id}")
    aid = str(app_id).strip()
    app_id_json: int | str = int(aid) if aid.isdigit() else aid
    body: dict[str, Any] = {
        "appId": app_id_json,
        "apiName": (api_name or "").strip(),
        "apiEndpoint": (api_endpoint or "").strip(),
        "method": (method or "").strip().upper(),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=8) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            if _api_catalog_body_indicates_failure(payload):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to update API."),
                    "data": payload if isinstance(payload, dict) else {},
                }
            return {
                "success": True,
                "message": _extract_error_message(payload, "API updated successfully."),
                "data": payload,
            }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        _log_api("PUT", url, body=body, response={"error": "Backend not reachable."})
        return {"success": False, "message": "Backend not reachable."}


def api_delete_api_by_id(
    api_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE API management api-list/delete-api-by-id/{api_id} — remove API catalog entry. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    base = (API_MGMT_API_LIST_DELETE_BY_ID_PREFIX or "api/api-mgmt/api-list/delete-api-by-id").lstrip("/").rstrip("/")
    url = _api_url(f"{base}/{api_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            # Do not treat HTTP 200 alone as success — backend may return 200 + status: FAILURE + msg.
            if _api_catalog_body_indicates_failure(payload):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete API failed."),
                }
            ok = (
                payload.get("success") is True
                or str(payload.get("status", "")).strip().upper() == "SUCCESS"
                or payload.get("statusCode") in (200, 204)
                or status in (200, 204)
            )
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "API deleted successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Delete API failed."),
            }
        return {"success": True, "message": "API deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_app_id(*, token: str | None = None) -> dict[str, Any]:
    """GET API management app-id list. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url((API_MGMT_APP_ID_GET_ALL_PATH or "api/api-mgmt/app-id/get-all-app-id").lstrip("/"))
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load app ids.", data=[]
            )
            if rej is not None:
                return rej
            for key in ("data", "content", "result", "records", "items", "appIds", "app_ids"):
                data = payload.get(key)
                if isinstance(data, list):
                    return {"success": True, "data": data}
            return {"success": False, "message": "Unexpected response format.", "data": []}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_create_app_id(
    *,
    description: str,
    token: str | None = None,
) -> dict[str, Any]:
    """POST API management app-id/create — JSON body with description. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url((API_MGMT_APP_ID_CREATE_PATH or "api/api-mgmt/app-id/create").lstrip("/"))
    body: dict[str, Any] = {"description": (description or "").strip()}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            if _api_catalog_body_indicates_failure(payload):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to create app id."),
                    "data": payload if isinstance(payload, dict) else {},
                }
            return {
                "success": True,
                "message": _extract_error_message(payload, "App id created successfully."),
                "data": payload,
            }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        _log_api("POST", url, body=body, response={"error": "Backend not reachable."})
        return {"success": False, "message": "Backend not reachable."}


def api_update_app_id_by_id(
    app_id: int | str,
    *,
    description: str,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT API management app-id/update-by-app-id/{app_id} — JSON body with description. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    base = (API_MGMT_APP_ID_UPDATE_BY_ID_PREFIX or "api/api-mgmt/app-id/update-by-app-id").lstrip("/").rstrip("/")
    url = _api_url(f"{base}/{app_id}")
    body: dict[str, Any] = {"description": (description or "").strip()}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=8) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            if _api_catalog_body_indicates_failure(payload):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to update app id."),
                    "data": payload if isinstance(payload, dict) else {},
                }
            return {
                "success": True,
                "message": _extract_error_message(payload, "App id updated successfully."),
                "data": payload,
            }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        _log_api("PUT", url, body=body, response={"error": "Backend not reachable."})
        return {"success": False, "message": "Backend not reachable."}


def api_delete_app_id_by_id(
    app_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE API management app-id/delete-by-app-id/{app_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    base = (API_MGMT_APP_ID_DELETE_BY_ID_PREFIX or "api/api-mgmt/app-id/delete-by-app-id").lstrip("/").rstrip("/")
    url = _api_url(f"{base}/{app_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        # Match curl: DELETE with Content-Type and no body (--data '').
        req = Request(url, headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if _api_catalog_body_indicates_failure(payload):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete app id failed."),
                }
            ok = (
                payload.get("success") is True
                or str(payload.get("status", "")).strip().upper() == "SUCCESS"
                or payload.get("statusCode") in (200, 204)
                or status in (200, 204)
            )
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "App id deleted successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Delete app id failed."),
            }
        return {"success": True, "message": "App id deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_grant_api_access(
    *,
    api_id: int | str,
    role_ids: list[int | str],
    token: str | None = None,
) -> dict[str, Any]:
    """POST api/api-mgmt/api-access/grant-multiple-role-to-api?apiId={api_id} with body roleIds."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    valid_ids = [r for r in (role_ids or []) if r is not None and str(r).strip() != ""]
    if not valid_ids:
        return {"success": False, "message": "Select at least one role."}
    query = urlencode({"apiId": api_id})
    url = _api_url(f"api/api-mgmt/api-access/grant-multiple-role-to-api?{query}")
    body = {"roleIds": [int(str(r)) if str(r).strip().isdigit() else str(r) for r in valid_ids]}
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            rej = _reject_json_business_failure(
                payload, message_fallback="Grant API access failed.", data=payload
            )
            if rej is not None:
                return rej
            return {
                "success": True,
                "message": _extract_error_message(payload, "Access granted successfully."),
                "data": payload,
            }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        _log_api("POST", url, response={"error": "Backend not reachable."})
        return {"success": False, "message": "Backend not reachable."}


def api_grant_multiple_api_access(
    *,
    role_id: int | str,
    api_ids: list[int | str],
    token: str | None = None,
) -> dict[str, Any]:
    """POST api/api-mgmt/api-access/grant-multiple-api-to-role?roleId={role_id} with JSON body {'apiIds': [...]}."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    valid_ids = [a for a in (api_ids or []) if a is not None and str(a).strip() != ""]
    if not valid_ids:
        return {"success": False, "message": "Select at least one API."}
    query = urlencode({"roleId": role_id})
    url = _api_url(f"api/api-mgmt/api-access/grant-multiple-api-to-role?{query}")
    body = {"apiIds": [int(str(a)) if str(a).strip().isdigit() else str(a) for a in valid_ids]}
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=12.0) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback="Grant multiple API access failed.")
            if rej is not None:
                return rej
            return {
                "success": True,
                "message": _extract_error_message(payload, "Access granted successfully."),
                "data": payload,
            }
        if isinstance(payload, list):
            return {"success": True, "message": "Access granted successfully.", "data": payload}
        return {"success": True, "message": "Access granted successfully.", "data": payload}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_api_access_by_api_id(
    api_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET api/api-mgmt/api-access/get-role-by-api-id/{api_id} — return roles assigned to API."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url(f"api/api-mgmt/api-access/get-role-by-api-id/{api_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load API access.", data=[]
            )
            if rej is not None:
                return rej
            for key in ("data", "content", "result", "records", "items", "roles"):
                data = payload.get(key)
                if isinstance(data, list):
                    return {"success": True, "data": data}
            return {"success": False, "message": "Unexpected response format.", "data": []}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_get_api_access_by_role_id(
    role_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET api/api-mgmt/api-access/get-api-by-role-id/{role_id} — return APIs assigned to role."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url(f"api/api-mgmt/api-access/get-api-by-role-id/{role_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load role APIs.", data=[]
            )
            if rej is not None:
                return rej
            for key in ("data", "content", "result", "records", "items", "apis"):
                data = payload.get(key)
                if isinstance(data, list):
                    return {"success": True, "data": data}
            return {"success": False, "message": "Unexpected response format.", "data": []}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_change_api_access_by_id(
    assign_id: int | str,
    status: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PATCH change-api-assignment-access-by-id/{assign_id}/{status} — path status ACTIVE or INACTIVE only."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    raw = str(status or "").strip().upper().replace("-", "").replace(" ", "").replace("_", "")
    if raw in ("DEACTIVE", "INACTIVE"):
        status_seg = "INACTIVE"
    elif raw == "ACTIVE":
        status_seg = "ACTIVE"
    else:
        return {"success": False, "message": "Status must be ACTIVE or INACTIVE."}
    url = _api_url(f"api/api-mgmt/api-access/change-api-assignment-access-by-id/{assign_id}/{status_seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_patch(url, headers=headers)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to change access.", data=payload
            )
            if rej is not None:
                return rej
        msg = _extract_error_message(payload, "Access updated.") if isinstance(payload, dict) else "Access updated."
        return {"success": True, "message": msg, "data": payload}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_remove_multiple_assignments_by_ids(
    *,
    assignment_ids: list[int | str],
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE api/api-mgmt/api-access/remove-multiple-role-by-api-id with JSON body {'assignmentId': [...]}."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    valid_ids = [a for a in (assignment_ids or []) if a is not None and str(a).strip() != ""]
    if not valid_ids:
        return {"success": False, "message": "Select at least one assignment."}
    url = _api_url("api/api-mgmt/api-access/remove-multiple-role-by-api-id")
    body = {
        "assignmentId": [
            int(str(a)) if str(a).strip().isdigit() else str(a) for a in valid_ids
        ],
    }
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=12.0) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback="Remove assignments failed.")
            if rej is not None:
                return rej
            return {
                "success": True,
                "message": _extract_error_message(payload, "Access removed."),
                "data": payload,
            }
        if isinstance(payload, list):
            return {"success": True, "message": "Access removed.", "data": payload}
        return {"success": True, "message": "Access removed.", "data": payload}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_deactivate_multiple_roles_by_api_id(
    *,
    api_id: int | str,
    role_ids: list[int | str],
    status: str = "INACTIVE",
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE change-status-multiple-role-by-api-id?apiId= with body roleIds + status (ACTIVE or INACTIVE only)."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    valid_ids = [r for r in (role_ids or []) if r is not None and str(r).strip() != ""]
    if not valid_ids:
        return {"success": False, "message": "Select at least one role."}
    raw = (status or "INACTIVE").strip().upper().replace("-", "")
    if raw in ("DEACTIVE", "INACTIVE"):
        status_seg = "INACTIVE"
    elif raw == "ACTIVE":
        status_seg = "ACTIVE"
    else:
        return {"success": False, "message": "Status must be ACTIVE or INACTIVE."}
    query = urlencode({"apiId": api_id})
    url = _api_url(f"api/api-mgmt/api-access/change-status-multiple-role-by-api-id?{query}")
    body = {
        "roleIds": [int(str(r)) if str(r).strip().isdigit() else str(r) for r in valid_ids],
        "status": status_seg,
    }
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=12.0) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Change role access status for API failed."
            )
            if rej is not None:
                return rej
            return {
                "success": True,
                "message": _extract_error_message(payload, "Role assignment status updated."),
                "data": payload,
            }
        if isinstance(payload, list):
            return {"success": True, "message": "Role assignment status updated.", "data": payload}
        return {"success": True, "message": "Role assignment status updated.", "data": payload}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_remove_multiple_api_by_role_id(
    *,
    role_id: int | str,
    assignment_ids: list[int | str],
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE api/api-mgmt/api-access/remove-multiple-api-by-role-id?roleId={role_id} with body {'assignmentId': [...]}."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    valid_ids = [a for a in (assignment_ids or []) if a is not None and str(a).strip() != ""]
    if not valid_ids:
        return {"success": False, "message": "Select at least one assignment."}
    query = urlencode({"roleId": role_id})
    url = _api_url(f"api/api-mgmt/api-access/remove-multiple-api-by-role-id?{query}")
    body = {
        "assignmentId": [
            int(str(a)) if str(a).strip().isdigit() else str(a) for a in valid_ids
        ],
    }
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=12.0) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback="Remove APIs from role failed.")
            if rej is not None:
                return rej
            return {
                "success": True,
                "message": _extract_error_message(payload, "APIs removed successfully."),
                "data": payload,
            }
        if isinstance(payload, list):
            return {"success": True, "message": "APIs removed successfully.", "data": payload}
        return {"success": True, "message": "APIs removed successfully.", "data": payload}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_change_status_multiple_api_by_role_id(
    *,
    role_id: int | str,
    api_ids: list[int | str],
    status: str = "ACTIVE",
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE change-status-multiple-api-by-role-id?roleId= with body apiIds + status (ACTIVE or INACTIVE only)."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    valid_ids = [a for a in (api_ids or []) if a is not None and str(a).strip() != ""]
    if not valid_ids:
        return {"success": False, "message": "Select at least one API."}
    raw = (status or "ACTIVE").strip().upper().replace("-", "")
    if raw in ("DEACTIVE", "INACTIVE"):
        status_seg = "INACTIVE"
    elif raw == "ACTIVE":
        status_seg = "ACTIVE"
    else:
        return {"success": False, "message": "Status must be ACTIVE or INACTIVE."}
    query = urlencode({"roleId": role_id})
    url = _api_url(f"api/api-mgmt/api-access/change-status-multiple-api-by-role-id?{query}")
    body = {
        "apiIds": [int(str(a)) if str(a).strip().isdigit() else str(a) for a in valid_ids],
        "status": status_seg,
    }
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=12.0) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Change status for role APIs failed."
            )
            if rej is not None:
                return rej
            return {
                "success": True,
                "message": _extract_error_message(payload, "API access status updated."),
                "data": payload,
            }
        if isinstance(payload, list):
            return {"success": True, "message": "API access status updated.", "data": payload}
        return {"success": True, "message": "API access status updated.", "data": payload}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_api_detail(
    project_id: int | str,
    *,
    token: str | None = None,
    app_id: int | str | None = None,
    folder: str | None = None,
    api_method: str | None = None,
    api_name: str | None = None,
    localhost_path: str | None = None,
    server_path: str | None = None,
    requirement: str | None = None,
    api_status: int | str | None = None,
    comments: str | None = None,
    request_body: str | None = None,
    response_body: str | None = None,
) -> dict[str, Any]:
    """Create API detail via POST api/create-api-detail/{project_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/create-api-detail/{project_id}")
    if api_status is None:
        seq_id_val: Any = ""
    elif isinstance(api_status, int):
        seq_id_val = api_status
    else:
        seq_text = str(api_status).strip()
        seq_id_val = int(seq_text) if seq_text.isdigit() else seq_text
    body: dict[str, Any] = {
        "appId": str(app_id).strip() if app_id is not None else "",
        "folder": (folder or "").strip(),
        "apiMethod": (api_method or "").strip().upper(),
        "apiName": (api_name or "").strip(),
        "localhostPath": (localhost_path or "").strip(),
        "serverPath": (server_path or "").strip(),
        "requirement": (requirement or "").strip(),
        "seqId": seq_id_val,
        "comments": (comments or "").strip(),
        "request": (request_body or "").strip(),
        "response": (response_body or "").strip(),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Create API detail failed."
            )
            if rej is not None:
                return rej
            data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            ok = (
                payload.get("success") is True
                or payload.get("status") == "SUCCESS"
                or "apiId" in payload
                or "api_id" in payload
                or "apiId" in data_obj
                or "api_id" in data_obj
                or status in (200, 201)
            )
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "API detail created successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Create API detail failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create API detail failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_api_detail_by_id(
    api_id: int | str,
    *,
    token: str | None = None,
    app_id: int | str | None = None,
    folder: str | None = None,
    api_method: str | None = None,
    api_name: str | None = None,
    localhost_path: str | None = None,
    server_path: str | None = None,
    requirement: str | None = None,
    api_status: int | str | None = None,
    comments: str | None = None,
    request_body: str | None = None,
    response_body: str | None = None,
) -> dict[str, Any]:
    """Update API detail via PUT api/update-api-detail-by-id/{id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/update-api-detail-by-id/{api_id}")
    if api_status is None:
        seq_payload: Any = ""
    elif isinstance(api_status, int):
        seq_payload = api_status
    else:
        seq_text = str(api_status).strip()
        seq_payload = int(seq_text) if seq_text.isdigit() else seq_text
    body: dict[str, Any] = {
        "folder": (folder or "").strip(),
        "apiName": (api_name or "").strip(),
        "localhostPath": (localhost_path or "").strip(),
        "serverPath": (server_path or "").strip(),
        "requirement": (requirement or "").strip(),
        "seqId": seq_payload,
        "comments": (comments or "").strip(),
        "request": (request_body or "").strip(),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            ok = payload.get("success") is True or payload.get("status") == "SUCCESS"
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "API detail updated successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Update API detail failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update API detail failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_api_detail_by_id(
    api_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Delete API detail via DELETE api/delete-api-detail-by-id/{api_id}. Requires JWT.
    api_id is the internal API Id."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    path = f"{DELETE_API_DETAIL_PATH.rstrip('/')}/{api_id}"
    url = _api_url(path)
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Delete API detail failed."
            )
            if rej is not None:
                return rej
            ok = (
                payload.get("success") is True
                or payload.get("status") == "SUCCESS"
                or payload.get("statusCode") in (200, 204)
                or status in (200, 204)
            )
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "API detail deleted successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Delete API detail failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete API detail failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_api_validations(*, token: str | None = None) -> dict[str, Any]:
    """Fetch all API validations from GET api/get-all-api-validations. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("api/get-all-api-validations")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load API validations.", data=[]
            )
            if rej is not None:
                return rej
            data_list = payload.get("data") or payload.get("apiValidations") or payload.get("result")
            if data_list is not None:
                items = data_list if isinstance(data_list, list) else [data_list]
                return {"success": True, "data": items}
            return {"success": True, "data": [payload]}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_create_api_validation(
    *,
    token: str | None = None,
    project_id: int | str | None = None,
    api_id: int | str | None = None,
    api_name: str | None = None,
    field_name: str | None = None,
    api_validation_summary: str | None = None,
    role: str | None = None,
    api_validation: str | None = None,
    validation_type: str | None = None,
    api_validation_status: str | None = None,
    error_message: str | None = None,
    success_message: str | None = None,
    comment: str | None = None,
) -> dict[str, Any]:
    """Create API validation via POST api/create-api-validation/{api_id}. Requires JWT.
    api_id is required in the path."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    if api_id is None or (isinstance(api_id, str) and not api_id.strip()):
        return {"success": False, "message": "api_id is required for create API validation."}
    url = _api_url(f"api/create-api-validation/{api_id}")
    body: dict[str, Any] = {
        "fieldName": (field_name or "").strip(),
        "apiValidationSummary": (api_validation_summary or "").strip(),
        "userType": (role or "").strip(),
        "apiValidation": (api_validation or "").strip(),
        "validationType": (validation_type or "").strip(),
        "apiValidationStatus": (api_validation_status or "ACTIVE").strip().upper(),
        "errorMessage": (error_message or "").strip(),
        "successMessage": (success_message or "").strip(),
        "comment": (comment or "").strip(),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Create API validation failed."
            )
            if rej is not None:
                return rej
            data_obj = payload.get("data") if isinstance(payload.get("data"), dict) else {}
            ok = (
                payload.get("success") is True
                or payload.get("status") == "SUCCESS"
                or "id" in payload
                or "id" in data_obj
                or status in (200, 201)
            )
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "API validation created successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Create API validation failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create API validation failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_api_validation_by_id(
    api_validation_id: int | str,
    *,
    token: str | None = None,
    field_name: str | None = None,
    api_validation_summary: str | None = None,
    role: str | None = None,
    api_validation: str | None = None,
    validation_type: str | None = None,
    api_validation_status: str | None = None,
    error_message: str | None = None,
    success_message: str | None = None,
    comment: str | None = None,
) -> dict[str, Any]:
    """Update API validation via PUT api/update-api-validation-by-id/{api_validation_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/update-api-validation-by-id/{api_validation_id}")
    body: dict[str, Any] = {
        "fieldName": (field_name or "").strip(),
        "apiValidationSummary": (api_validation_summary or "").strip(),
        "userType": (role or "").strip(),
        "apiValidation": (api_validation or "").strip(),
        "validationType": (validation_type or "").strip(),
        "apiValidationStatus": (api_validation_status or "ACTIVE").strip().upper(),
        "errorMessage": (error_message or "").strip(),
        "successMessage": (success_message or "").strip(),
        "comment": (comment or "").strip(),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            ok = payload.get("success") is True or payload.get("status") == "SUCCESS"
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "API validation updated successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Update API validation failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update API validation failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_api_validation_by_id(
    api_validation_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Delete API validation via DELETE api/delete-api-validation-by-id/{api_validation_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    path = f"{DELETE_API_VALIDATION_PATH.rstrip('/')}/{api_validation_id}"
    url = _api_url(path)
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Delete API validation failed."
            )
            if rej is not None:
                return rej
            ok = (
                payload.get("success") is True
                or payload.get("status") == "SUCCESS"
                or payload.get("statusCode") in (200, 204)
                or status in (200, 204)
            )
            if ok:
                return {
                    "success": True,
                    "message": payload.get("message", "API validation deleted successfully."),
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Delete API validation failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete API validation failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _extract_validation_comment_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    c = payload.get("comment")
    if isinstance(c, str):
        return c
    data = payload.get("data")
    if isinstance(data, dict):
        c2 = data.get("comment")
        if isinstance(c2, str):
            return c2
    if isinstance(data, str):
        return data
    return ""


def api_get_all_api_tasks(*, token: str | None = None) -> dict[str, Any]:
    """Fetch all API tasks from GET api/get-all-api-tasks. Requires JWT."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("api/get-all-api-tasks")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load API tasks.", data=[]
            )
            if rej is not None:
                return rej
            for key in ("data", "result", "items", "records", "content", "tasks"):
                data = payload.get(key)
                if isinstance(data, list):
                    return {"success": True, "data": data, "message": str(payload.get("message") or "")}
            return {"success": True, "data": [payload], "message": str(payload.get("message") or "")}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_create_api_task(
    api_id: int | str,
    *,
    token: str | None = None,
    summary: str | None = None,
    desc: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Create API task via POST api/create-api-task/{api_id}. Requires JWT."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(api_id)
    if not seg:
        return {"success": False, "message": "API ID is required."}
    url = _api_url(f"api/create-api-task/{seg}")
    body: dict[str, Any] = {
        "summary": (summary or "").strip(),
        "desc": (desc or "").strip(),
    }
    if status and str(status).strip():
        body["status"] = str(status).strip().upper()
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
            status_code = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback="Create API task failed.")
            if rej is not None:
                return rej
            ok = (
                payload.get("success") is True
                or payload.get("status") == "SUCCESS"
                or payload.get("statusCode") in (200, 201)
                or status_code in (200, 201)
            )
            if ok:
                return {"success": True, "message": str(payload.get("message") or "API task created successfully.")}
            return {"success": False, "message": _extract_error_message(payload, "Create API task failed.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create API task failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_api_task_by_id(
    task_id: int | str,
    *,
    token: str | None = None,
    summary: str | None = None,
    desc: str | None = None,
    status: str | None = None,
) -> dict[str, Any]:
    """Update API task via PUT api/update-api-task/{task_id}. Requires JWT."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(task_id)
    if not seg:
        return {"success": False, "message": "Task ID is required."}
    url = _api_url(f"api/update-api-task/{seg}")
    body: dict[str, Any] = {
        "summary": (summary or "").strip(),
        "desc": (desc or "").strip(),
    }
    if status and str(status).strip():
        body["status"] = str(status).strip().upper()
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
            status_code = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback="Update API task failed.")
            if rej is not None:
                return rej
            ok = (
                payload.get("success") is True
                or payload.get("status") == "SUCCESS"
                or payload.get("statusCode") in (200, 201)
                or status_code in (200, 201)
            )
            if ok:
                return {"success": True, "message": str(payload.get("message") or "API task updated successfully.")}
            return {"success": False, "message": _extract_error_message(payload, "Update API task failed.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update API task failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_api_task_by_id(task_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """Delete API task via DELETE api/delete-api-task/{task_id}. Requires JWT."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(task_id)
    if not seg:
        return {"success": False, "message": "Task ID is required."}
    url = _api_url(f"api/delete-api-task/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        payload = _http_delete(url, headers=headers)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback="Delete API task failed.")
            if rej is not None:
                return rej
        return {"success": True, "message": _extract_error_message(payload, "API task deleted successfully.")}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete API task failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _normalize_validation_comment_rows(payload: Any) -> list[dict[str, Any]]:
    """Normalize GET-all-comments payload into a standard list for UI rendering."""
    rows: list[dict[str, Any]] = []
    raw_items: list[Any] = []
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        for key in ("data", "comments", "result", "items", "records", "content"):
            cand = payload.get(key)
            if isinstance(cand, list):
                raw_items = cand
                break
    for item in raw_items:
        if isinstance(item, dict):
            txt = (
                item.get("comment")
                or item.get("message")
                or item.get("text")
                or item.get("content")
                or ""
            )
            author = (
                item.get("createdBy")
                or item.get("created_by")
                or item.get("username")
                or item.get("userName")
                or item.get("author")
                or item.get("userId")
                or item.get("user_id")
                or ""
            )
            created_at = (
                item.get("createdAt")
                or item.get("created_at")
                or item.get("timestamp")
                or item.get("time")
                or item.get("date")
                or ""
            )
            cid = (
                item.get("commentId")
                or item.get("comment_id")
                or item.get("validationCommentId")
                or item.get("validation_comment_id")
                or item.get("id")
            )
            rows.append(
                {
                    "comment": str(txt or ""),
                    "author": str(author or ""),
                    "createdAt": created_at,
                    "commentId": cid,
                    "raw": item,
                }
            )
        elif isinstance(item, str):
            rows.append({"comment": item, "author": "", "createdAt": "", "commentId": None, "raw": item})
    return rows


def _normalize_dmt_object_tracker_comment_rows(payload: Any) -> list[dict[str, Any]]:
    """Extract DMT object-tracker comment rows without squashing (preserves ``status``, usernames, ids)."""
    raw_items: list[Any] = []
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        for key in ("data", "comments", "result", "items", "records", "content"):
            cand = payload.get(key)
            if isinstance(cand, list):
                raw_items = cand
                break
    return [dict(item) for item in raw_items if isinstance(item, dict)]


def api_get_all_validation_comments_by_id(
    api_validation_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET {COMMENT_GET_ALL_BY_VALIDATION_ID_PATH}/{api_validation_id}. Returns list of comments."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "comments": []}
    vid = _api_path_id_segment(api_validation_id)
    url = _api_url(f"{COMMENT_GET_ALL_BY_VALIDATION_ID_PATH}/{vid}")
    fallback_url = _api_url(f"{COMMENT_GET_BY_ID_PATH}/{vid}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=15.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload,
                message_fallback="Failed to load comments.",
                comments=[],
            )
            if rej is not None:
                return rej
        rows = _normalize_validation_comment_rows(payload)
        # Some backends return comment-list from get-comment-by-id/{id}. If configured
        # path doesn't return rows, retry once with COMMENT_GET_BY_ID_PATH.
        if not rows and fallback_url != url:
            payload2 = _http_get_json(fallback_url, headers=headers, timeout_s=15.0)
            rows = _normalize_validation_comment_rows(payload2)
            if rows:
                payload = payload2
        return {
            "success": True,
            "comments": rows,
            "message": str(payload.get("message", "") or "") if isinstance(payload, dict) else "",
        }
    except HTTPError as exc:
        if getattr(exc, "code", None) == 404:
            return {"success": True, "message": "", "comments": []}
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "comments": [],
            "message": _extract_error_message(
                err_payload, f"Load comments failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return {"success": False, "comments": [], "message": "Backend not reachable."}


def api_get_validation_comment_by_id(
    api_validation_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET {COMMENT_GET_BY_ID_PATH}/{api_validation_id}. Returns success, comment, message."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "comment": ""}
    url = _api_url(f"{COMMENT_GET_BY_ID_PATH}/{_api_path_id_segment(api_validation_id)}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=15.0)
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {
                    "success": False,
                    "comment": "",
                    "message": _extract_error_message(payload, "Failed to load comment."),
                }
            return {
                "success": True,
                "comment": _extract_validation_comment_text(payload),
                "message": str(payload.get("message", "") or ""),
            }
        return {"success": True, "comment": "", "message": ""}
    except HTTPError as exc:
        if getattr(exc, "code", None) == 404:
            return {"success": True, "comment": "", "message": ""}
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "comment": "",
            "message": _extract_error_message(
                err_payload, f"Load comment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return {"success": False, "comment": "", "message": "Backend not reachable."}


def api_add_validation_comment(
    api_validation_id: int | str,
    comment: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST {COMMENT_ADD_PATH}/{api_validation_id} with body {\"comment\": \"...\"}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"{COMMENT_ADD_PATH}/{_api_path_id_segment(api_validation_id)}")
    body = {"comment": comment or ""}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=15.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            ok = payload.get("success") is True or payload.get("status") == "SUCCESS"
            if ok:
                return {"success": True, "message": payload.get("message", "Comment saved.")}
            return {
                "success": False,
                "message": _extract_error_message(payload, "Add comment failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Add comment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_validation_comment_by_id(
    comment_id: int | str,
    comment: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT ``{COMMENT_UPDATE_BY_ID_PATH}/{comment_id}`` with body ``{\"comment\": \"...\"}``. Requires JWT.

    Matches backend: ``PUT /comment/update-by-id/{commentId}`` with JSON ``comment`` field.
    """
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(comment_id)
    if not seg:
        return {"success": False, "message": "Invalid comment id."}
    url = _api_url(f"{COMMENT_UPDATE_BY_ID_PATH}/{seg}")
    body = {"comment": comment or ""}
    # Match working curl/Postman: only Content-Type + Authorization. Do not set Accept or
    # MY-ETLZONE User-Agent (some gateways return 403 for that). urllib adds Python-urllib User-Agent.
    data = json.dumps(body, separators=(",", ":")).encode("utf-8")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=15.0) as resp:
            raw = resp.read()
            http_status = int(getattr(resp, "status", 200) or 200)
        try:
            payload_any: Any = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            payload_any = {}
        if http_status >= 400:
            err_d = payload_any if isinstance(payload_any, dict) else {}
            return {
                "success": False,
                "message": _extract_error_message(
                    err_d,
                    f"Update comment failed ({http_status}).",
                ),
            }
        payload: Any = payload_any
        if not isinstance(payload, dict):
            if http_status in (200, 204):
                return {"success": True, "message": "Comment updated."}
            return {"success": False, "message": "Unexpected response."}
        if _json_payload_indicates_business_failure(payload):
            return {
                "success": False,
                "message": _extract_error_message(payload, "Update comment failed."),
            }
        st = str(payload.get("status", "")).strip().upper()
        if payload.get("success") is True or st in ("SUCCESS", "OK"):
            msg = str(payload.get("message") or payload.get("msg") or "").strip()
            return {"success": True, "message": msg or "Comment updated."}
        if http_status in (200, 204):
            msg = str(payload.get("message") or payload.get("msg") or "").strip()
            return {"success": True, "message": msg or "Comment updated."}
        return {
            "success": False,
            "message": _extract_error_message(payload, "Update comment failed."),
        }
    except HTTPError as exc:
        try:
            raw_err = exc.read()
            err_payload = json.loads(raw_err.decode("utf-8")) if raw_err else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload,
                f"Update comment failed ({getattr(exc, 'code', 'HTTP error')}).",
            ),
        }
    except (URLError, TimeoutError, ValueError, OSError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_validation_comment_by_id(
    comment_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE /comment/delete-by-id/{id} (comment id)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(comment_id)
    if not seg:
        return {"success": False, "message": "Invalid comment id."}
    url = _api_url(f"{COMMENT_DELETE_BY_ID_PATH}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=15.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            ok = (
                payload.get("success") is True
                or payload.get("status") == "SUCCESS"
                or status in (200, 204)
            )
            if ok:
                return {"success": True, "message": payload.get("message", "Comment deleted.")}
            return {
                "success": False,
                "message": _extract_error_message(payload, "Delete comment failed."),
            }
        return {"success": True, "message": "Comment deleted."}
    except HTTPError as exc:
        if getattr(exc, "code", None) in (404,):
            return {"success": True, "message": "No comment to delete."}
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete comment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_object_tracker_comments_by_object_id(
    object_tracker_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET ``{DMT_COMMENT_GET_BY_OBJECT_ID_PREFIX}/{object_tracker_id}``.

    Returns ``{'success': bool, 'comments': list, 'message': str}``.
    """
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "comments": []}
    seg = _api_path_id_segment(object_tracker_id)
    if not seg:
        return {"success": False, "message": "Invalid object tracker id.", "comments": []}
    base = DMT_COMMENT_GET_BY_OBJECT_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=15.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load comments.", comments=[]
            )
            if rej is not None:
                return rej
        rows = _normalize_dmt_object_tracker_comment_rows(payload)
        return {
            "success": True,
            "comments": rows,
            "message": str(payload.get("message", "") or "") if isinstance(payload, dict) else "",
        }
    except HTTPError as exc:
        if getattr(exc, "code", None) == 404:
            return {"success": True, "comments": [], "message": ""}
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "comments": [],
            "message": _extract_error_message(
                err_payload, f"Load comments failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return {"success": False, "comments": [], "message": "Backend not reachable."}


def _coerce_object_tracker_comment_status_seq(status: Any, *, default: int = 1) -> int:
    """DMT comment create expects ``status`` as a numeric seq only, never a JSON object."""
    v: Any = status
    if isinstance(v, dict):
        picked: Any = None
        for k in ("seq", "statusSeq", "status_seq", "id"):
            if k in v and v.get(k) is not None and str(v.get(k)).strip() != "":
                picked = v.get(k)
                break
        if picked is None:
            return default
        v = picked
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, float) and v == int(v):
        return int(v)
    s = str(v).strip() if v is not None else ""
    if not s:
        return default
    if s.isdigit() or (s.startswith("-") and len(s) > 1 and s[1:].isdigit()):
        return int(s)
    if s[:1] == "{":
        try:
            obj = json.loads(s)
        except (json.JSONDecodeError, TypeError):
            return default
        if isinstance(obj, dict):
            return _coerce_object_tracker_comment_status_seq(obj, default=default)
    return default


def api_add_object_tracker_comment(
    object_tracker_id: int | str,
    comment: str,
    *,
    status: Any = 1,
    comment_by_username: str | None = None,
    comment_on_date: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """POST ``DMT_COMMENT_CREATE_PATH`` with comment payload (incl. ``commentByUsername``, ``commentOnDate``)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(object_tracker_id)
    if not seg:
        return {"success": False, "message": "Invalid object tracker id."}
    url = _api_url(DMT_COMMENT_CREATE_PATH)
    otid: int | str = int(seg) if seg.isdigit() else seg
    st = _coerce_object_tracker_comment_status_seq(status, default=1)
    uname = (comment_by_username or "").strip()
    if not uname:
        from core.user_context import get_user_profile

        p = get_user_profile()
        uname = str(
            p.get("username") or p.get("userName") or p.get("user_name") or ""
        ).strip()
    on_date = (comment_on_date or "").strip()
    if not on_date:
        from datetime import date

        on_date = date.today().isoformat()
    body = {
        "comment": comment or "",
        "objectTrackerId": otid,
        "status": st,
        "commentByUsername": uname,
        "commentOnDate": on_date,
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=15.0) as resp:
            raw = resp.read()
            http_status = int(getattr(resp, "status", 200) or 200)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            st_top = payload.get("status")
            if payload.get("success") is True or st_top == "SUCCESS" or (
                isinstance(st_top, str) and st_top.strip().upper() in ("SUCCESS", "OK")
            ):
                return {"success": True, "message": payload.get("message", "Comment saved.")}
            if payload.get("success") is False or _json_payload_indicates_business_failure(payload):
                return {"success": False, "message": _extract_error_message(payload, "Add comment failed.")}
            # Backend returns the created comment row as the JSON body (status is nested object, not "SUCCESS").
            oid = payload.get("objectTrackerId")
            iid = payload.get("issueTrackerId")
            has_tracker = oid is not None and str(oid).strip() != ""
            has_issue = iid is not None and str(iid).strip() != ""
            if (
                http_status < 400
                and payload.get("id") is not None
                and "comment" in payload
                and (has_tracker or has_issue)
            ):
                msg = str(payload.get("message") or payload.get("msg") or "").strip()
                return {"success": True, "message": msg or "Comment saved."}
            return {"success": False, "message": _extract_error_message(payload, "Add comment failed.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Add comment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_object_tracker_comment_by_id(
    comment_id: int | str,
    comment: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT ``{DMT_COMMENT_UPDATE_BY_ID_PREFIX}/{comment_id}`` with JSON ``{'comment': ...}``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(comment_id)
    if not seg:
        return {"success": False, "message": "Invalid comment id."}
    base = DMT_COMMENT_UPDATE_BY_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    body: dict[str, Any] = {"comment": comment or ""}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {tk}",
    }
    try:
        data = json.dumps(body, separators=(",", ":")).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=15.0) as resp:
            raw = resp.read()
            status = int(getattr(resp, "status", 200) or 200)
        payload: Any
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        if status >= 400:
            err_d = payload if isinstance(payload, dict) else {}
            return {"success": False, "message": _extract_error_message(err_d, f"Update comment failed ({status}).")}
        if isinstance(payload, dict):
            if _json_payload_indicates_business_failure(payload):
                return {"success": False, "message": _extract_error_message(payload, "Update comment failed.")}
            st = str(payload.get("status", "")).strip().upper()
            if payload.get("success") is True or st in ("SUCCESS", "OK") or status in (200, 204):
                msg = str(payload.get("message") or payload.get("msg") or "").strip()
                return {"success": True, "message": msg or "Comment updated."}
            return {"success": False, "message": _extract_error_message(payload, "Update comment failed.")}
        if status in (200, 204):
            return {"success": True, "message": "Comment updated."}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update comment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError, OSError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_object_tracker_comment_by_id(
    comment_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE ``{DMT_COMMENT_DELETE_BY_ID_PREFIX}/{comment_id}``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(comment_id)
    if not seg:
        return {"success": False, "message": "Invalid comment id."}
    base = DMT_COMMENT_DELETE_BY_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=15.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            ok = payload.get("success") is True or payload.get("status") == "SUCCESS" or status in (200, 204)
            if ok:
                return {"success": True, "message": payload.get("message", "Comment deleted.")}
            return {"success": False, "message": _extract_error_message(payload, "Delete comment failed.")}
        if status in (200, 204):
            return {"success": True, "message": "Comment deleted."}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete comment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_user_timezone(
    user_id: int | str,
    timezone: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Update user timezone via POST api/user-profile/update-user-timezone. Requires JWT.

    Request: { "timezone": "..." } (IANA timezone id, e.g. Asia/Kolkata, UTC)
    Returns dict with success, message.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/user-profile/update-user-timezone")
    body: dict[str, Any] = {"timezone": (timezone or "").strip()}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    data = json.dumps(body).encode("utf-8")
    try:
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        backend_msg = _extract_error_message(err_payload, "")
        base = f"Timezone update failed ({getattr(exc, 'code', 'HTTP error')})."
        if backend_msg:
            base = f"{base} {backend_msg}"
        return {"success": False, "message": base}
    if isinstance(payload, dict):
        ok = payload.get("success", payload.get("status") == "SUCCESS")
        if ok:
            return {"success": True, "message": payload.get("message", "Timezone updated.")}
        return {
            "success": False,
            "message": _extract_error_message(payload, "Timezone update failed."),
        }
    return {"success": False, "message": "Unexpected response."}


def api_change_password(
    old_password: str,
    new_password: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Change password via POST api/change-password. Requires JWT.

    Request: { "oldPassword": "...", "newPassword": "..." }
    Response: { msg, status } - success when status == "SUCCESS"
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/change-password")
    body: dict[str, Any] = {
        "oldPassword": old_password,
        "newPassword": new_password,
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Password change failed."
            )
            if rej is not None:
                return rej
            status = payload.get("status", "")
            if status == "SUCCESS":
                msg = payload.get("msg", "Password updated successfully.")
                return {"success": True, "message": msg}
            msg = payload.get("msg") or _extract_error_message(payload, "Password change failed.")
            return {"success": False, "message": msg}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Password change failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _user_hierarchy_mutation_success(payload: dict[str, Any]) -> bool:
    """True when assign/update/delete response indicates success (various backend shapes)."""
    if not isinstance(payload, dict):
        return False
    if payload.get("success") is True:
        return True
    st = str(payload.get("status", "")).strip().upper()
    if st == "SUCCESS":
        return True
    if "success" in st.lower():
        return True
    msg = str(payload.get("msg", payload.get("message", ""))).lower()
    return "success" in msg


def api_user_hierarchy_assign(
    user_id: int | str,
    manager_id: int | str,
    level: int,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST (default: api/user-hierarchy/assign) — link employee (userId) to manager (managerId)."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(USER_HIERARCHY_ASSIGN_PATH)
    body: dict[str, Any] = {
        "userId": int(user_id) if str(user_id).isdigit() else user_id,
        "managerId": int(manager_id) if str(manager_id).isdigit() else manager_id,
        "level": int(level),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Assign manager failed."
            )
            if rej is not None:
                return rej
        if isinstance(payload, dict) and _user_hierarchy_mutation_success(payload):
            return {
                "success": True,
                "message": str(payload.get("msg") or payload.get("message") or "Manager assigned successfully."),
                "data": payload,
            }
        if isinstance(payload, dict):
            return {
                "success": False,
                "message": _extract_error_message(payload, "Assign manager failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Assign manager failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_user_hierarchy_update(
    hierarchy_id: int | str,
    user_id: int | str,
    manager_id: int | str,
    level: int,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT (default: api/user-hierarchy/update-by-id/{hierarchyId})."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"{USER_HIERARCHY_UPDATE_BY_ID_PREFIX.rstrip('/')}/{hierarchy_id}")
    body: dict[str, Any] = {
        "userId": int(user_id) if str(user_id).isdigit() else user_id,
        "managerId": int(manager_id) if str(manager_id).isdigit() else manager_id,
        "level": int(level),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Update hierarchy failed."
            )
            if rej is not None:
                return rej
        if isinstance(payload, dict) and _user_hierarchy_mutation_success(payload):
            return {
                "success": True,
                "message": str(payload.get("msg") or payload.get("message") or "Hierarchy updated."),
                "data": payload,
            }
        if isinstance(payload, dict):
            return {
                "success": False,
                "message": _extract_error_message(payload, "Update hierarchy failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update hierarchy failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_user_hierarchy_delete(hierarchy_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """DELETE (default: api/user-hierarchy/delete-by-id/{hierarchyId})."""
    if not token or not str(token).strip():
        print(
            "[API] user-hierarchy/delete SKIPPED (no token); hierarchy_id=%r" % (hierarchy_id,),
            file=sys.stderr,
            flush=True,
        )
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"{USER_HIERARCHY_DELETE_BY_ID_PREFIX.rstrip('/')}/{hierarchy_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        print(
            "[API] user-hierarchy/delete request: hierarchy_id=%r -> %s" % (hierarchy_id, url),
            file=sys.stderr,
            flush=True,
        )
        req = Request(url, headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Delete hierarchy failed."
            )
            if rej is not None:
                return rej
        if isinstance(payload, dict) and _user_hierarchy_mutation_success(payload):
            return {
                "success": True,
                "message": str(payload.get("msg") or payload.get("message") or "Hierarchy deleted."),
            }
        if isinstance(payload, dict):
            return {
                "success": False,
                "message": _extract_error_message(payload, "Delete hierarchy failed."),
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        raw = b""
        try:
            raw = exc.read() or b""
        except Exception:
            pass
        err_payload: dict[str, Any] = {}
        if raw:
            try:
                parsed = json.loads(raw.decode("utf-8"))
                if isinstance(parsed, dict):
                    err_payload = parsed
            except Exception:
                pass
        resp_for_log: Any = err_payload if err_payload else (raw.decode("utf-8", errors="replace") if raw else str(exc))
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete hierarchy failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError) as exc:
        _log_api("DELETE", url, response={"error": type(exc).__name__, "detail": str(exc)})
        return {"success": False, "message": "Backend not reachable."}


def api_user_hierarchy_get_managers(user_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """GET user-hierarchy/managers/{userId} — reporting lines where this user is the employee."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url(f"user-hierarchy/managers/{user_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load managers.", data=[]
            )
            if rej is not None:
                return rej
            data = payload.get("data")
            if isinstance(data, list):
                return {"success": True, "data": data}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_user_hierarchy_get_all(*, token: str | None = None) -> dict[str, Any]:
    """GET (default: api/user-hierarchy/get-all) — return all reporting assignments."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url(USER_HIERARCHY_GET_ALL_PATH)
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load hierarchy.", data=[]
            )
            if rej is not None:
                return rej
            for key in ("data", "content", "result", "records", "items"):
                data = payload.get(key)
                if isinstance(data, list):
                    return {"success": True, "data": data}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_user_hierarchy_get_subordinates(user_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """GET user-hierarchy/subordinates/{userId} — users reporting to this manager."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url(f"user-hierarchy/subordinates/{user_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_get_json(url, headers=headers)
        if isinstance(payload, list):
            return {"success": True, "data": payload}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load subordinates.", data=[]
            )
            if rej is not None:
                return rej
            data = payload.get("data")
            if isinstance(data, list):
                return {"success": True, "data": data}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_get_all_categories(*, token: str | None = None) -> dict[str, Any]:
    """GET api/dmt/category/get-all-dmt-category. Returns {'success': bool, 'data': list, 'message': str}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/dmt/category/get-all-dmt-category")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Failed to load categories.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load categories ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_dmt_category_by_id(
    category_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET api/dmt/category/get-dmt-category-by-id/{id}. Returns {'success': bool, 'data': dict, 'message': str}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(category_id)
    if not seg:
        return {"success": False, "message": "Category ID is required."}
    url = _api_url(f"api/dmt/category/get-dmt-category-by-id/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to load category."),
                }
            data = payload.get("data")
            if isinstance(data, dict):
                return {
                    "success": True,
                    "data": data,
                    "message": str(payload.get("message") or ""),
                }
            if isinstance(data, list) and len(data) == 1 and isinstance(data[0], dict):
                return {"success": True, "data": data[0], "message": str(payload.get("message") or "")}
            if data is None and any(
                k in payload for k in ("categoryId", "id", "categoryName", "categorySeq")
            ):
                return {"success": True, "data": payload, "message": str(payload.get("message") or "")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load category ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_category(
    category_name: str,
    *,
    status: int,
    token: str | None = None,
) -> dict[str, Any]:
    """POST api/dmt/category/create with JSON {'categoryName': '...', 'status': <seq int>}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    name = (category_name or "").strip()
    if not name:
        return {"success": False, "message": "Category name is required."}
    try:
        status_id = int(status)
    except (TypeError, ValueError):
        return {"success": False, "message": "Status must be a valid selection."}
    url = _api_url("api/dmt/category/create")
    body: dict[str, Any] = {"categoryName": name, "status": status_id}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Create category failed.")}
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                "success": True,
                "message": str(payload.get("message") or "Category created successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create category failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_category(
    category_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE api/dmt/category/delete-by-id/{id}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(category_id)
    if not seg:
        return {"success": False, "message": "Category ID is required."}
    url = _api_url(f"api/dmt/category/delete-by-id/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Delete category failed.")}
            return {"success": True, "message": str(payload.get("message") or "Category deleted successfully.")}
        return {"success": True, "message": "Category deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete category failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_category(
    category_id: int | str,
    category_name: str,
    *,
    status: int,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT api/dmt/category/update-by-id/{id} with JSON {'categoryName': '...', 'status': <seq int>}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(category_id)
    if not seg:
        return {"success": False, "message": "Category ID is required."}
    name = (category_name or "").strip()
    if not name:
        return {"success": False, "message": "Category name is required."}
    try:
        status_id = int(status)
    except (TypeError, ValueError):
        return {"success": False, "message": "Status must be a valid selection."}
    url = _api_url(f"api/dmt/category/update-by-id/{seg}")
    body: dict[str, Any] = {"categoryName": name, "status": status_id}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Update category failed.")}
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                "success": True,
                "message": str(payload.get("message") or "Category updated successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update category failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_modules(*, token: str | None = None) -> dict[str, Any]:
    """GET api/dmt/module/get-all-module. Returns {'success': bool, 'data': list, 'message': str}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/dmt/module/get-all-module")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Failed to load modules.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load modules ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_module(
    module_name: str,
    *,
    status: int,
    token: str | None = None,
) -> dict[str, Any]:
    """POST api/dmt/module/create with JSON {'moduleName': '...', 'status': <seq int>}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    name = (module_name or "").strip()
    if not name:
        return {"success": False, "message": "Module name is required."}
    try:
        status_id = int(status)
    except (TypeError, ValueError):
        return {"success": False, "message": "Status must be a valid selection."}
    url = _api_url("api/dmt/module/create")
    body: dict[str, Any] = {"moduleName": name, "status": status_id}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Create module failed.")}
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                "success": True,
                "message": str(payload.get("message") or payload.get("msg") or "Module created successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create module failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_module(
    module_id: int | str,
    module_name: str,
    *,
    status: int,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT api/dmt/module/update-module-by-id/{id} with JSON {'moduleName': '...', 'status': <seq int>}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(module_id)
    if not seg:
        return {"success": False, "message": "Module ID is required."}
    name = (module_name or "").strip()
    if not name:
        return {"success": False, "message": "Module name is required."}
    try:
        status_id = int(status)
    except (TypeError, ValueError):
        return {"success": False, "message": "Status must be a valid selection."}
    url = _api_url(f"api/dmt/module/update-module-by-id/{seg}")
    body: dict[str, Any] = {"moduleName": name, "status": status_id}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Update module failed.")}
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                "success": True,
                "message": str(payload.get("message") or payload.get("msg") or "Module updated successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update module failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_module(
    module_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE api/dmt/module/delete-module-by-id/{id} (empty body)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(module_id)
    if not seg:
        return {"success": False, "message": "Module ID is required."}
    url = _api_url(f"api/dmt/module/delete-module-by-id/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Delete module failed.")}
            return {"success": True, "message": str(payload.get("message") or payload.get("msg") or "Module deleted successfully.")}
        return {"success": True, "message": "Module deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete module failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_master_keys(*, token: str | None = None) -> dict[str, Any]:
    """GET api/masterKey/ALL. Returns {'success': bool, 'data': list, 'message': str}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/masterKey/ALL")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Failed to load master setup entries.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load master setup entries ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_master_key_category_entries(
    category: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET api/masterKey/{category} — list master rows for one category (e.g. BUSINESS_OBJECT_TYPE)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    cat = (category or "").strip()
    if not cat:
        return {"success": False, "message": "Category is required.", "data": []}
    seg = _api_path_id_segment(cat)
    if not seg:
        return {"success": False, "message": "Category is required.", "data": []}
    url = _api_url(f"api/masterKey/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(
                        payload, f"Failed to load master key list for {cat}."
                    ),
                    "data": [],
                }
        return {"success": False, "message": "Unexpected response.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load master key list ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_get_master_key_by_app_id_field_name(
    *,
    app_id: int | str | None = None,
    field_name: str,
    token: str | None = None,
) -> dict[str, Any]:
    """GET api/master-setup/master-config/get-by-field-name?fieldName=<name>[&appId=<id>].

    Returns rows with keys like ``seq`` and ``keyValue`` used by API Detail status selector.
    """
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    app_id_text = str(app_id).strip() if app_id is not None else ""
    fname = (field_name or "").strip()
    if not fname:
        return {"success": False, "message": "Field name is required.", "data": []}
    params: dict[str, str] = {"fieldName": fname}
    if app_id_text:
        params["appId"] = app_id_text
    query = urlencode(params)
    url = _api_url(f"api/master-setup/master-config/get-by-field-name?{query}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {
                    "success": True,
                    "data": rows,
                    "message": str(payload.get("message") or ""),
                }
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(
                        payload, f"Failed to load master key values for {fname}."
                    ),
                    "data": [],
                }
        return {"success": False, "message": "Unexpected response.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload,
                f"Failed to load master key values ({getattr(exc, 'code', 'HTTP error')}).",
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def master_key_row_display_label(row: dict[str, Any]) -> str:
    """Combo/list label for master-key rows: ``seq | keyValue`` (no description branch)."""
    if not isinstance(row, dict):
        return ""
    key_value = str(row.get("keyValue") or row.get("key_value") or "").strip()
    seq = row.get("seq")
    seq_text = str(seq).strip() if seq is not None else ""
    if seq_text and key_value:
        return f"{seq_text} | {key_value}"
    if seq_text:
        return seq_text
    if key_value:
        return key_value
    return ""


def master_key_row_seq_value(row: dict[str, Any]) -> Any | None:
    """Value to send to downstream APIs: master row ``seq`` only (int when numeric)."""
    if not isinstance(row, dict):
        return None
    seq = row.get("seq")
    if seq is None:
        return None
    if isinstance(seq, bool):
        return int(seq)
    if isinstance(seq, int):
        return seq
    if isinstance(seq, float) and seq == int(seq):
        return int(seq)
    s = str(seq).strip()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    try:
        f = float(s)
        if f == int(f):
            return int(f)
    except ValueError:
        pass
    return s


def api_create_master_key(
    *,
    category: str,
    seq: int | str,
    key_value: str,
    description: str = "",
    token: str | None = None,
) -> dict[str, Any]:
    """POST api/masterKey/add with JSON body for master setup entry."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    cat = (category or "").strip()
    if not cat:
        return {"success": False, "message": "Category is required."}
    kv = (key_value or "").strip()
    if not kv:
        return {"success": False, "message": "Key value is required."}
    seq_text = str(seq).strip() if seq is not None else ""
    if not seq_text:
        return {"success": False, "message": "Seq is required."}
    try:
        seq_num = int(seq_text)
    except (TypeError, ValueError):
        return {"success": False, "message": "Seq must be a valid integer."}
    url = _api_url("api/masterKey/add")
    body: dict[str, Any] = {
        "category": cat,
        "seq": seq_num,
        "keyValue": kv,
        "description": (description or "").strip(),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Create master setup entry failed.")}
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                "success": True,
                "message": str(payload.get("message") or payload.get("msg") or "Master setup entry created successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create master setup entry failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_master_key(
    master_key_id: int | str,
    *,
    category: str,
    seq: int | str,
    key_value: str,
    description: str = "",
    token: str | None = None,
) -> dict[str, Any]:
    """POST api/masterKey/update/{id} with JSON body for master setup entry."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(master_key_id)
    if not seg:
        return {"success": False, "message": "ID is required."}
    cat = (category or "").strip()
    if not cat:
        return {"success": False, "message": "Category is required."}
    kv = (key_value or "").strip()
    if not kv:
        return {"success": False, "message": "Key value is required."}
    seq_text = str(seq).strip() if seq is not None else ""
    if not seq_text:
        return {"success": False, "message": "Seq is required."}
    try:
        seq_num = int(seq_text)
    except (TypeError, ValueError):
        return {"success": False, "message": "Seq must be a valid integer."}
    url = _api_url(f"api/masterKey/update/{seg}")
    body: dict[str, Any] = {
        "category": cat,
        "seq": seq_num,
        "description": (description or "").strip(),
        "keyValue": kv,
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback="Update master setup entry failed.")
            if rej is not None:
                return rej
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                "success": True,
                "message": str(payload.get("message") or payload.get("msg") or "Master setup entry updated successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update master setup entry failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_master_key(
    master_key_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE api/masterKey/delete/{id} (empty body)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(master_key_id)
    if not seg:
        return {"success": False, "message": "ID is required."}
    url = _api_url(f"api/masterKey/delete/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback="Delete master setup entry failed.")
            if rej is not None:
                return rej
            return {
                "success": True,
                "message": str(payload.get("message") or payload.get("msg") or "Master setup entry deleted successfully."),
            }
        return {"success": True, "message": "Master setup entry deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete master setup entry failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def master_key_value_unique_category_options(rows: object) -> list[tuple[str, int]]:
    """Distinct ``(display label, categoryId)`` from master key value rows, sorted by label."""
    out: dict[int, str] = {}
    if not isinstance(rows, list):
        return []
    for r in rows:
        if not isinstance(r, dict):
            continue
        raw_id = r.get("categoryId") if r.get("categoryId") is not None else r.get("category_id")
        if raw_id is None:
            continue
        try:
            cid = int(raw_id)
        except (TypeError, ValueError):
            continue
        label = str(r.get("category") or r.get("categoryName") or r.get("category_name") or "").strip()
        if not label:
            label = f"Category {cid}"
        if cid not in out:
            out[cid] = label
    return sorted(((lbl, cid) for cid, lbl in out.items()), key=lambda t: t[0].lower())


def api_get_all_master_key_values(*, token: str | None = None) -> dict[str, Any]:
    """GET master key value list (path from :data:`MASTER_SETUP_KEY_VALUE_GET_ALL_PATH`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    path = (
        MASTER_SETUP_KEY_VALUE_GET_ALL_PATH or "api/master-setup/master-key-value/get-by-category/ALL"
    ).strip().lstrip("/")
    url = _api_url(path)
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            rej = _reject_json_business_failure(payload, message_fallback="Failed to load master key values.")
            if rej is not None:
                return {**rej, "data": []}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load master key values ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_master_key_value(
    *,
    category_id: int,
    seq: int | str,
    key_value: str,
    description: str = "",
    token: str | None = None,
) -> dict[str, Any]:
    """POST ``master-key-value/create`` with ``categoryId``, ``seq``, ``keyValue``, ``description``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    kv = (key_value or "").strip()
    if not kv:
        return {"success": False, "message": "Key value is required."}
    seq_text = str(seq).strip() if seq is not None else ""
    if not seq_text:
        return {"success": False, "message": "Seq is required."}
    try:
        seq_num = int(seq_text)
    except (TypeError, ValueError):
        return {"success": False, "message": "Seq must be a valid integer."}
    try:
        cid = int(category_id)
    except (TypeError, ValueError):
        return {"success": False, "message": "Category Id is required."}
    path = (MASTER_SETUP_KEY_VALUE_CREATE_PATH or "api/master-setup/master-key-value/create").strip().lstrip("/")
    url = _api_url(path)
    body: dict[str, Any] = {
        "categoryId": cid,
        "seq": seq_num,
        "keyValue": kv,
        "description": (description or "").strip(),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback="Create master key value failed.")
            if rej is not None:
                return rej
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                "success": True,
                "message": str(
                    payload.get("message") or payload.get("msg") or "Master key value created successfully."
                ),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create master key value failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_master_key_value(
    master_key_value_id: int | str,
    *,
    category_id: int,
    seq: int | str,
    key_value: str,
    description: str = "",
    token: str | None = None,
) -> dict[str, Any]:
    """POST ``master-key-value/update-by-id/{id}`` with JSON body (categoryId, seq, keyValue, description)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(master_key_value_id)
    if not seg:
        return {"success": False, "message": "ID is required."}
    kv = (key_value or "").strip()
    if not kv:
        return {"success": False, "message": "Key value is required."}
    seq_text = str(seq).strip() if seq is not None else ""
    if not seq_text:
        return {"success": False, "message": "Seq is required."}
    try:
        seq_num = int(seq_text)
    except (TypeError, ValueError):
        return {"success": False, "message": "Seq must be a valid integer."}
    try:
        cid = int(category_id)
    except (TypeError, ValueError):
        return {"success": False, "message": "Category Id is required."}
    base = (
        MASTER_SETUP_KEY_VALUE_UPDATE_BY_ID_PREFIX or "api/master-setup/master-key-value/update-by-id"
    ).strip().lstrip("/").rstrip("/")
    url = _api_url(f"{base}/{seg}")
    body: dict[str, Any] = {
        "categoryId": cid,
        "seq": seq_num,
        "keyValue": kv,
        "description": (description or "").strip(),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(payload, dict):
            return {"success": False, "message": "Unexpected response."}
        rej = _reject_json_business_failure(payload, message_fallback="Update master key value failed.")
        if rej is not None:
            return rej
        return {
            "success": True,
            "message": str(payload.get("message") or payload.get("msg") or "Master key value updated successfully."),
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update master key value failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_master_key_value(
    master_key_value_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE ``master-key-value/delete-by-id/{id}``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(master_key_value_id)
    if not seg:
        return {"success": False, "message": "ID is required."}
    base = (
        MASTER_SETUP_KEY_VALUE_DELETE_BY_ID_PREFIX or "api/master-setup/master-key-value/delete-by-id"
    ).strip().lstrip("/").rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if not isinstance(payload, dict):
            return {"success": True, "message": "Master key value deleted successfully."}
        rej = _reject_json_business_failure(payload, message_fallback="Delete master key value failed.")
        if rej is not None:
            return rej
        return {
            "success": True,
            "message": str(payload.get("message") or payload.get("msg") or "Master key value deleted successfully."),
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete master key value failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_master_setup_key_entries(*, token: str | None = None) -> dict[str, Any]:
    """GET ``api/master-setup/master-key/get-all-master-key`` (path from :data:`MASTER_SETUP_KEY_GET_ALL_PATH`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    path = (MASTER_SETUP_KEY_GET_ALL_PATH or "api/master-setup/master-key/get-all-master-key").strip().lstrip("/")
    url = _api_url(path)
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            rej = _reject_json_business_failure(payload, message_fallback="Failed to load master setup keys.")
            if rej is not None:
                return {**rej, "data": []}
        return {"success": False, "message": "Unexpected response.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load master setup keys ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def _master_setup_key_row_category_display(row: dict[str, Any]) -> str:
    """Human-readable category text from a master-key row (handles nested ``category`` objects)."""
    raw = row.get("category")
    if isinstance(raw, dict):
        inner = raw.get("category")
        if inner is not None and not isinstance(inner, (dict, list)):
            return str(inner).strip()
        for alt in ("categoryName", "category_name", "name"):
            v = raw.get(alt)
            if v is not None and not isinstance(v, (dict, list)):
                return str(v).strip()
        return ""
    if raw is not None and not isinstance(raw, (dict, list)):
        return str(raw).strip()
    for k in ("categoryName", "category_name"):
        v = row.get(k)
        if v is not None and not isinstance(v, (dict, list)):
            return str(v).strip()
    return ""


def master_setup_key_entry_category_combo_options(rows: object) -> list[tuple[str, int]]:
    """Build ``(display_label, id)`` pairs from get-all-master-key rows for Master Setup Value Category combo.

    Display label is ``"{id} | {category}"``; ``category`` is derived from the row's category field(s).
    The integer ``id`` is the value sent as ``categoryId`` when creating master key values.
    """
    options: list[tuple[str, int]] = []
    if not isinstance(rows, list):
        return []
    for r in rows:
        if not isinstance(r, dict):
            continue
        rid = r.get("id")
        if rid is None:
            rid = r.get("masterKeyId")
        if rid is None:
            rid = r.get("master_key_id")
        try:
            iid = int(rid)
        except (TypeError, ValueError):
            continue
        cat = _master_setup_key_row_category_display(r)
        label = f"{iid} | {cat}" if cat else f"{iid} |"
        options.append((label, iid))
    options.sort(key=lambda t: (t[1], t[0].lower()))
    return options


def api_create_master_setup_key_entry(
    categories: list[str],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST create with JSON ``{\"category\": [ ... ]}`` (path from :data:`MASTER_SETUP_KEY_CREATE_PATH`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    cleaned = [str(c).strip() for c in (categories or []) if str(c).strip()]
    if not cleaned:
        return {"success": False, "message": "At least one category is required."}
    path = (MASTER_SETUP_KEY_CREATE_PATH or "api/master-setup/master-key/create").strip().lstrip("/")
    url = _api_url(path)
    body: dict[str, Any] = {"category": cleaned}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload, "Create master setup key failed.")}
        return {
            "success": True,
            "message": str((payload or {}).get("message") or (payload or {}).get("msg") or "Master setup key created successfully."),
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create master setup key failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_master_setup_key_entry(
    key_id: int | str,
    *,
    category: str,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT ``update-by-id/{id}?category=…`` (prefix :data:`MASTER_SETUP_KEY_UPDATE_BY_ID_PREFIX`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(key_id)
    if not seg:
        return {"success": False, "message": "ID is required."}
    cat = (category or "").strip()
    if not cat:
        return {"success": False, "message": "Category is required."}
    base = (MASTER_SETUP_KEY_UPDATE_BY_ID_PREFIX or "api/master-setup/master-key/update-by-id").strip().lstrip("/").rstrip("/")
    q = urlencode({"category": cat})
    url = _api_url(f"{base}/{seg}?{q}")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"{}", headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload, "Update master setup key failed.")}
        return {
            "success": True,
            "message": str((payload or {}).get("message") or (payload or {}).get("msg") or "Master setup key updated successfully."),
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update master setup key failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_master_setup_key_entry(
    key_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE ``delete-by-id/{id}`` (prefix :data:`MASTER_SETUP_KEY_DELETE_BY_ID_PREFIX`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(key_id)
    if not seg:
        return {"success": False, "message": "ID is required."}
    base = (MASTER_SETUP_KEY_DELETE_BY_ID_PREFIX or "api/master-setup/master-key/delete-by-id").strip().lstrip("/").rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload, "Delete master setup key failed.")}
        return {
            "success": True,
            "message": str((payload or {}).get("message") or (payload or {}).get("msg") or "Master setup key deleted successfully."),
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete master setup key failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_master_setup_configs(*, token: str | None = None) -> dict[str, Any]:
    """GET master config list (path from :data:`MASTER_SETUP_CONFIG_GET_ALL_PATH`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    path = (MASTER_SETUP_CONFIG_GET_ALL_PATH or "api/master-setup/master-config/get-all-config").strip().lstrip("/")
    url = _api_url(path)
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Failed to load master setup configs."), "data": []}
        return {"success": False, "message": "Unexpected response.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load master setup configs ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_create_master_setup_config(
    *,
    field: str,
    category_id: int,
    token: str | None = None,
) -> dict[str, Any]:
    """POST master-config create with JSON ``field``, ``categoryId``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    f = (field or "").strip()
    if not f:
        return {"success": False, "message": "Field is required."}
    try:
        cid = int(category_id)
    except (TypeError, ValueError):
        return {"success": False, "message": "Category Id is required."}
    path = (MASTER_SETUP_CONFIG_CREATE_PATH or "api/master-setup/master-config/create").strip().lstrip("/")
    url = _api_url(path)
    body: dict[str, Any] = {"field": f, "categoryId": cid}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload, "Create master setup config failed.")}
        return {
            "success": True,
            "message": str(payload.get("message") or payload.get("msg") or "Master setup config created successfully.") if isinstance(payload, dict) else "Master setup config created successfully.",
            "data": payload if isinstance(payload, dict) else {},
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create master setup config failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_master_setup_config(
    config_id: int | str,
    *,
    field: str,
    category_id: int,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT master-config ``update-config-by-id/{id}`` with JSON ``field``, ``categoryId``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(config_id)
    if not seg:
        return {"success": False, "message": "ID is required."}
    f = (field or "").strip()
    if not f:
        return {"success": False, "message": "Field is required."}
    try:
        cid = int(category_id)
    except (TypeError, ValueError):
        return {"success": False, "message": "Category Id is required."}
    base = (
        MASTER_SETUP_CONFIG_UPDATE_BY_ID_PREFIX or "api/master-setup/master-config/update-config-by-id"
    ).strip().lstrip("/").rstrip("/")
    url = _api_url(f"{base}/{seg}")
    body: dict[str, Any] = {"field": f, "categoryId": cid}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload, "Update master setup config failed.")}
        return {
            "success": True,
            "message": str(payload.get("message") or payload.get("msg") or "Master setup config updated successfully.") if isinstance(payload, dict) else "Master setup config updated successfully.",
            "data": payload if isinstance(payload, dict) else {},
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update master setup config failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_master_setup_config(
    config_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE master-config ``delete-config-by-id/{id}``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(config_id)
    if not seg:
        return {"success": False, "message": "ID is required."}
    base = (
        MASTER_SETUP_CONFIG_DELETE_BY_ID_PREFIX or "api/master-setup/master-config/delete-config-by-id"
    ).strip().lstrip("/").rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload, "Delete master setup config failed.")}
        return {
            "success": True,
            "message": str(payload.get("message") or payload.get("msg") or "Master setup config deleted successfully.") if isinstance(payload, dict) else "Master setup config deleted successfully.",
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete master setup config failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_objects(*, token: str | None = None) -> dict[str, Any]:
    """GET api/dmt/object/get-all-dmt-object. Returns {'success': bool, 'data': list, 'message': str}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/dmt/object/get-all-dmt-object")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Failed to load objects.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load objects ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_object(
    object_name: str,
    module_id: int | str,
    *,
    status: int,
    token: str | None = None,
) -> dict[str, Any]:
    """POST api/dmt/object/create with JSON {'objectName': '...', 'moduleId': n, 'status': <seq int>}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    name = (object_name or "").strip()
    if not name:
        return {"success": False, "message": "Object name is required."}
    if module_id is None or (isinstance(module_id, str) and not str(module_id).strip()):
        return {"success": False, "message": "Module is required."}
    try:
        mid: int | str = int(str(module_id).strip())
    except (TypeError, ValueError):
        mid = str(module_id).strip()
    try:
        status_id = int(status)
    except (TypeError, ValueError):
        return {"success": False, "message": "Status must be a valid selection."}
    url = _api_url("api/dmt/object/create")
    body: dict[str, Any] = {"objectName": name, "moduleId": mid, "status": status_id}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Create object failed.")}
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                "success": True,
                "message": str(payload.get("message") or payload.get("msg") or "Object created successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create object failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_object(
    object_id: int | str,
    object_name: str,
    *,
    status: int,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT api/dmt/object/update-by-id/{id} with JSON {'objectName': '...', 'status': <seq int>}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(object_id)
    if not seg:
        return {"success": False, "message": "Object ID is required."}
    name = (object_name or "").strip()
    if not name:
        return {"success": False, "message": "Object name is required."}
    try:
        status_id = int(status)
    except (TypeError, ValueError):
        return {"success": False, "message": "Status must be a valid selection."}
    url = _api_url(f"api/dmt/object/update-by-id/{seg}")
    body: dict[str, Any] = {"objectName": name, "status": status_id}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Update object failed.")}
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                "success": True,
                "message": str(payload.get("message") or payload.get("msg") or "Object updated successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update object failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_object(
    object_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE api/dmt/object/delete-by-id/{id} (empty body)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(object_id)
    if not seg:
        return {"success": False, "message": "Object ID is required."}
    url = _api_url(f"api/dmt/object/delete-by-id/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Delete object failed.")}
            return {"success": True, "message": str(payload.get("message") or payload.get("msg") or "Object deleted successfully.")}
        return {"success": True, "message": "Object deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete object failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _dmt_user_status_for_json(status: Any) -> Any:
    """Master-key seq (int) or legacy ACTIVE/INACTIVE string for DMT user JSON ``status``."""
    if status is None:
        return "ACTIVE"
    if isinstance(status, bool):
        return int(status)
    if isinstance(status, int):
        return status
    if isinstance(status, float) and status == int(status):
        return int(status)
    s = str(status).strip()
    if not s:
        return "ACTIVE"
    if s.isdigit():
        return int(s)
    return s.upper()


def api_get_dmt_user_by_id(user_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """GET ``{DMT_USER_GET_BY_ID_PREFIX}/{id}``. Returns {'success': bool, 'data': dict, 'message': str}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "data": {}}
    seg = _api_path_id_segment(user_id)
    if not seg:
        return {"success": False, "message": "User ID is required.", "data": {}}
    base = DMT_USER_GET_BY_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to load DMT user."),
                    "data": {},
                }
            data = payload.get("data")
            if isinstance(data, dict):
                return {"success": True, "data": data, "message": str(payload.get("message") or "")}
            if data is None and any(
                k in payload for k in ("userId", "id", "firstName", "email", "first_name")
            ):
                return {"success": True, "data": payload, "message": str(payload.get("message") or "")}
        return {"success": False, "message": "Unexpected response.", "data": {}}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load DMT user ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": {},
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": {}}


def api_get_all_dmt_users(*, token: str | None = None) -> dict[str, Any]:
    """GET DMT user list path from :data:`DMT_USER_GET_ALL_PATH`. Returns {'success': bool, 'data': list, 'message': str}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(DMT_USER_GET_ALL_PATH.strip().lstrip("/"))
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Failed to load DMT users.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load DMT users ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _dmt_user_mobile_for_json(mobile: str, *, country_code: str = "+91") -> str:
    """National digits or pre-merged value → single ``mobile`` string for create/update body."""
    raw = (mobile or "").strip().replace(" ", "").replace("-", "")
    if not raw:
        return ""
    if raw.startswith("+"):
        return raw
    cc = (country_code or "+91").strip()
    return f"{cc}{raw}" if cc else raw


def api_create_dmt_user(
    first_name: str,
    last_name: str,
    email: str,
    mobile: str,
    *,
    country_code: str = "+91",
    status: Any = "ACTIVE",
    token: str | None = None,
) -> dict[str, Any]:
    """POST ``DMT_USER_CREATE_PATH`` with JSON ``mobile`` (country code + national digits merged)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    email = (email or "").strip()
    mobile_out = _dmt_user_mobile_for_json(mobile, country_code=country_code)
    status_out = _dmt_user_status_for_json(status if status is not None else "ACTIVE")
    if not first_name:
        return {"success": False, "message": "First name is required."}
    if not last_name:
        return {"success": False, "message": "Last name is required."}
    if not email:
        return {"success": False, "message": "Email is required."}
    if not mobile_out:
        return {"success": False, "message": "Mobile is required."}

    url = _api_url(DMT_USER_CREATE_PATH.strip().lstrip("/"))
    body: dict[str, Any] = {
        "firstName": first_name,
        "lastName": last_name,
        "status": status_out,
        "email": email,
        "mobile": mobile_out,
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            _http_status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Create DMT user failed.")}
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                "success": True,
                "message": str(payload.get("message") or payload.get("msg") or "DMT user created successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create DMT user failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_dmt_user(
    user_id: int | str,
    first_name: str,
    last_name: str,
    status: Any,
    email: str,
    mobile: str,
    *,
    country_code: str = "+91",
    token: str | None = None,
) -> dict[str, Any]:
    """PUT ``{DMT_USER_UPDATE_BY_ID_PREFIX}/{id}`` with JSON ``mobile`` (country code + national digits merged)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(user_id)
    if not seg:
        return {"success": False, "message": "User ID is required."}
    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    email = (email or "").strip()
    mobile_out = _dmt_user_mobile_for_json(mobile, country_code=country_code)
    if status is None or (isinstance(status, str) and not str(status).strip()):
        return {"success": False, "message": "Status is required."}
    status_out = _dmt_user_status_for_json(status)
    if isinstance(status_out, str) and not status_out.strip():
        return {"success": False, "message": "Status is required."}
    if not first_name:
        return {"success": False, "message": "First name is required."}
    if not last_name:
        return {"success": False, "message": "Last name is required."}
    if not email:
        return {"success": False, "message": "Email is required."}
    if not mobile_out:
        return {"success": False, "message": "Mobile is required."}
    base = DMT_USER_UPDATE_BY_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    body: dict[str, Any] = {
        "firstName": first_name,
        "lastName": last_name,
        "status": status_out,
        "email": email,
        "mobile": mobile_out,
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            _http_status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Update DMT user failed.")}
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {
                "success": True,
                "message": str(payload.get("message") or payload.get("msg") or "DMT user updated successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update DMT user failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_dmt_user(
    user_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE ``{DMT_USER_DELETE_BY_ID_PREFIX}/{id}`` (empty body)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(user_id)
    if not seg:
        return {"success": False, "message": "User ID is required."}
    base = DMT_USER_DELETE_BY_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Delete DMT user failed.")}
            return {"success": True, "message": str(payload.get("message") or payload.get("msg") or "DMT user deleted successfully.")}
        return {"success": True, "message": "DMT user deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete DMT user failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _dm_project_master_seq_for_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, dict):
        for k in ("seq", "statusSeq", "status_seq", "id"):
            if k in value and value.get(k) is not None:
                return _dm_project_master_seq_for_json(value.get(k))
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value == int(value):
        return int(value)
    s = str(value).strip()
    if s.isdigit():
        return int(s)
    return s


def _normalize_dm_project_rows(payload: Any) -> list[dict[str, Any]]:
    """Coerce get-all project responses to a list of project dicts (skip null/empty rows)."""
    if payload is None:
        return []
    if isinstance(payload, dict):
        for key in ("data", "projects", "content", "items", "result"):
            inner = payload.get(key)
            if isinstance(inner, list):
                return _normalize_dm_project_rows(inner)
            if isinstance(inner, dict) and (inner.get("id") is not None or inner.get("projectId") is not None):
                return [inner]
        if payload.get("id") is not None or payload.get("projectId") is not None:
            return [payload]
        return []
    if not isinstance(payload, list):
        return []
    out: list[dict[str, Any]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        pid = row.get("id")
        if pid is None:
            pid = row.get("projectId")
        if pid is None or str(pid).strip() == "":
            continue
        out.append(row)
    return out


def api_get_all_dm_projects(*, token: str | None = None) -> dict[str, Any]:
    """GET ``DM_PROJECT_GET_ALL_PATH``. Returns {'success': bool, 'data': list, 'message': str}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(DM_PROJECT_GET_ALL_PATH.strip().lstrip("/"))
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, dict) and payload.get("success") is False:
            return {
                "success": False,
                "message": _extract_error_message(payload, "Failed to load DM projects."),
            }
        rows = _normalize_dm_project_rows(payload)
        return {
            "success": True,
            "data": rows,
            "message": str(payload.get("message") or "") if isinstance(payload, dict) else "",
        }
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load DM projects ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _normalize_dm_user_project_rows(payload: Any) -> list[dict[str, Any]]:
    """Extract user–project assignment rows from common backend response shapes."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in (
        "data",
        "content",
        "result",
        "records",
        "items",
        "users",
        "assignments",
        "userProjects",
        "user_projects",
        "getUserByProjectId",
        "get_user_by_project_id",
    ):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
        if isinstance(rows, dict):
            nested = _normalize_dm_user_project_rows(rows)
            if nested:
                return nested
    return []


def api_get_dm_users_by_project_id(
    project_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET ``{DM_USER_PROJECT_GET_BY_PROJECT_ID_PREFIX}/{projectId}``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    seg = _api_path_id_segment(project_id)
    if not seg:
        return {"success": False, "message": "Project ID is required.", "data": []}
    base = DM_USER_PROJECT_GET_BY_PROJECT_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=15.0)
        if isinstance(payload, dict) and payload.get("success") is False:
            return {
                "success": False,
                "message": _extract_error_message(payload, "Failed to load project users."),
                "data": [],
            }
        rows = _normalize_dm_user_project_rows(payload)
        if rows or not isinstance(payload, dict):
            return {"success": True, "data": rows, "message": ""}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "data": [],
            "message": _extract_error_message(
                err_payload,
                f"Failed to load project users ({getattr(exc, 'code', 'HTTP error')}).",
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_assign_dm_user_project(
    *,
    user_id: int | str,
    project_id: int | str,
    status: int | str,
    user_type: int | str,
    token: str | None = None,
) -> dict[str, Any]:
    """POST ``DM_USER_PROJECT_ASSIGN_PATH`` with JSON ``{userId, projectId, status, userType}``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    uid = _api_path_id_segment(user_id)
    pid = _api_path_id_segment(project_id)
    if not uid:
        return {"success": False, "message": "User ID is required."}
    if not pid:
        return {"success": False, "message": "Project ID is required."}
    if status is None or str(status).strip() == "":
        return {"success": False, "message": "Status is required."}
    if user_type is None or str(user_type).strip() == "":
        return {"success": False, "message": "User type is required."}
    body = {
        "userId": int(uid) if str(uid).isdigit() else uid,
        "projectId": int(pid) if str(pid).isdigit() else pid,
        "status": int(status) if str(status).strip().isdigit() else status,
        "userType": int(user_type) if str(user_type).strip().isdigit() else user_type,
    }
    url = _api_url(DM_USER_PROJECT_ASSIGN_PATH.strip().lstrip("/"))
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=12.0) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {
                "success": False,
                "message": _extract_error_message(payload, "Assign user to project failed."),
            }
        return {
            "success": True,
            "message": str(
                (payload or {}).get("message") if isinstance(payload, dict) else ""
            ) or "User assigned to project successfully.",
        }
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Assign user failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_dm_user_project_by_id(
    mapping_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE ``{DM_USER_PROJECT_DELETE_BY_ID_PREFIX}/{id}``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(mapping_id)
    if not seg:
        return {"success": False, "message": "Mapping ID is required."}
    base = DM_USER_PROJECT_DELETE_BY_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=12.0) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {
                "success": False,
                "message": _extract_error_message(payload, "Remove user from project failed."),
            }
        return {
            "success": True,
            "message": str(
                (payload or {}).get("message") if isinstance(payload, dict) else ""
            ) or "User removed from project successfully.",
        }
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Remove failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_change_dm_user_project_status_by_id(
    mapping_id: int | str,
    status: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT ``{DM_USER_PROJECT_CHANGE_STATUS_BY_ID_PREFIX}/{id}?status=``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(mapping_id)
    if not seg:
        return {"success": False, "message": "Mapping ID is required."}
    if status is None or str(status).strip() == "":
        return {"success": False, "message": "Status is required."}
    base = DM_USER_PROJECT_CHANGE_STATUS_BY_ID_PREFIX.strip().rstrip("/")
    query = urlencode({"status": str(status).strip()})
    url = _api_url(f"{base}/{seg}?{query}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=12.0) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {
                "success": False,
                "message": _extract_error_message(payload, "Change status failed."),
            }
        return {
            "success": True,
            "message": str(
                (payload or {}).get("message") if isinstance(payload, dict) else ""
            ) or "Status updated successfully.",
        }
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Change status failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_assign_dm_users_to_project(
    *,
    project_id: int | str,
    user_ids: list[int | str],
    status: int | str,
    user_type: int | str,
    token: str | None = None,
) -> dict[str, Any]:
    """Assign multiple users; stops on first failure and reports count."""
    valid = [u for u in (user_ids or []) if u is not None and str(u).strip() != ""]
    if not valid:
        return {"success": False, "message": "Select at least one user."}
    ok = 0
    last_msg = ""
    for uid in valid:
        result = api_assign_dm_user_project(
            user_id=uid,
            project_id=project_id,
            status=status,
            user_type=user_type,
            token=token,
        )
        if not result.get("success"):
            if ok:
                return {
                    "success": False,
                    "message": f"{last_msg} Assigned {ok} of {len(valid)}; then: {result.get('message')}",
                }
            return result
        ok += 1
        last_msg = str(result.get("message") or "")
    return {
        "success": True,
        "message": last_msg or f"Assigned {ok} user(s) to project successfully.",
    }


def api_delete_dm_user_projects_by_ids(
    mapping_ids: list[int | str],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE each mapping id; stops on first failure."""
    valid = [m for m in (mapping_ids or []) if m is not None and str(m).strip() != ""]
    if not valid:
        return {"success": False, "message": "Select at least one mapping."}
    ok = 0
    last_msg = ""
    for mid in valid:
        result = api_delete_dm_user_project_by_id(mid, token=token)
        if not result.get("success"):
            if ok:
                return {
                    "success": False,
                    "message": f"{last_msg} Removed {ok} of {len(valid)}; then: {result.get('message')}",
                }
            return result
        ok += 1
        last_msg = str(result.get("message") or "")
    return {
        "success": True,
        "message": last_msg or f"Removed {ok} mapping(s) successfully.",
    }


def api_change_dm_user_project_status_by_ids(
    mapping_ids: list[int | str],
    status: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT status for each mapping id; stops on first failure."""
    valid = [m for m in (mapping_ids or []) if m is not None and str(m).strip() != ""]
    if not valid:
        return {"success": False, "message": "Select at least one mapping."}
    ok = 0
    last_msg = ""
    for mid in valid:
        result = api_change_dm_user_project_status_by_id(mid, status=status, token=token)
        if not result.get("success"):
            if ok:
                return {
                    "success": False,
                    "message": f"{last_msg} Updated {ok} of {len(valid)}; then: {result.get('message')}",
                }
            return result
        ok += 1
        last_msg = str(result.get("message") or "")
    return {
        "success": True,
        "message": last_msg or f"Updated status for {ok} mapping(s) successfully.",
    }


def _normalize_dm_project_contact_assigned_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in (
        "data",
        "content",
        "result",
        "records",
        "items",
        "contacts",
        "contactPersons",
        "contact_persons",
        "assignedContacts",
        "assigned_contacts",
    ):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
        if isinstance(rows, dict):
            nested = _normalize_dm_project_contact_assigned_rows(rows)
            if nested:
                return nested
    return []


def api_get_dm_project_contact_assigned(
    project_or_scope_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET ``{DM_PROJECT_GET_CONTACT_ASSIGNED_PREFIX}/{projectId}`` — contacts assigned to a project."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    seg = _api_path_id_segment(project_or_scope_id)
    if not seg:
        return {"success": False, "message": "Project ID is required.", "data": []}
    base = DM_PROJECT_GET_CONTACT_ASSIGNED_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=15.0)
        if isinstance(payload, dict) and payload.get("success") is False:
            return {
                "success": False,
                "message": _extract_error_message(
                    payload, "Failed to load contacts assigned to project."
                ),
                "data": [],
            }
        rows = _normalize_dm_project_contact_assigned_rows(payload)
        if rows or not isinstance(payload, dict):
            return {"success": True, "data": rows, "message": ""}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "data": [],
            "message": _extract_error_message(
                err_payload,
                f"Failed to load assigned contacts ({getattr(exc, 'code', 'HTTP error')}).",
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_get_dm_project_by_id(project_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """GET ``{DM_PROJECT_GET_BY_ID_PREFIX}/{id}``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "data": {}}
    seg = _api_path_id_segment(project_id)
    if not seg:
        return {"success": False, "message": "Project ID is required.", "data": {}}
    base = DM_PROJECT_GET_BY_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=10.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load project.", data={}
            )
            if rej is not None:
                return rej
            data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
            return {"success": True, "data": data if isinstance(data, dict) else {}, "message": ""}
        return {"success": False, "message": "Unexpected response.", "data": {}}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "data": {},
            "message": _extract_error_message(
                err_payload, f"Failed to load project ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": {}}


def api_create_dm_project(
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST ``DM_PROJECT_CREATE_PATH`` with JSON project body."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(DM_PROJECT_CREATE_PATH.strip().lstrip("/"))
    body = dict(payload or {})
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        response_payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(response_payload, dict) and response_payload.get("success") is False:
            return {
                "success": False,
                "message": _extract_error_message(response_payload, "Create project failed."),
            }
        data = response_payload.get("data") if isinstance(response_payload, dict) else None
        return {
            "success": True,
            "message": str(
                (response_payload or {}).get("message")
                or (response_payload or {}).get("msg")
                or "Project created successfully."
            ),
            "data": data if isinstance(data, dict) else response_payload,
        }
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create project failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_dm_project(
    project_id: int | str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT ``{DM_PROJECT_UPDATE_BY_ID_PREFIX}/{id}`` with JSON project body."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(project_id)
    if not seg:
        return {"success": False, "message": "Project ID is required."}
    base = DM_PROJECT_UPDATE_BY_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    body = dict(payload or {})
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        response_payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(response_payload, dict) and response_payload.get("success") is False:
            return {
                "success": False,
                "message": _extract_error_message(response_payload, "Update project failed."),
            }
        data = response_payload.get("data") if isinstance(response_payload, dict) else None
        return {
            "success": True,
            "message": str(
                (response_payload or {}).get("message")
                or (response_payload or {}).get("msg")
                or "Project updated successfully."
            ),
            "data": data if isinstance(data, dict) else response_payload,
        }
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update project failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_dm_project(
    project_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE ``{DM_PROJECT_DELETE_BY_ID_PREFIX}/{id}``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(project_id)
    if not seg:
        return {"success": False, "message": "Project ID is required."}
    base = DM_PROJECT_DELETE_BY_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload, "Delete project failed.")}
        return {"success": True, "message": str((payload or {}).get("message") or "Project deleted successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete project failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _comma_separated_ids(ids: list[int | str]) -> str:
    out: list[str] = []
    seen: set[str] = set()
    for x in ids:
        if x is None or isinstance(x, bool):
            continue
        s = str(x).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return ",".join(out)


def _normalize_dmt_user_module_assignment_rows(payload: Any) -> list[dict[str, Any]]:
    """Extract assignment rows from common backend response shapes."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in (
        "data",
        "content",
        "result",
        "records",
        "items",
        "modules",
        "assignments",
        "userModules",
        "user_modules",
        "getUserModules",
        "get_user_modules",
        "moduleAssignments",
        "module_assignments",
    ):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
        if isinstance(rows, dict):
            nested = _normalize_dmt_user_module_assignment_rows(rows)
            if nested:
                return nested
    return []


def api_get_dmt_user_module_assignments_by_user_id(
    user_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET ``{DMT_USER_MODULE_GET_BY_USER_ID_PREFIX}/{userId}`` (default ``api/dm-project/user/get-user-modules/{userId}``)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    seg = _api_path_id_segment(user_id)
    if not seg:
        return {"success": False, "message": "User ID is required.", "data": []}
    base = DMT_USER_MODULE_GET_BY_USER_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=15.0)
        if isinstance(payload, dict) and payload.get("success") is False:
            return {
                "success": False,
                "message": _extract_error_message(payload, "Failed to load user module assignments."),
                "data": [],
            }
        rows = _normalize_dmt_user_module_assignment_rows(payload)
        if rows or not isinstance(payload, dict):
            return {"success": True, "data": rows, "message": ""}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        code = getattr(exc, "code", None)
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        if code == 404:
            return {
                "success": False,
                "data": [],
                "message": _extract_error_message(
                    err_payload,
                    "Assignments API not found (404). Confirm backend exposes "
                    f"GET {base}/{{userId}} or set ETL_DMT_USER_MODULE_GET_BY_USER_ID_PREFIX.",
                ),
            }
        return {
            "success": False,
            "data": [],
            "message": _extract_error_message(
                err_payload, f"Failed to load assignments ({code or 'HTTP error'})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_assign_dmt_user_modules(
    user_id: int | str,
    module_ids: list[int | str],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST ``DMT_USER_MODULE_ASSIGN_PATH?userId=&moduleIds=1,2,3``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    uid = _api_path_id_segment(user_id)
    if not uid:
        return {"success": False, "message": "User ID is required."}
    mids = _comma_separated_ids(module_ids)
    if not mids:
        return {"success": False, "message": "Select at least one module."}
    base = DMT_USER_MODULE_ASSIGN_PATH.strip().lstrip("/")
    query = urlencode({"userId": uid, "moduleIds": mids})
    url = _api_url(f"{base}?{query}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=15.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {
                "success": False,
                "message": _extract_error_message(payload, "Assign modules failed."),
            }
        return {
            "success": True,
            "message": str(
                (payload or {}).get("message") if isinstance(payload, dict) else ""
            ) or "Module(s) assigned successfully.",
        }
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Assign modules failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_change_dmt_user_module_status_by_id(
    assignment_id: int | str,
    status: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT ``{DMT_USER_MODULE_CHANGE_STATUS_BY_ID_PREFIX}/{id}?status=``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(assignment_id)
    if not seg:
        return {"success": False, "message": "Assignment ID is required."}
    if status is None or str(status).strip() == "":
        return {"success": False, "message": "Status is required."}
    base = DMT_USER_MODULE_CHANGE_STATUS_BY_ID_PREFIX.strip().rstrip("/")
    query = urlencode({"status": str(status).strip()})
    url = _api_url(f"{base}/{seg}?{query}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=15.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {
                "success": False,
                "message": _extract_error_message(payload, "Change status failed."),
            }
        return {
            "success": True,
            "message": str(
                (payload or {}).get("message") if isinstance(payload, dict) else ""
            ) or "Status updated successfully.",
        }
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Change status failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_remove_dmt_user_module_assignments(
    user_id: int | str,
    module_ids: list[int | str],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE ``DMT_USER_MODULE_REMOVE_ASSIGNMENT_PATH?userId=&moduleIds=2,3``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    uid = _api_path_id_segment(user_id)
    if not uid:
        return {"success": False, "message": "User ID is required."}
    mids = _comma_separated_ids(module_ids)
    if not mids:
        return {"success": False, "message": "Select at least one module."}
    base = DMT_USER_MODULE_REMOVE_ASSIGNMENT_PATH.strip().lstrip("/")
    query = urlencode({"userId": uid, "moduleIds": mids})
    url = _api_url(f"{base}?{query}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=15.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {
                "success": False,
                "message": _extract_error_message(payload, "Remove assignment failed."),
            }
        return {
            "success": True,
            "message": str(
                (payload or {}).get("message") if isinstance(payload, dict) else ""
            ) or "Assignment(s) removed successfully.",
        }
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Remove assignment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _multipart_file_body(
    *,
    field_name: str,
    file_path: str,
    extra_fields: dict[str, str] | None = None,
) -> tuple[bytes, str]:
    from urllib.parse import quote as _url_quote

    path = Path(file_path)
    data = path.read_bytes()
    filename = path.name
    # ASCII-safe fallback filename + RFC 5987 UTF-8 filename* for non-ASCII names.
    ascii_name = filename.encode("ascii", errors="replace").decode("ascii").replace('"', "_")
    utf8_name = _url_quote(filename, safe="")
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    boundary = uuid4().hex
    b = boundary.encode("ascii")
    parts: list[bytes] = []
    for key, value in (extra_fields or {}).items():
        k = str(key or "").strip()
        if not k:
            continue
        parts.extend(
            [
                b"--",
                b,
                b"\r\n",
                f'Content-Disposition: form-data; name="{k}"\r\n\r\n'.encode("utf-8"),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    parts.extend(
        [
            b"--",
            b,
            b"\r\n",
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_name}\r\n'
            ).encode("utf-8"),
            f"Content-Type: {content_type}\r\n\r\n".encode("ascii"),
            data,
            b"\r\n--",
            b,
            b"--\r\n",
        ]
    )
    return b"".join(parts), boundary


def api_upload_dm_users_from_file(
    file_path: str,
    *,
    token: str | None = None,
    field_name: str = "file",
) -> dict[str, Any]:
    """POST multipart file to ``DMT_USER_UPLOAD_PATH`` (default ``api/dm-project/user/upload-users``)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    path = Path(file_path)
    if not path.is_file():
        return {"success": False, "message": "Select a file to upload."}
    try:
        body, boundary = _multipart_file_body(field_name=field_name, file_path=str(path))
    except OSError as exc:
        return {"success": False, "message": f"Could not read file: {exc}"}
    url = _api_url(DMT_USER_UPLOAD_PATH.strip().lstrip("/"))
    headers: dict[str, str] = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=body, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=120.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Upload users failed."),
                }
            return {
                "success": True,
                "message": str(
                    payload.get("message") or payload.get("msg") or "Users uploaded successfully."
                ),
                "data": payload.get("data"),
            }
        return {"success": True, "message": "Users uploaded successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Upload users failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_users_copy_from_app_user(
    app_user_ids: list[int | str],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST ``DMT_USER_COPY_FROM_APPUSER_PATH`` (default ``api/dm-project/user/copy-from-app-user``) with JSON body ``[id, ...]`` (app user IDs)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    ids: list[int] = []
    seen: set[int] = set()
    for x in app_user_ids:
        if isinstance(x, bool) or x is None:
            continue
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if n not in seen:
            seen.add(n)
            ids.append(n)
    if not ids:
        return {"success": False, "message": "At least one numeric user ID is required."}
    url = _api_url(DMT_USER_COPY_FROM_APPUSER_PATH.strip().lstrip("/"))
    body_list: list[int] = ids
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(
            url,
            data=json.dumps(body_list).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with _http_urlopen_logged(req, timeout=30.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Copy users failed."),
                }
            return {
                "success": True,
                "message": str(payload.get("message") or payload.get("msg") or "Users copied successfully."),
                "data": payload.get("data"),
            }
        return {"success": True, "message": "Users copied successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Copy users failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_lead_companies(*, token: str | None = None) -> dict[str, Any]:
    """GET lead-mgmt company list (path from :data:`LEAD_MGMT_COMPANY_GET_ALL_PATH`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    path = (LEAD_MGMT_COMPANY_GET_ALL_PATH or "api/lead-mgmt/company/get-all-company").strip().lstrip("/")
    url = _api_url(path)
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Failed to load companies.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load companies ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_lead_company_contacts_by_company_id(
    company_id: Any,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET contacts linked to a company (path prefix + id from config)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    if company_id is None or str(company_id).strip() == "":
        return {"success": False, "message": "Company is required."}
    base = (
        LEAD_MGMT_COMPANY_CONTACT_GET_BY_COMPANY_PREFIX
        or "api/lead-mgmt/company-contact/get-contact-by-company-id"
    ).strip().lstrip("/").rstrip("/")
    seg = _api_path_id_segment(company_id)
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        rows: list[Any]
        if isinstance(payload, list):
            rows = payload
        elif isinstance(payload, dict):
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to load company contacts."),
                }
            data = payload.get("data")
            if isinstance(data, list):
                rows = data
            elif isinstance(data, dict):
                inner = data.get("data") or data.get("contacts") or data.get("items")
                rows = list(inner) if isinstance(inner, list) else []
            else:
                rows = []
        else:
            rows = []
        out = [r for r in rows if isinstance(r, dict)]
        return {"success": True, "data": out, "message": ""}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load company contacts ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_lead_company(
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST lead-mgmt company create (path from :data:`LEAD_MGMT_COMPANY_CREATE_PATH`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    company_name = str((payload or {}).get("companyName") or "").strip()
    if not company_name:
        return {"success": False, "message": "Company Name is required."}
    path = (LEAD_MGMT_COMPANY_CREATE_PATH or "api/lead-mgmt/company/create").strip().lstrip("/")
    url = _api_url(path)
    body: dict[str, Any] = {}
    for k, v in (payload or {}).items():
        if v is None:
            continue
        if isinstance(v, (int, float, bool)):
            body[k] = v
            continue
        if str(v).strip() == "":
            continue
        body[k] = v
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict):
            if payload_resp.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload_resp, "Create company failed.")}
            data = payload_resp.get("data") if isinstance(payload_resp.get("data"), dict) else payload_resp
            return {
                "success": True,
                "message": str(payload_resp.get("message") or payload_resp.get("msg") or "Company created successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create company failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_lead_company(
    company_id: int | str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT lead-mgmt ``update-company-by-id/{id}`` (prefix :data:`LEAD_MGMT_COMPANY_UPDATE_PATH_PREFIX`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(company_id)
    if not seg:
        return {"success": False, "message": "Company is required for update."}
    body: dict[str, Any] = {}
    for k, v in (payload or {}).items():
        if v is None:
            continue
        if isinstance(v, (int, float, bool)):
            body[k] = v
            continue
        if str(v).strip() == "":
            continue
        body[k] = v
    if not body:
        return {"success": False, "message": "No changes to update."}
    base = (LEAD_MGMT_COMPANY_UPDATE_PATH_PREFIX or "api/lead-mgmt/company/update-company-by-id").strip().lstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict):
            if payload_resp.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload_resp, "Update company failed.")}
            data = payload_resp.get("data") if isinstance(payload_resp.get("data"), dict) else payload_resp
            return {
                "success": True,
                "message": str(payload_resp.get("message") or payload_resp.get("msg") or "Company updated successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update company failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_lead_company(
    company_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE lead-mgmt ``delete-company-by-id/{id}`` (prefix :data:`LEAD_MGMT_COMPANY_DELETE_PATH_PREFIX`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(company_id)
    if not seg:
        return {"success": False, "message": "Company is required."}
    base = (LEAD_MGMT_COMPANY_DELETE_PATH_PREFIX or "api/lead-mgmt/company/delete-company-by-id").strip().lstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Delete company failed.")}
            return {"success": True, "message": str(payload.get("message") or payload.get("msg") or "Company deleted successfully.")}
        return {"success": True, "message": "Company deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete company failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_dm_companies(*, token: str | None = None) -> dict[str, Any]:
    """GET dm company list (path from :data:`DM_COMPANY_GET_ALL_PATH`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    path = (DM_COMPANY_GET_ALL_PATH or "api/dm/company/get-all-company").strip().lstrip("/")
    url = _api_url(path)
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = _unwrap_api_row_list(payload.get("data"))
            if rows is not None:
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Failed to load companies.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load companies ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_dm_company(
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST dm company create (path from :data:`DM_COMPANY_CREATE_PATH`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    company_name = str((payload or {}).get("companyName") or "").strip()
    if not company_name:
        return {"success": False, "message": "Company Name is required."}
    path = (DM_COMPANY_CREATE_PATH or "api/dm/company/create").strip().lstrip("/")
    url = _api_url(path)
    body: dict[str, Any] = {}
    for k, v in (payload or {}).items():
        if v is None:
            continue
        if isinstance(v, (int, float, bool)):
            body[k] = v
            continue
        if str(v).strip() == "":
            continue
        body[k] = v
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict):
            if payload_resp.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload_resp, "Create company failed.")}
            data = payload_resp.get("data") if isinstance(payload_resp.get("data"), dict) else payload_resp
            return {
                "success": True,
                "message": str(payload_resp.get("message") or payload_resp.get("msg") or "Company created successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create company failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_dm_company(
    company_id: int | str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT dm ``update-company-by-id/{id}`` (prefix :data:`DM_COMPANY_UPDATE_PATH_PREFIX`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(company_id)
    if not seg:
        return {"success": False, "message": "Company is required for update."}
    body: dict[str, Any] = {}
    for k, v in (payload or {}).items():
        if v is None:
            continue
        if isinstance(v, (int, float, bool)):
            body[k] = v
            continue
        if str(v).strip() == "":
            continue
        body[k] = v
    if not body:
        return {"success": False, "message": "No changes to update."}
    base = (DM_COMPANY_UPDATE_PATH_PREFIX or "api/dm/company/update-company-by-id").strip().lstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict):
            if payload_resp.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload_resp, "Update company failed.")}
            data = payload_resp.get("data") if isinstance(payload_resp.get("data"), dict) else payload_resp
            return {
                "success": True,
                "message": str(payload_resp.get("message") or payload_resp.get("msg") or "Company updated successfully."),
                "data": data,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update company failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_dm_company(
    company_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE dm ``delete-company-by-id/{id}`` (prefix :data:`DM_COMPANY_DELETE_PATH_PREFIX`)."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(company_id)
    if not seg:
        return {"success": False, "message": "Company is required."}
    base = (DM_COMPANY_DELETE_PATH_PREFIX or "api/dm/company/delete-company-by-id").strip().lstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Delete company failed.")}
            return {"success": True, "message": str(payload.get("message") or payload.get("msg") or "Company deleted successfully.")}
        return {"success": True, "message": "Company deleted successfully."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete company failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _normalize_lead_comment_rows(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    src: Any = payload
    if isinstance(payload, dict):
        for key in ("data", "comments", "result", "items", "records", "content"):
            cand = payload.get(key)
            if isinstance(cand, list):
                src = cand
                break
        else:
            src = [payload]
    if not isinstance(src, list):
        return rows
    for item in src:
        if isinstance(item, dict):
            cid = (
                item.get("commentId")
                or item.get("id")
                or item.get("leadCommentId")
                or item.get("lead_comment_id")
            )
            rows.append(
                {
                    "commentId": cid,
                    "commentByUsername": str(
                        item.get("commentByUsername")
                        or item.get("commentBy")
                        or item.get("username")
                        or ""
                    ).strip(),
                    "commentOnDate": str(item.get("commentOnDate") or item.get("createdAt") or "").strip(),
                    "comment": str(item.get("comment") or item.get("commentText") or "").strip(),
                    "createdAt": str(item.get("createdAt") or "").strip(),
                    "createdBy": str(item.get("createdBy") or "").strip(),
                    "modifiedAt": str(item.get("modifiedAt") or "").strip(),
                    "modifiedBy": str(item.get("modifiedBy") or "").strip(),
                    "raw": item,
                }
            )
        elif item is not None:
            rows.append(
                {
                    "commentId": None,
                    "commentByUsername": "",
                    "commentOnDate": "",
                    "comment": str(item).strip(),
                    "createdAt": "",
                    "createdBy": "",
                    "modifiedAt": "",
                    "modifiedBy": "",
                    "raw": item,
                }
            )
    return rows


def api_get_lead_comments_by_lead_id(lead_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "comments": []}
    seg = _api_path_id_segment(lead_id)
    if not seg:
        return {"success": False, "message": "Lead ID is required.", "comments": []}
    url = _api_url(f"{LEAD_MGMT_COMMENT_GET_BY_LEAD_ID_PREFIX}/{seg}")
    headers = {"Accept": "application/json", "User-Agent": "MY-ETLZONE-App/1.0", "Authorization": f"Bearer {tk}"}
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, dict) and payload.get("success") is False:
            return {
                "success": False,
                "comments": [],
                "message": _extract_error_message(payload, "Failed to load lead comments."),
            }
        return {
            "success": True,
            "comments": _normalize_lead_comment_rows(payload),
            "message": str(payload.get("message") or "") if isinstance(payload, dict) else "",
        }
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "comments": [],
            "message": _extract_error_message(
                err_payload, f"Failed to load lead comments ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "comments": [], "message": "Backend not reachable."}


def api_get_all_lead_comments_by_lead_id(lead_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """Backward-compatible alias used by UI pages."""
    return api_get_lead_comments_by_lead_id(lead_id, token=token)


def api_get_lead_contact_persons_by_lead_id(lead_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    seg = _api_path_id_segment(lead_id)
    if not seg:
        return {"success": False, "message": "Lead ID is required.", "data": []}
    url = _api_url(f"{LEAD_MGMT_LEAD_CONTACT_PERSON_BY_LEAD_ID_PREFIX}/{seg}")
    headers = {"Accept": "application/json", "User-Agent": "MY-ETLZONE-App/1.0", "Authorization": f"Bearer {tk}"}
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        rows: list[Any] = []
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {
                    "success": False,
                    "data": [],
                    "message": _extract_error_message(payload, "Failed to load lead contact persons."),
                }
            data = payload.get("data")
            if isinstance(data, list):
                rows = data
            elif isinstance(data, dict):
                rows = [data]
            elif isinstance(payload.get("result"), list):
                rows = payload.get("result") or []
        elif isinstance(payload, list):
            rows = payload
        return {"success": True, "data": rows, "message": str((payload or {}).get("message") if isinstance(payload, dict) else "")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "data": [],
            "message": _extract_error_message(
                err_payload, f"Failed to load lead contact persons ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "data": [], "message": "Backend not reachable."}


def api_add_lead_comment(lead_id: int | str, payload: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(lead_id)
    if not seg:
        return {"success": False, "message": "Lead ID is required."}
    body = {k: v for k, v in (payload or {}).items() if v is not None and str(v).strip() != ""}
    url = _api_url(f"{LEAD_MGMT_COMMENT_ADD_BY_LEAD_ID_PREFIX}/{seg}")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict) and payload_resp.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload_resp, "Add lead comment failed.")}
        return {"success": True, "message": str((payload_resp or {}).get("message") or "Lead comment added.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Add lead comment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_lead_comment_by_id(comment_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(comment_id)
    if not seg:
        return {"success": False, "message": "Comment ID is required."}
    url = _api_url(f"{LEAD_MGMT_COMMENT_DELETE_BY_ID_PREFIX}/{seg}")
    headers = {"Accept": "application/json", "User-Agent": "MY-ETLZONE-App/1.0", "Authorization": f"Bearer {tk}"}
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict) and payload_resp.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload_resp, "Delete lead comment failed.")}
        return {"success": True, "message": str((payload_resp or {}).get("message") or "Lead comment deleted.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete lead comment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_lead_comment_by_id(
    comment_id: int | str, payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(comment_id)
    if not seg:
        return {"success": False, "message": "Comment ID is required."}
    body = {k: v for k, v in (payload or {}).items() if v is not None and str(v).strip() != ""}
    if not body:
        return {"success": False, "message": "No changes to update."}
    url = _api_url(f"{LEAD_MGMT_COMMENT_UPDATE_BY_ID_PREFIX}/{seg}")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict) and payload_resp.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload_resp, "Update lead comment failed.")}
        return {"success": True, "message": str((payload_resp or {}).get("message") or "Lead comment updated.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update lead comment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_leads(*, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(LEAD_MGMT_LEAD_GET_ALL_PATH)
    headers = {"Accept": "application/json", "User-Agent": "MY-ETLZONE-App/1.0", "Authorization": f"Bearer {tk}"}
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Failed to load leads.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Failed to load leads ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_lead(payload: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    body = {k: v for k, v in (payload or {}).items() if v is not None and str(v).strip() != ""}
    url = _api_url(LEAD_MGMT_LEAD_CREATE_PATH)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict) and payload_resp.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload_resp, "Create lead failed.")}
        return {"success": True, "message": str((payload_resp or {}).get("message") or "Lead created successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Create lead failed ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_lead(lead_id: int | str, payload: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(lead_id)
    if not seg:
        return {"success": False, "message": "Lead ID is required."}
    body = {k: v for k, v in (payload or {}).items() if v is not None and str(v).strip() != ""}
    if not body:
        return {"success": False, "message": "No changes to update."}
    url = _api_url(f"{LEAD_MGMT_LEAD_UPDATE_BY_ID_PREFIX}/{seg}")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict) and payload_resp.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload_resp, "Update lead failed.")}
        return {"success": True, "message": str((payload_resp or {}).get("message") or "Lead updated successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Update lead failed ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_lead(lead_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(lead_id)
    if not seg:
        return {"success": False, "message": "Lead ID is required."}
    url = _api_url(f"{LEAD_MGMT_LEAD_DELETE_BY_ID_PREFIX}/{seg}")
    headers = {"Accept": "application/json", "User-Agent": "MY-ETLZONE-App/1.0", "Authorization": f"Bearer {tk}"}
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload, "Delete lead failed.")}
        return {"success": True, "message": str((payload or {}).get("message") or "Lead deleted successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Delete lead failed ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_contact_persons(*, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(LEAD_MGMT_CONTACT_PERSON_GET_ALL_PATH)
    headers = {"Accept": "application/json", "User-Agent": "MY-ETLZONE-App/1.0", "Authorization": f"Bearer {tk}"}
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Failed to load contact persons.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Failed to load contact persons ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _lead_mgmt_contact_person_request_body(payload: dict[str, Any]) -> dict[str, Any]:
    """JSON body for lead-mgmt contact person create/update (curl-aligned keys)."""
    body: dict[str, Any] = {}
    for k, v in (payload or {}).items():
        if v is None:
            continue
        if isinstance(v, bool):
            body[k] = v
            continue
        if isinstance(v, int):
            body[k] = v
            continue
        if isinstance(v, float) and v == int(v):
            body[k] = int(v)
            continue
        if isinstance(v, str):
            s = v.strip()
            if not s:
                continue
            if k == "hierarchy" and s.isdigit():
                body[k] = int(s)
            else:
                body[k] = s
            continue
        s = str(v).strip()
        if not s:
            continue
        if k == "hierarchy" and s.isdigit():
            body[k] = int(s)
        else:
            body[k] = s
    return body


def api_create_contact_person(payload: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    if not str((payload or {}).get("name") or "").strip():
        return {"success": False, "message": "Contact Person Name is required."}
    body = _lead_mgmt_contact_person_request_body(payload or {})
    url = _api_url(LEAD_MGMT_CONTACT_PERSON_CREATE_PATH)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict) and payload_resp.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload_resp, "Create contact person failed.")}
        return {"success": True, "message": str((payload_resp or {}).get("message") or "Contact person created successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Create contact person failed ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_contact_person(contact_person_id: int | str, payload: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(contact_person_id)
    if not seg:
        return {"success": False, "message": "Contact Person is required."}
    body = _lead_mgmt_contact_person_request_body(payload or {})
    if not body:
        return {"success": False, "message": "No changes to update."}
    base = LEAD_MGMT_CONTACT_PERSON_UPDATE_PATH_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict) and payload_resp.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload_resp, "Update contact person failed.")}
        return {"success": True, "message": str((payload_resp or {}).get("message") or "Contact person updated successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Update contact person failed ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_contact_person(contact_person_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(contact_person_id)
    if not seg:
        return {"success": False, "message": "Contact Person is required."}
    base = LEAD_MGMT_CONTACT_PERSON_DELETE_PATH_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers = {"Accept": "application/json", "User-Agent": "MY-ETLZONE-App/1.0", "Authorization": f"Bearer {tk}"}
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload, "Delete contact person failed.")}
        return {"success": True, "message": str((payload or {}).get("message") or "Contact person deleted successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Delete contact person failed ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_dm_contact_persons(*, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(DM_CONTACT_PERSON_GET_ALL_PATH)
    headers = {"Accept": "application/json", "User-Agent": "MY-ETLZONE-App/1.0", "Authorization": f"Bearer {tk}"}
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Failed to load contact persons.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Failed to load contact persons ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_dm_contact_person(payload: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    if not str((payload or {}).get("name") or "").strip():
        return {"success": False, "message": "Contact Person Name is required."}
    body = _lead_mgmt_contact_person_request_body(payload or {})
    url = _api_url(DM_CONTACT_PERSON_CREATE_PATH)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict) and payload_resp.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload_resp, "Create contact person failed.")}
        return {"success": True, "message": str((payload_resp or {}).get("message") or "Contact person created successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Create contact person failed ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_dm_contact_person(
    contact_person_id: int | str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(contact_person_id)
    if not seg:
        return {"success": False, "message": "Contact Person is required."}
    body = _lead_mgmt_contact_person_request_body(payload or {})
    if not body:
        return {"success": False, "message": "No changes to update."}
    base = DM_CONTACT_PERSON_UPDATE_PATH_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict) and payload_resp.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload_resp, "Update contact person failed.")}
        return {"success": True, "message": str((payload_resp or {}).get("message") or "Contact person updated successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Update contact person failed ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_dm_contact_person(contact_person_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(contact_person_id)
    if not seg:
        return {"success": False, "message": "Contact Person is required."}
    base = DM_CONTACT_PERSON_DELETE_PATH_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers = {"Accept": "application/json", "User-Agent": "MY-ETLZONE-App/1.0", "Authorization": f"Bearer {tk}"}
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload, "Delete contact person failed.")}
        return {"success": True, "message": str((payload or {}).get("message") or "Contact person deleted successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Delete contact person failed ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_contact_person_company_assignments(*, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/contact-person-company-assignment/all")
    headers = {"Accept": "application/json", "User-Agent": "MY-ETLZONE-App/1.0", "Authorization": f"Bearer {tk}"}
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {"success": False, "message": _extract_error_message(payload, "Failed to load assignments.")}
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Failed to load assignments ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_contact_person_company_assignment(payload: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    company_id = (payload or {}).get("companyId")
    contact_id = (payload or {}).get("contactPersonId")
    status = (payload or {}).get("status")
    if company_id is None or contact_id is None:
        return {"success": False, "message": "Contact Person and Company are required."}
    if status is None or str(status).strip() == "":
        return {"success": False, "message": "Status is required."}
    params = urlencode(
        {
            "companyId": str(company_id).strip(),
            "contactIds": str(contact_id).strip(),
            "status": str(status).strip(),
        }
    )
    url = _api_url(f"api/lead-mgmt/company-contact/assign?{params}")
    headers = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict) and payload_resp.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload_resp, "Create assignment failed.")}
        return {"success": True, "message": str((payload_resp or {}).get("message") or "Assignment created successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Create assignment failed ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_contact_person_company_assignment(assignment_id: int | str, payload: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(assignment_id)
    if not seg:
        return {"success": False, "message": "Assignment ID is required."}
    status_val = (payload or {}).get("status")
    if status_val is None or str(status_val).strip() == "":
        return {"success": False, "message": "Status is required for update."}
    query = urlencode({"status": str(status_val).strip()})
    url = _api_url(f"api/lead-mgmt/company-contact/update-status-by-id/{seg}?{query}")
    headers = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict) and payload_resp.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload_resp, "Update assignment failed.")}
        return {"success": True, "message": str((payload_resp or {}).get("message") or "Assignment updated successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Update assignment failed ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_contact_person_company_assignment(assignment_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(assignment_id)
    if not seg:
        return {"success": False, "message": "Assignment ID is required."}
    url = _api_url(f"api/lead-mgmt/company-contact/delete-by-id/{seg}")
    headers = {"Accept": "application/json", "User-Agent": "MY-ETLZONE-App/1.0", "Authorization": f"Bearer {tk}"}
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload, "Delete assignment failed.")}
        return {"success": True, "message": str((payload or {}).get("message") or "Assignment deleted successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {"success": False, "message": _extract_error_message(err_payload, f"Delete assignment failed ({getattr(exc, 'code', 'HTTP error')}).")}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_dm_contact_person_company_assignment(
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    company_id = (payload or {}).get("companyId")
    contact_id = (payload or {}).get("contactPersonId")
    status = (payload or {}).get("status")
    if company_id is None or contact_id is None:
        return {"success": False, "message": "Contact Person and Company are required."}
    if status is None or str(status).strip() == "":
        return {"success": False, "message": "Status is required."}
    params = urlencode(
        {
            "companyId": str(company_id).strip(),
            "contactIds": str(contact_id).strip(),
            "status": str(status).strip(),
        }
    )
    base = (DM_COMPANY_CONTACT_ASSIGN_PATH or "api/dm/company-contact/assign").strip().lstrip("/")
    url = _api_url(f"{base}?{params}")
    headers = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict) and payload_resp.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload_resp, "Create assignment failed.")}
        return {"success": True, "message": str((payload_resp or {}).get("message") or "Assignment created successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create assignment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_dm_contact_person_company_assignment(
    assignment_id: int | str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(assignment_id)
    if not seg:
        return {"success": False, "message": "Assignment ID is required."}
    status_val = (payload or {}).get("status")
    if status_val is None or str(status_val).strip() == "":
        return {"success": False, "message": "Status is required for update."}
    query = urlencode({"status": str(status_val).strip()})
    base = (
        DM_COMPANY_CONTACT_UPDATE_STATUS_PATH_PREFIX or "api/dm/company-contact/update-status-by-id"
    ).strip().lstrip("/").rstrip("/")
    url = _api_url(f"{base}/{seg}?{query}")
    headers = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload_resp = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload_resp, dict) and payload_resp.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload_resp, "Update assignment failed.")}
        return {"success": True, "message": str((payload_resp or {}).get("message") or "Assignment updated successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update assignment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_dm_contact_person_company_assignment(
    assignment_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(assignment_id)
    if not seg:
        return {"success": False, "message": "Assignment ID is required."}
    base = (DM_COMPANY_CONTACT_DELETE_PATH_PREFIX or "api/dm/company-contact/delete-by-id").strip().lstrip("/").rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers = {"Accept": "application/json", "User-Agent": "MY-ETLZONE-App/1.0", "Authorization": f"Bearer {tk}"}
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict) and payload.get("success") is False:
            return {"success": False, "message": _extract_error_message(payload, "Delete assignment failed.")}
        return {"success": True, "message": str((payload or {}).get("message") or "Assignment deleted successfully.")}
    except HTTPError as exc:
        try:
            err_payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete assignment failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_object_trackers(*, token: str | None = None) -> dict[str, Any]:
    """GET ``DMT_OBJECT_TRACKER_GET_ALL_PATH``. Returns {'success': bool, 'data': list, 'message': str}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(DMT_OBJECT_TRACKER_GET_ALL_PATH.strip().lstrip("/"))
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to load object tracker records."),
                }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load object tracker records ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_object_tracker(
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST ``DMT_OBJECT_TRACKER_CREATE_PATH`` with JSON payload."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(DMT_OBJECT_TRACKER_CREATE_PATH.strip().lstrip("/"))
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    body = dict(payload or {})
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        response_payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(response_payload, dict):
            if response_payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(response_payload, "Create object tracker failed."),
                }
            data = response_payload.get("data")
            return {
                "success": True,
                "message": str(
                    response_payload.get("message")
                    or response_payload.get("msg")
                    or "Object tracker record created successfully."
                ),
                "data": data if isinstance(data, dict) else response_payload,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create object tracker failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_object_tracker(
    tracker_id: int | str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT ``{DMT_OBJECT_TRACKER_UPDATE_BY_ID_PREFIX}/{id}`` with JSON payload."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(tracker_id)
    if not seg:
        return {"success": False, "message": "Object tracker ID is required."}
    base = DMT_OBJECT_TRACKER_UPDATE_BY_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    body = dict(payload or {})
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        response_payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(response_payload, dict):
            if response_payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(response_payload, "Update object tracker failed."),
                }
            data = response_payload.get("data")
            return {
                "success": True,
                "message": str(
                    response_payload.get("message")
                    or response_payload.get("msg")
                    or "Object tracker record updated successfully."
                ),
                "data": data if isinstance(data, dict) else response_payload,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update object tracker failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_object_tracker(
    tracker_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE ``{DMT_OBJECT_TRACKER_DELETE_BY_ID_PREFIX}/{id}``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(tracker_id)
    if not seg:
        return {"success": False, "message": "Object tracker ID is required."}
    base = DMT_OBJECT_TRACKER_DELETE_BY_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete object tracker failed."),
                }
            return {
                "success": True,
                "message": str(payload.get("message") or payload.get("msg") or "Object tracker record deleted."),
            }
        return {"success": True, "message": "Object tracker record deleted."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete object tracker failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_all_issue_trackers(*, token: str | None = None) -> dict[str, Any]:
    """GET ``DMT_ISSUE_TRACKER_GET_ALL_PATH``. Returns {'success': bool, 'data': list, 'message': str}."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(DMT_ISSUE_TRACKER_GET_ALL_PATH.strip().lstrip("/"))
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, headers=headers, method="GET")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else []
        if isinstance(payload, list):
            return {"success": True, "data": payload, "message": ""}
        if isinstance(payload, dict):
            rows = payload.get("data")
            if isinstance(rows, list):
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to load issue tracker records."),
                }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load issue tracker records ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_issue_tracker(
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST ``DMT_ISSUE_TRACKER_CREATE_PATH`` with JSON payload."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(DMT_ISSUE_TRACKER_CREATE_PATH.strip().lstrip("/"))
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    body = dict(payload or {})
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        response_payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(response_payload, dict):
            if response_payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(response_payload, "Create issue tracker failed."),
                }
            data = response_payload.get("data")
            return {
                "success": True,
                "message": str(
                    response_payload.get("message")
                    or response_payload.get("msg")
                    or "Issue tracker record created successfully."
                ),
                "data": data if isinstance(data, dict) else response_payload,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create issue tracker failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_issue_tracker(
    issue_id: int | str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT ``{DMT_ISSUE_TRACKER_UPDATE_BY_ID_PREFIX}/{id}`` with JSON payload."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(issue_id)
    if not seg:
        return {"success": False, "message": "Issue tracker ID is required."}
    base = DMT_ISSUE_TRACKER_UPDATE_BY_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    body = dict(payload or {})
    try:
        req = Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="PUT")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        response_payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(response_payload, dict):
            if response_payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(response_payload, "Update issue tracker failed."),
                }
            data = response_payload.get("data")
            return {
                "success": True,
                "message": str(
                    response_payload.get("message")
                    or response_payload.get("msg")
                    or "Issue tracker record updated successfully."
                ),
                "data": data if isinstance(data, dict) else response_payload,
            }
        return {"success": False, "message": "Unexpected response."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update issue tracker failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_issue_tracker(
    issue_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE ``{DMT_ISSUE_TRACKER_DELETE_BY_ID_PREFIX}/{id}``."""
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(issue_id)
    if not seg:
        return {"success": False, "message": "Issue tracker ID is required."}
    base = DMT_ISSUE_TRACKER_DELETE_BY_ID_PREFIX.strip().rstrip("/")
    url = _api_url(f"{base}/{seg}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="DELETE")
        with _http_urlopen_logged(req, timeout=10.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Delete issue tracker failed."),
                }
            return {
                "success": True,
                "message": str(payload.get("message") or payload.get("msg") or "Issue tracker record deleted."),
            }
        return {"success": True, "message": "Issue tracker record deleted."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete issue tracker failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _connections_auth_headers(token: str | None) -> dict[str, str] | None:
    if not token or not str(token).strip():
        return None
    return {"Authorization": f"Bearer {token}"}


def api_create_import(
    name: str,
    source_type: str,
    *,
    encoding: str | None = None,
    token: str | None = None,
) -> dict[str, Any]:
    """POST create an import job (default: ``imports``).

    Body: ``name``, ``sourceType`` (e.g. EXCEL, CSV, JSON), optional ``encoding``
    (e.g. ``UTF_8``).
    """
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    body: dict[str, Any] = {
        "name": (name or "").strip(),
        "sourceType": (source_type or "").strip().upper(),
    }
    enc = str(encoding or "").strip()
    if enc:
        body["encoding"] = enc.upper().replace("-", "_").replace(" ", "_")
    if not body["name"]:
        return {"success": False, "message": "Name is required."}
    if not body["sourceType"]:
        return {"success": False, "message": "Type is required."}
    url = _api_url(IMPORTS_CREATE_PATH)
    try:
        payload = _http_post_json(url, body, timeout_s=15.0, extra_headers=headers)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to create import."
            )
            if rej is not None:
                return rej
            # Backend may return {sessionId, state, sessionName} with no success flag.
            has_session = any(
                payload.get(k) is not None and str(payload.get(k)).strip()
                for k in (
                    "sessionId",
                    "sessionID",
                    "session_id",
                    "importSessionId",
                    "importId",
                    "uuid",
                    "id",
                )
            )
            ok = (
                payload.get("success") is True
                or str(payload.get("status") or "").strip().upper() == "SUCCESS"
                or has_session
            )
            if ok or payload == {}:
                return {
                    "success": True,
                    "message": payload.get("message")
                    or payload.get("msg")
                    or "Import created.",
                    "data": payload,
                }
            # Some backends return the created entity without a success flag.
            if (
                payload.get("name") is not None
                or payload.get("sessionName") is not None
                or payload.get("sourceType") is not None
            ):
                return {
                    "success": True,
                    "message": payload.get("message")
                    or payload.get("msg")
                    or "Import created.",
                    "data": payload,
                }
        return {
            "success": False,
            "message": _extract_error_message(payload, "Failed to create import."),
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Import failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _parse_import_sessions(payload: Any) -> list[dict[str, Any]]:
    """Normalize get-all-sessionId responses into session row dicts.

    Always includes ``sessionId`` / ``sessionName``. When the API returns richer
    objects, also copies common activity-dashboard fields (state, sourceType, …).
    """
    raw: Any = payload
    if isinstance(payload, dict):
        for key in (
            "data",
            "sessionIds",
            "sessionIdList",
            "session_ids",
            "result",
            "content",
        ):
            if key in payload and payload.get(key) is not None:
                raw = payload.get(key)
                break

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    def _add(row: dict[str, Any]) -> None:
        sid = str(row.get("sessionId") or "").strip()
        name = str(row.get("sessionName") or "").strip()
        if not sid and not name:
            return
        key = sid or name
        if key in seen:
            return
        seen.add(key)
        row["sessionId"] = sid or name
        row["sessionName"] = name or sid
        out.append(row)

    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                sid = None
                for key in ("sessionId", "sessionID", "session_id", "uuid", "id"):
                    if key in item and item.get(key) is not None:
                        sid = item.get(key)
                        break
                name = None
                for key in ("sessionName", "session_name", "importName", "name"):
                    if key in item and item.get(key) is not None:
                        name = item.get(key)
                        break
                if sid is None and name is None and len(item) == 1:
                    only = next(iter(item.values()))
                    _add({"sessionId": only, "sessionName": only})
                    continue
                row: dict[str, Any] = {
                    "sessionId": sid,
                    "sessionName": name,
                    "_raw": item,
                }
                for src, dst in (
                    ("state", "state"),
                    ("status", "status"),
                    ("sourceType", "sourceType"),
                    ("fileType", "sourceType"),
                    ("encoding", "encoding"),
                    ("operation", "operation"),
                    ("targetTableName", "targetTableName"),
                    ("tableName", "targetTableName"),
                    ("target_table_name", "targetTableName"),
                    ("fileName", "fileName"),
                    ("executionDate", "executionDate"),
                    ("executedAt", "executionDate"),
                    ("completedAt", "executionDate"),
                    ("updatedAt", "executionDate"),
                    ("createdAt", "executionDate"),
                    ("duration", "duration"),
                    ("durationMs", "duration"),
                    ("rowsProcessed", "rowsProcessed"),
                    ("totalRows", "rowsProcessed"),
                    ("successfulRows", "rowsProcessed"),
                    ("rowsFailed", "rowsFailed"),
                    ("failedRows", "rowsFailed"),
                    ("failCount", "rowsFailed"),
                    ("executedBy", "executedBy"),
                    ("createdBy", "executedBy"),
                    ("username", "executedBy"),
                    ("userName", "executedBy"),
                ):
                    if item.get(src) is not None and str(item.get(src)).strip():
                        row.setdefault(dst, item.get(src))
                _add(row)
            else:
                _add({"sessionId": item, "sessionName": item})
    elif isinstance(raw, (str, int, float)):
        _add({"sessionId": raw, "sessionName": raw})
    return out


def api_get_all_import_session_ids(token: str | None = None) -> dict[str, Any]:
    """GET import sessions (default: ``imports/get-all-sessionId``).

    Uses the same Bearer token pattern as :func:`api_get_all_connections`.
    Returns ``data`` as a list of ``{sessionId, sessionName}`` dicts.
    """
    headers = _connections_auth_headers(token)
    if headers is None:
        return {
            "success": False,
            "message": "Session expired. Please log in again.",
            "data": [],
        }
    url = _api_url(IMPORTS_GET_ALL_SESSION_ID_PATH)
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=15.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load session IDs.", data=[]
            )
            if rej is not None:
                return rej
        sessions = _parse_import_sessions(payload)
        return {
            "success": True,
            "message": "Session IDs loaded.",
            "data": sessions,
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load session IDs ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {
            "success": False,
            "message": "Backend not reachable.",
            "data": [],
        }


def api_upload_import_file(
    session_id: str,
    file_path: str,
    *,
    token: str | None = None,
    field_name: str = "file",
    codepage: str | None = None,
    multi_language: bool = False,
) -> dict[str, Any]:
    """POST multipart file to ``imports/{sessionId}/upload``.

    Optional ``codepage`` / ``multi_language`` are sent as multipart form fields so the
    backend can preserve non-ASCII sheet and column names.
    """
    tk = _normalize_bearer_token(token)
    if not tk:
        return {"success": False, "message": "Session expired. Please log in again."}
    sid = str(session_id or "").strip()
    if not sid:
        return {"success": False, "message": "Select a session before uploading."}
    path = Path(file_path)
    if not path.is_file():
        return {"success": False, "message": "Select a file to upload."}
    extra: dict[str, str] = {}
    cp = str(codepage or "").strip()
    if cp:
        extra["codePage"] = cp
        extra["codepage"] = cp
        extra["encoding"] = cp
    if multi_language:
        extra["multiLanguage"] = "true"
        extra["enableMultiLanguage"] = "true"
        extra["unicode"] = "true"
    try:
        body, boundary = _multipart_file_body(
            field_name=field_name,
            file_path=str(path),
            extra_fields=extra or None,
        )
    except OSError as exc:
        return {"success": False, "message": f"Could not read file: {exc}"}
    url = _api_url(f"{IMPORTS_UPLOAD_PATH_PREFIX}/{quote(sid, safe='')}/upload")
    headers: dict[str, str] = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {tk}",
    }
    try:
        req = Request(url, data=body, headers=headers, method="POST")
        with _http_urlopen_logged(req, timeout=120.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Upload failed."
            )
            if rej is not None:
                rej["data"] = payload
                return rej
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Upload failed."),
                    "data": payload,
                }
            status = str(payload.get("status") or "").strip().upper()
            ok = (
                payload.get("success") is True
                or status == "SUCCESS"
                or "sessionId" in payload
            )
            if ok:
                return {
                    "success": True,
                    "message": str(
                        payload.get("message")
                        or payload.get("msg")
                        or "File uploaded successfully."
                    ),
                    "data": payload.get("data", payload),
                    "status": status or "SUCCESS",
                }
            return {
                "success": False,
                "message": _extract_error_message(payload, "Upload failed."),
                "data": payload,
            }
        return {
            "success": True,
            "message": "File uploaded successfully.",
            "data": payload,
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Upload failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": err_payload if isinstance(err_payload, dict) else None,
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in row and row.get(key) is not None:
            return row.get(key)
    return None


def _normalize_analyze_column(row: dict[str, Any], ordinal_fallback: int) -> dict[str, Any]:
    name = _first_present(row, "name", "columnName", "column_name", "srcColumnName", "sourceName")
    datatype = _first_present(row, "datatype", "dataType", "data_type", "type", "srcDatatype")
    nullable = _first_present(row, "nullable", "isNullable", "nullAble")
    ordinal = _first_present(row, "ordinal", "ordinalPosition", "position", "index", "seq")
    tgt_name = _first_present(
        row,
        "tgtColumnName",
        "targetColumnName",
        "tgt_column_name",
        "targetName",
        "mappedColumnName",
    )
    tgt_type = _first_present(
        row,
        "tgtDatatype",
        "targetDatatype",
        "tgtDataType",
        "targetDataType",
        "mappedDatatype",
    )
    length = _first_present(row, "length", "maxLength", "size", "charLength")
    decimal_val = _first_present(row, "decimal", "scale", "decimalScale")
    precision = _first_present(row, "precision", "pricision", "numericPrecision")
    source_column_id = _first_present(
        row,
        "sourceColumnId",
        "source_column_id",
        "columnId",
        "column_id",
        "fieldId",
        "id",
    )
    primary_key = _first_present(
        row,
        "primaryKey",
        "isPrimaryKey",
        "primary_key",
        "pk",
        "isPk",
    )
    selected = _first_present(row, "selected", "isSelected", "include", "mapped")

    if nullable is None:
        nullable_text = ""
        nullable_bool = True
    elif isinstance(nullable, bool):
        nullable_text = "TRUE" if nullable else "FALSE"
        nullable_bool = nullable
    else:
        text = str(nullable).strip()
        low = text.lower()
        if low in ("1", "true", "yes", "y"):
            nullable_text = "TRUE"
            nullable_bool = True
        elif low in ("0", "false", "no", "n"):
            nullable_text = "FALSE"
            nullable_bool = False
        else:
            nullable_text = text.upper()
            nullable_bool = True

    if isinstance(primary_key, bool):
        primary_key_bool = primary_key
    elif primary_key is None:
        primary_key_bool = False
    else:
        primary_key_bool = str(primary_key).strip().lower() in ("1", "true", "yes", "y")

    if isinstance(selected, bool):
        selected_bool = selected
    elif selected is None:
        selected_bool = True
    else:
        selected_bool = str(selected).strip().lower() not in ("0", "false", "no", "n")

    name_text = "" if name is None else str(name).strip()
    tgt_name_text = "" if tgt_name is None else str(tgt_name).strip()
    if not tgt_name_text:
        tgt_name_text = name_text.lstrip("#").strip() if name_text else ""

    try:
        ordinal_num = int(ordinal) if ordinal is not None and str(ordinal).strip() != "" else ordinal_fallback
    except (TypeError, ValueError):
        ordinal_num = ordinal_fallback

    return {
        "name": name_text,
        "datatype": "" if datatype is None else str(datatype).strip(),
        "nullable": nullable_text,
        "nullableBool": nullable_bool,
        "ordinal": ordinal_num,
        "tgtColumnName": tgt_name_text,
        "tgtDatatype": "" if tgt_type is None else str(tgt_type).strip(),
        "length": "255" if length is None or str(length).strip() == "" else str(length).strip(),
        "decimal": "" if decimal_val is None else str(decimal_val).strip(),
        "precision": "" if precision is None else str(precision).strip(),
        "sourceColumnId": source_column_id,
        "primaryKey": primary_key_bool,
        "selected": selected_bool,
        "_raw": row,
    }


def _normalize_analyze_columns(raw_columns: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_columns, list):
        return []
    out: list[dict[str, Any]] = []
    for i, item in enumerate(raw_columns, start=1):
        if isinstance(item, dict):
            out.append(_normalize_analyze_column(item, i))
        elif item is not None:
            text = str(item).strip()
            if text:
                out.append(
                    _normalize_analyze_column(
                        {"name": text, "tgtColumnName": text, "ordinal": i},
                        i,
                    )
                )
    return out


def _normalize_import_connection_id(value: Any) -> Any:
    """Resolve connection id from a scalar or nested connection object."""
    if isinstance(value, dict):
        return _first_present(value, "id", "connectionId", "connectionID", "connection_id")
    return value


def _extract_import_target_meta(
    payload: Any,
    sheets: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Pull ``targetTableName`` / ``targetConnectionId`` from analyze payloads.

    Backend ``analyze-if-present`` shape:
    - ``connectionId``: full connection object (``{ id, connectionName, ... }``)
    - sheet ``tableName``: target table for that sheet (may be null)
    """
    table_name: Any = None
    connection_id: Any = None

    def _from_mapping(row: dict[str, Any], *, allow_table_name_alias: bool = False) -> None:
        nonlocal table_name, connection_id
        if table_name is None or str(table_name).strip() == "":
            keys = [
                "targetTableName",
                "target_table_name",
                "tgtTableName",
                "tgt_table_name",
                "targetTable",
            ]
            if allow_table_name_alias:
                keys.append("tableName")
            found = _first_present(row, *keys)
            if found is not None and str(found).strip():
                table_name = found
        if connection_id is None or str(connection_id).strip() == "":
            raw_conn = _first_present(
                row,
                "targetConnectionId",
                "target_connection_id",
                "connectionId",
                "connection_id",
                "connectionID",
                "connection",
            )
            connection_id = _normalize_import_connection_id(raw_conn)

    if isinstance(payload, dict):
        # Prefer nested connection object at top level.
        top_conn = payload.get("connectionId") or payload.get("connection")
        if isinstance(top_conn, dict):
            connection_id = _normalize_import_connection_id(top_conn)
        _from_mapping(payload, allow_table_name_alias=False)
        for key in ("data", "result", "payload", "content", "analyzeResult", "analysis"):
            nested = payload.get(key)
            if isinstance(nested, dict):
                nested_conn = nested.get("connectionId") or nested.get("connection")
                if connection_id is None and isinstance(nested_conn, dict):
                    connection_id = _normalize_import_connection_id(nested_conn)
                _from_mapping(nested, allow_table_name_alias=False)

    for sheet in sheets or []:
        if not isinstance(sheet, dict):
            continue
        # Sheet target table is ``tableName`` in analyze-if-present.
        _from_mapping(sheet, allow_table_name_alias=True)
        raw = sheet.get("_raw")
        if isinstance(raw, dict):
            _from_mapping(raw, allow_table_name_alias=True)

    out: dict[str, Any] = {}
    if table_name is not None and str(table_name).strip():
        out["targetTableName"] = str(table_name).strip()
    connection_id = _normalize_import_connection_id(connection_id)
    if connection_id is not None and str(connection_id).strip() != "":
        out["targetConnectionId"] = connection_id
    return out


def _parse_import_analyze_payload(payload: Any) -> list[dict[str, Any]]:
    """Normalize analyze response into ``[{name, columns: [...]}, ...]`` sheets."""
    root: Any = payload
    if isinstance(payload, dict):
        for key in ("data", "result", "payload", "content", "analyzeResult", "analysis"):
            if isinstance(payload.get(key), (dict, list)):
                root = payload.get(key)
                break

    sheets: list[dict[str, Any]] = []

    def _add_sheet(name: Any, columns: Any, sheet_meta: dict[str, Any] | None = None) -> None:
        meta = sheet_meta if isinstance(sheet_meta, dict) else {}
        sheet_name = str(name or "").strip() or f"Sheet{len(sheets) + 1}"
        sheet_id = _first_present(meta, "sheetId", "sheet_id", "sheetID", "id")
        target_table = _first_present(
            meta,
            "targetTableName",
            "target_table_name",
            "tgtTableName",
            "tgt_table_name",
            "targetTable",
            "tableName",
        )
        raw_connection = _first_present(
            meta,
            "targetConnectionId",
            "target_connection_id",
            "connectionId",
            "connection_id",
            "connectionID",
            "connection",
        )
        target_connection = _normalize_import_connection_id(raw_connection)
        sheets.append(
            {
                "name": sheet_name,
                "sheetId": sheet_id,
                "targetTableName": (
                    str(target_table).strip()
                    if target_table is not None and str(target_table).strip()
                    else None
                ),
                "targetConnectionId": target_connection,
                "columns": _normalize_analyze_columns(columns),
                "_raw": meta,
            }
        )

    if isinstance(root, list):
        if not root:
            return []
        if all(
            isinstance(x, dict)
            and ("columns" in x or "fields" in x or "sheetName" in x or "name" in x)
            for x in root
        ):
            for item in root:
                if not isinstance(item, dict):
                    continue
                cols = (
                    item.get("columns")
                    or item.get("fields")
                    or item.get("columnList")
                    or item.get("columnMetadata")
                    or []
                )
                _add_sheet(
                    item.get("sheetName")
                    or item.get("name")
                    or item.get("sheet")
                    or item.get("title"),
                    cols,
                    item,
                )
        else:
            # Flat column list → single sheet
            _add_sheet("Sheet1", root)
        return sheets

    if isinstance(root, dict):
        nested_sheets = (
            root.get("sheets")
            or root.get("sheetList")
            or root.get("worksheets")
            or root.get("sheetMetadata")
        )
        if isinstance(nested_sheets, list):
            for item in nested_sheets:
                if not isinstance(item, dict):
                    continue
                cols = (
                    item.get("columns")
                    or item.get("fields")
                    or item.get("columnList")
                    or item.get("columnMetadata")
                    or []
                )
                _add_sheet(
                    item.get("sheetName")
                    or item.get("name")
                    or item.get("sheet")
                    or item.get("title"),
                    cols,
                    item,
                )
            if sheets:
                return sheets

        # Dict keyed by sheet name → column lists
        dict_sheet_candidates = {
            k: v
            for k, v in root.items()
            if isinstance(v, list) and k.lower() not in ("columns", "fields", "data", "errors", "messages")
        }
        if dict_sheet_candidates and all(
            (not v) or isinstance(v[0], (dict, str)) for v in dict_sheet_candidates.values() if isinstance(v, list)
        ):
            for name, cols in dict_sheet_candidates.items():
                _add_sheet(name, cols)
            if sheets:
                return sheets

        cols = root.get("columns") or root.get("fields") or root.get("columnList")
        if isinstance(cols, list):
            _add_sheet(root.get("sheetName") or root.get("name") or "Sheet1", cols, root)
    return sheets


def api_analyze_import_file(
    session_id: str,
    *,
    token: str | None = None,
    codepage: str | None = None,
    multi_language: bool = False,
) -> dict[str, Any]:
    """POST analyze an uploaded import session (default: ``imports/{sessionId}/analyze``).

    When set, ``codepage`` and ``multi_language`` are included in the JSON body so the
    backend can decode multi-language sheet/column names correctly.
    """
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    sid = str(session_id or "").strip()
    if not sid:
        return {"success": False, "message": "Session ID is required.", "data": []}
    url = _api_url(f"{IMPORTS_ANALYZE_PATH_PREFIX}/{quote(sid, safe='')}/analyze")
    body: dict[str, Any] = {}
    cp = str(codepage or "").strip()
    if cp:
        body["codePage"] = cp
        body["codepage"] = cp
        body["encoding"] = cp
    if multi_language:
        body["multiLanguage"] = True
        body["enableMultiLanguage"] = True
        body["unicode"] = True
    try:
        payload = _http_post_json(url, body, timeout_s=120.0, extra_headers=headers)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Analyze failed.", data=[]
            )
            if rej is not None:
                return rej
            status = str(payload.get("status") or "").strip().upper()
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Analyze failed."),
                    "data": [],
                    "raw": payload,
                }
            if status and status not in ("SUCCESS", "OK", "SUCCEEDED", ""):
                # Some backends only set status on failure; keep parsing if sheets exist.
                pass
        sheets = _parse_import_analyze_payload(payload)
        return {
            "success": True,
            "message": "Analyze completed.",
            "data": sheets,
            "raw": payload,
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Analyze failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
            "raw": err_payload if err_payload else None,
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_analyze_import_if_present(
    session_id: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST ``imports/{sessionId}/analyze-if-present``.

    Returns ``present=True`` with sheet data when upload/analyze already exists;
    ``present=False`` when nothing is uploaded yet (normal upload flow continues).
    """
    headers = _connections_auth_headers(token)
    if headers is None:
        return {
            "success": False,
            "present": False,
            "message": "Session expired. Please log in again.",
            "data": [],
        }
    sid = str(session_id or "").strip()
    if not sid:
        return {
            "success": False,
            "present": False,
            "message": "Session ID is required.",
            "data": [],
        }
    url = _api_url(
        f"{IMPORTS_ANALYZE_IF_PRESENT_PATH_PREFIX}/{quote(sid, safe='')}/analyze-if-present"
    )
    try:
        payload = _http_post_json(url, {}, timeout_s=120.0, extra_headers=headers)
        if isinstance(payload, dict):
            # Explicit not-present signals from backend.
            present_flag = payload.get("present")
            if present_flag is False or str(present_flag).strip().lower() in (
                "false",
                "0",
                "no",
            ):
                return {
                    "success": True,
                    "present": False,
                    "message": str(payload.get("message") or "No uploaded file for this session."),
                    "data": [],
                    "raw": payload,
                }
            status = str(payload.get("status") or "").strip().upper()
            msg = str(payload.get("message") or payload.get("msg") or "").strip().lower()
            if payload.get("success") is False:
                # Treat "not found / not present / no file" style failures as empty, not hard errors.
                if any(
                    needle in msg
                    for needle in (
                        "not present",
                        "not found",
                        "no file",
                        "not uploaded",
                        "no upload",
                        "empty",
                    )
                ) or status in ("NOT_FOUND", "NOT_PRESENT", "NO_DATA", "EMPTY"):
                    return {
                        "success": True,
                        "present": False,
                        "message": _extract_error_message(
                            payload, "No uploaded file for this session."
                        ),
                        "data": [],
                        "raw": payload,
                    }
                rej = _reject_json_business_failure(
                    payload, message_fallback="Analyze-if-present failed.", data=[]
                )
                if rej is not None:
                    rej["present"] = False
                    return rej
        sheets = _parse_import_analyze_payload(payload)
        # Require at least one sheet with columns; empty shells are "not present".
        usable = [
            s
            for s in sheets
            if isinstance(s, dict) and isinstance(s.get("columns"), list) and s.get("columns")
        ]
        if usable:
            meta = _extract_import_target_meta(payload, usable)
            return {
                "success": True,
                "present": True,
                "message": "Existing analysis loaded.",
                "data": usable,
                "targetTableName": meta.get("targetTableName"),
                "targetConnectionId": meta.get("targetConnectionId"),
                "raw": payload,
            }
        return {
            "success": True,
            "present": False,
            "message": "No uploaded file for this session.",
            "data": [],
            "targetTableName": None,
            "targetConnectionId": None,
            "raw": payload,
        }
    except HTTPError as exc:
        code = getattr(exc, "code", None)
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        # 404 / 204-style "nothing uploaded yet" → continue normal upload flow.
        if code in (404, 204, 409):
            return {
                "success": True,
                "present": False,
                "message": _extract_error_message(
                    err_payload, "No uploaded file for this session."
                ),
                "data": [],
                "targetTableName": None,
                "targetConnectionId": None,
                "raw": err_payload if err_payload else None,
            }
        return {
            "success": False,
            "present": False,
            "message": _extract_error_message(
                err_payload,
                f"Analyze-if-present failed ({code or 'HTTP error'}).",
            ),
            "data": [],
            "targetTableName": None,
            "targetConnectionId": None,
            "raw": err_payload if err_payload else None,
        }
    except (URLError, TimeoutError, ValueError):
        return {
            "success": False,
            "present": False,
            "message": "Backend not reachable.",
            "data": [],
            "targetTableName": None,
            "targetConnectionId": None,
        }


def import_target_data_type_to_java(value: Any) -> str:
    """Map SQL / UI datatype labels to Java-style types expected by mapping API."""
    text = str(value or "").strip().upper()
    if not text:
        return "STRING"
    if "(" in text:
        text = text.split("(", 1)[0].strip()
    # Normalize spaced postgres labels.
    text = text.replace("DOUBLE PRECISION", "DOUBLE_PRECISION")
    mapping = {
        "STRING": "STRING",
        "TEXT": "STRING",
        "NTEXT": "STRING",
        "NVARCHAR": "STRING",
        "VARCHAR": "STRING",
        "VARCHAR2": "STRING",
        "NVARCHAR2": "STRING",
        "CHAR": "STRING",
        "NCHAR": "STRING",
        "CLOB": "STRING",
        "INTEGER": "INTEGER",
        "INT": "INTEGER",
        "SMALLINT": "INTEGER",
        "TINYINT": "INTEGER",
        "NUMBER": "DECIMAL",
        "BIGINT": "LONG",
        "LONG": "LONG",
        "DECIMAL": "DECIMAL",
        "NUMERIC": "DECIMAL",
        "FLOAT": "FLOAT",
        "REAL": "FLOAT",
        "BINARY_FLOAT": "FLOAT",
        "DOUBLE": "DOUBLE",
        "DOUBLE_PRECISION": "DOUBLE",
        "BINARY_DOUBLE": "DOUBLE",
        "BOOLEAN": "BOOLEAN",
        "BOOL": "BOOLEAN",
        "BIT": "BOOLEAN",
        "DATE": "DATE",
        "DATETIME": "DATETIME",
        "DATETIME2": "DATETIME",
        "SMALLDATETIME": "DATETIME",
        "TIMESTAMP": "TIMESTAMP",
        "TIMESTAMPTZ": "TIMESTAMP",
    }
    return mapping.get(text, text)


def import_sql_datatypes_for_db(db_type: Any) -> tuple[str, ...]:
    """SQL datatype choices for the selected connection ``dbType``."""
    key = str(db_type or "").strip().upper().replace(" ", "").replace("_", "")
    if key in ("SQLSERVER", "MSSQL", "SQLSERVERVPS"):
        return (
            "NVARCHAR",
            "VARCHAR",
            "CHAR",
            "NCHAR",
            "INT",
            "BIGINT",
            "SMALLINT",
            "TINYINT",
            "DECIMAL",
            "NUMERIC",
            "FLOAT",
            "REAL",
            "BIT",
            "DATE",
            "DATETIME",
            "DATETIME2",
            "SMALLDATETIME",
            "TIME",
            "TEXT",
            "NTEXT",
        )
    if key in ("ORACLE",):
        return (
            "VARCHAR2",
            "NVARCHAR2",
            "CHAR",
            "NCHAR",
            "NUMBER",
            "INTEGER",
            "FLOAT",
            "BINARY_FLOAT",
            "BINARY_DOUBLE",
            "DATE",
            "TIMESTAMP",
            "CLOB",
            "BLOB",
            "RAW",
        )
    if key in ("MYSQL", "MARIADB"):
        return (
            "VARCHAR",
            "CHAR",
            "TEXT",
            "TINYINT",
            "SMALLINT",
            "INT",
            "BIGINT",
            "DECIMAL",
            "FLOAT",
            "DOUBLE",
            "BOOLEAN",
            "DATE",
            "DATETIME",
            "TIMESTAMP",
            "TIME",
            "BLOB",
        )
    if key in ("POSTGRES", "POSTGRESQL", "PG"):
        return (
            "VARCHAR",
            "CHAR",
            "TEXT",
            "SMALLINT",
            "INTEGER",
            "BIGINT",
            "NUMERIC",
            "DECIMAL",
            "REAL",
            "DOUBLE PRECISION",
            "BOOLEAN",
            "DATE",
            "TIMESTAMP",
            "TIMESTAMPTZ",
            "BYTEA",
        )
    # Fallback generic SQL list.
    return (
        "VARCHAR",
        "NVARCHAR",
        "CHAR",
        "INT",
        "BIGINT",
        "DECIMAL",
        "FLOAT",
        "DOUBLE",
        "BOOLEAN",
        "DATE",
        "DATETIME",
        "TIMESTAMP",
        "TEXT",
    )


def import_target_data_type_to_sql(value: Any, db_type: Any = None) -> str:
    """Map Java / mixed datatype labels into SQL types for the selected connection."""
    java = import_target_data_type_to_java(value)
    key = str(db_type or "").strip().upper().replace(" ", "").replace("_", "")
    sql_options = import_sql_datatypes_for_db(db_type)
    raw = str(value or "").strip().upper()
    if "(" in raw:
        raw = raw.split("(", 1)[0].strip()
    if raw in {opt.upper() for opt in sql_options}:
        # Preserve already-valid SQL label casing from options list.
        for opt in sql_options:
            if opt.upper() == raw:
                return opt

    by_db: dict[str, dict[str, str]] = {
        "SQLSERVER": {
            "STRING": "NVARCHAR",
            "INTEGER": "INT",
            "LONG": "BIGINT",
            "DECIMAL": "DECIMAL",
            "FLOAT": "FLOAT",
            "DOUBLE": "FLOAT",
            "BOOLEAN": "BIT",
            "DATE": "DATE",
            "DATETIME": "DATETIME",
            "TIMESTAMP": "DATETIME2",
        },
        "MSSQL": {},
        "ORACLE": {
            "STRING": "VARCHAR2",
            "INTEGER": "NUMBER",
            "LONG": "NUMBER",
            "DECIMAL": "NUMBER",
            "FLOAT": "BINARY_FLOAT",
            "DOUBLE": "BINARY_DOUBLE",
            "BOOLEAN": "NUMBER",
            "DATE": "DATE",
            "DATETIME": "DATE",
            "TIMESTAMP": "TIMESTAMP",
        },
        "MYSQL": {
            "STRING": "VARCHAR",
            "INTEGER": "INT",
            "LONG": "BIGINT",
            "DECIMAL": "DECIMAL",
            "FLOAT": "FLOAT",
            "DOUBLE": "DOUBLE",
            "BOOLEAN": "BOOLEAN",
            "DATE": "DATE",
            "DATETIME": "DATETIME",
            "TIMESTAMP": "TIMESTAMP",
        },
        "MARIADB": {},
        "POSTGRES": {
            "STRING": "VARCHAR",
            "INTEGER": "INTEGER",
            "LONG": "BIGINT",
            "DECIMAL": "NUMERIC",
            "FLOAT": "REAL",
            "DOUBLE": "DOUBLE PRECISION",
            "BOOLEAN": "BOOLEAN",
            "DATE": "DATE",
            "DATETIME": "TIMESTAMP",
            "TIMESTAMP": "TIMESTAMP",
        },
        "POSTGRESQL": {},
        "PG": {},
    }
    # Alias empty maps to primary family maps.
    by_db["MSSQL"] = by_db["SQLSERVER"]
    by_db["SQLSERVERVPS"] = by_db["SQLSERVER"]
    by_db["MARIADB"] = by_db["MYSQL"]
    by_db["POSTGRESQL"] = by_db["POSTGRES"]
    by_db["PG"] = by_db["POSTGRES"]

    family = by_db.get(key) or by_db["SQLSERVER"]
    mapped = family.get(java, "NVARCHAR" if key in ("SQLSERVER", "MSSQL", "SQLSERVERVPS", "") else "VARCHAR")
    # Ensure result is in options; otherwise fall back to first option.
    for opt in sql_options:
        if opt.upper() == mapped.upper():
            return opt
    return sql_options[0] if sql_options else mapped


def api_save_import_mapping(
    session_id: str,
    body: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST import column mapping (default: ``imports/{sessionId}/mapping``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    sid = str(session_id or "").strip()
    if not sid:
        return {"success": False, "message": "Session ID is required."}
    if not isinstance(body, dict):
        return {"success": False, "message": "Mapping payload is required."}
    url = _api_url(f"{IMPORTS_MAPPING_PATH_PREFIX}/{quote(sid, safe='')}/mapping")
    try:
        payload = _http_post_json(url, body, timeout_s=60.0, extra_headers=headers)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to save mapping."
            )
            if rej is not None:
                return rej
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to save mapping."),
                    "data": payload,
                }
            return {
                "success": True,
                "message": str(
                    payload.get("message")
                    or payload.get("msg")
                    or "Mapping saved successfully."
                ),
                "data": payload.get("data", payload),
            }
        return {
            "success": True,
            "message": "Mapping saved successfully.",
            "data": payload,
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to save mapping ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": err_payload if isinstance(err_payload, dict) else None,
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _parse_import_sheets(payload: Any) -> list[dict[str, Any]]:
    """Normalize ``get-all-import-sheet`` into ``{sessionId, sessionName, sheetId, sheetName}`` rows."""
    raw: Any = payload
    if isinstance(payload, dict):
        for key in ("data", "result", "payload", "content", "sheets", "importSheets"):
            if isinstance(payload.get(key), list):
                raw = payload.get(key)
                break
        else:
            if isinstance(payload.get("data"), dict):
                nested = payload.get("data") or {}
                for key in ("sheets", "importSheets", "list", "items", "content"):
                    if isinstance(nested.get(key), list):
                        raw = nested.get(key)
                        break

    if not isinstance(raw, list):
        return []

    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        session_id = (
            item.get("sessionId")
            or item.get("session_id")
            or item.get("importSessionId")
            or item.get("importId")
        )
        session_name = (
            item.get("sessionName")
            or item.get("session_name")
            or item.get("importName")
            or item.get("name")
            or session_id
        )
        sheet_id = (
            item.get("sheetId")
            or item.get("sheet_id")
            or item.get("id")
        )
        sheet_name = (
            item.get("sheetName")
            or item.get("sheet_name")
            or item.get("sheet")
            or item.get("title")
        )
        table_name = (
            item.get("tableName")
            or item.get("table_name")
            or item.get("targetTableName")
            or item.get("target_table_name")
        )
        sid = str(session_id).strip() if session_id is not None else ""
        if not sid and sheet_id is None:
            continue
        out.append(
            {
                "sessionId": sid,
                "sessionName": str(session_name or sid).strip(),
                "sheetId": sheet_id,
                "sheetName": str(sheet_name).strip() if sheet_name is not None else "",
                "tableName": (
                    str(table_name).strip()
                    if table_name is not None and str(table_name).strip()
                    else None
                ),
                "_raw": item,
            }
        )
    return out


def api_get_all_import_sheets(token: str | None = None) -> dict[str, Any]:
    """GET import sheets for Extract File (default: ``imports/get-all-import-sheet``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {
            "success": False,
            "message": "Session expired. Please log in again.",
            "data": [],
        }
    url = _api_url(IMPORTS_GET_ALL_IMPORT_SHEET_PATH)
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=20.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load import sheets.", data=[]
            )
            if rej is not None:
                return rej
        sheets = _parse_import_sheets(payload)
        return {
            "success": True,
            "message": "Import sheets loaded.",
            "data": sheets,
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Failed to load import sheets ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {
            "success": False,
            "message": "Backend not reachable.",
            "data": [],
        }


def api_get_import_sheets_by_uuid(
    session_id: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET sheets for one import session (``imports/get-import-sheet-by-uuid/{sessionId}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {
            "success": False,
            "message": "Session expired. Please log in again.",
            "data": [],
        }
    sid = str(session_id or "").strip()
    if not sid:
        return {
            "success": False,
            "message": "Select a session first.",
            "data": [],
        }
    url = _api_url(f"{IMPORTS_GET_IMPORT_SHEET_BY_UUID_PREFIX}/{quote(sid, safe='')}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=20.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load sheets for session.", data=[]
            )
            if rej is not None:
                return rej
        sheets = _parse_import_sheets(payload)
        # Ensure session id is attached when API returns only sheet fields.
        for row in sheets:
            if not str(row.get("sessionId") or "").strip():
                row["sessionId"] = sid
        return {
            "success": True,
            "message": "Sheets loaded.",
            "data": sheets,
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload,
                f"Failed to load sheets ({getattr(exc, 'code', 'HTTP error')}).",
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {
            "success": False,
            "message": "Backend not reachable.",
            "data": [],
        }


def _normalize_import_operation(operation: str) -> str | None:
    op = str(operation or "").strip().upper().replace("-", "_").replace(" ", "_")
    if op in {"DROP_AND_CREATE", "DROPANDCREATE"}:
        op = "DROP_CREATE"
    if op in {"DROP_CREATE", "DELETE"}:
        return op
    return None


def _import_sheet_post(
    session_id: str,
    sheet_id: int | str,
    *,
    operation: str,
    path_suffix: str,
    path_prefix: str,
    token: str | None = None,
    ok_fallback: str,
    fail_fallback: str,
    timeout_s: float = 120.0,
) -> dict[str, Any]:
    """POST ``imports/{sessionId}/{path_suffix}`` with sheetId + operation."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    sid = str(session_id or "").strip()
    if not sid:
        return {"success": False, "message": "Session ID is required."}
    op = _normalize_import_operation(operation)
    if not op:
        return {"success": False, "message": "Select Drop and Create or Delete."}
    try:
        sheet_id_value: int | str = int(sheet_id)
    except (TypeError, ValueError):
        sheet_id_value = str(sheet_id).strip()
        if not sheet_id_value:
            return {"success": False, "message": "Sheet ID is required."}
    url = _api_url(f"{path_prefix}/{quote(sid, safe='')}/{path_suffix.lstrip('/')}")
    body: dict[str, Any] = {
        "sheetId": sheet_id_value,
        "operation": op,
    }
    try:
        payload = _http_post_json(url, body, timeout_s=timeout_s, extra_headers=headers)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback=fail_fallback
            )
            if rej is not None:
                return rej
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, fail_fallback),
                    "data": payload,
                }
            return {
                "success": True,
                "message": str(
                    payload.get("message")
                    or payload.get("msg")
                    or ok_fallback
                ),
                "data": payload.get("data", payload),
            }
        return {
            "success": True,
            "message": ok_fallback,
            "data": payload,
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"{fail_fallback} ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": err_payload if isinstance(err_payload, dict) else None,
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_validate_import_sheet(
    session_id: str,
    sheet_id: int | str,
    *,
    operation: str,
    token: str | None = None,
) -> dict[str, Any]:
    """POST validate import operation (default: ``imports/{sessionId}/validate``).

    Body: ``{"sheetId": 1, "operation": "DROP_CREATE"|"DELETE"}``.
    """
    return _import_sheet_post(
        session_id,
        sheet_id,
        operation=operation,
        path_suffix="validate",
        path_prefix=IMPORTS_VALIDATE_PATH_PREFIX,
        token=token,
        ok_fallback="Validation passed.",
        fail_fallback="Validation failed.",
        timeout_s=60.0,
    )


def api_execute_import_sheet(
    session_id: str,
    sheet_id: int | str,
    *,
    operation: str,
    token: str | None = None,
) -> dict[str, Any]:
    """POST execute a mapped import sheet (default: ``imports/{sessionId}/execute``)."""
    return _import_sheet_post(
        session_id,
        sheet_id,
        operation=operation,
        path_suffix="execute",
        path_prefix=IMPORTS_EXECUTE_PATH_PREFIX,
        token=token,
        ok_fallback="Extract completed.",
        fail_fallback="Extract failed.",
        timeout_s=120.0,
    )


def _parse_connections_list_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        rej = _reject_json_business_failure(payload, message_fallback="Failed to load connections.", data=[])
        if rej is not None:
            return []
        raw = payload.get("data") or payload.get("connections") or payload.get("result")
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
    return []


def _connection_row_id_sort_key(conn: dict[str, Any]) -> tuple[int, int | str]:
    """Sort key for connection rows: ascending numeric id, then non-numeric id text."""
    for key in ("connectionId", "connectionID", "connection_id", "id"):
        value = conn.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        try:
            return (0, int(text))
        except (ValueError, TypeError):
            return (1, text.lower())
    return (2, 0)


def _sort_connections_by_id(connections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(connections, key=_connection_row_id_sort_key)


def _connection_post_result(payload: Any, *, ok_fallback: str, fail_fallback: str) -> dict[str, Any]:
    if isinstance(payload, dict):
        rej = _reject_json_business_failure(payload, message_fallback=fail_fallback)
        if rej is not None:
            return rej
        status = str(payload.get("status") or "").strip().upper()
        if payload.get("success") is True or status == "SUCCESS":
            return {
                "success": True,
                "message": str(payload.get("message") or payload.get("msg") or ok_fallback),
            }
        return {
            "success": False,
            "message": _extract_error_message(payload, fail_fallback),
        }
    return {"success": False, "message": fail_fallback}


def api_get_all_connections(token: str | None = None) -> dict[str, Any]:
    """GET all database connections (default: ``api/etl/connection/get-all``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url(ETL_CONNECTIONS_LIST_PATH)
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=12.0)
        items = _sort_connections_by_id(_parse_connections_list_payload(payload))
        if isinstance(payload, dict) and not items:
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load connections.", data=[]
            )
            if rej is not None:
                return rej
        return {"success": True, "data": items}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_test_connection(payload: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    """POST test a database connection (default: ``api/etl/connection/test``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(ETL_CONNECTIONS_TEST_PATH)
    try:
        body = _http_post_json(url, payload, timeout_s=15.0, extra_headers=headers)
        return _connection_post_result(
            body,
            ok_fallback="Connection successful.",
            fail_fallback="Invalid connection details.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Test failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_save_connection(payload: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    """POST create a database connection (default: ``api/etl/connection/save``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(ETL_CONNECTIONS_SAVE_PATH)
    try:
        body = _http_post_json(url, payload, timeout_s=15.0, extra_headers=headers)
        return _connection_post_result(
            body,
            ok_fallback="Connection saved.",
            fail_fallback="Failed to save connection.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Save failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_connection(
    connection_id: int | str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST update an existing connection (default: ``api/etl/connection/update-by-id/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(connection_id)
    if not seg:
        return {"success": False, "message": "Connection ID is required."}
    url = _api_url(f"{ETL_CONNECTIONS_UPDATE_BY_ID_PREFIX}/{seg}")
    try:
        body = _http_post_json(url, payload, timeout_s=15.0, extra_headers=headers)
        return _connection_post_result(
            body,
            ok_fallback="Connection saved.",
            fail_fallback="Failed to save connection.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_connection(
    connection_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE an existing connection (default: ``api/etl/connection/remove-by-id/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(connection_id)
    if not seg:
        return {"success": False, "message": "Connection ID is required."}
    url = _api_url(f"{ETL_CONNECTIONS_REMOVE_BY_ID_PREFIX}/{seg}")
    try:
        payload = _http_delete(url, headers=headers, timeout_s=12.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback="Failed to delete connection.")
            if rej is not None:
                return rej
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to delete connection."),
                }
            return {
                "success": True,
                "message": str(payload.get("message") or "Connection deleted."),
            }
        return {"success": True, "message": "Connection deleted."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _parse_extract_groups_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        rej = _reject_json_business_failure(payload, message_fallback="Failed to load extract groups.", data=[])
        if rej is not None:
            return []
        for key in ("data", "groups", "content", "result"):
            raw = payload.get(key)
            if isinstance(raw, list):
                return [r for r in raw if isinstance(r, dict)]
    return []


def api_get_extract_groups(*, token: str | None = None) -> dict[str, Any]:
    """GET all extract groups (default: ``group``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url(ETL_EXTRACT_GROUP_PATH)
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=15.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load extract groups.", data=[]
            )
            if rej is not None:
                return rej
        groups = _parse_extract_groups_list(payload)
        return {"success": True, "data": groups, "message": ""}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_create_extract_group(payload: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    """POST create an extract group (default: ``group``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(ETL_EXTRACT_GROUP_PATH)
    try:
        body = _http_post_json(url, payload, timeout_s=15.0, extra_headers=headers)
        return _connection_post_result(
            body,
            ok_fallback="Extract group created.",
            fail_fallback="Failed to create extract group.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Create failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_extract_group(
    group_id: int | str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT update an extract group (default: ``group/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(group_id)
    if not seg:
        return {"success": False, "message": "Group ID is required."}
    url = _api_url(f"{ETL_EXTRACT_GROUP_PATH}/{seg}")
    try:
        status, body = _http_put_json(url, payload, timeout_s=15.0, extra_headers=headers)
        if status in (200, 201, 204):
            if isinstance(body, dict) and body:
                result = _connection_post_result(
                    body,
                    ok_fallback="Extract group updated.",
                    fail_fallback="Failed to update extract group.",
                )
                if result.get("success"):
                    return result
            return {"success": True, "message": "Extract group updated."}
        if isinstance(body, dict):
            return {
                "success": False,
                "message": _extract_error_message(body, "Failed to update extract group."),
            }
        return {"success": False, "message": f"Update failed (HTTP {status})."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_add_extract_group_tables(
    group_id: int | str,
    tables: list[dict[str, str]],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST add tables to an extract group (``group/table/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(group_id)
    if not seg:
        return {"success": False, "message": "Group ID is required."}
    table_entries: list[dict[str, str]] = []
    for item in tables:
        if not isinstance(item, dict):
            continue
        table_name = str(item.get("tableName") or "").strip()
        if not table_name:
            continue
        table_entries.append(
            {
                "tableName": table_name,
                "newTableName": str(item.get("newTableName") or "").strip(),
            }
        )
    if not table_entries:
        return {"success": False, "message": "At least one table is required."}
    url = _api_url(f"{ETL_EXTRACT_GROUP_PATH}/table/{seg}")
    try:
        body = _http_post_json(url, {"tables": table_entries}, timeout_s=15.0, extra_headers=headers)
        return _connection_post_result(
            body,
            ok_fallback="Tables added to extract group.",
            fail_fallback="Failed to add tables to extract group.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Add tables failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_extract_group_table(
    group_table_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE a table from an extract group (``group/table/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(group_table_id)
    if not seg:
        return {"success": False, "message": "Group table ID is required."}
    url = _api_url(f"{ETL_EXTRACT_GROUP_PATH}/table/{seg}")
    try:
        payload = _http_delete(url, headers=headers, timeout_s=12.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to remove table from extract group."
            )
            if rej is not None:
                return rej
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(
                        payload, "Failed to remove table from extract group."
                    ),
                }
            return {
                "success": True,
                "message": str(payload.get("message") or "Table removed from extract group."),
            }
        return {"success": True, "message": "Table removed from extract group."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Remove table failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_group_tgt_table_name(
    group_table_id: int | str,
    new_table_name: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT update group table target name (``group/update/tgt-table/{id}?newTableName=…``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(group_table_id)
    new_tbl = (new_table_name or "").strip()
    if not seg:
        return {"success": False, "message": "Group table ID is required."}
    if not new_tbl:
        return {"success": False, "message": "New target table name is required."}
    query = urlencode({"newTableName": new_tbl})
    url = _api_url(f"{ETL_EXTRACT_GROUP_UPDATE_TGT_TABLE_PATH}/{seg}?{query}")
    put_headers = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        **headers,
    }
    try:
        req = Request(url, data=b"", headers=put_headers, method="PUT")
        with _http_urlopen_logged(req, timeout=30.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        return _connection_post_result(
            payload,
            ok_fallback="Target table name updated.",
            fail_fallback="Failed to update target table name.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_add_group_table_where_clause(
    group_table_id: int | str,
    where_clause: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST add or update a group table WHERE clause (``group/table/add-where-clause/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(group_table_id)
    clause = (where_clause or "").strip()
    if not seg:
        return {"success": False, "message": "Group table ID is required."}
    if not clause:
        return {"success": False, "message": "Where clause is required."}
    url = _api_url(f"{ETL_GROUP_TABLE_ADD_WHERE_CLAUSE_PATH}/{seg}")
    try:
        body = _http_post_json(
            url,
            {"whereClause": clause},
            timeout_s=30.0,
            extra_headers=headers,
        )
        return _connection_post_result(
            body,
            ok_fallback="Where clause saved.",
            fail_fallback="Failed to save where clause.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Save where clause failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_validate_group_table_where_clause(
    connection_id: int | str,
    table_name: str,
    where_clause: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST validate a WHERE clause (``group/table/validate-where-clause/{connectionId}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "valid": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(connection_id)
    clause = (where_clause or "").strip()
    tbl = (table_name or "").strip()
    if not seg:
        return {"success": False, "valid": False, "message": "Connection ID is required."}
    if not tbl:
        return {"success": False, "valid": False, "message": "Table name is required."}
    if not clause:
        return {"success": False, "valid": False, "message": "Where clause is required."}
    url = _api_url(f"{ETL_GROUP_VALIDATE_WHERE_CLAUSE_PATH}/{seg}")
    try:
        body = _http_post_json(
            url,
            {"whereClause": clause, "tableName": tbl},
            timeout_s=30.0,
            extra_headers=headers,
        )
        if isinstance(body, dict):
            rej = _reject_json_business_failure(body, message_fallback="Validation failed.")
            if rej is not None:
                return {
                    "success": False,
                    "valid": False,
                    "message": str(
                        rej.get("error")
                        or rej.get("message")
                        or "Validation failed."
                    ),
                }
            valid = body.get("valid")
            is_valid = valid is True or str(valid).strip().lower() in ("true", "1", "yes")
            if is_valid:
                message = str(body.get("message") or "Validation successful.")
            else:
                message = str(
                    body.get("error")
                    or body.get("message")
                    or _extract_error_message(body, "Validation failed.")
                ).strip()
            return {"success": is_valid, "valid": is_valid, "message": message}
        return {"success": False, "valid": False, "message": "Validation failed."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "valid": False,
            "message": str(
                err_payload.get("error")
                or _extract_error_message(
                    err_payload, f"Validation failed ({getattr(exc, 'code', 'HTTP error')})."
                )
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "valid": False, "message": "Backend not reachable."}


def api_delete_extract_group(group_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    """DELETE an extract group (default: ``group/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(group_id)
    if not seg:
        return {"success": False, "message": "Group ID is required."}
    url = _api_url(f"{ETL_EXTRACT_GROUP_PATH}/{seg}")
    try:
        payload = _http_delete(url, headers=headers, timeout_s=12.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback="Failed to delete extract group.")
            if rej is not None:
                return rej
            if payload.get("success") is False:
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to delete extract group."),
                }
            return {
                "success": True,
                "message": str(payload.get("message") or "Extract group deleted."),
            }
        return {"success": True, "message": "Extract group deleted."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _metadata_json_success(payload: Any, *, fail_fallback: str) -> bool:
    if not isinstance(payload, dict):
        return False
    if _json_payload_indicates_business_failure(payload):
        return False
    status = str(payload.get("status") or "").strip().upper()
    return payload.get("success") is True or status == "SUCCESS"


def _extract_scan_tables_list(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in (
        "tableList",
        "tables",
        "data",
        "content",
        "extractedTables",
        "extractedTableList",
        "tableNames",
        "result",
    ):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for nested_key in ("tables", "tableList", "data", "content"):
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    return nested
    return []


def _normalize_metadata_table_rows(items: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            rows.append(item)
        elif isinstance(item, str) and item.strip():
            rows.append({"tableName": item.strip()})
    return rows


def api_post_scan_connection_source_tables(
    connection_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST database tables for a connection (``api/etl/scan-connection/table/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "tables": []}
    seg = _api_path_id_segment(connection_id)
    if not seg:
        return {"success": False, "message": "Connection ID is required.", "tables": []}
    url = _api_url(f"{ETL_SCAN_CONNECTION_SOURCE_TABLES_PATH_PREFIX}/{seg}")
    try:
        payload = _http_post_json(url, {}, timeout_s=60.0, extra_headers=headers)
        if not _metadata_json_success(payload, fail_fallback="Failed to load database tables."):
            if isinstance(payload, dict):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to load database tables."),
                    "tables": [],
                }
            return {"success": False, "message": "Failed to load database tables.", "tables": []}
        tables = _extract_scan_tables_list(payload)
        return {
            "success": True,
            "tables": tables,
            "status": str(payload.get("status") or "") if isinstance(payload, dict) else "",
            "message": str(payload.get("message") or ""),
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "tables": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "tables": []}


def api_get_metadata_tables(
    connection_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET scanned tables for a connection (``api/etl/scan-connection/get-scanned-table-by-id/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "tables": []}
    seg = _api_path_id_segment(connection_id)
    if not seg:
        return {"success": False, "message": "Connection ID is required.", "tables": []}
    url = _api_url(f"{ETL_METADATA_SCAN_TABLES_PATH_PREFIX}/{seg}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if not _metadata_json_success(payload, fail_fallback="Failed to load tables."):
            if isinstance(payload, dict):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to load tables."),
                    "tables": [],
                }
            return {"success": False, "message": "Failed to load tables.", "tables": []}
        tables = _extract_scan_tables_list(payload)
        last_scan_date = ""
        if isinstance(payload, dict):
            for key in (
                "lastScanDate",
                "LAST_SCAN_DATE",
                "last_scan_date",
                "lastScannedOn",
                "lastScannedAt",
            ):
                value = payload.get(key)
                if value is not None and str(value).strip():
                    last_scan_date = str(value).strip()
                    break
        return {
            "success": True,
            "tables": tables,
            "status": str(payload.get("status") or "") if isinstance(payload, dict) else "",
            "message": str(payload.get("message") or ""),
            "lastScanDate": last_scan_date,
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "tables": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "tables": []}


def api_get_extracted_metadata_tables_by_connection(
    connection_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET extracted tables (``api/etl/extract-metadata/extracted-table-by-id/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "tables": []}
    seg = _api_path_id_segment(connection_id)
    if not seg:
        return {"success": False, "message": "Connection ID is required.", "tables": []}
    url = _api_url(f"{ETL_EXTRACT_METADATA_EXTRACTED_TABLE_BY_ID_PATH_PREFIX}/{seg}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        raw_tables = _extract_scan_tables_list(payload)
        tables = _normalize_metadata_table_rows(raw_tables)
        if tables:
            return {"success": True, "tables": tables}
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load extracted tables.", data=[]
            )
            if rej is not None:
                return {**rej, "tables": []}
            if _metadata_json_success(payload, fail_fallback="Failed to load extracted tables."):
                return {"success": True, "tables": []}
            return {
                "success": False,
                "message": _extract_error_message(payload, "Failed to load extracted tables."),
                "tables": [],
            }
        if isinstance(payload, list):
            return {"success": True, "tables": []}
        return {"success": False, "message": "Failed to load extracted tables.", "tables": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "tables": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "tables": []}


def api_get_metadata_table_columns(
    connection_id: int | str,
    table_name: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET column metadata (``api/etl/scan-connection/get-scanned-table-detail/{id}?tableName=…``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "columns": []}
    seg = _api_path_id_segment(connection_id)
    tbl = (table_name or "").strip()
    if not seg or not tbl:
        return {"success": False, "message": "Connection ID and table name are required.", "columns": []}
    base = _api_url(f"{ETL_METADATA_SCAN_FIELDS_PATH_PREFIX}/{seg}")
    url = f"{base}?{urlencode({'tableName': tbl})}"
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback="Could not load table info.", columns=[])
            if rej is not None:
                return rej
        columns = payload.get("columns", []) if isinstance(payload, dict) else []
        if not isinstance(columns, list):
            columns = []
        return {
            "success": True,
            "columns": columns,
            "tableName": str(payload.get("tableName") or tbl) if isinstance(payload, dict) else tbl,
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "columns": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "columns": []}


def _parse_etl_details_alias_name(record: dict[str, Any]) -> str:
    for key in (
        "aliasName",
        "alias_name",
        "ALIAS_NAME",
        "sourceAlias",
        "source_alias",
        "SOURCE_ALIAS",
        "alias",
        "ALIAS",
    ):
        text = str(record.get(key) or "").strip()
        if text:
            return text
    return ""


def _parse_etl_details_column_field_name(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("columnName", "column_name", "COLUMN_NAME", "fieldName", "field_name", "name"):
            text = str(value.get(key) or "").strip()
            if text:
                return text
        return ""
    return str(value or "").strip()


def _parse_etl_details_column_rows(payload: Any) -> list[dict[str, Any]]:
    """Normalize ETL-details column payload to rows with tableName and columnName."""
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = None
        for key in ("data", "content", "result", "fieldList", "columns", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                raw_items = value
                break
        if raw_items is None:
            if _parse_etl_details_column_field_name(payload) or str(
                payload.get("tableName") or payload.get("table_name") or ""
            ).strip():
                raw_items = [payload]
            else:
                raw_items = []
    else:
        return []

    rows: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        table_name = str(
            item.get("tableName") or item.get("table_name") or item.get("TABLE_NAME") or ""
        ).strip()
        nested = item.get("columns") or item.get("columnList") or item.get("fields") or item.get(
            "fieldList"
        )
        if isinstance(nested, list):
            parent_alias = _parse_etl_details_alias_name(item)
            for col in nested:
                column_name = _parse_etl_details_column_field_name(col)
                if not column_name:
                    continue
                row = {"tableName": table_name, "columnName": column_name}
                if parent_alias:
                    row.setdefault("aliasName", parent_alias)
                    row.setdefault("sourceAlias", parent_alias)
                if isinstance(col, dict):
                    row.update(col)
                if not _parse_etl_details_alias_name(row) and parent_alias:
                    row["aliasName"] = parent_alias
                    row["sourceAlias"] = parent_alias
                rows.append(row)
            continue
        column_name = _parse_etl_details_column_field_name(item)
        if table_name and column_name:
            row = dict(item)
            row.setdefault("tableName", table_name)
            row.setdefault("columnName", column_name)
            rows.append(row)
    return rows


def api_get_table_columns_from_etl_details(
    connection_id: int | str,
    table_list: list[str],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST column metadata for tables (``api/metadata/get-table-name-from-etl-details/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "rows": []}
    seg = _api_path_id_segment(connection_id)
    if not seg:
        return {"success": False, "message": "Connection ID is required.", "rows": []}
    tables = [str(t).strip() for t in table_list if str(t).strip()]
    if not tables:
        return {"success": False, "message": "At least one table is required.", "rows": []}
    url = _api_url(f"{ETL_METADATA_GET_TABLE_NAME_FROM_ETL_DETAILS_PATH_PREFIX}/{seg}")
    payload_body: dict[str, Any] = {"tableList": tables}
    try:
        body = _http_post_json(url, payload_body, timeout_s=60.0, extra_headers=headers)
        if isinstance(body, dict):
            rej = _reject_json_business_failure(
                body, message_fallback="Failed to load table columns.", data=[]
            )
            if rej is not None:
                return {**rej, "rows": []}
        rows = _parse_etl_details_column_rows(body)
        return {"success": True, "rows": rows, "message": ""}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "rows": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "rows": []}


def _api_check_metadata_fields(
    connection_id: int | str,
    table_list: list[str],
    path_prefix: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(connection_id)
    if not seg:
        return {"success": False, "message": "Connection ID is required."}
    tables = [str(t).strip() for t in table_list if str(t).strip()]
    if not tables:
        return {"success": False, "message": "Select at least one table."}
    payload: dict[str, Any] = {"tableList": tables}
    url = _api_url(f"{path_prefix}/{seg}")
    try:
        body = _http_post_json(url, payload, timeout_s=60.0, extra_headers=headers)
        if not isinstance(body, dict):
            return {"success": False, "message": "Field check failed."}
        status = str(body.get("status") or "").strip().upper()
        msg = str(body.get("msg") or body.get("message") or "").strip()
        if body.get("success") is True or status == "SUCCESS":
            return {"success": True, "message": msg or "FIELDS"}
        if status == "FAILURE":
            data = body.get("data")
            rows = [r for r in data if isinstance(r, dict)] if isinstance(data, list) else []
            return {
                "success": False,
                "field_mismatch": True,
                "message": msg or "FIELD MISMATCH",
                "data": rows,
            }
        return {
            "success": False,
            "message": _extract_error_message(body, "Field check failed."),
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Field check failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_check_import_metadata_fields(
    connection_id: int | str,
    table_list: list[str],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST validate fields before import (``api/etl/import-metadata/check-field/{id}``)."""
    return _api_check_metadata_fields(
        connection_id,
        table_list,
        ETL_METADATA_CHECK_FIELD_PATH_PREFIX,
        token=token,
    )


def api_check_scan_connection_fields(
    connection_id: int | str,
    table_list: list[str],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST validate fields after scan (``api/etl/scan-connection/check-field/{id}``)."""
    return _api_check_metadata_fields(
        connection_id,
        table_list,
        ETL_SCAN_CONNECTION_CHECK_FIELD_PATH_PREFIX,
        token=token,
    )


def api_import_metadata_tables(
    connection_id: int | str,
    table_list: list[str],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST import selected tables (``api/etl/import-metadata/import-table-detail/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(connection_id)
    if not seg:
        return {"success": False, "message": "Connection ID is required."}
    payload: dict[str, Any] = {"tableList": list(table_list)}
    url = _api_url(f"{ETL_METADATA_IMPORT_TABLE_DETAILS_PATH}/{seg}")
    try:
        body = _http_post_json(url, payload, timeout_s=60.0, extra_headers=headers)
        return _connection_post_result(
            body,
            ok_fallback="Table imported successfully.",
            fail_fallback="Import failed.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Import failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_metadata_scan_all(connection_name: str, *, token: str | None = None) -> dict[str, Any]:
    """POST scan all tables for a connection (default: ``api/etl/scan-connection/scan-all``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    name = (connection_name or "").strip()
    if not name:
        return {"success": False, "message": "Connection name is required."}
    url = _api_url(ETL_METADATA_SCAN_ALL_PATH)
    try:
        body = _http_post_json(
            url, {"connectionName": name}, timeout_s=120.0, extra_headers=headers
        )
        result = _connection_post_result(
            body,
            ok_fallback="Scan completed.",
            fail_fallback="Scan all failed.",
        )
        if result.get("success") and isinstance(body, dict):
            result["connectionName"] = str(body.get("connectionName") or name)
        return result
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Scan failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_metadata_scan_by_filter(
    connection_id: int | str,
    table_names: list[str],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST scan selected tables (``api/etl/scan-connection/scan-all-by-filter/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(connection_id)
    if not seg:
        return {"success": False, "message": "Connection ID is required."}
    tables = [str(t).strip() for t in table_names if str(t).strip()]
    if not tables:
        return {"success": False, "message": "Select at least one table to scan."}
    body: dict[str, Any] = {"tableList": tables}
    url = _api_url(f"{ETL_METADATA_SCAN_BY_FILTER_PATH_PREFIX}/{seg}")
    try:
        payload = _http_post_json(url, body, timeout_s=120.0, extra_headers=headers)
        result = _connection_post_result(
            payload,
            ok_fallback="Scan completed.",
            fail_fallback="Scan by filter failed.",
        )
        return result
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Scan failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_imported_tables(
    connection_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET imported tables for extraction (``api/etl/import-metadata/imported-table-by-id/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "tables": []}
    seg = _api_path_id_segment(connection_id)
    if not seg:
        return {"success": False, "message": "Connection ID is required.", "tables": []}
    url = _api_url(f"{ETL_METADATA_IMPORTED_TABLES_PATH_PREFIX}/{seg}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if not _metadata_json_success(payload, fail_fallback="Failed to load tables."):
            if isinstance(payload, dict):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to load tables."),
                    "tables": [],
                }
            return {"success": False, "message": "Failed to load tables.", "tables": []}
        tables = _extract_scan_tables_list(payload)
        return {"success": True, "tables": tables}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "tables": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "tables": []}


def api_update_tgt_table_name(
    import_table_id: int | str,
    new_table_name: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT update imported table target name (``api/etl/import-metadata/update-tgt-table-name/{id}?newTableName=…``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(import_table_id)
    new_tbl = (new_table_name or "").strip()
    if not seg:
        return {"success": False, "message": "Import table ID is required."}
    if not new_tbl:
        return {"success": False, "message": "New target table name is required."}
    query = urlencode({"newTableName": new_tbl})
    url = _api_url(f"{ETL_SCAN_UPDATE_TGT_TABLE_NAME_PATH_PREFIX}/{seg}?{query}")
    put_headers = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        **headers,
    }
    try:
        req = Request(url, data=b"", headers=put_headers, method="PUT")
        with _http_urlopen_logged(req, timeout=30.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        return _connection_post_result(
            payload,
            ok_fallback="Target table name updated.",
            fail_fallback="Failed to update target table name.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_import_table_where_clause(
    import_table_id: int | str,
    where_clause: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT update imported table WHERE clause (``api/etl/import-metadata/update-where-clause/{id}?whereClause=…``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(import_table_id)
    clause = (where_clause or "").strip()
    if not seg:
        return {"success": False, "message": "Import table ID is required."}
    if not clause:
        return {"success": False, "message": "Where clause is required."}
    query = urlencode({"whereClause": clause})
    url = _api_url(f"{ETL_IMPORT_METADATA_UPDATE_WHERE_CLAUSE_PATH_PREFIX}/{seg}?{query}")
    put_headers = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        **headers,
    }
    try:
        req = Request(url, data=b"", headers=put_headers, method="PUT")
        with _http_urlopen_logged(req, timeout=30.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        return _connection_post_result(
            payload,
            ok_fallback="Where clause saved.",
            fail_fallback="Failed to save where clause.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _parse_extraction_tables_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "tables", "tableList", "content", "result"):
        raw = payload.get(key)
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
    return []


def api_get_extraction_tables_by_connection(
    connection_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET extraction tables for a connection (``api/extraction/connection/{connectionId}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "tables": []}
    seg = _api_path_id_segment(connection_id)
    if not seg:
        return {"success": False, "message": "Connection ID is required.", "tables": []}
    url = _api_url(f"{ETL_EXTRACTION_BY_CONNECTION_PATH_PREFIX}/{seg}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load extraction tables.", data=[]
            )
            if rej is not None:
                return {**rej, "tables": []}
        tables = _parse_extraction_tables_list(payload)
        return {"success": True, "tables": tables, "message": ""}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "tables": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "tables": []}


def api_get_extraction_by_id(
    extraction_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET one extraction record (``api/extraction/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(extraction_id)
    if not seg:
        return {"success": False, "message": "Extraction ID is required."}
    url = _api_url(f"{ETL_EXTRACTION_PATH}/{seg}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load extraction record."
            )
            if rej is not None:
                return rej
            for key in ("data", "result", "extraction"):
                nested = payload.get(key)
                if isinstance(nested, dict):
                    return {"success": True, "data": nested, "message": ""}
            return {"success": True, "data": payload, "message": ""}
        return {"success": False, "message": "Failed to load extraction record."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_create_extraction_table(
    table_name: str,
    connection_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST add a table to extraction (``api/extraction?tableName=…&connectionName={connectionId}``).

    The backend expects the connection ID in the ``connectionName`` query parameter.
    """
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    tbl = (table_name or "").strip()
    conn_id = str(connection_id or "").strip()
    if not tbl:
        return {"success": False, "message": "Table name is required."}
    if not conn_id:
        return {"success": False, "message": "Connection ID is required."}
    query = urlencode({"tableName": tbl, "connectionName": conn_id})
    url = _api_url(f"{ETL_EXTRACTION_PATH}?{query}")
    post_headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        **headers,
    }
    try:
        req = Request(url, data=b"", headers=post_headers, method="POST")
        with _http_urlopen_logged(req, timeout=30.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        return _connection_post_result(
            payload,
            ok_fallback="Table added to extraction.",
            fail_fallback="Failed to add table to extraction.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Add failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_extraction_target_table(
    extraction_id: int | str,
    target_table_name: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT update extraction target table name (``api/extraction/target-table/{id}?targetTableName=…``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(extraction_id)
    tgt = (target_table_name or "").strip()
    if not seg:
        return {"success": False, "message": "Extraction ID is required."}
    if not tgt:
        return {"success": False, "message": "Target table name is required."}
    query = urlencode({"targetTableName": tgt})
    url = _api_url(f"{ETL_EXTRACTION_UPDATE_TARGET_TABLE_PATH_PREFIX}/{seg}?{query}")
    put_headers = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        **headers,
    }
    try:
        req = Request(url, data=b"", headers=put_headers, method="PUT")
        with _http_urlopen_logged(req, timeout=30.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        return _connection_post_result(
            payload,
            ok_fallback="Target table name updated.",
            fail_fallback="Failed to update target table name.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_update_extraction_where_clause(
    extraction_id: int | str,
    where_clause: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PUT update extraction where clause (``api/extraction/where-clause/{id}?whereClause=…``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(extraction_id)
    clause = (where_clause or "").strip()
    if not seg:
        return {"success": False, "message": "Extraction ID is required."}
    if not clause:
        return {"success": False, "message": "Where clause is required."}
    query = urlencode({"whereClause": clause})
    url = _api_url(f"{ETL_EXTRACTION_UPDATE_WHERE_CLAUSE_PATH_PREFIX}/{seg}?{query}")
    put_headers = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        **headers,
    }
    try:
        req = Request(url, data=b"", headers=put_headers, method="PUT")
        with _http_urlopen_logged(req, timeout=30.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        return _connection_post_result(
            payload,
            ok_fallback="Where clause saved.",
            fail_fallback="Failed to save where clause.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_delete_extraction_table(
    extraction_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE an extraction table (``api/extraction/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(extraction_id)
    if not seg:
        return {"success": False, "message": "Extraction ID is required."}
    url = _api_url(f"{ETL_EXTRACTION_PATH}/{seg}")
    try:
        payload = _http_delete(url, headers=headers, timeout_s=30.0)
        return _connection_post_result(
            payload,
            ok_fallback="Table removed from extraction.",
            fail_fallback="Failed to remove extraction table.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_remove_imported_table(
    connection_name: str,
    table_name: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE an imported table (``api/metadata/imported-remove/{connection}?tableName={table}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    conn = (connection_name or "").strip()
    tbl = (table_name or "").strip()
    if not conn or not tbl:
        return {"success": False, "message": "Connection and table name are required."}
    url = _api_url(
        f"{ETL_METADATA_IMPORTED_REMOVE_PATH_PREFIX}/{quote(conn, safe='')}?tableName={quote(tbl, safe='')}"
    )
    try:
        payload = _http_delete(url, headers=headers, timeout_s=30.0)
        return _connection_post_result(
            payload,
            ok_fallback="Table removed.",
            fail_fallback="Failed to remove table.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Remove failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_extracted_fields(
    connection_name: str,
    table_name: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET extraction column metadata (``api/metadata/scan-extracted-feilds/{connection}?tableName={table}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "columns": []}
    conn = (connection_name or "").strip()
    tbl = (table_name or "").strip()
    if not conn or not tbl:
        return {"success": False, "message": "Connection and table name are required.", "columns": []}
    url = _api_url(
        f"{ETL_METADATA_SCAN_EXTRACTED_FIELDS_PATH_PREFIX}/{quote(conn, safe='')}?tableName={quote(tbl, safe='')}"
    )
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Could not load columns.", columns=[]
            )
            if rej is not None:
                return rej
        columns = payload.get("columns", []) if isinstance(payload, dict) else []
        if not isinstance(columns, list):
            columns = []
        return {
            "success": True,
            "columns": columns,
            "tableName": str(payload.get("tableName") or tbl) if isinstance(payload, dict) else tbl,
        }
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "columns": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "columns": []}


def api_update_extracted_fields(
    connection_name: str,
    table_name: str,
    checked_columns: list[str],
    unchecked_columns: list[str],
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST update extraction columns (``api/metadata/update-extracted-feilds/{connection}?tableName={table}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    conn = (connection_name or "").strip()
    tbl = (table_name or "").strip()
    if not conn or not tbl:
        return {"success": False, "message": "Connection and table name are required."}
    url = _api_url(
        f"{ETL_METADATA_UPDATE_EXTRACTED_FIELDS_PATH_PREFIX}/{quote(conn, safe='')}?tableName={quote(tbl, safe='')}"
    )
    payload = {
        "checkedColumns": list(checked_columns),
        "unCheckedColumns": list(unchecked_columns),
    }
    try:
        body = _http_post_json(url, payload, timeout_s=30.0, extra_headers=headers)
        return _connection_post_result(
            body,
            ok_fallback="Columns updated.",
            fail_fallback="Failed to update columns.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_start_group_extraction_job(
    group_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """POST start an extract-group ETL job (``etl/jobs/group/start/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(group_id)
    if not seg:
        return {"success": False, "message": "Group ID is required."}
    url = _api_url(f"{ETL_GROUP_JOB_START_PATH}/{seg}")
    try:
        body = _http_post_json(url, {}, timeout_s=120.0, extra_headers=headers)
        if isinstance(body, dict):
            rej = _reject_json_business_failure(body, message_fallback="Failed to start extraction job.")
            if rej is not None:
                return rej
            status = str(body.get("status") or "").strip().upper()
            if body.get("success") is True or status in ("SUCCESS", "QUEUED"):
                job_id = body.get("jobId")
                msg = body.get("message") or body.get("msg")
                if job_id is not None:
                    message = f"Job queued successfully. Job ID: {job_id}"
                else:
                    message = str(msg or "Job queued successfully.")
                return {"success": True, "message": message, "jobId": job_id}
            return {
                "success": False,
                "message": _extract_error_message(body, "Failed to start extraction job."),
            }
        return {"success": False, "message": "Failed to start extraction job."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Job start failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_start_etl_job(job_payload: dict[str, Any], *, token: str | None = None) -> dict[str, Any]:
    """POST start an ETL extraction job (``etl/jobs/start``).

    Expected body keys: ``connection_name_src``, ``connection_name_tgt``,
    ``src_fetch_size``, ``tgt_commit_size``, ``tableName`` (list of
    ``{tableName, newTableName, whereClause}`` objects).
    """
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(ETL_JOB_START_PATH)
    try:
        body = _http_post_json(url, job_payload, timeout_s=120.0, extra_headers=headers)
        if isinstance(body, dict):
            rej = _reject_json_business_failure(body, message_fallback="Failed to start extraction job.")
            if rej is not None:
                return rej
            status = str(body.get("status") or "").strip().upper()
            if body.get("success") is True or status in ("SUCCESS", "QUEUED"):
                job_id = body.get("jobId")
                msg = body.get("message") or body.get("msg")
                if job_id is not None:
                    message = f"Job queued successfully. Job ID: {job_id}"
                else:
                    message = str(msg or "Job queued successfully.")
                return {"success": True, "message": message, "jobId": job_id}
            return {
                "success": False,
                "message": _extract_error_message(body, "Failed to start extraction job."),
            }
        return {"success": False, "message": "Failed to start extraction job."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Job start failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _extract_etl_log_detail_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("details", "data", "logs", "steps", "content"):
        value = payload.get(key)
        if isinstance(value, list):
            return [r for r in value if isinstance(r, dict)]
    return []


def api_get_etl_log_by_id(
    log_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET step details for one ETL log (default: ``api/etl/logs/{id}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    seg = _api_path_id_segment(log_id)
    if not seg:
        return {"success": False, "message": "Log ID is required.", "data": []}
    url = _api_url(f"{ETL_LOG_BY_ID_PATH_PREFIX}/{seg}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=15.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load log details.", data=[]
            )
            if rej is not None:
                return rej
            rows = _extract_etl_log_detail_rows(payload)
            if rows:
                return {"success": True, "data": rows, "message": str(payload.get("message") or "")}
            if any(k in payload for k in ("details", "data", "logs", "steps")):
                return {"success": True, "data": [], "message": str(payload.get("message") or "")}
            return {"success": True, "data": [payload], "message": str(payload.get("message") or "")}
        if isinstance(payload, list):
            return {
                "success": True,
                "data": [r for r in payload if isinstance(r, dict)],
                "message": "",
            }
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_get_all_etl_jobs(token: str | None = None) -> dict[str, Any]:
    """GET all ETL job logs (default: ``api/etl/logs``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url(ETL_JOBS_ALL_PATH)
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=15.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load job logs.", data={}
            )
            if rej is not None:
                return rej
            for key in ("data", "jobs", "logs", "content"):
                value = payload.get(key)
                if isinstance(value, list):
                    return {
                        "success": True,
                        "data": [r for r in value if isinstance(r, dict)],
                        "message": str(payload.get("message") or ""),
                    }
            return {
                "success": True,
                "data": [payload],
                "message": str(payload.get("message") or ""),
            }
        if isinstance(payload, list):
            return {"success": True, "data": [r for r in payload if isinstance(r, dict)]}
        return {"success": False, "message": "Unexpected response format.", "data": []}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def _parse_transformation_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "content", "result", "objects", "jobs", "workflows", "flows", "stepMasters", "stepMasterList", "masters", "sources", "sourceList"):
        raw = payload.get(key)
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
    return []


def _transformation_record(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        # Source/target rows include a nested ``flow`` object — keep the parent row.
        if (
            _transformation_step_table_name(payload)
            or str(payload.get("connectionId") or payload.get("connection_id") or "").strip()
            or "whereClause" in payload
            or "where_clause" in payload
            or "loadType" in payload
            or "commitSize" in payload
            or "fetchSize" in payload
        ):
            return payload
        for key in (
            "data",
            "result",
            "content",
            "object",
            "job",
            "workflow",
            "flow",
            "source",
            "target",
        ):
            nested = payload.get(key)
            if isinstance(nested, dict):
                return nested
            if isinstance(nested, list):
                for item in nested:
                    if isinstance(item, dict):
                        return item
        return payload
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                return item
    return None


def _transformation_step_table_name(record: dict[str, Any]) -> str:
    for key in ("tableName", "TABLE_NAME", "table_name", "name"):
        value = record.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _transformation_step_has_data(record: dict[str, Any], *id_keys: str) -> bool:
    for key in id_keys:
        value = record.get(key)
        if value is not None and str(value).strip() != "":
            return True
    for key in ("connectionId", "connection_id", "CONNECTION_ID"):
        if str(record.get(key) or "").strip():
            return True
    return bool(_transformation_step_table_name(record))


def _get_transformation_list(
    base_path: str,
    *,
    token: str | None = None,
    fail_message: str = "Failed to load records.",
) -> dict[str, Any]:
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url(base_path)
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback=fail_message, data=[])
            if rej is not None:
                return {**rej, "data": []}
        rows = _parse_transformation_list(payload)
        return {"success": True, "data": rows, "message": ""}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def _get_transformation_by_id(
    base_path: str,
    record_id: int | str,
    *,
    token: str | None = None,
    fail_message: str = "Failed to load record.",
) -> dict[str, Any]:
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(record_id)
    if not seg:
        return {"success": False, "message": "ID is required."}
    url = _api_url(f"{base_path}/{seg}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback=fail_message)
            if rej is not None:
                return rej
        record = _transformation_record(payload)
        if record:
            return {"success": True, "data": record, "message": ""}
        return {"success": False, "message": fail_message}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _get_transformation_by_parent(
    base_path: str,
    parent_segment: str,
    parent_id: int | str,
    *,
    token: str | None = None,
    fail_message: str = "Failed to load records.",
) -> dict[str, Any]:
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    seg = _api_path_id_segment(parent_id)
    if not seg:
        return {"success": False, "message": "Parent ID is required.", "data": []}
    url = _api_url(f"{base_path}/{parent_segment}/{seg}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(payload, message_fallback=fail_message, data=[])
            if rej is not None:
                return {**rej, "data": []}
        rows = _parse_transformation_list(payload)
        return {"success": True, "data": rows, "message": ""}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Request failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
            "data": [],
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def _post_transformation(
    base_path: str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
    ok_fallback: str = "Saved.",
    fail_fallback: str = "Save failed.",
) -> dict[str, Any]:
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(base_path)
    try:
        body = _http_post_json(url, payload, timeout_s=30.0, extra_headers=headers)
        result = _connection_post_result(body, ok_fallback=ok_fallback, fail_fallback=fail_fallback)
        if result.get("success") and isinstance(body, dict):
            data = body.get("data")
            if isinstance(data, dict):
                result["data"] = data
            elif body.get("id") is not None:
                result["data"] = body
        return result
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Save failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _put_transformation(
    base_path: str,
    record_id: int | str,
    payload: dict[str, Any],
    *,
    token: str | None = None,
    ok_fallback: str = "Updated.",
    fail_fallback: str = "Update failed.",
) -> dict[str, Any]:
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(record_id)
    if not seg:
        return {"success": False, "message": "ID is required."}
    url = _api_url(f"{base_path}/{seg}")
    try:
        status, body = _http_put_json(url, payload, timeout_s=30.0, extra_headers=headers)
        if status in (200, 201, 204):
            if isinstance(body, dict) and body:
                result = _connection_post_result(body, ok_fallback=ok_fallback, fail_fallback=fail_fallback)
                if result.get("success"):
                    data = body.get("data")
                    if isinstance(data, dict):
                        result["data"] = data
                    elif body.get("id") is not None:
                        result["data"] = body
                    return result
            return {"success": True, "message": ok_fallback}
        if isinstance(body, dict):
            return {"success": False, "message": _extract_error_message(body, fail_fallback)}
        return {"success": False, "message": f"Update failed (HTTP {status})."}
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Update failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _delete_transformation(
    base_path: str,
    record_id: int | str,
    *,
    token: str | None = None,
    ok_fallback: str = "Deleted.",
    fail_fallback: str = "Delete failed.",
) -> dict[str, Any]:
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(record_id)
    if not seg:
        return {"success": False, "message": "ID is required."}
    url = _api_url(f"{base_path}/{seg}")
    try:
        payload = _http_delete(url, headers=headers, timeout_s=30.0)
        return _connection_post_result(payload, ok_fallback=ok_fallback, fail_fallback=fail_fallback)
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def api_get_transformation_objects(*, token: str | None = None) -> dict[str, Any]:
    return _get_transformation_list(
        ETL_TRANSFORMATION_OBJECT_PATH, token=token, fail_message="Failed to load objects."
    )


def api_get_transformation_object_by_id(
    object_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _get_transformation_by_id(
        ETL_TRANSFORMATION_OBJECT_PATH, object_id, token=token, fail_message="Failed to load object."
    )


def api_create_transformation_object(
    payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _post_transformation(
        ETL_TRANSFORMATION_OBJECT_PATH,
        payload,
        token=token,
        ok_fallback="Object created.",
        fail_fallback="Failed to create object.",
    )


def api_update_transformation_object(
    object_id: int | str, payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _put_transformation(
        ETL_TRANSFORMATION_OBJECT_PATH,
        object_id,
        payload,
        token=token,
        ok_fallback="Object updated.",
        fail_fallback="Failed to update object.",
    )


def api_delete_transformation_object(
    object_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _delete_transformation(
        ETL_TRANSFORMATION_OBJECT_PATH,
        object_id,
        token=token,
        ok_fallback="Object deleted.",
        fail_fallback="Failed to delete object.",
    )


def api_get_transformation_jobs(*, token: str | None = None) -> dict[str, Any]:
    return _get_transformation_list(
        ETL_TRANSFORMATION_JOB_PATH, token=token, fail_message="Failed to load jobs."
    )


def api_get_transformation_job_by_id(job_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    return _get_transformation_by_id(
        ETL_TRANSFORMATION_JOB_PATH, job_id, token=token, fail_message="Failed to load job."
    )


def api_get_transformation_jobs_by_object(
    object_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _get_transformation_by_parent(
        ETL_TRANSFORMATION_JOB_PATH,
        "object",
        object_id,
        token=token,
        fail_message="Failed to load jobs for object.",
    )


def api_create_transformation_job(
    payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _post_transformation(
        ETL_TRANSFORMATION_JOB_PATH,
        payload,
        token=token,
        ok_fallback="Job created.",
        fail_fallback="Failed to create job.",
    )


def api_update_transformation_job(
    job_id: int | str, payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _put_transformation(
        ETL_TRANSFORMATION_JOB_PATH,
        job_id,
        payload,
        token=token,
        ok_fallback="Job updated.",
        fail_fallback="Failed to update job.",
    )


def api_delete_transformation_job(job_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    return _delete_transformation(
        ETL_TRANSFORMATION_JOB_PATH,
        job_id,
        token=token,
        ok_fallback="Job deleted.",
        fail_fallback="Failed to delete job.",
    )


def api_get_transformation_workflows(*, token: str | None = None) -> dict[str, Any]:
    return _get_transformation_list(
        ETL_TRANSFORMATION_WORKFLOW_PATH, token=token, fail_message="Failed to load work flows."
    )


def api_get_transformation_workflow_by_id(
    workflow_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _get_transformation_by_id(
        ETL_TRANSFORMATION_WORKFLOW_PATH,
        workflow_id,
        token=token,
        fail_message="Failed to load work flow.",
    )


def api_get_transformation_workflows_by_job(
    job_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _get_transformation_by_parent(
        ETL_TRANSFORMATION_WORKFLOW_PATH,
        "job",
        job_id,
        token=token,
        fail_message="Failed to load work flows for job.",
    )


def api_create_transformation_workflow(
    payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _post_transformation(
        ETL_TRANSFORMATION_WORKFLOW_PATH,
        payload,
        token=token,
        ok_fallback="Work flow created.",
        fail_fallback="Failed to create work flow.",
    )


def api_update_transformation_workflow(
    workflow_id: int | str, payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _put_transformation(
        ETL_TRANSFORMATION_WORKFLOW_PATH,
        workflow_id,
        payload,
        token=token,
        ok_fallback="Work flow updated.",
        fail_fallback="Failed to update work flow.",
    )


def api_delete_transformation_workflow(
    workflow_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _delete_transformation(
        ETL_TRANSFORMATION_WORKFLOW_PATH,
        workflow_id,
        token=token,
        ok_fallback="Work flow deleted.",
        fail_fallback="Failed to delete work flow.",
    )


def api_get_transformation_flows(*, token: str | None = None) -> dict[str, Any]:
    return _get_transformation_list(
        ETL_TRANSFORMATION_FLOW_PATH, token=token, fail_message="Failed to load flows."
    )


def api_get_transformation_flow_by_id(
    flow_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _get_transformation_by_id(
        ETL_TRANSFORMATION_FLOW_PATH, flow_id, token=token, fail_message="Failed to load flow."
    )


def api_get_transformation_flows_by_workflow(
    workflow_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _get_transformation_by_parent(
        ETL_TRANSFORMATION_FLOW_PATH,
        "workflow",
        workflow_id,
        token=token,
        fail_message="Failed to load flows for work flow.",
    )


def api_create_transformation_flow(
    payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _post_transformation(
        ETL_TRANSFORMATION_FLOW_PATH,
        payload,
        token=token,
        ok_fallback="Flow created.",
        fail_fallback="Failed to create flow.",
    )


def api_update_transformation_flow(
    flow_id: int | str, payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _put_transformation(
        ETL_TRANSFORMATION_FLOW_PATH,
        flow_id,
        payload,
        token=token,
        ok_fallback="Flow updated.",
        fail_fallback="Failed to update flow.",
    )


def api_delete_transformation_flow(flow_id: int | str, *, token: str | None = None) -> dict[str, Any]:
    return _delete_transformation(
        ETL_TRANSFORMATION_FLOW_PATH,
        flow_id,
        token=token,
        ok_fallback="Flow deleted.",
        fail_fallback="Failed to delete flow.",
    )


def api_create_transformation_source(
    payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _post_transformation(
        ETL_TRANSFORMATION_SOURCE_PATH,
        payload,
        token=token,
        ok_fallback="Source configuration saved.",
        fail_fallback="Failed to save source configuration.",
    )


def api_update_transformation_source(
    source_id: int | str, payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _put_transformation(
        ETL_TRANSFORMATION_SOURCE_PATH,
        source_id,
        payload,
        token=token,
        ok_fallback="Source configuration updated.",
        fail_fallback="Failed to update source configuration.",
    )


def _transformation_source_not_found(
    payload: Any = None,
    *,
    http_code: int | None = None,
    message: str = "",
) -> bool:
    if http_code == 404:
        return True
    text = (message or "").strip().lower()
    if isinstance(payload, dict) and not text:
        text = str(payload.get("message") or payload.get("error") or "").strip().lower()
    if not text:
        return False
    markers = (
        "not found",
        "no source",
        "source not present",
        "does not exist",
        "doesn't exist",
        "not exist",
        "not present",
    )
    return any(marker in text for marker in markers)


def _parse_transformation_sources_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "content", "result", "sources", "sourceList", "source"):
        raw = payload.get(key)
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
    return []


def api_get_transformation_source_by_id(
    source_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _get_transformation_by_id(
        ETL_TRANSFORMATION_SOURCE_PATH,
        source_id,
        token=token,
        fail_message="Failed to load source configuration.",
    )


def api_get_transformation_sources_by_flow(
    flow_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    """GET source tables for a flow (``api/transformation/source/flow/{flowId}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    seg = _api_path_id_segment(flow_id)
    if not seg:
        return {"success": False, "message": "Flow ID is required.", "data": []}
    url = _api_url(f"{ETL_TRANSFORMATION_SOURCE_PATH}/flow/{seg}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load source configurations.", data=[]
            )
            if rej is not None:
                if _transformation_source_not_found(
                    payload, message=str(rej.get("message") or "")
                ):
                    return {"success": True, "data": [], "message": ""}
                return {**rej, "data": []}
        rows = _parse_transformation_sources_list(payload)
        if not rows:
            rows = _parse_transformation_list(payload)
        if not rows and isinstance(payload, dict):
            record = _transformation_record(payload)
            if isinstance(record, dict) and _transformation_step_has_data(
                record, "id", "sourceId", "source_id", "ID"
            ):
                rows = [record]
        return {"success": True, "data": rows, "message": ""}
    except HTTPError as exc:
        code = getattr(exc, "code", None)
        if code == 404:
            return {"success": True, "data": [], "message": ""}
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        message = _extract_error_message(
            err_payload, f"Request failed ({code or 'HTTP error'})."
        )
        if _transformation_source_not_found(err_payload, http_code=code, message=message):
            return {"success": True, "data": [], "message": ""}
        return {"success": False, "message": message, "data": []}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_delete_transformation_source(
    source_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _delete_transformation(
        ETL_TRANSFORMATION_SOURCE_PATH,
        source_id,
        token=token,
        ok_fallback="Source configuration deleted.",
        fail_fallback="Failed to delete source configuration.",
    )


def api_get_transformation_source_by_flow(
    flow_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    """Backward-compatible wrapper — returns first source row if any."""
    result = api_get_transformation_sources_by_flow(flow_id, token=token)
    if not result.get("success"):
        return result
    rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
    return {**result, "data": rows[0] if rows else None}


def api_create_transformation_target(
    payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _post_transformation(
        ETL_TRANSFORMATION_TARGET_PATH,
        payload,
        token=token,
        ok_fallback="Target configuration saved.",
        fail_fallback="Failed to save target configuration.",
    )


def api_update_transformation_target(
    target_id: int | str, payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _put_transformation(
        ETL_TRANSFORMATION_TARGET_PATH,
        target_id,
        payload,
        token=token,
        ok_fallback="Target configuration updated.",
        fail_fallback="Failed to update target configuration.",
    )


def _transformation_target_not_found(
    payload: Any = None,
    *,
    http_code: int | None = None,
    message: str = "",
) -> bool:
    if http_code == 404:
        return True
    text = (message or "").strip().lower()
    if isinstance(payload, dict) and not text:
        text = str(payload.get("message") or payload.get("error") or "").strip().lower()
    if not text:
        return False
    markers = (
        "not found",
        "no target",
        "target not present",
        "does not exist",
        "doesn't exist",
        "not exist",
        "not present",
    )
    return any(marker in text for marker in markers)


def _parse_transformation_targets_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "content", "result", "targets", "targetList", "target"):
        raw = payload.get(key)
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
        if isinstance(raw, dict):
            return [raw]
    if _transformation_step_has_data(payload, "id", "targetId", "target_id", "ID"):
        return [payload]
    return []


def api_get_transformation_targets_by_flow(
    flow_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    """GET target rows for a flow (``api/transformation/target/flow/{flowId}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    seg = _api_path_id_segment(flow_id)
    if not seg:
        return {"success": False, "message": "Flow ID is required.", "data": []}
    url = _api_url(f"{ETL_TRANSFORMATION_TARGET_PATH}/flow/{seg}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load target configuration.", data=[]
            )
            if rej is not None:
                if _transformation_target_not_found(
                    payload, message=str(rej.get("message") or "")
                ):
                    return {"success": True, "data": [], "message": ""}
                return {**rej, "data": []}
        rows = _parse_transformation_targets_list(payload)
        if not rows:
            rows = _parse_transformation_list(payload)
        if not rows and isinstance(payload, dict):
            record = _transformation_record(payload)
            if isinstance(record, dict) and _transformation_step_has_data(
                record, "id", "targetId", "target_id", "ID"
            ):
                rows = [record]
        return {"success": True, "data": rows, "message": ""}
    except HTTPError as exc:
        code = getattr(exc, "code", None)
        if code == 404:
            return {"success": True, "data": [], "message": ""}
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        message = _extract_error_message(
            err_payload, f"Request failed ({code or 'HTTP error'})."
        )
        if _transformation_target_not_found(err_payload, http_code=code, message=message):
            return {"success": True, "data": [], "message": ""}
        return {"success": False, "message": message, "data": []}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_get_transformation_target_by_flow(
    flow_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    """Backward-compatible wrapper — returns first target row if any."""
    result = api_get_transformation_targets_by_flow(flow_id, token=token)
    if not result.get("success"):
        return result
    rows = [r for r in (result.get("data") or []) if isinstance(r, dict)]
    return {**result, "data": rows[0] if rows else None}


def _parse_transformation_columns_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "content", "result", "columns", "columnList"):
        raw = payload.get(key)
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
    return []


def _transformation_columns_not_found(
    payload: Any = None,
    *,
    http_code: int | None = None,
    message: str = "",
) -> bool:
    if http_code == 404:
        return True
    text = (message or "").strip().lower()
    if isinstance(payload, dict) and not text:
        text = str(payload.get("message") or payload.get("error") or "").strip().lower()
    if not text:
        return False
    markers = (
        "not found",
        "no column",
        "columns not present",
        "does not exist",
        "doesn't exist",
        "not exist",
        "not present",
    )
    return any(marker in text for marker in markers)


def api_create_transformation_column(
    payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _post_transformation(
        ETL_TRANSFORMATION_COLUMN_PATH,
        payload,
        token=token,
        ok_fallback="Column mapping saved.",
        fail_fallback="Failed to save column mapping.",
    )


def api_update_transformation_column(
    column_id: int | str, payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _put_transformation(
        ETL_TRANSFORMATION_COLUMN_PATH,
        column_id,
        payload,
        token=token,
        ok_fallback="Column mapping updated.",
        fail_fallback="Failed to update column mapping.",
    )


def api_get_transformation_columns_by_flow(
    flow_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    """GET column mappings for a flow (``api/transformation/column/flow/{flowId}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    seg = _api_path_id_segment(flow_id)
    if not seg:
        return {"success": False, "message": "Flow ID is required.", "data": []}
    url = _api_url(f"{ETL_TRANSFORMATION_COLUMN_PATH}/flow/{seg}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load column mappings.", data=[]
            )
            if rej is not None:
                if _transformation_columns_not_found(
                    payload, message=str(rej.get("message") or "")
                ):
                    return {"success": True, "data": [], "message": ""}
                return {**rej, "data": []}
        rows = _parse_transformation_columns_list(payload)
        return {"success": True, "data": rows, "message": ""}
    except HTTPError as exc:
        code = getattr(exc, "code", None)
        if code == 404:
            return {"success": True, "data": [], "message": ""}
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        message = _extract_error_message(
            err_payload, f"Request failed ({code or 'HTTP error'})."
        )
        if _transformation_columns_not_found(err_payload, http_code=code, message=message):
            return {"success": True, "data": [], "message": ""}
        return {"success": False, "message": message, "data": []}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_delete_transformation_columns_by_flow(
    flow_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    """DELETE all column mappings for a flow (``api/transformation/column/flow/{flowId}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again."}
    seg = _api_path_id_segment(flow_id)
    if not seg:
        return {"success": False, "message": "Flow ID is required."}
    url = _api_url(f"{ETL_TRANSFORMATION_COLUMN_PATH}/flow/{seg}")
    try:
        payload = _http_delete(url, headers=headers, timeout_s=30.0)
        return _connection_post_result(
            payload,
            ok_fallback="Column mappings deleted.",
            fail_fallback="Failed to delete column mappings.",
        )
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        return {
            "success": False,
            "message": _extract_error_message(
                err_payload, f"Delete failed ({getattr(exc, 'code', 'HTTP error')})."
            ),
        }
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}


def _parse_transformation_joins_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "content", "result", "joins", "joinList"):
        raw = payload.get(key)
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
    return []


def _transformation_joins_not_found(
    payload: Any = None,
    *,
    http_code: int | None = None,
    message: str = "",
) -> bool:
    if http_code == 404:
        return True
    text = (message or "").strip().lower()
    if isinstance(payload, dict) and not text:
        text = str(payload.get("message") or payload.get("error") or "").strip().lower()
    if not text:
        return False
    markers = (
        "not found",
        "no join",
        "joins not present",
        "does not exist",
        "doesn't exist",
        "not exist",
        "not present",
    )
    return any(marker in text for marker in markers)


def api_create_transformation_join(
    payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _post_transformation(
        ETL_TRANSFORMATION_JOIN_PATH,
        payload,
        token=token,
        ok_fallback="Join configuration saved.",
        fail_fallback="Failed to save join configuration.",
    )


def api_update_transformation_join(
    join_id: int | str, payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _put_transformation(
        ETL_TRANSFORMATION_JOIN_PATH,
        join_id,
        payload,
        token=token,
        ok_fallback="Join configuration updated.",
        fail_fallback="Failed to update join configuration.",
    )


def api_get_transformation_join_by_id(
    join_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _get_transformation_by_id(
        ETL_TRANSFORMATION_JOIN_PATH,
        join_id,
        token=token,
        fail_message="Failed to load join configuration.",
    )


def api_get_transformation_joins_by_flow(
    flow_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    """GET join configurations for a flow (``api/transformation/join/flow/{flowId}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    seg = _api_path_id_segment(flow_id)
    if not seg:
        return {"success": False, "message": "Flow ID is required.", "data": []}
    url = _api_url(f"{ETL_TRANSFORMATION_JOIN_PATH}/flow/{seg}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load join configurations.", data=[]
            )
            if rej is not None:
                if _transformation_joins_not_found(
                    payload, message=str(rej.get("message") or "")
                ):
                    return {"success": True, "data": [], "message": ""}
                return {**rej, "data": []}
        rows = _parse_transformation_joins_list(payload)
        return {"success": True, "data": rows, "message": ""}
    except HTTPError as exc:
        code = getattr(exc, "code", None)
        if code == 404:
            return {"success": True, "data": [], "message": ""}
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        message = _extract_error_message(
            err_payload, f"Request failed ({code or 'HTTP error'})."
        )
        if _transformation_joins_not_found(err_payload, http_code=code, message=message):
            return {"success": True, "data": [], "message": ""}
        return {"success": False, "message": message, "data": []}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_delete_transformation_join(
    join_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _delete_transformation(
        ETL_TRANSFORMATION_JOIN_PATH,
        join_id,
        token=token,
        ok_fallback="Join configuration deleted.",
        fail_fallback="Failed to delete join configuration.",
    )


def _parse_transformation_steps_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", "content", "result", "steps", "stepList"):
        raw = payload.get(key)
        if isinstance(raw, list):
            return [r for r in raw if isinstance(r, dict)]
    return []


def _transformation_steps_not_found(
    payload: Any = None,
    *,
    http_code: int | None = None,
    message: str = "",
) -> bool:
    if http_code == 404:
        return True
    text = (message or "").strip().lower()
    if isinstance(payload, dict) and not text:
        text = str(payload.get("message") or payload.get("error") or "").strip().lower()
    if not text:
        return False
    markers = (
        "not found",
        "no step",
        "steps not present",
        "does not exist",
        "doesn't exist",
        "not exist",
        "not present",
    )
    return any(marker in text for marker in markers)


def api_get_transformation_step_masters(*, token: str | None = None) -> dict[str, Any]:
    """GET step master catalog (``api/transformation/step-master``)."""
    return _get_transformation_list(
        ETL_TRANSFORMATION_STEP_MASTER_PATH,
        token=token,
        fail_message="Failed to load step masters.",
    )


def api_create_transformation_step(
    payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _post_transformation(
        ETL_TRANSFORMATION_STEP_PATH,
        payload,
        token=token,
        ok_fallback="Transform step saved.",
        fail_fallback="Failed to save transform step.",
    )


def api_update_transformation_step(
    step_id: int | str, payload: dict[str, Any], *, token: str | None = None
) -> dict[str, Any]:
    return _put_transformation(
        ETL_TRANSFORMATION_STEP_PATH,
        step_id,
        payload,
        token=token,
        ok_fallback="Transform step updated.",
        fail_fallback="Failed to update transform step.",
    )


def api_get_transformation_step_by_id(
    step_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _get_transformation_by_id(
        ETL_TRANSFORMATION_STEP_PATH,
        step_id,
        token=token,
        fail_message="Failed to load transform step.",
    )


def api_get_transformation_steps_by_flow(
    flow_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    """GET transform steps for a flow (``api/transformation/step/flow/{flowId}``)."""
    headers = _connections_auth_headers(token)
    if headers is None:
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    seg = _api_path_id_segment(flow_id)
    if not seg:
        return {"success": False, "message": "Flow ID is required.", "data": []}
    url = _api_url(f"{ETL_TRANSFORMATION_STEP_PATH}/flow/{seg}")
    try:
        payload = _http_get_json(url, headers=headers, timeout_s=30.0)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to load transform steps.", data=[]
            )
            if rej is not None:
                if _transformation_steps_not_found(
                    payload, message=str(rej.get("message") or "")
                ):
                    return {"success": True, "data": [], "message": ""}
                return {**rej, "data": []}
        rows = _parse_transformation_steps_list(payload)
        return {"success": True, "data": rows, "message": ""}
    except HTTPError as exc:
        code = getattr(exc, "code", None)
        if code == 404:
            return {"success": True, "data": [], "message": ""}
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        message = _extract_error_message(
            err_payload, f"Request failed ({code or 'HTTP error'})."
        )
        if _transformation_steps_not_found(err_payload, http_code=code, message=message):
            return {"success": True, "data": [], "message": ""}
        return {"success": False, "message": message, "data": []}
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable.", "data": []}


def api_delete_transformation_step(
    step_id: int | str, *, token: str | None = None
) -> dict[str, Any]:
    return _delete_transformation(
        ETL_TRANSFORMATION_STEP_PATH,
        step_id,
        token=token,
        ok_fallback="Transform step deleted.",
        fail_fallback="Failed to delete transform step.",
    )
