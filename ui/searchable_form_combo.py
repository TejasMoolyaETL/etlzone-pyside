"""Searchable form QComboBox: top-N on open, filter-as-you-type, shared master-key populate.

Create/save validation must use :func:`combo_resolved_master_key_seq`,
:func:`require_master_key_seq_for_payload`, :func:`reference_id_for_payload`, or
:func:`combo_payload_user_data` — never ``currentData()`` / ``currentIndex()`` alone on
searchable (editable) combos, or a cleared field can still submit a stale list value.
"""

from __future__ import annotations

from typing import Any, Sequence

from PySide6.QtCore import QEvent, QModelIndex, QObject, QStringListModel, Qt, QTimer
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtWidgets import QApplication, QComboBox, QCompleter, QAbstractItemView

from core.api import (
    api_get_master_key_by_app_id_field_name,
    master_key_row_display_label,
    master_key_row_seq_value,
)
from ui.form_combobox_style import (
    FORM_COMBO_LIST_ROW_HEIGHT_PX,
    apply_completer_popup_list_style,
    install_combo_ignore_wheel_when_closed,
)

# Backend sentinel when a master-config combo (get-by-field-name) has no selection.
MASTER_KEY_BLANK_SEQ_DEFAULT = 99

_LIST_NAV_KEYS = frozenset(
    {
        Qt.Key.Key_Down,
        Qt.Key.Key_Up,
        Qt.Key.Key_PageDown,
        Qt.Key.Key_PageUp,
        Qt.Key.Key_Home,
        Qt.Key.Key_End,
    }
)


class _CompleterPopupKeyFilter(QObject):
    """Forward keys from the completer popup (e.g. Tab while the list has focus)."""

    def __init__(self, controller: "_SearchableMasterKeyComboController", popup: QObject) -> None:
        super().__init__(popup)
        self._controller = controller

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if self._controller._handle_list_key_press(watched, event):
                return True
        return False


