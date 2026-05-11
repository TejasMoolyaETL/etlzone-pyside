"""Shared UI styles built from :mod:`ui.theme`.

Import :class:`Theme` or legacy names (:data:`COLOR_ERROR`, etc.) for widgets.
Call :func:`apply_app_theme` once after creating :class:`QApplication`.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

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


def _fusion_light_palette() -> QPalette:
    """Palette that keeps system dark mode from bleeding into the app."""
    t = Theme
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(t.BG_APP))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(t.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor(t.BG_WHITE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(t.BG_PAGE_ALT))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(t.BG_WHITE))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(t.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Text, QColor(t.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(t.BG_WHITE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(t.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(t.BG_WHITE))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#cfe3ff"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(t.TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Link, QColor("#2563eb"))
    palette.setColor(QPalette.ColorRole.LinkVisited, QColor("#1d4ed8"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(INPUT_PLACEHOLDER_COLOR))
    palette.setColor(QPalette.ColorRole.Light, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Midlight, QColor("#edf2f7"))
    palette.setColor(QPalette.ColorRole.Mid, QColor(t.BORDER_DEFAULT))
    palette.setColor(QPalette.ColorRole.Dark, QColor("#94a3b8"))
    palette.setColor(QPalette.ColorRole.Shadow, QColor("#64748b"))

    disabled_text = QColor(t.TEXT_SECONDARY)
    disabled_base = QColor(t.BG_PAGE_ALT)
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
        QPalette.ColorRole.HighlightedText,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled_text)
    for role in (
        QPalette.ColorRole.Base,
        QPalette.ColorRole.Button,
        QPalette.ColorRole.Window,
    ):
        palette.setColor(QPalette.ColorGroup.Disabled, role, disabled_base)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#dbeafe"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.PlaceholderText, QColor(INPUT_PLACEHOLDER_COLOR))
    return palette


def global_application_stylesheet() -> str:
    """Base stylesheet applied to :class:`QApplication` for consistent shell colors.

    Widgets that call ``setStyleSheet`` with their own rules still override
    locally; this sets defaults for main windows, stacked content, and common
    controls where no per-widget style is set.
    """
    t = Theme
    return f"""
    QWidget {{
        color: {t.TEXT_PRIMARY};
    }}
    QMainWindow {{
        background-color: {t.BG_APP};
    }}
    QDialog {{
        background-color: {t.BG_WHITE};
        color: {t.TEXT_PRIMARY};
    }}
    /* Default transparent so form cards / white panels do not show a grey slab
       around small stacks (e.g. Edit/Back). Main content stacks set BG_APP locally
       (see dashboard_window). */
    QStackedWidget {{
        background-color: transparent;
        border: none;
    }}
    QAbstractScrollArea {{
        background-color: {t.BG_WHITE};
        color: {t.TEXT_PRIMARY};
    }}
    QTextEdit,
    QPlainTextEdit,
    QListView,
    QTreeView,
    QTableView,
    QTableWidget {{
        background-color: {t.BG_WHITE};
        color: {t.TEXT_PRIMARY};
        alternate-background-color: {t.BG_PAGE_ALT};
        selection-background-color: #cfe3ff;
        selection-color: {t.TEXT_PRIMARY};
    }}
    QHeaderView::section {{
        background-color: #f8fafc;
        color: #475569;
    }}
    QToolTip {{
        background-color: {t.BG_WHITE};
        color: {t.TEXT_PRIMARY};
        border: 1px solid {t.BORDER_DEFAULT};
        padding: 4px;
    }}
    QMenuBar {{
        background-color: {t.BG_WHITE};
        color: {t.TEXT_PRIMARY};
    }}
    QMenuBar::item:selected {{
        background-color: {t.BG_APP};
        color: {t.TEXT_PRIMARY};
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
    QRadioButton {{
        font-size: {APP_FONT_SIZE_PX}px;
        color: {t.TEXT_PRIMARY};
        spacing: 6px;
    }}
    QLineEdit,
    QTextEdit,
    QPlainTextEdit,
    QComboBox {{
        background-color: {t.BG_WHITE};
        color: {t.TEXT_INPUT};
        border: 1px solid {t.BORDER_DEFAULT};
        font-size: {APP_FONT_SIZE_PX}px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {t.BG_WHITE};
        color: {t.TEXT_PRIMARY};
        selection-background-color: #cfe3ff;
        selection-color: {t.TEXT_PRIMARY};
    }}
    QPushButton {{
        color: {t.TEXT_PRIMARY};
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
    """Apply app styling and neutralize system dark-theme palette leakage."""
    fusion = QStyleFactory.create("Fusion")
    if fusion is not None:
        app.setStyle(fusion)
    app.setPalette(_fusion_light_palette())
    app.setStyleSheet(global_application_stylesheet())
