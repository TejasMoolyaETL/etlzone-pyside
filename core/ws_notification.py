"""Parse WebSocket JSON payloads into structured UI notification data."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

_SKIP_MESSAGE_TYPES = frozenset(
    {"ping", "pong", "heartbeat", "connected", "subscribe", "ack", "welcome"}
)


def _scalar_text(v: Any) -> str:
    if v is None or isinstance(v, (dict, list)):
        return ""
    t = str(v).strip()
    return t


def _s(d: dict[str, Any], *keys: str) -> str:
    for k in keys:
        t = _scalar_text(d.get(k))
        if t:
            return t
    return ""


def _friendly_fallback_headline(d: dict[str, Any], mt: str) -> str:
    if "update" in mt or "update" in _s(d, "category", "event").lower():
        return "A new app update is available."
    return "You have a new notification."


def _flatten_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Merge nested payload/data objects; outer keys win on conflict."""
    out: dict[str, Any] = dict(data)
    for key in ("payload", "data"):
        inner = data.get(key)
        if isinstance(inner, dict):
            merged = {**inner, **out}
            out = merged
    return out


def _meta_rows(d: dict[str, Any], headline: str) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    hl = headline.strip().lower()
    specs = (
        ("App name", ("appName", "applicationName",)),
        ("App Id", ("appId", "app_id", "applicationId")),
        ("Description", ("appDesc", "appDescription",)),
        ("Version", ("version", "latestVersion", "newVersion", "appVersion", "targetVersion")),
        ("Your version", ("currentVersion", "installedVersion")),
        ("Endpoint", ("endpoint", "apiEndpoint", "urlPath")),
        ("Severity", ("severity", "level", "priority")),
        ("Type", ("type", "category", "eventType")),
        ("When", ("timestamp", "time", "sentAt", "releaseDate", "releasedAt")),
    )
    seen_vals: set[str] = set()
    for label, keys in specs:
        val = _s(d, *keys)
        if not val or val.lower() == hl:
            continue
        if val.lower() in seen_vals:
            continue
        seen_vals.add(val.lower())
        if label == "Description" and len(val) > 280:
            val = val[:277] + "…"
        rows.append((label, val))
    return rows


@dataclass(frozen=True)
class WsNotificationPayload:
    """Structured push notification for the UI dialog."""

    window_title: str
    header_title: str
    headline: str
    body: str = ""
    meta: tuple[tuple[str, str], ...] = ()
    action_url: str | None = None
    action_label: str = "Open link"


def parse_ws_notification(raw: str) -> WsNotificationPayload | None:
    """
    Build a payload from a WebSocket text frame.
    Returns None when the message should be ignored (heartbeats, empty, etc.).
    """
    s = (raw or "").strip()
    if not s:
        return None

    data: Any
    try:
        data = json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return WsNotificationPayload(
            window_title="Notification",
            header_title="Notification",
            headline=s[:2000] if len(s) > 2000 else s,
            body="",
        )

    if isinstance(data, str) and data.strip():
        t = data.strip()
        return WsNotificationPayload(
            window_title="Notification",
            header_title="Notification",
            headline=t[:2000] if len(t) > 2000 else t,
        )

    if not isinstance(data, dict):
        return WsNotificationPayload(
            window_title="Notification",
            header_title="Notification",
            headline="You have a new notification.",
            body="",
        )

    d = _flatten_payload(data)

    mt = str(d.get("type", "")).lower()
    if mt in _SKIP_MESSAGE_TYPES:
        has_user_text = any(
            _s(d, k)
            for k in (
                "message",
                "text",
                "title",
                "body",
                "content",
                "description",
                "subject",
                "headline",
            )
        )
        if not has_user_text:
            return None

    headline = _s(
        d,
        "message",
        "text",
        "headline",
        "description",
        "body",
        "content",
        "alertMessage",
        "detail",
        "summary",
        "msg",
        "notification",
        "notificationMessage",
        "updateMessage",
        "infoMessage",
        "hint",
        "label",
    )
    title_candidate = _s(
        d,
        "title",
        "subject",
        "notificationTitle",
        "header",
        "name",
    )

    if not headline and title_candidate:
        headline = title_candidate
        title_candidate = ""

    body = _s(
        d,
        "subtitle",
        "details",
        "reason",
        "note",
        "info",
        "additionalInfo",
        "longMessage",
    )
    if body and body == headline:
        body = _s(d, "details", "reason", "note", "info", "additionalInfo", "longMessage")

    if title_candidate and headline and title_candidate.lower() != headline.lower():
        header_title = title_candidate
    elif title_candidate:
        header_title = title_candidate
    elif "update" in mt or "update" in _s(d, "category", "event").lower():
        header_title = "App update"
    elif mt:
        header_title = mt.replace("_", " ").title()
    else:
        header_title = "Notification"

    window_title = header_title
    if len(window_title) > 42:
        window_title = window_title[:39] + "…"

    if not headline:
        headline = _friendly_fallback_headline(d, mt)

    meta_list = _meta_rows(d, headline)
    meta = tuple(meta_list)

    action_url = _s(d, "url", "link", "downloadUrl", "downloadURL", "actionUrl", "href", "webUrl")
    if not action_url.startswith(("http://", "https://")):
        action_url = ""

    action_label = _s(d, "actionLabel", "linkText", "buttonText") or "Open link"

    return WsNotificationPayload(
        window_title=window_title,
        header_title=header_title,
        headline=headline,
        body=body,
        meta=meta,
        action_url=action_url or None,
        action_label=action_label,
    )
