"""Shared UI styles built from :mod:`ui.theme`.

Import :class:`Theme` or legacy names (:data:`COLOR_ERROR`, etc.) for widgets.
Call :func:`apply_app_theme` once after creating :class:`QApplication`.
"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from ui.form_page_styles import (
    APP_FONT_SIZE_PX,
    INPUT_PLACEHOLDER_COLOR,
    INPUT_PLACEHOLDER_FONT_WEIGHT,
    SUBMENU_FONT_SIZE_PX,
)
from ui.theme import Theme, panel_frame_stylesheet

# —— Backward-compatible aliases (delegate to Theme) ——
COLOR_ERROR = Theme.ERROR
COLOR_SUCCESS = Theme.SUCCESS
COLOR_CARD_BG = Theme.BG_CARD_TINT
COLOR_CARD_BORDER = Theme.BORDER_CARD
COLOR_ACTIVITY_BG = Theme.BG_ACTIVITY
COLOR_ACTIVITY_BORDER = Theme.BORDER_ACTIVITY

TITLE_STYLE = (
    f"font-size: 28px; font-weight: 700; color: {Theme.TEXT_TITLE};"
)
SUBTITLE_STYLE = f"font-size: 14px; color: {Theme.TEXT_SUBTITLE};"

PANEL_STYLESHEET = panel_frame_stylesheet()

# Fixed width for menu-bar submenus (px). Context menus use wider bounds below.
_SUBMENU_WIDTH_PX = 120
# Force each row to span the submenu so hover/selection is not text-sized only.
_SUBMENU_ITEM_MIN_WIDTH_PX = _SUBMENU_WIDTH_PX

# Table / list context menus — width follows content; cap only for very long single lines.
_CONTEXT_MENU_MAX_WIDTH_PX = 480

# Table / list right-click menus — :data:`APP_FONT_SIZE_PX` (global body); 1px item margin.
_CONTEXT_MENU_PAD_V = 1
_CONTEXT_MENU_PAD_H = 8

CONTEXT_MENU_STYLESHEET = (
    f"QMenu {{ border: 1px solid #e2e8f0; border-radius: 4px; background: white; "
    f"padding: 0px; min-width: 0px; max-width: {_CONTEXT_MENU_MAX_WIDTH_PX}px; "
    f"font-size: {APP_FONT_SIZE_PX}px; }} "
    f"QMenu::item {{ margin: 1px; padding: {_CONTEXT_MENU_PAD_V}px {_CONTEXT_MENU_PAD_H}px; "
    f"font-size: {APP_FONT_SIZE_PX}px; color: #334155; "
    "border-radius: 0px; } "
    "QMenu::item:selected, QMenu::item:hover { background: #e2e8f0; color: #1e293b; } "
    "QMenu::separator { height: 1px; background: #e2e8f0; margin: 1px 0; } "
)


def global_application_stylesheet() -> str:
    """Base stylesheet applied to :class:`QApplication` for consistent shell colors.

    Widgets that call ``setStyleSheet`` with their own rules still override
    locally; this sets defaults for main windows, stacked content, and common
    controls where no per-widget style is set.
    """
    t = Theme
    return f"""
    QMainWindow {{
        background-color: {t.BG_APP};
    }}
    QStackedWidget {{
        background-color: {t.BG_APP};
    }}
    QToolTip {{
        background-color: {t.BG_WHITE};
        color: {t.TEXT_PRIMARY};
        border: 1px solid {t.BORDER_DEFAULT};
        padding: 4px;
    }}
    QMenu {{
        background-color: {t.BG_WHITE};
        color: {t.TEXT_PRIMARY};
        border: 1px solid {t.BORDER_DEFAULT};
        padding: 0px;
        min-width: {_SUBMENU_WIDTH_PX}px;
        max-width: {_CONTEXT_MENU_MAX_WIDTH_PX}px;
        font-size: {SUBMENU_FONT_SIZE_PX}px;
    }}
    QMenu::item {{
        margin: 1px;
        padding: {_CONTEXT_MENU_PAD_V}px {_CONTEXT_MENU_PAD_H}px;
        font-size: {SUBMENU_FONT_SIZE_PX}px;
        min-height: 14px;
        border-radius: 0px;
        min-width: {_SUBMENU_WIDTH_PX}px;
    }}
    QMenu::item:selected,
    QMenu::item:hover {{
        background-color: {t.BG_APP};
        color: {t.TEXT_PRIMARY};
    }}
    QCheckBox {{
        font-size: {APP_FONT_SIZE_PX}px;
        color: {t.TEXT_PRIMARY};
        spacing: 6px;
    }}
    QComboBox {{
        font-size: {APP_FONT_SIZE_PX}px;
    }}
    QLineEdit::placeholder {{
        color: {INPUT_PLACEHOLDER_COLOR};
        font-size: {APP_FONT_SIZE_PX}px;
        font-weight: {INPUT_PLACEHOLDER_FONT_WEIGHT};
    }}
    QPlainTextEdit::placeholder {{
        color: {INPUT_PLACEHOLDER_COLOR};
        font-size: {APP_FONT_SIZE_PX}px;
        font-weight: {INPUT_PLACEHOLDER_FONT_WEIGHT};
    }}
    """


def apply_app_theme(app: QApplication) -> None:
    """Apply :func:`global_application_stylesheet` to the running application."""
    app.setStyleSheet(global_application_stylesheet())
