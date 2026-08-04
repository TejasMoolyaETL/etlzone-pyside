"""Shared QComboBox stylesheet for form dropdowns (uses :mod:`ui.form_page_styles`).

Use :func:`apply_form_combobox_field` after populating items so every combo matches the
Create API modal **HTTP method** row (style, fixed height, expanding width).

Vertical padding matches :data:`FORM_INPUT_STYLE` (2px) so combo height aligns with QLineEdit
when both use the same ``height_px`` (e.g. :data:`MODAL_FIELD_HEIGHT_PX` or
:data:`FORM_SINGLELINE_FIELD_HEIGHT_PX`).
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QCompleter,
    QSizePolicy,
    QStyledItemDelegate,
)

from ui.form_page_styles import APP_FONT_SIZE_PX
from ui.theme import Theme

_fs = APP_FONT_SIZE_PX
# Compact popup rows (native dropdown + searchable completer list).
FORM_COMBO_LIST_ROW_HEIGHT_PX = 20

# Shared list / menu row hover (combo popups, QCompleter popups, QMenu).
FORM_LIST_ITEM_HOVER_BG = Theme.ACCENT_SOFT
FORM_LIST_ITEM_HOVER_FG = Theme.BTN_PRIMARY_PRESSED
FORM_LIST_ITEM_SELECTED_BG = Theme.ACCENT_SOFT
FORM_LIST_ITEM_SELECTED_FG = Theme.BTN_PRIMARY_HOVER

# Shared popup list chrome (native combo dropdown and QCompleter popup).
FORM_COMBO_POPUP_LIST_STYLE = f"""
    QListView {{
        border: 1px solid {Theme.BORDER_DEFAULT};
        outline: 0;
        background: {Theme.BG_WHITE};
        border-radius: 4px;
        font-size: {_fs}px;
        font-weight: 400;
        color: {Theme.TEXT_PRIMARY};
    }}
    QListView::item {{
        margin: 0px;
        padding: 1px 6px;
        min-height: 0px;
        height: {FORM_COMBO_LIST_ROW_HEIGHT_PX}px;
    }}
    QListView::item:hover {{
        background-color: {FORM_LIST_ITEM_HOVER_BG};
        color: {FORM_LIST_ITEM_HOVER_FG};
    }}
    QListView::item:selected {{
        background-color: {FORM_LIST_ITEM_SELECTED_BG};
        color: {FORM_LIST_ITEM_SELECTED_FG};
    }}
"""

FORM_COMBOBOX_STYLE = f"""
    QComboBox {{
        font-size: {_fs}px;
        font-weight: 400;
        color: {Theme.TEXT_PRIMARY};
        margin: 0px;
        padding: 2px 22px 2px 8px;
        border: 1px solid {Theme.BORDER_INPUT};
        border-radius: 4px;
        background-color: {Theme.BG_WHITE};
        outline: none;
    }}
    QComboBox:disabled {{
        color: {Theme.TEXT_SECONDARY};
        background-color: {Theme.BG_PAGE_ALT};
        border: 1px solid {Theme.BORDER_DEFAULT};
    }}
    QComboBox:hover:enabled {{
        border-color: {Theme.FOCUS_RING};
    }}
    QComboBox:focus:enabled {{
        border: 1px solid {Theme.FOCUS_RING};
    }}
    QComboBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        border: none;
        margin: 0px;
        padding: 0px;
        width: 18px;
    }}
    QComboBox QAbstractItemView {{
        border: 1px solid {Theme.BORDER_DEFAULT};
        outline: 0;
        background: {Theme.BG_WHITE};
        border-radius: 4px;
        margin: 0px;
        padding: 0px;
        selection-background-color: {Theme.ACCENT_SOFT};
        selection-color: {Theme.TEXT_PRIMARY};
        font-size: {_fs}px;
        font-weight: 400;
    }}
    QComboBox QAbstractItemView::item {{
        margin: 0px;
        padding: 1px 6px;
        min-height: 0px;
        height: {FORM_COMBO_LIST_ROW_HEIGHT_PX}px;
    }}
    QComboBox QAbstractItemView::item:hover {{
        background-color: {FORM_LIST_ITEM_HOVER_BG};
        color: {FORM_LIST_ITEM_HOVER_FG};
    }}
    QComboBox QAbstractItemView::item:selected {{
        background-color: {FORM_LIST_ITEM_SELECTED_BG};
        color: {FORM_LIST_ITEM_SELECTED_FG};
    }}