class _SearchableMasterKeyComboController(QObject):
    """Keeps a QStringListModel completer in sync with combo items; limits empty-prefix list to N rows."""

    def __init__(
        self,
        combo: QComboBox,
        *,
        top_n_when_empty: int,
        max_visible_items: int,
        open_popup_on_focus_click: bool,
    ) -> None:
        super().__init__(combo)
        self._combo = combo
        self._top_n = max(1, int(top_n_when_empty))
        self._open_on_focus_click = open_popup_on_focus_click

        self._string_model = QStringListModel(combo)
        self._completer = QCompleter(self._string_model, combo)
        self._completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self._completer.setMaxVisibleItems(max(1, int(max_visible_items)))
        combo.setCompleter(self._completer)
        apply_completer_popup_list_style(self._completer)
        self._suppress_focus_click_open = False
        self._accepting_selection = False
        self._browsing_list = False
        self._programmatic_update_depth = 0
        self._anchor_text = ""
        # Do not use QCompleter.activated — Qt may fire it when the arrow opens the list.
        self._completer.highlighted.connect(self._on_completer_highlighted)
        combo.currentIndexChanged.connect(self._on_combo_index_changed_during_browse)
        combo.currentTextChanged.connect(self._on_combo_current_text_changed_during_browse)
        combo.activated.connect(self._on_combo_native_activated)

        le = combo.lineEdit()
        if le is not None:
            le.textChanged.connect(self._on_text_changed)
            le.installEventFilter(self)
        combo.installEventFilter(self)

        m = combo.model()
        m.modelReset.connect(self._rebuild_model)
        m.rowsInserted.connect(self._rebuild_model)
        m.rowsRemoved.connect(self._rebuild_model)

        self._rebuild_model()

    def _guarded_combo(self) -> QComboBox | None:
        """Return ``self._combo`` only if the underlying C++ widget still exists (avoids shutdown races)."""
        c = getattr(self, "_combo", None)
        if c is None:
            return None
        try:
            c.count()
        except RuntimeError:
            return None
        return c

    def _all_labels(self) -> list[str]:
        c = self._guarded_combo()
        if c is None:
            return []
        out: list[str] = []
        for i in range(c.count()):
            s = (c.itemText(i) or "").strip()
            if s:
                out.append(s)
        return out

    def _label_matches_combo_item(self, text: str) -> bool:
        """True when ``text`` equals a full row label (Qt often injects one when the list opens)."""
        c = self._guarded_combo()
        if c is None:
            return False
        needle = (text or "").strip().lower()
        if not needle:
            return False
        for i in range(c.count()):
            if (c.itemText(i) or "").strip().lower() == needle:
                return True
        return False

    def _filter_text_for_list(self) -> str:
        """Search/filter string (``_anchor_text``, kept in sync while the user types)."""
        if self._anchor_text is not None:
            return self._anchor_text
        c = self._guarded_combo()
        if c is None:
            return ""
        le = c.lineEdit()
        return (le.text() if le is not None else "") or ""

    def _rebuild_model(self) -> None:
        c = self._guarded_combo()
        if c is None:
            return
        text = self._filter_text_for_list()
        t = text.strip().lower()
        labels = self._all_labels()
        if not t:
            shown = labels[: self._top_n]
        else:
            shown = [x for x in labels if t in x.lower()]
        self._string_model.setStringList(shown)

    def _sync_anchor_from_line_edit_while_browsing(self) -> None:
        """Keep filter text stable when Qt stuffs a full row label into the line edit on open."""
        c = self._guarded_combo()
        if c is None or not self._browsing_list or self._accepting_selection:
            return
        le = c.lineEdit()
        if le is None:
            return
        current = le.text() or ""
        anchor = self._anchor_text if self._anchor_text is not None else ""
        if self._label_matches_combo_item(current):
            if current != anchor:
                le.blockSignals(True)
                le.setText(anchor)
                le.blockSignals(False)
            return
        if current != anchor:
            self._anchor_text = current

    def _highlight_popup_row_for_text(self, text: str) -> None:
        try:
            popup = self._completer.popup()
        except RuntimeError:
            return
        if popup is None:
            return
        needle = (text or "").strip().lower()
        if not needle:
            popup.setCurrentIndex(QModelIndex())
            return
        model = self._string_model
        for row in range(model.rowCount()):
            label = (model.data(model.index(row, 0)) or "").strip().lower()
            if label == needle:
                idx = model.index(row, 0)
                popup.setCurrentIndex(idx)
                popup.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtCenter)
                return
        for row in range(model.rowCount()):
            label = (model.data(model.index(row, 0)) or "").strip().lower()
            if needle in label:
                idx = model.index(row, 0)
                popup.setCurrentIndex(idx)
                popup.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)
                return
        popup.setCurrentIndex(QModelIndex())

    def _refresh_open_popup_list(self, *, scroll_to_filter: bool = False) -> None:
        """Update the visible list from ``_string_model`` without ``complete()`` (resets highlight)."""
        try:
            popup = self._completer.popup()
            if popup is None or not popup.isVisible():
                return
            popup.setModel(self._string_model)
            if scroll_to_filter and (self._anchor_text or "").strip():
                self._highlight_popup_row_for_text(self._anchor_text)
            else:
                popup.setCurrentIndex(QModelIndex())
                popup.scrollToTop()
        except RuntimeError:
            return

    def _present_popup_list(self, *, scroll_to_filter: bool = False) -> None:
        """Show the completer popup from ``_string_model`` (works with an empty filter / arrow click)."""
        c = self._guarded_combo()
        if c is None:
            return
        self._rebuild_model()
        if self._string_model.rowCount() <= 0:
            return
        self._ensure_popup_pick_binding()
        try:
            popup = self._completer.popup()
        except RuntimeError:
            return
        if popup is None:
            return
        prefix = self._filter_text_for_list()
        self._completer.setCompletionPrefix(prefix)
        popup.setModel(self._string_model)
        le = c.lineEdit()
        width = max((le.width() if le is not None else 0), c.width(), 200)
        popup.setMinimumWidth(width)
        visible_rows = min(
            self._string_model.rowCount(),
            max(1, int(self._completer.maxVisibleItems())),
        )
        popup.setFixedHeight(visible_rows * FORM_COMBO_LIST_ROW_HEIGHT_PX + 6)
        if le is not None:
            origin = le.mapToGlobal(le.rect().bottomLeft())
        else:
            origin = c.mapToGlobal(c.rect().bottomLeft())
        popup.move(origin)
        popup.show()
        self._refresh_open_popup_list(scroll_to_filter=scroll_to_filter)

    def _is_programmatic_update(self) -> bool:
        return int(getattr(self, "_programmatic_update_depth", 0)) > 0

    def _hide_list_popup(self) -> None:
        self._browsing_list = False
        try:
            popup = self._completer.popup()
            if popup is not None:
                popup.hide()
        except RuntimeError:
            pass

    def _begin_programmatic_update(self) -> None:
        self._programmatic_update_depth = int(getattr(self, "_programmatic_update_depth", 0)) + 1

    def _end_programmatic_update(self) -> None:
        depth = int(getattr(self, "_programmatic_update_depth", 0))
        self._programmatic_update_depth = max(0, depth - 1)
        if self._programmatic_update_depth == 0:
            self._anchor_text = ""
            self._hide_list_popup()
            c = self._guarded_combo()
            if c is not None:
                le = c.lineEdit()
                if le is not None:
                    le.blockSignals(True)
                    le.clear()
                    le.blockSignals(False)

    def _read_anchor_text(self) -> str:
        c = self._guarded_combo()
        if c is None:
            return ""
        le = c.lineEdit()
        return (le.text() if le is not None else "") or ""

    def _click_on_combo_line_edit(self, combo: QComboBox, event: QMouseEvent) -> bool:
        """True when the click is on the text area (not the arrow)."""
        le = combo.lineEdit()
        if le is None:
            return False
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        return le.geometry().contains(pos)

    def _ensure_popup_pick_binding(self) -> None:
        try:
            popup = self._completer.popup()
        except RuntimeError:
            return
        if popup is None or getattr(popup, "_etl_pick_bound", False):
            return
        popup.clicked.connect(self._on_popup_item_clicked)
        popup.activated.connect(self._on_popup_item_clicked)
        if not getattr(popup, "_etl_popup_key_filter", None):
            filt = _CompleterPopupKeyFilter(self, popup)
            popup.installEventFilter(filt)
            popup._etl_popup_key_filter = filt  # type: ignore[attr-defined]
        popup._etl_pick_bound = True  # type: ignore[attr-defined]

    def _on_popup_item_clicked(self, index: QModelIndex) -> None:
        """Commit only on explicit mouse choice in the list."""
        if not index.isValid():
            return
        try:
            data = index.data(Qt.ItemDataRole.DisplayRole)
        except RuntimeError:
            return
        if data:
            self._finish_list_selection(str(data))

    def _list_key_target(self, watched: QObject) -> bool:
        """Line edit, combo, or completer popup — all receive list navigation keys."""
        c = self._guarded_combo()
        if c is None:
            return False
        if watched is c:
            return True
        le = c.lineEdit()
        if le is not None and watched is le:
            return True
        try:
            popup = self._completer.popup()
            if popup is not None and watched is popup:
                return True
        except RuntimeError:
            pass
        return False

    def _prepare_popup_row_for_tab_commit(self) -> None:
        """Tab should commit like autocomplete: highlight first filtered row if none selected."""
        try:
            popup = self._completer.popup()
        except RuntimeError:
            return
        if popup is None or not popup.isVisible():
            return
        if popup.currentIndex().isValid():
            return
        model = self._string_model
        if model.rowCount() <= 0:
            return
        idx = model.index(0, 0)
        popup.setCurrentIndex(idx)
        popup.scrollTo(idx, QAbstractItemView.ScrollHint.PositionAtTop)

    def _label_to_commit_from_open_popup(
        self, *, allow_first_filtered_row: bool = False
    ) -> str | None:
        """Highlighted popup row, sole filtered match, or (Tab) first visible row."""
        try:
            popup = self._completer.popup()
            if popup is None or not popup.isVisible():
                return None
        except RuntimeError:
            return None
        cur = popup.currentIndex()
        if cur.isValid():
            data = popup.model().data(cur, Qt.ItemDataRole.DisplayRole)
            if data:
                return str(data).strip() or None
        model = self._string_model
        if model.rowCount() == 1:
            data = model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
            if data:
                return str(data).strip() or None
        if allow_first_filtered_row and model.rowCount() >= 1:
            data = model.data(model.index(0, 0), Qt.ItemDataRole.DisplayRole)
            if data:
                return str(data).strip() or None
        return None

    def _commit_popup_selection_if_any(self, *, tab_autocomplete: bool = False) -> bool:
        if tab_autocomplete:
            self._prepare_popup_row_for_tab_commit()
        label = self._label_to_commit_from_open_popup(
            allow_first_filtered_row=tab_autocomplete
        )
        if not label:
            return False
        self._finish_list_selection(label)
        return True

    def _on_combo_native_activated(self, _index: int) -> None:
        """Block native QComboBox popup from committing while browsing the search list."""
        if self._accepting_selection:
            return
        if self._browsing_list:
            self._apply_browse_open_state()

    def _apply_browse_open_state(self) -> None:
        """Keep filter text in the field; highlight the matching row when reopening after a pick."""
        c = self._guarded_combo()
        if c is None:
            return
        anchor = self._anchor_text if self._anchor_text is not None else ""
        le = c.lineEdit()
        if le is not None:
            le.blockSignals(True)
            le.setText(anchor)
            le.blockSignals(False)
        if anchor and self._label_matches_combo_item(anchor):
            self._sync_combo_index_from_label(anchor, emit_change=True)
        else:
            c.blockSignals(True)
            c.setCurrentIndex(-1)
            c.blockSignals(False)
        try:
            if anchor.strip():
                self._highlight_popup_row_for_text(anchor)
            else:
                popup = self._completer.popup()
                if popup is not None:
                    popup.setCurrentIndex(QModelIndex())
        except RuntimeError:
            pass

    def _reset_browse_without_pick(self) -> None:
        """Closing the list without Enter / click — leave the field unchanged."""
        if self._accepting_selection:
            return
        self._browsing_list = False
        self._apply_browse_open_state()

    def _on_combo_index_changed_during_browse(self, index: int) -> None:
        """Qt may set index 0 when the arrow opens the list; undo until user confirms."""
        if self._accepting_selection or not self._browsing_list:
            return
        if index < 0:
            return
        self._apply_browse_open_state()

    def _on_combo_current_text_changed_during_browse(self, text: str) -> None:
        """Revert only when Qt injects a full row label — not while the user types a filter."""
        if self._accepting_selection or not self._browsing_list:
            return
        if not self._label_matches_combo_item(text):
            return
        self._sync_anchor_from_line_edit_while_browsing()

    def _open_popup(self) -> None:
        c = self._guarded_combo()
        if c is None or getattr(c, "_etl_form_combo_view_only", False):
            return
        try:
            self._accepting_selection = False
            self._browsing_list = True
            self._anchor_text = self._read_anchor_text()
            self._apply_browse_open_state()
            anchor = (self._anchor_text or "").strip()
            self._present_popup_list(scroll_to_filter=bool(anchor))
        except RuntimeError:
            return

    def _on_completer_highlighted(self, *args: Any) -> None:
        """Keep the line edit showing filter text until the user confirms a row (Enter / click)."""
        if self._accepting_selection:
            return
        self._sync_anchor_from_line_edit_while_browsing()

    def _update_filter_from_line_edit(self, text: str) -> None:
        """Apply user filter text; ignore Qt stuffing a different full row label into the field."""
        typed = (text or "").strip()
        if self._label_matches_combo_item(text):
            c = self._guarded_combo()
            le = c.lineEdit() if c is not None else None
            anchor = self._anchor_text if self._anchor_text is not None else ""
            if typed and typed.lower() != anchor.strip().lower():
                # Field shows a committed value (e.g. India) — use it as the search filter.
                self._anchor_text = text
                return
            if le is not None and le.text() != anchor:
                le.blockSignals(True)
                le.setText(anchor)
                le.blockSignals(False)
            return
        self._anchor_text = text or ""

    def _show_filter_popup(self) -> None:
        """Open or refresh the search list for the current ``_anchor_text``."""
        try:
            self._browsing_list = True
            anchor = (self._anchor_text or "").strip()
            try:
                popup = self._completer.popup()
                if popup is not None and popup.isVisible():
                    self._present_popup_list(scroll_to_filter=bool(anchor))
                    return
            except RuntimeError:
                pass
            self._present_popup_list(scroll_to_filter=bool(anchor))
        except RuntimeError:
            return

    def _on_text_changed(self, text: str) -> None:
        c = self._guarded_combo()
        if c is None or self._accepting_selection:
            return
        if self._is_programmatic_update():
            return
        try:
            self._update_filter_from_line_edit(text)
            typed = (self._anchor_text or "").strip()
            if not typed and not self._browsing_list and c.currentIndex() >= 0:
                c.blockSignals(True)
                c.setCurrentIndex(-1)
                c.blockSignals(False)
            self._rebuild_model()

            popup = self._completer.popup()
            if popup is not None and popup.isVisible():
                self._refresh_open_popup_list(scroll_to_filter=bool(typed))
                return
            if not typed:
                return
            shown = self._string_model.stringList()
            if not shown:
                return
            if len(shown) == 1 and (shown[0] or "").strip().lower() == typed.lower():
                return
            self._show_filter_popup()
        except RuntimeError:
            return

    def _sync_combo_index_from_label(self, label: str, *, emit_change: bool = False) -> None:
        c = self._guarded_combo()
        if c is None:
            return
        needle = (label or "").strip().lower()
        if not needle:
            return
        for i in range(c.count()):
            if (c.itemText(i) or "").strip().lower() == needle:
                if emit_change:
                    c.setCurrentIndex(i)
                else:
                    c.blockSignals(True)
                    c.setCurrentIndex(i)
                    c.blockSignals(False)
                return

    def _finish_list_selection(self, label: str) -> None:
        c = self._guarded_combo()
        if c is None:
            return
        text = (label or "").strip()
        self._browsing_list = False
        self._accepting_selection = True
        self._anchor_text = text  # Reopen list filtered to this label (e.g. India).
        le = c.lineEdit()
        if le is not None and text:
            le.blockSignals(True)
            le.setText(text)
            le.blockSignals(False)
        if text:
            # Emit currentIndexChanged so dependent combos (e.g. Country → State) refill.
            self._sync_combo_index_from_label(text, emit_change=True)
        hint_clear = getattr(c, "_world_loc_clear_inline_error", None)
        if hint_clear is not None and text:
            QTimer.singleShot(0, hint_clear)
        try:
            popup = self._completer.popup()
            if popup is not None:
                popup.hide()
        except RuntimeError:
            pass
        self._suppress_focus_click_open = True
        QTimer.singleShot(150, self._clear_suppress_focus_click_open)

    def _clear_suppress_focus_click_open(self) -> None:
        self._suppress_focus_click_open = False
        self._accepting_selection = False

    def _open_popup_then_nav(self, key: int, modifiers: Qt.KeyboardModifier, text: str) -> None:
        self._open_popup()
        try:
            popup = self._completer.popup()
            if popup is not None and popup.isVisible():
                nav = QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text)
                QApplication.sendEvent(popup, nav)
        except RuntimeError:
            return

    def _navigate_popup_list(self, popup: QAbstractItemView, key: int) -> None:
        """Move list highlight without ``sendEvent`` (avoids event-filter recursion on the popup)."""
        try:
            model = popup.model()
        except RuntimeError:
            return
        if model is None or model.rowCount() <= 0:
            return
        row = popup.currentIndex().row()
        if row < 0:
            row = 0
        last = model.rowCount() - 1
        if key == Qt.Key.Key_Down:
            row = min(row + 1, last)
        elif key == Qt.Key.Key_Up:
            row = max(row - 1, 0)
        elif key == Qt.Key.Key_PageDown:
            row = min(row + max(1, int(self._completer.maxVisibleItems())), last)
        elif key == Qt.Key.Key_PageUp:
            row = max(row - max(1, int(self._completer.maxVisibleItems())), 0)
        elif key == Qt.Key.Key_Home:
            row = 0
        elif key == Qt.Key.Key_End:
            row = last
        idx = model.index(row, 0)
        popup.setCurrentIndex(idx)
        popup.scrollTo(idx, QAbstractItemView.ScrollHint.EnsureVisible)

    def _handle_list_key_press(self, watched: QObject, event: QKeyEvent) -> bool:
        if not self._list_key_target(watched):
            return False

        key = event.key()
        try:
            popup = self._completer.popup()
            popup_visible = popup is not None and popup.isVisible()
        except RuntimeError:
            return False

        if key in _LIST_NAV_KEYS:
            if popup_visible and popup is not None:
                if watched is popup:
                    self._navigate_popup_list(popup, key)
                else:
                    QApplication.sendEvent(popup, event)
                return True
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                QTimer.singleShot(
                    0,
                    lambda k=key, m=event.modifiers(), t=event.text(): self._open_popup_then_nav(
                        k, m, t
                    ),
                )
                return True

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and popup_visible and popup is not None:
            self._commit_popup_selection_if_any()
            return True

        if key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
            if popup_visible and popup is not None:
                if not self._commit_popup_selection_if_any(tab_autocomplete=True):
                    popup.hide()
                    self._reset_browse_without_pick()
                return False
            c = self._guarded_combo()
            le = c.lineEdit() if c is not None else None
            typed = (le.text() if le is not None else c.currentText() if c else "") or ""
            typed = typed.strip()
            if typed and self._label_matches_combo_item(typed):
                self._finish_list_selection(typed)
            return False

        if key == Qt.Key.Key_Escape and popup_visible and popup is not None:
            popup.hide()
            self._reset_browse_without_pick()
            return True

        return False

    def _handle_dropdown_click(self, combo: QComboBox, event: QMouseEvent) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if self._click_on_combo_line_edit(combo, event):
            return False
        try:
            popup = self._completer.popup()
            if popup is not None and popup.isVisible():
                popup.hide()
                self._reset_browse_without_pick()
            else:
                self._open_popup()
        except RuntimeError:
            return False
        return True

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.KeyPress and isinstance(event, QKeyEvent):
            if self._handle_list_key_press(watched, event):
                return True

        c = self._guarded_combo()
        if (
            c is not None
            and watched is c
            and event.type() == QEvent.Type.MouseButtonPress
            and isinstance(event, QMouseEvent)
        ):
            if self._handle_dropdown_click(c, event):
                return True

        if not self._open_on_focus_click or self._suppress_focus_click_open:
            return False
        if self._is_programmatic_update():
            return False
        c = self._guarded_combo()
        if c is None or getattr(c, "_etl_form_combo_view_only", False):
            return False
        try:
            le = c.lineEdit()
        except RuntimeError:
            return False
        if le is None or watched is not le:
            return False
        if event.type() not in (QEvent.Type.FocusIn, QEvent.Type.MouseButtonPress):
            return False
        QTimer.singleShot(0, self._open_popup)
        return False

    def set_limits(self, top_n_when_empty: int, max_visible_items: int) -> None:
        """Update how many rows show with an empty filter (large static lists need a higher cap)."""
        self._top_n = max(1, int(top_n_when_empty))
        try:
            self._completer.setMaxVisibleItems(max(1, int(max_visible_items)))
        except RuntimeError:
            return
        self._rebuild_model()


