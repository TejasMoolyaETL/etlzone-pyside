"""API client for login and sign out."""

from __future__ import annotations

import base64
import json
import sys
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from core.config import (
    API_BASE_URL,
    API_DETAILS_ALL_IN_ONE_PATH,
    GET_APP_STEP_LIST_PATH,
    COMMENT_ADD_PATH,
    COMMENT_DELETE_BY_ID_PATH,
    COMMENT_GET_ALL_BY_VALIDATION_ID_PATH,
    COMMENT_GET_BY_ID_PATH,
    COMMENT_UPDATE_BY_ID_PATH,
    DELETE_API_DETAIL_PATH,
    DELETE_API_VALIDATION_PATH,
    DELETE_USER_PATH,
    LOGIN_URL,
    RESET_USER_PASSWORD_PATH,
    UPDATE_USER_ROLE_STATUS_PATH,
    UPDATE_USER_STATUS_PATH,
    UPDATE_PROFILE_PATH,
    UPDATE_USER_PATH,
)


def _log_api(method: str, url: str, body: Any = None, response: Any = None, status: int | None = None) -> None:
    """Log API request and response to console (not in app). Redacts password in body."""
    out = sys.stderr
    req_key = f"{method} {url}"
    if not hasattr(_log_api, "_pending"):
        _log_api._pending = {}  # type: ignore[attr-defined]
    pending = _log_api._pending  # type: ignore[attr-defined]
    if response is None:
        pending.setdefault(req_key, []).append(time.perf_counter())
        print(f"[API] REQUEST: {method} {url}", file=out, flush=True)
    if body is not None:
        try:
            safe_body = body
            if isinstance(body, dict) and "password" in body:
                safe_body = {k: ("***" if k == "password" else v) for k, v in body.items()}
            s = json.dumps(safe_body, indent=2) if isinstance(safe_body, dict) else str(safe_body)
            print(f"[API] REQUEST BODY:\n{s}", file=out, flush=True)
        except Exception:
            print(f"[API] REQUEST BODY: (non-serializable)", file=out, flush=True)
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
            print(f"[API] RESPONSE{status_str}{elapsed_suffix}:\n{s}", file=out, flush=True)
        except Exception:
            print(f"[API] RESPONSE: (non-serializable)", file=out, flush=True)


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
    _log_api("GET", url)
    hdrs: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
    }
    if headers:
        hdrs.update(headers)
    req = Request(url, headers=hdrs, method="GET")
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    if not raw:
        _log_api("GET", url, response={})
        return {}
    data = json.loads(raw.decode("utf-8"))
    _log_api("GET", url, response=data, status=getattr(resp, "status", None))
    return data


def _http_post_json(url: str, payload: dict[str, Any], *, timeout_s: float = 8.0) -> Any:
    """HTTP POST JSON returning parsed JSON (or {} if empty)."""
    _log_api("POST", url, body=payload)
    data = json.dumps(payload).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "MY-ETLZONE-App/1.0",
        },
        method="POST",
    )
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    if not raw:
        _log_api("POST", url, body=payload, response={})
        return {}
    result = json.loads(raw.decode("utf-8"))
    _log_api("POST", url, body=payload, response=result, status=getattr(resp, "status", None))
    return result


def _http_put_json(
    url: str,
    payload: dict[str, Any],
    *,
    timeout_s: float = 8.0,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, Any]:
    """HTTP PUT JSON. Returns ``(http_status, parsed body or {})``."""
    _log_api("PUT", url, body=payload)
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
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
        status = int(getattr(resp, "status", 200) or 200)
    if not raw:
        _log_api("PUT", url, body=payload, response={}, status=status)
        return status, {}
    try:
        result = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError:
        result = {}
    _log_api("PUT", url, body=payload, response=result, status=status)
    return status, result


