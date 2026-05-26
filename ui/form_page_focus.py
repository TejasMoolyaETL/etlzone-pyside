"""Initial keyboard focus on create / view / edit form pages."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QPlainTextEdit,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QWidget,
)

_INPUT_WIDGET_TYPES = (
    QLineEdit,
    QPlainTextEdit,
    QTextEdit,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QAbstractSpinBox,
)


def is_crud_form_page(widget: QWidget) -> bool:
    """True for ``Create*Page`` / ``View*Page`` widgets (not list or settings screens)."""
    name = type(widget).__name__
    return (name.startswith("Create") or name.startswith("View")) and name.endswith("Page")


def _is_form_input(widget: QWidget) -> bool:
    if not widget.isVisible() or not widget.isEnabled():
        return False
    if not isinstance(widget, _INPUT_WIDGET_TYPES):
        return False
    policy = widget.focusPolicy()
    if policy == Qt.FocusPolicy.NoFocus:
        return False
    return bool(policy & Qt.FocusPolicy.TabFocus)


def _position_key(widget: QWidget, root: QWidget) -> tuple[int, int]:
    pt = widget.mapTo(root, widget.rect().topLeft())
    return (pt.y(), pt.x())


def find_first_focusable_field(page: QWidget) -> QWidget | None:
    """First enabled, visible, tab-focusable input in top-to-left reading order."""
    candidates = [w for w in page.findChildren(QWidget) if _is_form_input(w)]
    if not candidates:
        return None
    candidates.sort(key=lambda w: _position_key(w, page))
    return candidates[0]


def _scroll_form_to_top(page: QWidget) -> None:
    for scroll in page.findChildren(QScrollArea):
        if not scroll.isVisible():
            continue
        bar = scroll.verticalScrollBar()
        if bar is not None:
            bar.setValue(0)
        break


def focus_first_form_field(page: QWidget) -> bool:
    """Scroll to top (if the page uses a scroll area) and focus the first input."""
    _scroll_form_to_top(page)
    target = find_first_focusable_field(page)
    if target is None:
        return False
    target.setFocus(Qt.FocusReason.OtherFocusReason)
    return True


def schedule_focus_first_form_field(page: QWidget) -> None:
    """Defer focus until after the page's ``showEvent`` / layout work finishes."""
    QTimer.singleShot(0, lambda: focus_first_form_field(page))


def _wrap_handle_edit_for_focus(page: QWidget) -> None:
    if getattr(page, "_etl_edit_focus_wrapped", False):
        return
    original = getattr(page, "_handle_edit", None)
    if original is None or not callable(original):
        return

    def wrapped() -> None:
        original()
        schedule_focus_first_form_field(page)

    page._handle_edit = wrapped  # type: ignore[method-assign]
    page._etl_edit_focus_wrapped = True  # type: ignore[attr-defined]


class _FormPageFocusFilter(QObject):
    def __init__(self, page: QWidget) -> None:
        super().__init__(page)
        self._page = page

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if watched is self._page and event.type() == QEvent.Type.Show:
            reload = getattr(self._page, "_etl_form_reload_on_show", None)
            if callable(reload):
                QTimer.singleShot(0, reload)
            schedule_focus_first_form_field(self._page)
        return False


def register_form_page_reload_on_show(page: QWidget, reload_fn: Callable[[], None]) -> None:
    """Register API list reload for :func:`install_form_page_focus_on_show` (runs each show)."""
    page._etl_form_reload_on_show = reload_fn  # type: ignore[attr-defined]


def install_form_page_focus_on_show(page: QWidget) -> None:
    """Install on a create or view page once (safe to call repeatedly)."""
    if getattr(page, "_etl_form_focus_installed", False):
        return
    filt = _FormPageFocusFilter(page)
    page.installEventFilter(filt)
    page._etl_form_focus_filter = filt  # type: ignore[attr-defined]
    page._etl_form_focus_installed = True  # type: ignore[attr-defined]
    _wrap_handle_edit_for_focus(page)


def install_form_page_focus_on_all_stack_pages(stack: QWidget) -> None:
    """Register every ``Create*Page`` / ``View*Page`` on a ``QStackedWidget``."""
    from PySide6.QtWidgets import QStackedWidget

    if not isinstance(stack, QStackedWidget):
        return
    for i in range(stack.count()):
        w = stack.widget(i)
        if w is not None and is_crud_form_page(w):
            install_form_page_focus_on_show(w)
