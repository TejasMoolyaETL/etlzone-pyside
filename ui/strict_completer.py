"""Shared helpers for QCompleter-backed fields: only exact list display strings are valid."""

from __future__ import annotations

from typing import Iterable


def strict_list_selection_message(select_what: str) -> str:
    """User-facing error when text does not match an allowed completion.

    select_what: phrase after "select", e.g. "a project", "an organization".
    """
    return (
        f"Please select {select_what} from the search list. Typed values are not allowed."
    )


def is_exact_completion_display(text: str, allowed_displays: Iterable[str]) -> bool:
    """True if stripped text is exactly one of the allowed completion strings."""
    t = (text or "").strip()
    if not t:
        return False
    return t in set(allowed_displays)