def _patch_searchable_combo_show_popup(combo: QComboBox) -> None:
    """Arrow / Alt+Down: completer list only (native QComboBox popup commits row 0 on open)."""
    if getattr(combo, "_etl_search_popup_patched", False):
        return
    orig_show = combo.showPopup
    orig_hide = combo.hidePopup

    def show_popup() -> None:
        if getattr(combo, "_etl_form_combo_view_only", False):
            return
        ctrl = getattr(combo, "_etl_searchable_mk_ctrl", None)
        if ctrl is not None:
            popup = ctrl._completer.popup()
            if popup is not None and popup.isVisible():
                popup.hide()
                ctrl._reset_browse_without_pick()
                return
            ctrl._open_popup()
            return
        orig_show()

    def hide_popup() -> None:
        ctrl = getattr(combo, "_etl_searchable_mk_ctrl", None)
        if ctrl is not None:
            try:
                popup = ctrl._completer.popup()
                if popup is not None:
                    popup.hide()
            except RuntimeError:
                pass
            ctrl._reset_browse_without_pick()
            return
        orig_hide()

    combo.showPopup = show_popup  # type: ignore[method-assign]
    combo.hidePopup = hide_popup  # type: ignore[method-assign]
    combo._etl_search_popup_patched = True  # type: ignore[attr-defined]


