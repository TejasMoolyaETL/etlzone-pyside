"""User context for login session."""

from __future__ import annotations

from typing import Any

current_user_role = ""
current_user_email = ""
current_user_profile: dict[str, Any] = {}
# None = do not filter left nav (SADMIN bypass only). Non-None list = strict nav_access from getAppStepList.
_nav_access_steps: list[dict[str, Any]] | None = None


def set_user_role(value: str) -> None:
    global current_user_role
    current_user_role = value or ""


def get_user_role() -> str:
    return current_user_role


def set_user_email(value: str) -> None:
    global current_user_email
    current_user_email = value or ""


def get_user_email() -> str:
    return current_user_email


def set_user_profile(profile: dict[str, Any]) -> None:
    """Store full profile from api/auth/login response."""
    global current_user_profile
    current_user_profile = dict(profile) if profile else {}


def get_user_profile() -> dict[str, Any]:
    """Return full profile from login response."""
    return dict(current_user_profile)


def set_nav_access_steps(steps: list[dict[str, Any]] | None) -> None:
    """Set raw getAppStepList rows.

    ``None`` — skip filtering (show all gated menu items; used for SADMIN only).

    ``[]`` or a non-empty list — apply :mod:`core.nav_access`: each gated submenu is visible only
    if its configured ``appIdDescription`` appears on at least one step row.
    """
    global _nav_access_steps
    _nav_access_steps = None if steps is None else list(steps)


def get_nav_access_steps() -> list[dict[str, Any]] | None:
    """Return a copy of step rows, or ``None`` if the nav should not be restricted."""
    if _nav_access_steps is None:
        return None
    return list(_nav_access_steps)
