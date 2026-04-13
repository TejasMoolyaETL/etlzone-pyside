"""Delayed navigation after create/update: navigate first, then optional callback (next event tick).

Avoids overlapping list reloads when the destination page uses showEvent→refresh, and isolates
callback exceptions so they do not abort the Qt slot.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable

from PySide6.QtCore import QTimer


def schedule_after_success(
    *,
    delay_ms: int = 800,
    clear_error: Callable[[], None],
    reset: Callable[[], None] | None = None,
    on_back: Callable[[], None] | None = None,
    on_success: Callable[[], None] | None = None,
) -> None:
    """After ``delay_ms``, clear error (and optionally reset form), call ``on_back``, then ``on_success`` on the next tick."""

    def _do_after() -> None:
        clear_error()
        if reset is not None:
            reset()
        try:
            if on_back is not None:
                on_back()
        except Exception:
            traceback.print_exc()

        def _run_success() -> None:
            if on_success is None:
                return
            try:
                on_success()
            except Exception:
                traceback.print_exc()

        QTimer.singleShot(0, _run_success)

    QTimer.singleShot(delay_ms, _do_after)


NO_CHANGES_MESSAGE = "No Changes made"


def navigate_after_no_changes(
    *,
    show_non_error_message: Callable[[str], None],
    clear_message: Callable[[], None],
    on_back: Callable[[], None] | None,
    delay_ms: int = 800,
) -> None:
    """Show a neutral success message and navigate to the list (or previous page) without calling an update API."""
    show_non_error_message(NO_CHANGES_MESSAGE)
    schedule_after_success(
        delay_ms=delay_ms,
        clear_error=clear_message,
        on_back=on_back,
        on_success=None,
    )