def _http_patch(url: str, *, headers: dict[str, str] | None = None, timeout_s: float = 8.0) -> Any:
    """HTTP PATCH (no body) returning parsed JSON (or {} if empty)."""
    _log_api("PATCH", url)
    hdrs: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
    }
    if headers:
        hdrs.update(headers)
    req = Request(url, headers=hdrs, method="PATCH")
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
        http_status = getattr(resp, "status", None)
    if not raw:
        _log_api("PATCH", url, response={})
        return {}
    result = json.loads(raw.decode("utf-8"))
    _log_api("PATCH", url, response=result, status=http_status)
    return result


def _http_delete(url: str, *, headers: dict[str, str] | None = None, timeout_s: float = 8.0) -> Any:
    """HTTP DELETE returning parsed JSON (or {} if empty)."""
    _log_api("DELETE", url)
    hdrs: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
    }
    if headers:
        hdrs.update(headers)
    req = Request(url, headers=hdrs, method="DELETE")
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    if not raw:
        _log_api("DELETE", url, response={})
        return {}
    result = json.loads(raw.decode("utf-8"))
    _log_api("DELETE", url, response=result, status=getattr(resp, "status", None))
    return result


def _http_delete_json(
    url: str,
    body: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout_s: float = 8.0,
) -> Any:
    """HTTP DELETE with JSON body, returning parsed JSON (or {} if empty)."""
    _log_api("DELETE", url, body=body)
    hdrs: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
    }
    if headers:
        hdrs.update(headers)
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers=hdrs, method="DELETE")
    with urlopen(req, timeout=timeout_s) as resp:
        raw = resp.read()
    if not raw:
        _log_api("DELETE", url, body=body, response={})
        return {}
    result = json.loads(raw.decode("utf-8"))
    _log_api("DELETE", url, body=body, response=result, status=getattr(resp, "status", None))
    return result


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