def _patch_searchable_widget_key_press(widget: QComboBox, *, attr: str) -> None:
    if getattr(widget, attr, False):
        return
    orig = widget.keyPressEvent

    def key_press(event) -> None:  # type: ignore[no-untyped-def]
        ctrl = getattr(widget, "_etl_searchable_mk_ctrl", None)
        if ctrl is not None and isinstance(event, QKeyEvent):
            if ctrl._handle_list_key_press(widget, event):
                return
        orig(event)

    widget.keyPressEvent = key_press  # type: ignore[method-assign]
    setattr(widget, attr, True)


def apply_searchable_master_key_combo(
    combo: QComboBox,
    *,
    top_n_when_empty: int = 10,
    max_visible_items: int = 10,
    open_popup_on_focus_click: bool = True,
    line_edit_placeholder: str | None = None,
) -> None:
    """Searchable combo: first ``top_n_when_empty`` rows when empty; filter as you type.

    Use when the combo has real rows only (no leading ``Select …`` item). Call after
    :func:`ui.form_combobox_style.apply_form_combobox_field`.
    """
    attr = "_etl_searchable_mk_ctrl"
    existing = getattr(combo, attr, None)
    if existing is not None:
        existing.set_limits(top_n_when_empty, max_visible_items)
        if line_edit_placeholder:
            le = combo.lineEdit()
            if le is not None:
                le.setPlaceholderText(line_edit_placeholder)
        existing._rebuild_model()
        _patch_searchable_combo_show_popup(combo)
        le = combo.lineEdit()
        if le is not None:
            _patch_searchable_widget_key_press(le, attr="_etl_search_le_kp_patched")
        _patch_searchable_widget_key_press(combo, attr="_etl_search_combo_kp_patched")
        return

    combo.setEditable(True)
    combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
    install_combo_ignore_wheel_when_closed(combo)
    le = combo.lineEdit()
    if line_edit_placeholder and le is not None:
        le.setPlaceholderText(line_edit_placeholder)

    ctrl = _SearchableMasterKeyComboController(
        combo,
        top_n_when_empty=top_n_when_empty,
        max_visible_items=max_visible_items,
        open_popup_on_focus_click=open_popup_on_focus_click,
    )
    setattr(combo, attr, ctrl)
    _patch_searchable_combo_show_popup(combo)
    le = combo.lineEdit()
    if le is not None:
        _patch_searchable_widget_key_press(le, attr="_etl_search_le_kp_patched")
    _patch_searchable_widget_key_press(combo, attr="_etl_search_combo_kp_patched")


