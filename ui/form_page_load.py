"""Reload API-backed dropdown / completer lists when create or view pages are shown."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QWidget


class _FormPageReloadFilter(QObject):
    def __init__(self, page: QWidget, reload_fn: Callable[[], None]) -> None:
        super().__init__(page)
        self._page = page
        self._reload_fn = reload_fn

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._page and event.type() == QEvent.Type.Show:
            QTimer.singleShot(0, self._reload_fn)
        return False


def install_form_page_reload_on_show(page: QWidget, reload_fn: Callable[[], None]) -> None:
    """Call ``reload_fn`` after every ``showEvent`` (deferred one event-loop tick)."""
    existing = getattr(page, "_etl_form_reload_filter", None)
    if existing is not None:
        page._etl_form_reload_fn = reload_fn  # type: ignore[attr-defined]
        return
    filt = _FormPageReloadFilter(page, reload_fn)
    page.installEventFilter(filt)
    page._etl_form_reload_filter = filt  # type: ignore[attr-defined]
    page._etl_form_reload_fn = reload_fn  # type: ignore[attr-defined]
    page._etl_form_reload_installed = True  # type: ignore[attr-defined]


def set_form_page_reload_on_show(page: QWidget, reload_fn: Callable[[], None] | None) -> None:
    """Register (or clear) the reload callback used by :func:`install_form_page_reload_on_show`."""
    page._etl_form_reload_on_show = reload_fn  # type: ignore[attr-defined]
