"""App preferences (timezone, etc.) used across the app."""

from __future__ import annotations

import json
import re
from ast import literal_eval
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# Normalize Java-style offset +0000 -> +00:00 for fromisoformat
_OFFSET_FIX = re.compile(r"([+-])(\d{2})(\d{2})$")
_NESTED_KEYVALUE_RE = re.compile(r"(?:^|[,{]\s*)keyValue\s*[:=]\s*['\"]?([^,'\"}]+)")

_PREFS_FILE = Path(__file__).resolve().parent.parent / ".etl_app_prefs.json"

# Display timezone: set by Settings when user saves; used when profile lookup fails
_display_timezone: str = ""


def _load_prefs() -> dict[str, Any]:
    try:
        if _PREFS_FILE.exists():
            data = json.loads(_PREFS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _save_prefs(prefs: dict[str, Any]) -> None:
    try:
        _PREFS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PREFS_FILE.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    except Exception:
        pass

# Comprehensive IANA timezone list (works on Windows without tzdata)
# Sorted by region. First item '' = Local (System)
_IANA_TIMEZONES = [
    "",
    "Africa/Abidjan", "Africa/Accra", "Africa/Addis_Ababa", "Africa/Algiers", "Africa/Cairo",
    "Africa/Casablanca", "Africa/Johannesburg", "Africa/Lagos", "Africa/Nairobi", "Africa/Tunis",
    "America/Argentina/Buenos_Aires", "America/Bogota", "America/Caracas", "America/Chicago",
    "America/Denver", "America/Los_Angeles", "America/Mexico_City", "America/New_York",
    "America/Panama", "America/Phoenix", "America/Sao_Paulo", "America/Toronto",
    "America/Vancouver", "America/Winnipeg",
    "Asia/Bangkok", "Asia/Dubai", "Asia/Hong_Kong", "Asia/Jakarta", "Asia/Karachi",
    "Asia/Kolkata", "Asia/Riyadh", "Asia/Shanghai", "Asia/Singapore", "Asia/Tokyo",
    "Atlantic/Reykjavik",
    "Australia/Adelaide", "Australia/Brisbane", "Australia/Perth", "Australia/Sydney",
    "Europe/Amsterdam", "Europe/Berlin", "Europe/Brussels", "Europe/Budapest",
    "Europe/Dublin", "Europe/Helsinki", "Europe/Istanbul", "Europe/London",
    "Europe/Madrid", "Europe/Moscow", "Europe/Paris", "Europe/Prague",
    "Europe/Rome", "Europe/Stockholm", "Europe/Vienna", "Europe/Warsaw",
    "Pacific/Auckland", "Pacific/Fiji", "Pacific/Guam", "Pacific/Honolulu",
    "UTC",
]


def get_iana_timezone_list() -> list[str]:
    """Return IANA timezone names for dropdown. First is '' (system local)."""
    try:
        from zoneinfo import available_timezones
        tz_set = available_timezones()
        if tz_set:
            return [""] + sorted(tz_set)
    except Exception:
        pass
    return _IANA_TIMEZONES

# Keys that should be formatted as user timezone (use with format_datetime)
DATE_KEYS = frozenset(
    {
        "createdAt", "created_at", "CreatedAt", "CREATED_AT",
        "createdOn", "created_on", "CreatedOn", "CREATED_ON",
        "createDate", "creationDate", "dateCreated",
        "createdDate", "created_date", "CreatedDate",
        "modifiedAt", "modified_at", "ModifiedAt", "MODIFIED_AT",
        "modifiedOn", "modified_on", "ModifiedOn", "MODIFIED_ON",
        "updatedAt", "updated_at", "UpdatedAt", "UPDATED_AT",
        "modifyDate", "dateModified",
        "lastModified", "last_modified", "LastModified",
        "validFrom", "valid_from", "ValidFrom", "VALID_FROM",
        "validTo", "valid_to", "ValidTo", "VALID_TO",
        "grantedAt", "granted_at", "assignedAt", "assigned_at",
        "revokedAt", "revoked_at", "deletedAt", "deleted_at",
        "lastLogin", "last_login", "LastLogin", "loginAt", "login_at",
        "startDate", "start_date", "endDate", "end_date",
        "effectiveFrom", "effective_from", "effectiveTo", "effective_to",
        "timestamp", "Timestamp", "timeStamp", "time_stamp",
        "functionalUnitTestingCompletionDate",
        "functional_unit_testing_completion_date",
    }
)


def is_datetime_field(key: str, key_candidates: tuple[str, ...] = ()) -> bool:
    """True if ``key`` or any entry in ``key_candidates`` is a known API datetime field name."""
    def _looks_like_datetime_key(name: str) -> bool:
        n = (name or "").strip()
        if not n:
            return False
        if n in DATE_KEYS:
            return True
        low = n.lower()
        date_hints = (
            "date",
            "time",
            "timestamp",
            "createdat",
            "modifiedat",
            "updatedat",
            "startat",
            "endat",
            "validfrom",
            "validto",
            "fromdate",
            "todate",
            "on",
        )
        if low.endswith(("at", "_at", "date", "_date", "time", "_time", "timestamp", "_timestamp")):
            return True
        return any(h in low for h in date_hints)

    if _looks_like_datetime_key(key):
        return True
    return any(_looks_like_datetime_key(k) for k in key_candidates)


def _get_zoneinfo(tz_id: str):
    """Return timezone for tz_id. Uses ZoneInfo if available, else fixed offset fallback for Windows."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_id)
    except Exception:
        pass
    # Fallback for Windows without tzdata: use fixed UTC offsets for common zones
    _FALLBACK_OFFSETS: dict[str, timedelta] = {
        "UTC": timedelta(0),
        "Asia/Kolkata": timedelta(hours=5, minutes=30),
        "Asia/Dubai": timedelta(hours=4),
        "Asia/Singapore": timedelta(hours=8),
        "America/New_York": timedelta(hours=-5),
        "Europe/London": timedelta(hours=0),
    }
    offset = _FALLBACK_OFFSETS.get(tz_id)
    if offset is not None:
        return timezone(offset)
    return None


def get_timezone() -> str:
    """Return timezone for display. _display_timezone (Settings) wins, else profile (login)."""
    if _display_timezone:
        return _display_timezone
    from core.user_context import get_user_profile
    profile = get_user_profile()

    def _extract(obj: dict, seen: set | None = None) -> str:
        if seen is None:
            seen = set()
        if id(obj) in seen:
            return ""
        seen.add(id(obj))
        tz_keys = ("timezone", "userTimezone", "user_timezone", "timeZone", "Timezone", "userTimeZone", "tzdata", "tz")
        for key in tz_keys:
            v = obj.get(key)
            if v is not None and str(v).strip():
                return str(v).strip()
        for key, val in obj.items():
            if isinstance(val, dict) and key not in ("password",):
                found = _extract(val, seen)
                if found:
                    return found
        return ""

    tz = _extract(profile)
    if tz:
        return tz
    for key, val in profile.items():
        if "timezone" in key.lower() and val is not None:
            s = str(val).strip()
            if s and "/" in s:
                return s
    prefs = _load_prefs()
    return prefs.get("timezone") or prefs.get("userTimezone") or ""


def set_display_timezone(tz_id: str) -> None:
    """Explicitly set timezone for display. Call from Settings on save or login."""
    global _display_timezone
    _display_timezone = (tz_id or "").strip()
    if _display_timezone:
        prefs = _load_prefs()
        prefs["timezone"] = _display_timezone
        _save_prefs(prefs)


def to_utc_iso(
    date_str: str,
    *,
    end_of_day: bool = False,
) -> str | None:
    """Convert date string to UTC ISO before calling API.

    User input (in user's timezone from Settings) is converted to UTC.
    Call this for any datetime sent to the backend.
    date_str: YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS (interpreted in user's timezone)
    end_of_day: if True, use 23:59:59; else 00:00:00 for date-only strings
    Returns e.g. 2025-03-14T18:30:00Z or None on parse error.
    """
    if not date_str or not str(date_str).strip():
        return None
    s = str(date_str).strip()
    try:
        if "T" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00")[:26])
            if dt.tzinfo is None:
                # Interpret as user timezone
                tz_id = get_timezone()
                if tz_id:
                    target = _get_zoneinfo(tz_id)
                    dt = dt.replace(tzinfo=target) if target else dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
            dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        # Date only: YYYY-MM-DD
        hour, minute, second = (23, 59, 59) if end_of_day else (0, 0, 0)
        dt = datetime.strptime(s[:10], "%Y-%m-%d").replace(hour=hour, minute=minute, second=second)
        tz_id = get_timezone()
        if tz_id:
            target = _get_zoneinfo(tz_id)
            dt = dt.replace(tzinfo=target) if target else dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.replace(tzinfo=datetime.now().astimezone().tzinfo)
        dt_utc = dt.astimezone(timezone.utc)
        return dt_utc.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    except (ValueError, OSError, OverflowError):
        return None


def format_datetime(value: Any) -> str | None:
    """Convert backend date/datetime (UTC) to user's timezone for display.

    Use everywhere a date or datetime is shown on screen. The timezone comes from
    the user's Settings (stored in backend, loaded into profile).
    Handles: int/float (timestamp ms or s), ISO strings with/without Z.
    Returns None if not parseable.
    """
    if value is None:
        return None
    if isinstance(value, str) and value.strip().lower() in ("", "null", "none"):
        return None
    # Some APIs return {"date": "...", "time": "..."} or {"timestamp": ...}
    if isinstance(value, dict):
        value = value.get("date") or value.get("time") or value.get("timestamp") or value.get("$date")
        if value is None:
            return None
    try:
        dt: datetime | None = None
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1e12:
                ts /= 1000
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)  # timestamps are UTC
        elif isinstance(value, str) and value.strip():
            s = value.strip()
            try:
                s_iso = s.replace("Z", "+00:00").replace("z", "+00:00")
                # Backend often uses space: "2026-03-10 11:10:07.289347" -> use T for fromisoformat
                if len(s_iso) >= 10 and s_iso[10:11] == " ":
                    s_iso = s_iso[:10] + "T" + s_iso[11:]
                # Java/Spring: +0000 -> +00:00 (fromisoformat needs colon)
                s_iso = _OFFSET_FIX.sub(r"\1\2:\3", s_iso)
                # Parse; allow up to 40 chars to include timezone (e.g. 2025-02-25T10:30:00.000+00:00)
                parse_str = s_iso[:40].rstrip()
                dt = datetime.fromisoformat(parse_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
            except ValueError:
                pass
            if dt is None:
                s_clean = s.rstrip("Z").rstrip("z")
                for fmt, max_len in (
                    ("%Y-%m-%dT%H:%M:%S.%f", 30),
                    ("%Y-%m-%dT%H:%M:%S", 26),
                    ("%Y-%m-%d %H:%M:%S.%f", 30),
                    ("%Y-%m-%d %H:%M:%S", 26),
                    ("%Y-%m-%d", 10),
                    ("%d/%m/%Y %H:%M:%S", 26),
                    ("%d/%m/%Y", 10),
                    ("%m/%d/%Y %H:%M:%S", 26),
                    ("%m/%d/%Y", 10),
                ):
                    try:
                        dt = datetime.strptime(s_clean[:max_len], fmt)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        break
                    except ValueError:
                        continue
            if dt is None:
                try:
                    from dateutil.parser import parse as dateutil_parse
                    dt = dateutil_parse(s)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    else:
                        dt = dt.astimezone(timezone.utc)
                except Exception:
                    pass
        if dt is None:
            return None
        # Convert UTC to user's timezone (from Settings/backend, e.g. Asia/Kolkata).
        # Very large years (e.g. 9999 "forever" validTo) can make astimezone() raise
        # OverflowError on Windows; keep UTC and still apply the display strftime below.
        tz_id = get_timezone()
        if tz_id:
            target_tz = _get_zoneinfo(tz_id)
            if target_tz is not None:
                try:
                    dt = dt.astimezone(target_tz)
                except OverflowError:
                    pass
            # else: ZoneInfo failed, keep UTC
        else:
            try:
                dt = dt.astimezone()
            except OverflowError:
                pass
        try:
            return dt.strftime("%d %b %Y %I:%M %p")
        except OverflowError:
            # Rare: platform strftime limits on extreme years; keep raw string.
            s = str(value).strip() if not isinstance(value, (int, float)) else ""
            return s if s else ""
    except (ValueError, OSError, OverflowError):
        return None


def format_datetime_display(value: Any) -> str:
    """Format API timestamps for UI: same rules as list tables (user timezone, ``dd Mon YYYY hh:mm AM/PM``).

    Use for any on-screen datetime without passing a ``DATE_KEYS`` column key. If parsing fails,
    returns ``str(value)`` or empty string when there is nothing to show.
    """
    if value is None:
        return ""
    if isinstance(value, str) and value.strip().lower() in ("", "null", "none"):
        return ""
    out = format_datetime(value)
    if out is not None:
        return out
    s = str(value).strip()
    return s if s else ""


def format_field_display_value(value: Any, key: str = "", key_candidates: tuple[str, ...] = ()) -> str:
    """Shared UI field formatter for list/view pages.

    Rules:
    - datetime-like fields use timezone-aware ``format_datetime_display``
    - dict values prefer ``keyValue``/``key_value`` display text, then ``seq``
    - everything else falls back to ``str(value)``
    """
    if value is None:
        return ""
    if isinstance(value, str) and value.strip().lower() in ("", "null", "none"):
        return ""

    def _extract_nested_display(obj: Any) -> str:
        if not isinstance(obj, dict):
            return ""
        # Common variants from different backend serializers.
        for k in ("keyValue", "key_value", "keyvalue", "value", "label", "name"):
            v = obj.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        # Case-insensitive fallback.
        lower_map = {str(k).lower(): v for k, v in obj.items()}
        for k in ("keyvalue", "key_value", "value", "label", "name"):
            v = lower_map.get(k)
            if v is not None and str(v).strip():
                return str(v).strip()
        seq_val = obj.get("seq")
        if seq_val is not None:
            return str(seq_val)
        return ""

    # Some APIs return nested objects as JSON text; extract display value when possible.
    if isinstance(value, str):
        raw = value.strip()
        if raw.startswith("{") and raw.endswith("}"):
            try:
                parsed = json.loads(raw)
                nested_out = _extract_nested_display(parsed)
                if nested_out:
                    return nested_out
            except Exception:
                # Some APIs send Python-dict-like strings with single quotes.
                try:
                    parsed = literal_eval(raw)
                    nested_out = _extract_nested_display(parsed)
                    if nested_out:
                        return nested_out
                except Exception:
                    pass
            # Java map-style fallback: "{category=..., keyValue=Fulltime, seq=1}"
            m = _NESTED_KEYVALUE_RE.search(raw)
            if m:
                out = str(m.group(1) or "").strip()
                if out:
                    return out
    if is_datetime_field(key, key_candidates):
        return format_datetime_display(value)
    if isinstance(value, dict):
        nested_out = _extract_nested_display(value)
        if nested_out:
            return nested_out
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    text = str(value).strip()
    return text if text else ""