"""

# Display / view mode: value only (no arrow, no list) — matches :data:`ui.form_page_styles.FORM_READONLY_INPUT_STYLE`.
FORM_COMBOBOX_READONLY_STYLE = f"""
    QComboBox {{
        font-size: {_fs}px;
        font-weight: 400;
        color: {Theme.TEXT_SECONDARY};
        margin: 0px;
        padding: 2px 8px;
        border: 1px solid {Theme.BORDER_DEFAULT};
        border-radius: 4px;
        background-color: {Theme.BG_PAGE_ALT};
        outline: none;
    }}
    QComboBox::drop-down {{
        width: 0px;
        border: none;
        margin: 0px;
        padding: 0px;
    }}
    QComboBox::down-arrow {{
        image: none;
        width: 0px;
        height: 0px;
    }}
"""


class _FormComboViewOnlyFilter(QObject):
    """Block opening the list while the combo is in display (view-only) mode."""

    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo)
        self._combo = combo

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not getattr(self._combo, "_etl_form_combo_view_only", False):
            return False
        if event.type() in (
            QEvent.Type.MouseButtonPress,
            QEvent.Type.MouseButtonDblClick,
        ):
            if watched is self._combo or watched is self._combo.lineEdit():
                return True
        if event.type() == QEvent.Type.KeyPress:
            key = event.key() if hasattr(event, "key") else None
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up, Qt.Key.Key_F4, Qt.Key.Key_Space):
                if watched is self._combo or watched is self._combo.lineEdit():
                    return True
        return False


class _ComboIgnoreWheelWhenClosedFilter(QObject):
    """Ignore mouse wheel on closed combos so page scroll does not change the selection."""

    def __init__(self, combo: QComboBox) -> None:
        super().__init__(combo)
        self._combo = combo

    def _list_popup_open(self) -> bool:
        c = self._combo
        view = c.view()
        if view is not None and view.isVisible():
            return True
        completer = c.completer()
        if completer is not None:
            popup = completer.popup()
            if popup is not None and popup.isVisible():
                return True
        return False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() != QEvent.Type.Wheel:
            return False
        if watched is not self._combo and watched is not self._combo.lineEdit():
            return False
        if self._list_popup_open():
            return False
        event.ignore()
        return True


class _CompactComboListItemDelegate(QStyledItemDelegate):
    def __init__(self, row_height_px: int, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._row_height_px = max(14, int(row_height_px))

    def sizeHint(self, option, index):  # type: ignore[no-untyped-def]
        base = super().sizeHint(option, index)
        width = base.width() if base.width() > 0 else 200
        return QSize(width, self._row_height_px)


def apply_completer_popup_list_style(completer: QCompleter | None) -> None:
    """Match searchable combo list chrome on any :class:`QCompleter` popup."""
    if completer is None:
        return
    popup = completer.popup()
    if popup is None:
        return
    popup.setStyleSheet(FORM_COMBO_POPUP_LIST_STYLE)
    apply_compact_combo_popup_list(popup)


def install_global_completer_popup_styling() -> None:
    """Style every :class:`QCompleter` popup (line-edit search fields) at construction."""
    if getattr(QCompleter, "_etl_popup_list_styled", False):
        return
    from ui.list_field_keyboard import install_line_edit_completer_tab_commit

    _orig_init = QCompleter.__init__

    def _init(self: QCompleter, *args, **kwargs) -> None:
        _orig_init(self, *args, **kwargs)
        apply_completer_popup_list_style(self)
        install_line_edit_completer_tab_commit(self)

    QCompleter.__init__ = _init  # type: ignore[method-assign]
    QCompleter._etl_popup_list_styled = True  # type: ignore[attr-defined]


def apply_compact_combo_popup_list(view: QAbstractItemView | None) -> None:
    """Tight row height and no extra spacing on combo / completer popups."""
    if view is None:
        return
    view.setSpacing(0)
    view.setUniformItemSizes(True)
    if getattr(view, "_etl_compact_list_delegate", None) is None:
        delegate = _CompactComboListItemDelegate(FORM_COMBO_LIST_ROW_HEIGHT_PX, view)
        view.setItemDelegate(delegate)
        setattr(view, "_etl_compact_list_delegate", delegate)


def is_form_combobox_view_only(combo: QComboBox | None) -> bool:
    return combo is not None and bool(getattr(combo, "_etl_form_combo_view_only", False))


def _apply_combo_view_only_chrome(combo: QComboBox) -> None:
    setattr(combo, "_etl_form_combo_view_only", True)
    combo.setStyleSheet(FORM_COMBOBOX_READONLY_STYLE)
    le = combo.lineEdit()
    if le is not None:
        le.setReadOnly(True)
        le.setCursor(Qt.CursorShape.ArrowCursor)
    ctrl = getattr(combo, "_etl_searchable_mk_ctrl", None)
    if ctrl is not None:
        try:
            ctrl._hide_list_popup()
        except (AttributeError, RuntimeError):
            pass
    filt = getattr(combo, "_etl_combo_view_only_filter", None)
    if filt is None:
        filt = _FormComboViewOnlyFilter(combo)
        combo.installEventFilter(filt)
        le = combo.lineEdit()
        if le is not None:
            le.installEventFilter(filt)
        setattr(combo, "_etl_combo_view_only_filter", filt)


def _apply_combo_edit_chrome(combo: QComboBox) -> None:
    setattr(combo, "_etl_form_combo_view_only", False)
    edit_ss = getattr(combo, "_etl_combo_edit_stylesheet", FORM_COMBOBOX_STYLE)
    combo.setStyleSheet(edit_ss)
    le = combo.lineEdit()
    if le is not None:
        le.setReadOnly(False)
        le.setCursor(Qt.CursorShape.IBeamCursor)


def _wrap_combo_set_enabled_for_view_mode(combo: QComboBox) -> None:
    if getattr(combo, "_etl_enabled_view_wrap", False):
        return
    orig_set_enabled = combo.setEnabled

    def set_enabled(enabled: bool) -> None:
        orig_set_enabled(enabled)
        if enabled:
            _apply_combo_edit_chrome(combo)
        else:
            _apply_combo_view_only_chrome(combo)

    combo.setEnabled = set_enabled  # type: ignore[method-assign, assignment]
    setattr(combo, "_etl_enabled_view_wrap", True)


def set_form_combobox_view_only(combo: QComboBox | None, view_only: bool) -> None:
    """Display mode: show the current value only (no dropdown list or arrow).

    Edit mode: restores normal searchable / dropdown behavior. Safe to call on any
    combo that used :func:`apply_form_combobox_field`.
    """
    if combo is None:
        return
    _wrap_combo_set_enabled_for_view_mode(combo)
    combo.setEnabled(not view_only)


def set_form_combobox_edit_mode(combo: QComboBox | None) -> None:
    """Re-enable list interaction after :func:`set_form_combobox_view_only`."""
    set_form_combobox_view_only(combo, False)


def install_combo_ignore_wheel_when_closed(combo: QComboBox) -> None:
    """Prevent scroll-wheel from changing selection until the user opens the list."""
    attr = "_etl_combo_no_wheel_filter"
    if getattr(combo, attr, None) is not None:
        return
    filt = _ComboIgnoreWheelWhenClosedFilter(combo)
    combo.installEventFilter(filt)
    le = combo.lineEdit()
    if le is not None:
        le.installEventFilter(filt)
    setattr(combo, attr, filt)


def install_combo_popup_below_field(combo: QComboBox) -> None:
    """Anchor the list under the field.

    Some platform styles center the popup on the current item, so picking a lower entry
    shifts the list upward and covers the caption above the field.
    """
    attr = "_etl_combo_popup_below"
    if getattr(combo, attr, False):
        return
    open_list = combo.showPopup

    def show_popup() -> None:
        open_list()
        view = combo.view()
        if view is None:
            return
        popup = view.parentWidget() or view
        popup.resize(max(combo.width(), popup.width()), popup.height())
        target = combo.mapToGlobal(QPoint(0, combo.height()))
        screen = combo.screen()
        if screen is not None:
            available = screen.availableGeometry()
            if target.y() + popup.height() > available.bottom():
                above_y = combo.mapToGlobal(QPoint(0, 0)).y() - popup.height()
                if above_y >= available.top():
                    target.setY(above_y)
        popup.move(target)

    combo.showPopup = show_popup  # type: ignore[method-assign]
    setattr(combo, attr, True)


def apply_form_combobox_field(
    combo: QComboBox,
    *,
    height_px: int,
    min_width: int | None = None,
) -> None:
    """Apply shared combo chrome (same as Create API → HTTP method in modal).

    Call after ``addItem`` / ``addItems`` / ``configure_api_method_combo`` so the widget
    is fully configured before styling.
    """
    setattr(combo, "_etl_combo_edit_stylesheet", FORM_COMBOBOX_STYLE)
    combo.setStyleSheet(FORM_COMBOBOX_STYLE)
    combo.setFixedHeight(height_px)
    combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    if min_width is not None:
        combo.setMinimumWidth(min_width)
    apply_compact_combo_popup_list(combo.view())
    install_combo_ignore_wheel_when_closed(combo)
    from ui.list_field_keyboard import install_native_combo_dropdown_tab_commit

    install_native_combo_dropdown_tab_commit(combo)
    _wrap_combo_set_enabled_for_view_mode(combo)
    if not combo.isEnabled():
        _apply_combo_view_only_chrome(combo)