def _json_payload_indicates_business_failure(payload: Any) -> bool:
    """True when JSON marks business failure (success False or status FAILURE/FAILED/ERROR); HTTP may be 2xx."""
    if not isinstance(payload, dict):
        return False
    if payload.get("success") is False:
        return True
    st = str(payload.get("status", "")).strip().upper()
    return st in ("FAILURE", "FAILED", "ERROR")


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
    """GET api-access/getAppStepList — left-nav access. Requires Bearer JWT.

    Returns ``success``, ``message``, and ``steps`` (list of dicts). On failure,
    ``steps`` is ``[]`` so callers can treat as "do not restrict" via separate logic.
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
    _log_api(method, url, body=body)
    data = json.dumps(body).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api(method, url, body=body, response=payload, status=getattr(resp, "status", None))
        return (payload, None)
    except HTTPError as exc:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
            _log_api(method, url, body=body, response=err_payload, status=getattr(exc, "code", None))
        except Exception:
            pass
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
    """Fetch all users from GET api/get-all-user. Requires JWT.

    Returns dict with:
    - success: bool
    - data: list of user dicts (when success=True)
    - message: str (when success=False)
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("api/get-all-user")
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
    """Fetch all organizations from GET api/orgs/get-all-orgs. Requires JWT.

    Returns dict with:
    - success: bool
    - data: list of org dicts (when success=True)
    - message: str (when success=False)
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("api/orgs/get-all-orgs")
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
    status: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Create organization via POST api/orgs/create-org. Requires JWT.

    Request body: orgName, orgCode, industry, status.
    Returns dict with success, message. On success, may include created org data.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/orgs/create-org")
    body: dict[str, Any] = {
        "orgName": (org_name or "").strip(),
        "orgCode": (org_code or "").strip(),
        "industry": (industry or "").strip(),
        "status": (status or "ACTIVE").strip().upper(),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
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
    status: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Update organization via PUT api/orgs/update-org-by-id/{org_id}. Requires JWT.

    Request body: orgName, orgCode, industry, status.
    Returns dict with success, message. On success, may include updated org data.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/orgs/update-org-by-id/{org_id}")
    body: dict[str, Any] = {
        "orgName": (org_name or "").strip(),
        "orgCode": (org_code or "").strip(),
        "industry": (industry or "").strip(),
        "status": (status or "ACTIVE").strip().upper(),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
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
    """Delete organization via DELETE api/orgs/delete-org-by-id/{org_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/orgs/delete-org-by-id/{org_id}")
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
    """Fetch all business units from GET api/bu/get-all-bu. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("api/bu/get-all-bu")
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
    """Fetch all departments from GET departments/get-all-depts. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("departments/get-all-depts")
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
    token: str | None = None,
) -> dict[str, Any]:
    """Create department via POST departments/create-dept. Body: buId, deptName; parentDeptId if set."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("departments/create-dept")
    body: dict[str, Any] = {
        "buId": int(bu_id),
        "deptName": (dept_name or "").strip(),
    }
    if parent_dept_id is not None:
        body["parentDeptId"] = int(parent_dept_id)
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=8.0) as resp:
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
    token: str | None = None,
) -> dict[str, Any]:
    """Update department via PUT departments/update-dept-by-id/{dept_id}. Body: buId, deptName; parentDeptId if set."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"departments/update-dept-by-id/{dept_id}")
    body: dict[str, Any] = {
        "buId": int(bu_id),
        "deptName": (dept_name or "").strip(),
    }
    if parent_dept_id is not None:
        body["parentDeptId"] = int(parent_dept_id)
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        _log_api("PUT", url, body=body)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None) or resp.getcode() or 200

        if not raw or not str(raw).strip():
            _log_api("PUT", url, body=body, response="(empty body)", status=status)
            return {"success": True, "message": "Department updated successfully."}

        try:
            payload: Any = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            if 200 <= int(status) < 300:
                return {"success": True, "message": "Department updated successfully."}
            return {"success": False, "message": "Invalid response from server."}

        if payload is True:
            _log_api("PUT", url, body=body, response=payload, status=status)
            return {"success": True, "message": "Department updated successfully."}

        if isinstance(payload, dict):
            if payload.get("success") is False:
                _log_api("PUT", url, body=body, response=payload, status=status)
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to update department."),
                }
            if payload.get("error") is not None or payload.get("errors") is not None:
                _log_api("PUT", url, body=body, response=payload, status=status)
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
                _log_api("PUT", url, body=body, response=payload, status=status)
                return {
                    "success": True,
                    "message": payload.get("message", "Department updated."),
                    "data": payload,
                }
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to update department."
            )
            if rej is not None:
                _log_api("PUT", url, body=body, response=payload, status=status)
                return rej
            if 200 <= int(status) < 300:
                _log_api("PUT", url, body=body, response=payload, status=status)
                return {
                    "success": True,
                    "message": payload.get("message", "Department updated."),
                    "data": payload,
                }

        _log_api("PUT", url, body=body, response=payload, status=status)
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
    """Delete department via DELETE departments/delete-dept-by-id/{dept_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"departments/delete-dept-by-id/{dept_id}")
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
    """Fetch all positions from GET api/positions/get-all-positions. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("api/positions/get-all-positions")
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
    token: str | None = None,
) -> dict[str, Any]:
    """Create position via POST api/positions/create-position. Body: positionName, hierarchyLevel."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/positions/create-position")
    body: dict[str, Any] = {
        "positionName": (position_name or "").strip(),
        "hierarchyLevel": int(hierarchy_level),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        if isinstance(payload, dict):
            status = str(payload.get("status", "")).strip().upper()
            if status in ("FAILURE", "FAILED", "ERROR"):
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to create position."),
                }
            ok = (
                payload.get("success") is True
                or status == "SUCCESS"
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
    token: str | None = None,
) -> dict[str, Any]:
    """Update position via PUT api/positions/update-position-by-id/{position_id}. Body: positionName, hierarchyLevel."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/positions/update-position-by-id/{position_id}")
    body: dict[str, Any] = {
        "positionName": (position_name or "").strip(),
        "hierarchyLevel": int(hierarchy_level),
    }
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        _log_api("PUT", url, body=body)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None) or resp.getcode() or 200

        if not raw or not str(raw).strip():
            _log_api("PUT", url, body=body, response="(empty body)", status=status)
            return {"success": True, "message": "Position updated successfully."}

        try:
            payload: Any = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            if 200 <= int(status) < 300:
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
                _log_api("PUT", url, body=body, response=payload, status=status)
                return {
                    "success": True,
                    "message": payload.get("message", "Position updated."),
                    "data": payload,
                }
            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to update position."
            )
            if rej is not None:
                _log_api("PUT", url, body=body, response=payload, status=status)
                return rej
            if 200 <= int(status) < 300:
                _log_api("PUT", url, body=body, response=payload, status=status)
                return {
                    "success": True,
                    "message": payload.get("message", "Position updated."),
                    "data": payload,
                }

        _log_api("PUT", url, body=body, response=payload, status=status)
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
    """Delete position via DELETE api/positions/delete-position-by-id/{position_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/positions/delete-position-by-id/{position_id}")
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
    """Fetch all roles from GET roles/get-all-roles. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("roles/get-all-roles")
    headers: dict[str, str] = {"Authorization": f"Bearer {token}"}
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
    """Create role via POST roles/create-role?roleName=<name> (query param, no body). Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    name = (role_name or "").strip()
    if not name:
        return {"success": False, "message": "Role name is required."}
    base = _api_url("roles/create-role")
    url = f"{base}?{urlencode({'roleName': name})}"
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        # POST with empty body; roleName is only in the query string (matches backend / Postman).
        req = Request(url, data=b"", headers=headers, method="POST")
        with urlopen(req, timeout=8.0) as resp:
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
    """Update role via PUT roles/update-role-by-id/{role_id}?roleName=<name> (query param, no body). Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    name = (role_name or "").strip()
    if not name:
        return {"success": False, "message": "Role name is required."}
    base = _api_url(f"roles/update-role-by-id/{role_id}")
    url = f"{base}?{urlencode({'roleName': name})}"
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, data=b"", headers=headers, method="PUT")
        with urlopen(req, timeout=8.0) as resp:
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
    """Delete role via DELETE roles/delete-role-by-id/{role_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"roles/delete-role-by-id/{role_id}")
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
    token: str | None = None,
) -> dict[str, Any]:
    """Create business unit via POST api/bu/create-bu. Body: organizationId, buName, parentBu (null if omitted)."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/bu/create-bu")
    body: dict[str, Any] = {
        "organizationId": int(organization_id),
        "buName": (bu_name or "").strip(),
    }
    if parent_bu is not None:
        body["parentBu"] = int(parent_bu)
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
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
    token: str | None = None,
) -> dict[str, Any]:
    """Update business unit via PUT api/bu/update-bu-by-id/{bu_id}. Body: organizationId, buName; parentBu if set."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/bu/update-bu-by-id/{bu_id}")
    body: dict[str, Any] = {
        "organizationId": int(organization_id),
        "buName": (bu_name or "").strip(),
    }
    if parent_bu is not None:
        body["parentBu"] = int(parent_bu)
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    try:
        _log_api("PUT", url, body=body)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None) or resp.getcode() or 200

        # Many backends return 200/204 with empty body or minimal JSON on success.
        if not raw or not str(raw).strip():
            _log_api("PUT", url, body=body, response="(empty body)", status=status)
            return {"success": True, "message": "Business unit updated successfully."}

        try:
            payload: Any = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            if 200 <= int(status) < 300:
                return {"success": True, "message": "Business unit updated successfully."}
            return {"success": False, "message": "Invalid response from server."}

        if payload is True:
            _log_api("PUT", url, body=body, response=payload, status=status)
            return {"success": True, "message": "Business unit updated successfully."}

        if isinstance(payload, dict):
            if payload.get("success") is False:
                _log_api("PUT", url, body=body, response=payload, status=status)
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to update business unit."),
                }
            if payload.get("error") is not None or payload.get("errors") is not None:
                _log_api("PUT", url, body=body, response=payload, status=status)
                return {
                    "success": False,
                    "message": _extract_error_message(payload, "Failed to update business unit."),
                }

            inner = payload.get("data")
            if isinstance(inner, dict) and ("buId" in inner or "bu_id" in inner):
                _log_api("PUT", url, body=body, response=payload, status=status)
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
                _log_api("PUT", url, body=body, response=payload, status=status)
                return {
                    "success": True,
                    "message": payload.get("message", "Business unit updated."),
                    "data": payload,
                }

            rej = _reject_json_business_failure(
                payload, message_fallback="Failed to update business unit."
            )
            if rej is not None:
                _log_api("PUT", url, body=body, response=payload, status=status)
                return rej

            # 2xx with JSON but no explicit markers — treat as success (entity-only responses).
            if 200 <= int(status) < 300:
                _log_api("PUT", url, body=body, response=payload, status=status)
                return {
                    "success": True,
                    "message": payload.get("message", "Business unit updated."),
                    "data": payload,
                }

        _log_api("PUT", url, body=body, response=payload, status=status)
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
    """Delete business unit via DELETE api/bu/delete-bu-by-id/{bu_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/bu/delete-bu-by-id/{bu_id}")
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
        with urlopen(req, timeout=8.0) as resp:
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
        with urlopen(req, timeout=8.0) as resp:
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
        with urlopen(req, timeout=8.0) as resp:
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
        with urlopen(req, timeout=8.0) as resp:
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
    """Create user via POST api/create-user. Requires JWT (only api/auth/login is unauthenticated).

    Request body: firstName, lastName, email, mobileNumber, password, status, orgId, deptId, positionId.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/create-user")
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
        _log_api("POST", url, body=body)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("POST", url, body=body, response=payload, status=getattr(resp, "status", None))
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
            _log_api("POST", url, body=body, response=err_payload, status=getattr(exc, "code", None))
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
    buId: int | None = None,
) -> dict[str, Any]:
    """Update user via PUT api/update-user-by-id/{user_id} (or POST if PUT returns 403). Requires JWT.

    Request body: email, firstName, lastName, mobileNumber (country code + national digits),
    orgId, deptId, positionId, and optionally buId when supported by the API.
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
    if buId is not None:
        body["buId"] = buId
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        data = json.dumps(body).encode("utf-8")
        for method in ("PUT", "POST"):
            _log_api(method, url, body=body)
            req = Request(url, data=data, headers=headers, method=method)
            try:
                with urlopen(req, timeout=8.0) as resp:
                    raw = resp.read()
            except HTTPError as exc:
                if exc.code == 403 and method == "PUT":
                    continue
                raise
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            _log_api(method, url, body=body, response=payload, status=getattr(resp, "status", None) if raw else None)
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
            _log_api("PUT", url, body=body, response=err_payload, status=getattr(exc, "code", None))
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
    """Delete user via DELETE api/delete-user-by-id/{user_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"{DELETE_USER_PATH.rstrip('/')}/{user_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        _log_api("DELETE", url)
        req = Request(url, headers=headers, method="DELETE")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("DELETE", url, response=payload, status=getattr(resp, "status", None))
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
    """POST api/reset-user-password with JSON { userName, password }. Requires JWT."""
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
        _log_api("POST", url, body=body)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("POST", url, body=body, response=payload, status=getattr(resp, "status", None))
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
        _log_api("POST", url, body=body)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("POST", url, body=body, response=payload, status=getattr(resp, "status", None))
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
        _log_api("POST", url, body=body)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("POST", url, body=body, response=payload, status=getattr(resp, "status", None))
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
    """Assign role to user via POST user-role/assign. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("user-role/assign")
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
        _log_api("POST", url, body=body)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("POST", url, body=body, response=payload, status=getattr(resp, "status", None))
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
    """Delete user-role assignment via DELETE delete-user-role-assignment-by-id/{id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"delete-user-role-assignment-by-id/{assignment_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        _log_api("DELETE", url)
        req = Request(url, headers=headers, method="DELETE")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("DELETE", url, response=payload, status=getattr(resp, "status", None))
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
    """PUT update-user-role-assignment-by-id/{id} — JSON body like curl (userId, roleId, validFrom, validTo, defaultRole, status)."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}

    def _json_int_id(v: int | str) -> int | str:
        if isinstance(v, bool):
            return v
        if isinstance(v, int):
            return v
        s = str(v).strip()
        return int(s) if s.isdigit() else v

    url = _api_url(f"update-user-role-assignment-by-id/{assignment_id}")
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
        _log_api("PUT", url, body=body)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        print(f"[UPDATE USER ROLE] RESPONSE: {json.dumps(payload)}", flush=True)
        _log_api("PUT", url, body=body, response=payload, status=getattr(resp, "status", None))
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


def api_get_all_api_details(*, token: str | None = None) -> dict[str, Any]:
    """Fetch all API details from GET api/get-all-api-details. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
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
    """GET apis/get-all-apis — operational API catalog (governance). Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("apis/get-all-apis")
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
        _log_api("GET", url)
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
            status = getattr(resp, "status", None)
        payload: Any = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("GET", url, response=payload, status=status)
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
    """POST apis/create-api — create API catalog entry. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("apis/create-api")
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
        _log_api("POST", url, body=body)
        with urlopen(req, timeout=8) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            _log_api("POST", url, body=body, response=payload, status=getattr(resp, "status", None))
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
            _log_api(
                "POST",
                url,
                body=body,
                response=err_payload or {"error": f"HTTP {getattr(exc, 'code', 'error')}"},
                status=getattr(exc, "code", None),
            )
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
    """PUT apis/update-api-by-id/{api_id} — update operational API catalog entry. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"apis/update-api-by-id/{api_id}")
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
        _log_api("PUT", url, body=body)
        with urlopen(req, timeout=8) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            _log_api("PUT", url, body=body, response=payload, status=getattr(resp, "status", None))
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
            _log_api(
                "PUT",
                url,
                body=body,
                response=err_payload or {"error": f"HTTP {getattr(exc, 'code', 'error')}"},
                status=getattr(exc, "code", None),
            )
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
    """DELETE apis/delete-api-by-id/{api_id} — remove operational API catalog entry. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"apis/delete-api-by-id/{api_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, headers=headers, method="DELETE")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("DELETE", url, response=payload, status=status)
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
    """GET get-all-app-id — list app identifiers (host root path). Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("get-all-app-id")
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
    """POST create-app-id — JSON body with description. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("create-app-id")
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
        _log_api("POST", url, body=body)
        with urlopen(req, timeout=8) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            _log_api("POST", url, body=body, response=payload, status=getattr(resp, "status", None))
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
            _log_api(
                "POST",
                url,
                body=body,
                response=err_payload or {"error": f"HTTP {getattr(exc, 'code', 'error')}"},
                status=getattr(exc, "code", None),
            )
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
    """PUT update-app-id/{app_id} — JSON body with description. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"update-app-id/{app_id}")
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
        _log_api("PUT", url, body=body)
        with urlopen(req, timeout=8) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            _log_api("PUT", url, body=body, response=payload, status=getattr(resp, "status", None))
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
            _log_api(
                "PUT",
                url,
                body=body,
                response=err_payload or {"error": f"HTTP {getattr(exc, 'code', 'error')}"},
                status=getattr(exc, "code", None),
            )
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
    """DELETE delete-by-app-id/{app_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"delete-by-app-id/{app_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        # Match curl: DELETE with Content-Type and no body (--data '').
        req = Request(url, headers=headers, method="DELETE")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("DELETE", url, response=payload, status=status)
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
    role_id: int | str,
    api_id: int | str,
    token: str | None = None,
) -> dict[str, Any]:
    """POST api-access/grant?roleId={role_id}&apiId={api_id} — grant API access to role."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    query = urlencode({"roleId": role_id, "apiId": api_id})
    url = _api_url(f"api-access/grant?{query}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        req = Request(url, headers=headers, method="POST")
        _log_api("POST", url)
        with urlopen(req, timeout=8) as resp:
            raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            _log_api("POST", url, response=payload, status=getattr(resp, "status", None))
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
            _log_api(
                "POST",
                url,
                response=err_payload or {"error": f"HTTP {getattr(exc, 'code', 'error')}"},
                status=getattr(exc, "code", None),
            )
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


def api_get_api_access_by_api_id(
    api_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """GET api-access/get-by-api-id/{api_id} — return roles assigned to API."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url(f"api-access/get-by-api-id/{api_id}")
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


def api_change_api_access_by_id(
    assign_id: int | str,
    status: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """PATCH api-access/change-access-api-by-id/{assign_id}/{status} — update role-API access status."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    status_seg = str(status).strip().upper().replace(" ", "_")
    if not status_seg:
        return {"success": False, "message": "Status is required."}
    url = _api_url(f"api-access/change-access-api-by-id/{assign_id}/{status_seg}")
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


def api_delete_api_access_by_id(
    assign_id: int | str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """DELETE api-access/delete-access-api-by-id/{assign_id} — remove role-API assignment."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api-access/delete-access-api-by-id/{assign_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        payload = _http_delete(url, headers=headers)
        if isinstance(payload, dict):
            rej = _reject_json_business_failure(
                payload, message_fallback="Remove API access failed.", data=payload
            )
            if rej is not None:
                return rej
        return {
            "success": True,
            "message": _extract_error_message(payload, "Access removed."),
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
        return {"success": False, "message": "Backend not reachable."}


def api_create_api_detail(
    project_id: int | str,
    *,
    token: str | None = None,
    folder: str | None = None,
    api_method: str | None = None,
    api_name: str | None = None,
    localhost_path: str | None = None,
    server_path: str | None = None,
    requirement: str | None = None,
    api_status: str | None = None,
    comments: str | None = None,
    request_body: str | None = None,
    response_body: str | None = None,
) -> dict[str, Any]:
    """Create API detail via POST api/create-api-detail/{project_id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/create-api-detail/{project_id}")
    body: dict[str, Any] = {
        "folder": (folder or "").strip(),
        "apiMethod": (api_method or "").strip().upper(),
        "apiName": (api_name or "").strip(),
        "localhostPath": (localhost_path or "").strip(),
        "serverPath": (server_path or "").strip(),
        "requirement": (requirement or "").strip(),
        "apiStatus": (api_status or "ACTIVE").strip().upper(),
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
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("POST", url, body=body, response=payload, status=status)
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
    folder: str | None = None,
    api_method: str | None = None,
    api_name: str | None = None,
    localhost_path: str | None = None,
    server_path: str | None = None,
    requirement: str | None = None,
    api_status: str | None = None,
    comments: str | None = None,
    request_body: str | None = None,
    response_body: str | None = None,
) -> dict[str, Any]:
    """Update API detail via PUT api/update-api-detail-by-id/{id}. Requires JWT."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"api/update-api-detail-by-id/{api_id}")
    body: dict[str, Any] = {
        "folder": (folder or "").strip(),
        "apiMethod": (api_method or "").strip().upper(),
        "apiName": (api_name or "").strip(),
        "localhostPath": (localhost_path or "").strip(),
        "serverPath": (server_path or "").strip(),
        "requirement": (requirement or "").strip(),
        "apiStatus": (api_status or "ACTIVE").strip().upper(),
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
        req = Request(url, data=data, headers=headers, method="PUT")
        with urlopen(req, timeout=8.0) as resp:
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
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("DELETE", url, response=payload, status=status)
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
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("POST", url, body=body, response=payload, status=status)
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
        with urlopen(req, timeout=8.0) as resp:
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
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        status = getattr(resp, "status", None)
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("DELETE", url, response=payload, status=status)
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
        with urlopen(req, timeout=15.0) as resp:
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
    _log_api("PUT", url, body=body)
    try:
        req = Request(url, data=data, headers=headers, method="PUT")
        with urlopen(req, timeout=15.0) as resp:
            raw = resp.read()
            http_status = int(getattr(resp, "status", 200) or 200)
        try:
            payload_any: Any = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            payload_any = {}
        _log_api("PUT", url, body=body, response=payload_any, status=http_status)
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
        with urlopen(req, timeout=15.0) as resp:
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


def api_update_user_timezone(
    user_id: int | str,
    timezone: str,
    *,
    token: str | None = None,
) -> dict[str, Any]:
    """Update user timezone via PUT api/update-user-time-zone (or POST if PUT returns 403). Requires JWT.

    Request: { "timezone": "..." } (IANA timezone id, e.g. Asia/Kolkata, UTC)
    Returns dict with success, message.
    """
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("api/update-user-time-zone")
    body: dict[str, Any] = {"timezone": (timezone or "").strip()}
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    data = json.dumps(body).encode("utf-8")

    def _do_request(method: str) -> tuple[dict[str, Any] | None, HTTPError | None]:
        req = Request(url, data=data, headers=headers, method=method)
        try:
            with urlopen(req, timeout=8.0) as resp:
                raw = resp.read()
            payload = json.loads(raw.decode("utf-8")) if raw else {}
            return (payload, None)
        except HTTPError as exc:
            return (None, exc)

    try:
        payload, exc = _do_request("PUT")
        if exc is not None and getattr(exc, "code", None) == 403:
            payload, exc = _do_request("POST")
    except (URLError, TimeoutError, ValueError):
        return {"success": False, "message": "Backend not reachable."}

    if exc is not None:
        try:
            raw = exc.read()
            err_payload = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            err_payload = {}
        backend_msg = _extract_error_message(err_payload, "")
        base = f"Timezone update failed (403)."
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
        with urlopen(req, timeout=8.0) as resp:
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
    """POST user-hierarchy/assign — link employee (userId) to manager (managerId)."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url("user-hierarchy/assign")
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
        _log_api("POST", url, body=body)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="POST")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("POST", url, body=body, response=payload, status=getattr(resp, "status", None))
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
    """PUT user-hierarchy/update/{hierarchyId}."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"user-hierarchy/update/{hierarchy_id}")
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
        _log_api("PUT", url, body=body)
        data = json.dumps(body).encode("utf-8")
        req = Request(url, data=data, headers=headers, method="PUT")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("PUT", url, body=body, response=payload, status=getattr(resp, "status", None))
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
    """DELETE user-hierarchy/delete/{hierarchyId}."""
    if not token or not str(token).strip():
        print(
            "[API] user-hierarchy/delete SKIPPED (no token); hierarchy_id=%r" % (hierarchy_id,),
            file=sys.stderr,
            flush=True,
        )
        return {"success": False, "message": "Session expired. Please log in again."}
    url = _api_url(f"user-hierarchy/delete/{hierarchy_id}")
    headers: dict[str, str] = {
        "Accept": "application/json",
        "User-Agent": "MY-ETLZONE-App/1.0",
        "Authorization": f"Bearer {token}",
    }
    try:
        _log_api("DELETE", url)
        print(
            "[API] user-hierarchy/delete request: hierarchy_id=%r -> %s" % (hierarchy_id, url),
            file=sys.stderr,
            flush=True,
        )
        req = Request(url, headers=headers, method="DELETE")
        with urlopen(req, timeout=8.0) as resp:
            raw = resp.read()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        _log_api("DELETE", url, response=payload, status=getattr(resp, "status", None))
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
        _log_api("DELETE", url, response=resp_for_log, status=getattr(exc, "code", None))
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
    """GET user-hierarchy/get-all-heirarchy — return all reporting assignments."""
    if not token or not str(token).strip():
        return {"success": False, "message": "Session expired. Please log in again.", "data": []}
    url = _api_url("user-hierarchy/get-all-heirarchy")
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
