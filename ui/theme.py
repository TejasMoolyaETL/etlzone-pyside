"""Central color and design tokens for MY ETLZONE App.

Change :class:`Theme` attributes to retheme the application. Global QSS and
shared styles in ``ui/styles.py`` are built from these values. Individual pages
may still set local ``setStyleSheet`` — prefer referencing :class:`Theme` when
editing those strings so colors stay consistent.
"""

from __future__ import annotations

import os


# ``polished`` is the new product UI. Set ``ETLZONE_UI_THEME=legacy`` before
# starting the app to restore the previous visual treatment without reverting
# code or affecting any workflow.
ACTIVE_UI_THEME = os.getenv("ETLZONE_UI_THEME", "polished").strip().lower()
IS_LEGACY_THEME = ACTIVE_UI_THEME == "legacy"


def _theme_value(polished: str, legacy: str) -> str:
    return legacy if IS_LEGACY_THEME else polished


class Theme:
    """Semantic palette — single source of truth for app-wide colors."""

    # Status
    ERROR = "#b00020"
    SUCCESS = "#107c10"
    WARNING = "#ca8a04"

    # App shell & surfaces
    BG_APP = _theme_value("#f3f6fb", "#f1f5f9")
    BG_PAGE_ALT = _theme_value("#f7f9fc", "#f6f8fb")
    BG_WHITE = "#ffffff"
    BG_CARD = "#ffffff"
    BG_CARD_TINT = _theme_value("#f2f6ff", "#eef4ff")
    BG_ACTIVITY = "#f4f7fb"
    BG_LOGIN_IMAGE = "#14243b"

    # Text
    TEXT_PRIMARY = _theme_value("#152238", "#0f172a")
    TEXT_SECONDARY = "#64748b"
    TEXT_MUTED = "#6b7280"
    TEXT_TITLE = _theme_value("#10233f", "#12243c")
    TEXT_SUBTITLE = "#4f5b6b"
    TEXT_INPUT = "#1f2937"
    PANEL_TEXT = "#dbe7fa"
    PANEL_TEXT_BRIGHT = "#ffffff"

    # Nav / headers (dashboard strip, list headers)
    HEADER_NAV = _theme_value("#0b1f3a", "#0f2340")
    # Top-right header actions (Filters / Refresh / Extract style): slate on navy.
    HEADER_ACCENT = "#334155"
    HEADER_ACCENT_HOVER = "#475569"
    HEADER_ACCENT_PRESSED = "#64748b"

    # Left panel
    PANEL_BG = _theme_value("#0b1f3a", "#0f2340")
    PANEL_BORDER = _theme_value("#18365f", "#243f66")
    PANEL_NAV_BORDER = _theme_value("#244368", "#3d5a7a")
    PANEL_NAV_HOVER = _theme_value("#132f52", "#19365f")
    PANEL_NAV_HOVER_BORDER = _theme_value("#28507c", "#2d4f7a")
    PANEL_NAV_SELECTED = _theme_value("#173a63", "#1e3a5f")
    PANEL_NAV_SELECTED_HOVER = _theme_value("#1b4676", "#234876")
    ACCENT = _theme_value("#3b82f6", "#3b82f6")
    ACCENT_STRONG = _theme_value("#2563eb", "#2563eb")
    ACCENT_SOFT = _theme_value("#eaf2ff", "#e0e7ff")
    FOCUS_RING = _theme_value("#60a5fa", "#94a3b8")

    # Borders
    BORDER_DEFAULT = _theme_value("#dbe3ef", "#e2e8f0")
    BORDER_INPUT = _theme_value("#cbd6e4", "#d1d5db")
    BORDER_CARD = "#d3dff6"
    BORDER_ACTIVITY = "#d9e1ec"

    # Primary buttons (dark)
    BTN_PRIMARY_BG = _theme_value("#2563eb", "#0f172a")
    BTN_PRIMARY_HOVER = _theme_value("#1d4ed8", "#1e293b")
    BTN_PRIMARY_PRESSED = _theme_value("#1e40af", "#020617")

    # Show-panel strip (when nav hidden)
    SHOW_PANEL_STRIP_BG = _theme_value("#0b1f3a", "#0f2340")
    SHOW_PANEL_STRIP_BORDER = _theme_value("#18365f", "#243f66")
    SHOW_PANEL_STRIP_TEXT = "#e2e8f0"
    SHOW_PANEL_STRIP_HOVER = "#1e3a5f"

    # Login placeholder gradient (also used in code with QColor)
    LOGIN_GRADIENT_START = "#0a1c33"
    LOGIN_GRADIENT_END = "#274f8a"


def panel_frame_stylesheet() -> str:
    """Stylesheet for the left navigation ``QFrame`` (DM_Tool style)."""
    t = Theme
    return (
        f"QFrame {{ background-color: {t.PANEL_BG}; border-right: 1px solid {t.PANEL_BORDER}; }}"
        f"QLabel {{ color: {t.PANEL_TEXT}; font-size: 13px; }}"
        f"QPushButton {{"
        f"  color: {t.PANEL_TEXT_BRIGHT}; background-color: transparent;"
        f"  border: none; border-bottom: 1px solid {t.PANEL_NAV_BORDER};"
        f"  border-radius: 7px; text-align: left; padding: 9px 11px;"
        f"}}"
        f"QPushButton:hover {{ background-color: {t.PANEL_NAV_HOVER}; border: 1px solid {t.PANEL_NAV_HOVER_BORDER}; border-bottom: 1px solid {t.PANEL_NAV_BORDER}; }}"
    )
