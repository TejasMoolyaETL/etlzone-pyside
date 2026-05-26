"""Shared keyboard behavior for form list fields (native combo dropdown + line-edit QCompleter).

Searchable form combos (:mod:`ui.searchable_form_combo`) implement their own Tab/Enter logic;
this module covers the remaining patterns app-wide.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QComboBox, QCompleter, QLineEdit, QWidget


def _line_edit_in_searchable_combo(widget: QWidget | None) -> bool:
    p = widget
    while p is not None:
        if isinstance(p, QComboBox) and getattr(p, "_etl_searchable_mk_ctrl", None) is not None:
            return True
        p = p.parent()  # type: ignore[assignment]
    return False


class _LineEditCompleterTabFilter(QObject):
    """Tab / Enter on :class:`QCompleter` popups (project search, org name, etc.)."""

    def __init__(self, completer: QCompleter) -> None:
        super().__init__(completer)
        self._completer = completer

    def _popup(self):
        try:
            return self._completer.popup()
        except RuntimeError:
            return None

    def _commit(self, *, tab_autocomplete: bool = False) -> bool:
        popup = self._popup()
        if popup is not None and popup.isVisible():
            cur = popup.currentIndex()
            if tab_autocomplete and not cur.isValid():
                model = popup.model()
                if model is not None and model.rowCount() > 0:
                    cur = model.index(0, 0)
                    popup.setCurrentIndex(cur)
            if cur.isValid():
                text = popup.model().data(cur, Qt.ItemDataRole.DisplayRole)
                if text:
                    label = str(text).strip()
                    if label:
                        self._completer.setCompletionPrefix("")
                        self._completer.activated.emit(label)
                        popup.hide()
                        return True
            popup.hide()
            return False
        widget = self._completer.widget()
        if isinstance(widget, QLineEdit):
            typed = (widget.text() or "").strip()
            if typed:
                model = self._completer.model()
                if model is not None:
                    for row in range(model.rowCount()):
                        match = model.data(model.index(row, 0), Qt.ItemDataRole.DisplayRole)
                        if match and str(match).strip().lower() == typed.lower():
                            self._completer.activated.emit(str(match).strip())
                            return True
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.KeyPress or not isinstance(event, QKeyEvent):
            return False
        key = event.key()
        popup = self._popup()
        popup_open = popup is not None and popup.isVisible()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and popup_open:
            self._commit()
            return True
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self._commit(tab_autocomplete=popup_open)
            return False
        return False


class _NativeComboDropdownKeyFilter(QObject):
    """Tab / Enter on native (non-searchable) :class:`QComboBox` dropdown lists."""

    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo)
        self._combo = combo

    def _view(self):
        try:
            return self._combo.view()
        except RuntimeError:
            return None

    def _popup_open(self) -> bool:
        view = self._view()
        return view is not None and view.isVisible()

    def _commit(self, *, tab_autocomplete: bool = False) -> bool:
        if not self._popup_open():
            if tab_autocomplete:
                return False
            typed = (self._combo.currentText() or "").strip()
            if typed:
                idx = self._combo.findText(typed, Qt.MatchFlag.MatchExactly)
                if idx < 0:
                    idx = self._combo.findText(typed, Qt.MatchFlag.MatchFixedString)
                if idx >= 0:
                    self._combo.setCurrentIndex(idx)
                    return True
            return False
        view = self._view()
        if view is None:
            return False
        cur = view.currentIndex()
        if tab_autocomplete and not cur.isValid():
            model = view.model()
            if model is not None and model.rowCount() > 0:
                cur = model.index(0, 0)
                view.setCurrentIndex(cur)
        if cur.isValid():
            row = cur.row()
            if 0 <= row < self._combo.count():
                self._combo.setCurrentIndex(row)
            self._combo.hidePopup()
            return True
        self._combo.hidePopup()
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if getattr(self._combo, "_etl_form_combo_view_only", False):
            return False
        if event.type() != QEvent.Type.KeyPress or not isinstance(event, QKeyEvent):
            return False
        key = event.key()
        popup_open = self._popup_open()
        le = self._combo.lineEdit()
        if watched is not self._combo and watched is not le and watched is not self._view():
            return False
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and popup_open:
            self._commit()
            return True
        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            self._commit(tab_autocomplete=popup_open)
            return False
        return False


def install_line_edit_completer_tab_commit(completer: QCompleter | None) -> None:
    """Tab selects from the list then moves focus; Enter commits the highlighted row."""
    if completer is None or getattr(completer, "_etl_completer_tab_filter", None) is not None:
        return
    widget = completer.widget()
    if _line_edit_in_searchable_combo(widget):
        return
    filt = _LineEditCompleterTabFilter(completer)
    completer.installEventFilter(filt)
    if widget is not None:
        widget.installEventFilter(filt)
    popup = completer.popup()
    if popup is not None and not getattr(popup, "_etl_popup_key_filter", None):
        popup.installEventFilter(filt)
    setattr(completer, "_etl_completer_tab_filter", filt)


def install_native_combo_dropdown_tab_commit(combo: QComboBox | None) -> None:
    """Tab / Enter for standard dropdown combos (module pickers, HTTP method, etc.)."""
    if combo is None or getattr(combo, "_etl_searchable_mk_ctrl", None) is not None:
        return
    if getattr(combo, "_etl_native_tab_filter", None) is not None:
        return
    filt = _NativeComboDropdownKeyFilter(combo)
    combo.installEventFilter(filt)
    le = combo.lineEdit()
    if le is not None:
        le.installEventFilter(filt)
    setattr(combo, "_etl_native_tab_filter", filt)
