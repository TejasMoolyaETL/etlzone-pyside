"""Central color and design tokens for MY ETLZONE App.

Change :class:`Theme` attributes to retheme the application. Global QSS and
shared styles in ``ui/styles.py`` are built from these values. Individual pages
may still set local ``setStyleSheet`` — prefer referencing :class:`Theme` when
editing those strings so colors stay consistent.
"""

from __future__ import annotations


class Theme:
    """Semantic palette — single source of truth for app-wide colors."""

    # Status
    ERROR = "#b00020"
    SUCCESS = "#107c10"
    WARNING = "#ca8a04"

    # App shell & surfaces
    BG_APP = "#f1f5f9"
    BG_PAGE_ALT = "#f6f8fb"
    BG_WHITE = "#ffffff"
    BG_CARD = "#ffffff"
    BG_CARD_TINT = "#eef4ff"
    BG_ACTIVITY = "#f4f7fb"
    BG_LOGIN_IMAGE = "#14243b"

    # Text
    TEXT_PRIMARY = "#0f172a"
    TEXT_SECONDARY = "#64748b"
    TEXT_MUTED = "#6b7280"
    TEXT_TITLE = "#12243c"
    TEXT_SUBTITLE = "#4f5b6b"
    TEXT_INPUT = "#1f2937"
    PANEL_TEXT = "#dbe7fa"
    PANEL_TEXT_BRIGHT = "#ffffff"

    # Nav / headers (dashboard strip, list headers)
    HEADER_NAV = "#0f2340"
    HEADER_ACCENT = "#334155"
    HEADER_ACCENT_HOVER = "#475569"
    HEADER_ACCENT_PRESSED = "#64748b"

    # Left panel
    PANEL_BG = "#0f2340"
    PANEL_BORDER = "#243f66"
    PANEL_NAV_BORDER = "#3d5a7a"
    PANEL_NAV_HOVER = "#19365f"
    PANEL_NAV_HOVER_BORDER = "#2d4f7a"

    # Borders
    BORDER_DEFAULT = "#e2e8f0"
    BORDER_INPUT = "#d1d5db"
    BORDER_CARD = "#d3dff6"
    BORDER_ACTIVITY = "#d9e1ec"

    # Primary buttons (dark)
    BTN_PRIMARY_BG = "#0f172a"
    BTN_PRIMARY_HOVER = "#1e293b"
    BTN_PRIMARY_PRESSED = "#020617"

    # Show-panel strip (when nav hidden)
    SHOW_PANEL_STRIP_BG = "#0f2340"
    SHOW_PANEL_STRIP_BORDER = "#243f66"
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
        f"  border-radius: 6px; text-align: left; padding: 8px 10px;"
        f"}}"
        f"QPushButton:hover {{ background-color: {t.PANEL_NAV_HOVER}; border: 1px solid {t.PANEL_NAV_HOVER_BORDER}; border-bottom: 1px solid {t.PANEL_NAV_BORDER}; }}"
    )