def wire_searchable_master_key_combo(
    combo: QComboBox,
    *,
    search_field_label: str,
    top_n_when_empty: int = 10,
    max_visible_items: int = 10,
) -> None:
    """Apply :func:`apply_searchable_master_key_combo` with the same column hint as Create BU Organization."""
    from ui.form_page_styles import placeholder_search_select

    label = (search_field_label or "Item").strip()
    apply_searchable_master_key_combo(
        combo,
        top_n_when_empty=top_n_when_empty,
        max_visible_items=max_visible_items,
        line_edit_placeholder=placeholder_search_select(f"{label} Id", f"{label} Name"),
    )


def wire_searchable_labeled_rows_combo(
    combo: QComboBox,
    *,
    rows: Sequence[tuple[str, Any]],
    search_field_label: str,
    default_display_text: str | None = None,
    top_n_when_empty: int | None = None,
    max_visible_items: int | None = None,
    select_first_on_fill: bool = True,
) -> None:
    """Replace ``combo`` contents with ``(label, userData)`` rows and the same searchable UX as master-key fields.

    Call after :func:`ui.form_combobox_style.apply_form_combobox_field`. ``userData`` may match ``label`` for
    plain string enums.

    By default, empty-filter popup size scales with row count (so e.g. all countries appear). Typing still
    filters the full list.

    When ``select_first_on_fill`` is False, no row is selected after fill (line edit cleared); use for
    cascading location fields that must stay empty until the user picks a value.
    """
    ctrl = getattr(combo, "_etl_searchable_mk_ctrl", None)
    if ctrl is not None:
        ctrl._begin_programmatic_update()
    le = combo.lineEdit()
    combo.blockSignals(True)
    if le is not None:
        le.blockSignals(True)
    combo.clear()
    for label, data in rows:
        text = (label or "").strip()
        if not text:
            continue
        combo.addItem(text, data)
    if default_display_text and combo.findText(default_display_text) >= 0:
        combo.setCurrentText(default_display_text)
    elif combo.count() > 0 and select_first_on_fill:
        combo.setCurrentIndex(0)
    elif combo.count() > 0 and not select_first_on_fill:
        combo.setCurrentIndex(-1)
        if le is not None:
            le.clear()
    if le is not None:
        le.blockSignals(False)
    combo.blockSignals(False)
    if ctrl is not None:
        ctrl._end_programmatic_update()
    n_items = combo.count()
    if top_n_when_empty is None:
        # Cap very large lists for empty-prefix popup performance; typing narrows further.
        top = min(8000, max(50, n_items))
    else:
        top = max(1, int(top_n_when_empty))
    if max_visible_items is None:
        mx = min(80, max(20, min(top, 50)))
    else:
        mx = max(1, int(max_visible_items))
    wire_searchable_master_key_combo(
        combo,
        search_field_label=search_field_label,
        top_n_when_empty=top,
        max_visible_items=mx,
    )
    ctrl = getattr(combo, "_etl_searchable_mk_ctrl", None)
    if ctrl is not None:
        ctrl._anchor_text = ""
        ctrl._rebuild_model()


def sync_combo_index_from_display_text(
    combo: QComboBox | None,
    *,
    emit_change: bool = False,
    ignore_leading_rows: int = 0,
) -> bool:
    """When the line edit shows a full row label, align ``currentIndex`` (and ``itemData``) with it."""
    if combo is None:
        return False
    text = (combo.currentText() or "").strip()
    if not text:
        return False
    needle = text.lower()
    start = max(0, int(ignore_leading_rows))
    for i in range(start, combo.count()):
        if (combo.itemText(i) or "").strip().lower() != needle:
            continue
        data = combo.itemData(i)
        if data is None or str(data).strip() == "":
            continue
        if combo.currentIndex() != i:
            if emit_change:
                combo.setCurrentIndex(i)
            else:
                combo.blockSignals(True)
                combo.setCurrentIndex(i)
                combo.blockSignals(False)
        return True
    return False


def is_searchable_form_combo(combo: QComboBox | None) -> bool:
    """True when the combo uses :class:`_SearchableMasterKeyComboController` (editable + list)."""
    return combo is not None and getattr(combo, "_etl_searchable_mk_ctrl", None) is not None


def combo_payload_user_data(
    combo: QComboBox | None,
    *,
    ignore_leading_rows: int = 0,
) -> Any | None:
    """Resolve ``itemData`` for API payloads from what the user sees in the field.

    Searchable combos: match line-edit text to a row (see :func:`combo_resolved_master_key_seq`).
    Plain combos: ``itemData`` for ``currentIndex`` when index is valid.
    """
    if combo is None:
        return None
    if is_searchable_form_combo(combo):
        return combo_resolved_master_key_seq(combo, ignore_leading_rows=ignore_leading_rows)
    idx = combo.currentIndex()
    if idx < 0:
        return None
    return combo.itemData(idx)


def combo_resolved_master_key_seq(
    combo: QComboBox | None,
    *,
    ignore_leading_rows: int = 0,
) -> Any | None:
    """``itemData`` for the row whose label equals the line edit (case-insensitive strip).

    Only the text visible in the field counts for create/save — an old ``currentIndex`` left
    after clearing the line edit is ignored.

    ``ignore_leading_rows`` skips leading combo rows (e.g. a legacy ``Select …`` placeholder).
    """
    if combo is None:
        return None
    needle = (combo.currentText() or "").strip().lower()
    if not needle:
        return None
    start = max(0, int(ignore_leading_rows))
    sync_combo_index_from_display_text(combo, ignore_leading_rows=start)
    idx = combo.currentIndex()
    if idx >= start and idx < combo.count():
        row = (combo.itemText(idx) or "").strip().lower()
        if needle == row:
            data = combo.itemData(idx)
            if data is not None and str(data).strip() != "":
                return data
    for i in range(start, combo.count()):
        if (combo.itemText(i) or "").strip().lower() == needle:
            data = combo.itemData(i)
            if data is not None and str(data).strip() != "":
                return data
    return None


def master_key_invalid_typed_text(
    combo: QComboBox | None,
    *,
    ignore_leading_rows: int = 0,
) -> bool:
    """True when the line edit has text that does not match any combo row."""
    if combo is None:
        return False
    typed = (combo.currentText() or "").strip()
    if not typed:
        return False
    return combo_resolved_master_key_seq(combo, ignore_leading_rows=ignore_leading_rows) is None


def _coerce_master_seq_int(seq_val: Any, *, blank_default: int = MASTER_KEY_BLANK_SEQ_DEFAULT) -> int:
    if seq_val is None or str(seq_val).strip() == "":
        return blank_default
    if isinstance(seq_val, bool):
        return int(seq_val)
    if isinstance(seq_val, int):
        return seq_val
    if isinstance(seq_val, float) and seq_val == int(seq_val):
        return int(seq_val)
    s = str(seq_val).strip()
    if s.isdigit():
        return int(s)
    raise ValueError(f"Not a whole number: {seq_val!r}")


def _coerce_master_seq_int_required(seq_val: Any) -> int:
    if seq_val is None or str(seq_val).strip() == "":
        raise ValueError("empty master-key seq")
    if isinstance(seq_val, bool):
        return int(seq_val)
    if isinstance(seq_val, int):
        return seq_val
    if isinstance(seq_val, float) and seq_val == int(seq_val):
        return int(seq_val)
    s = str(seq_val).strip()
    if s.isdigit():
        return int(s)
    raise ValueError(f"Not a whole number: {seq_val!r}")


def require_master_key_seq_for_payload(
    combo: QComboBox | None,
    *,
    field_caption: str,
    strict_phrase: str | None = None,
    ignore_leading_rows: int = 0,
) -> tuple[int | None, str | None]:
    """Resolve a required master-config combo for create/update.

    Returns ``(seq, None)`` on success, or ``(None, error_message)`` when the user
    must fix the field before calling the API (empty, invalid typed text, etc.).
    """
    from ui.strict_completer import strict_list_selection_message

    if combo is None:
        return None, f"{field_caption} is required."
    if master_key_invalid_typed_text(combo, ignore_leading_rows=ignore_leading_rows):
        phrase = strict_phrase or f"a {field_caption.lower()}"
        return None, strict_list_selection_message(phrase)
    raw = combo_resolved_master_key_seq(combo, ignore_leading_rows=ignore_leading_rows)
    if raw is None or str(raw).strip() == "":
        typed = (combo.currentText() or "").strip()
        if typed:
            phrase = strict_phrase or f"a {field_caption.lower()}"
            return None, strict_list_selection_message(phrase)
        return None, f"{field_caption} is required."
    try:
        return _coerce_master_seq_int_required(raw), None
    except ValueError:
        return None, f"{field_caption} must be a valid selection."


def master_key_seq_for_payload(
    combo: QComboBox | None,
    *,
    ignore_leading_rows: int = 0,
    blank_default: int = MASTER_KEY_BLANK_SEQ_DEFAULT,
) -> int:
    """Seq for optional master-config combos only (blank → ``blank_default``, default 99).

    Use only for combos filled via :func:`populate_master_key_by_field_name`
    (``api/master-setup/master-config/get-by-field-name``). For company/user/module
    list combos use :func:`reference_id_for_payload` instead (blank → ``None``).
    """
    raw = combo_resolved_master_key_seq(combo, ignore_leading_rows=ignore_leading_rows)
    return _coerce_master_seq_int(raw, blank_default=blank_default)


def _reference_value_empty(value: Any) -> bool:
    if value is None:
        return True
    s = str(value).strip()
    return not s or s.lower() in ("null", "none")


def coerce_reference_id_payload(value: Any) -> int | None:
    """Entity/reference list ids (company, contact, module, hierarchy level, etc.): blank → ``None``."""
    if _reference_value_empty(value):
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
    raise ValueError(f"Not a whole number: {value!r}")


def coerce_master_key_payload_int(
    value: Any, *, blank_default: int = MASTER_KEY_BLANK_SEQ_DEFAULT
) -> int:
    """Raw master-config seq for JSON: blank → ``blank_default`` (default 99)."""
    return _coerce_master_seq_int(value, blank_default=blank_default)


def reference_id_for_payload(combo: QComboBox | None) -> int | None:
    """Reference/entity combos (not master-config): blank → ``None`` (JSON null)."""
    raw = combo_resolved_item_data(combo)
    return coerce_reference_id_payload(raw)


def require_reference_id_for_payload(
    combo: QComboBox | None,
    *,
    field_caption: str,
    strict_phrase: str | None = None,
    ignore_leading_rows: int = 0,
) -> tuple[int | None, str | None]:
    """Like :func:`require_master_key_seq_for_payload` for reference/entity searchable combos."""
    from ui.strict_completer import strict_list_selection_message

    if combo is None:
        return None, f"{field_caption} is required."
    if master_key_invalid_typed_text(combo, ignore_leading_rows=ignore_leading_rows):
        phrase = strict_phrase or f"a {field_caption.lower()}"
        return None, strict_list_selection_message(phrase)
    try:
        ref_id = reference_id_for_payload(combo)
    except ValueError:
        return None, f"{field_caption} must be a valid selection."
    if ref_id is None:
        typed = (combo.currentText() or "").strip()
        if typed:
            phrase = strict_phrase or f"a {field_caption.lower()}"
            return None, strict_list_selection_message(phrase)
        return None, f"{field_caption} is required."
    return ref_id, None


# Alias for reference-data combos (company list, etc.) that are not strictly master-key rows.
combo_resolved_item_data = combo_resolved_master_key_seq


def reset_searchable_combo(combo: QComboBox | None) -> None:
    """Clear selection for a searchable (editable) combo."""
    if combo is None:
        return
    ctrl = getattr(combo, "_etl_searchable_mk_ctrl", None)
    if ctrl is not None:
        ctrl._begin_programmatic_update()
    le = combo.lineEdit()
    combo.blockSignals(True)
    if le is not None:
        le.blockSignals(True)
    combo.setCurrentIndex(-1)
    if le is not None:
        le.clear()
    if le is not None:
        le.blockSignals(False)
    combo.blockSignals(False)
    if ctrl is not None:
        ctrl._end_programmatic_update()


def set_searchable_combo_by_user_data(combo: QComboBox | None, user_data: Any) -> None:
    """Select the row whose ``itemData`` matches ``user_data`` and mirror its label into the line edit."""
    if combo is None:
        return
    if user_data is None:
        reset_searchable_combo(combo)
        return
    idx = combo.findData(user_data)
    if idx < 0 and isinstance(user_data, int):
        idx = combo.findData(str(user_data))
    if idx < 0:
        reset_searchable_combo(combo)
        return
    text = combo.itemText(idx)
    combo.blockSignals(True)
    combo.setCurrentIndex(idx)
    le = combo.lineEdit()
    if le is not None:
        le.setText(text)
    combo.blockSignals(False)
    ctrl = getattr(combo, "_etl_searchable_mk_ctrl", None)
    if ctrl is not None:
        ctrl._anchor_text = text


def populate_master_key_by_field_name(
    combo: QComboBox | None,
    field_name: str,
    *,
    token: str | None,
    include_placeholder: bool = False,
    placeholder: str = "Select…",
) -> None:
    """Fill ``combo`` from :func:`core.api.api_get_master_key_by_app_id_field_name`."""
    if combo is None:
        return
    result = api_get_master_key_by_app_id_field_name(
        field_name=field_name,
        token=token,
    )
    rows = result.get("data") if result.get("success") else []
    ctrl = getattr(combo, "_etl_searchable_mk_ctrl", None)
    if ctrl is not None:
        ctrl._begin_programmatic_update()
    le = combo.lineEdit()
    combo.blockSignals(True)
    if le is not None:
        le.blockSignals(True)
    combo.clear()
    if include_placeholder:
        combo.addItem(placeholder, None)
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            seq_val = master_key_row_seq_value(row)
            if seq_val is None:
                continue
            label = master_key_row_display_label(row).strip()
            if not label:
                continue
            combo.addItem(label, seq_val)
    if include_placeholder:
        combo.setCurrentIndex(0)
    else:
        combo.setCurrentIndex(-1)
        if le is not None:
            le.clear()
    if le is not None:
        le.blockSignals(False)
    combo.blockSignals(False)
    if ctrl is not None:
        ctrl._end_programmatic_update()
