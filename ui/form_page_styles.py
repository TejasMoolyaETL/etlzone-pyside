"""Global UI typography — one place for font size across forms and data tables.

Change :data:`APP_FONT_SIZE_PX` to scale:
  - Create / View / Edit form labels, inputs, headers, buttons, errors
  - Form combo boxes (via :mod:`ui.form_combobox_style`)
  - Data table cells, filter row edits, and (slightly larger) column headers

Caption-to-control vertical gap on create/view/edit forms uses
:data:`FORM_LABEL_FIELD_SPACING_PX`.

Navy toolbars (Org list, other lists, Settings, Dashboard, and Create/View/Edit page headers)
share :data:`LIST_PAGE_HEADER_STYLESHEET` / :data:`FORM_PAGE_HEADER_STYLESHEET` (same value),
with :data:`LIST_PAGE_HEADER_TITLE_FONT_PX`, :data:`LIST_PAGE_HEADER_BUTTON_FONT_PX`,
and :data:`LIST_PAGE_HEADER_HEIGHT_PX`.

:data:`FORM_PAGE_FONT_SIZE_PX` is an alias of :data:`APP_FONT_SIZE_PX` for existing imports.

:data:`PAGE_SUBTITLE_FONT_SIZE_PX` / :data:`PAGE_SUBTITLE_STYLE` — muted line under a page title (Settings, etc.).

:data:`SUBMENU_FONT_SIZE_PX` — menu bar :class:`~PySide6.QtWidgets.QMenu` dropdowns (see :mod:`ui.styles` global stylesheet). Right-click menus use :data:`APP_FONT_SIZE_PX` via :data:`CONTEXT_MENU_STYLESHEET`.
"""

from __future__ import annotations

from ui.theme import Theme

APP_FONT_SIZE_PX = 10

# Menu bar dropdowns and shared QMenu styling (see :mod:`ui.styles`).
SUBMENU_FONT_SIZE_PX = 13

# Full-page create/view forms: one row height for QLineEdit and QComboBox (10px text + padding + border).
FORM_SINGLELINE_FIELD_HEIGHT_PX = 28

# QLineEdit / QPlainTextEdit placeholder (same body size as inputs; muted color).
INPUT_PLACEHOLDER_COLOR = "#94a3b8"
INPUT_PLACEHOLDER_FONT_WEIGHT = 400


def placeholder_search_select(*field_labels: str) -> str:
    """Completer/search fields — same wording as Create User Dept Name."""
    return "Search and select: " + " | ".join(field_labels)


def placeholder_auto_filled(source_field: str) -> str:
    return f"Auto-filled from {source_field.strip()}"


def placeholder_enter(noun_phrase: str) -> str:
    """Short hint, e.g. ``Enter username``."""
    return f"Enter {noun_phrase.strip()}"


def placeholder_confirm(phrase: str) -> str:
    """Second field in a pair, e.g. ``Confirm new password``."""
    return f"Confirm {phrase.strip()}"


def placeholder_example(sample: str) -> str:
    return f"e.g. {sample.strip()}"


# Appended to per-widget QLineEdit stylesheets (global :func:`ui.styles.global_application_stylesheet` also applies).
LINEEDIT_PLACEHOLDER_SUBSTYLE = (
    f"QLineEdit::placeholder {{ color: {INPUT_PLACEHOLDER_COLOR}; font-size: {APP_FONT_SIZE_PX}px; "
    f"font-weight: {INPUT_PLACEHOLDER_FONT_WEIGHT}; }}"
)

# Muted subtitle under a screen title (not the 14px marketing :data:`ui.styles.SUBTITLE_STYLE`).
PAGE_SUBTITLE_FONT_SIZE_PX = 12
PAGE_SUBTITLE_STYLE = (
    f"font-size: {PAGE_SUBTITLE_FONT_SIZE_PX}px; color: {Theme.TEXT_SECONDARY}; font-weight: 400;"
)

# Table header is one step larger than body text for hierarchy.
DATA_TABLE_HEADER_FONT_SIZE_PX = APP_FONT_SIZE_PX + 1

FORM_PAGE_FONT_SIZE_PX = APP_FONT_SIZE_PX

# Modal dialogs (QDialog): field row captions and feedback labels match form body size.
MODAL_FIELD_LABEL_STYLE = (
    f"color: #64748b; font-size: {APP_FONT_SIZE_PX}px; font-weight: 500;"
)
MODAL_FEEDBACK_SUCCESS_STYLE = (
    f"color: #16a34a; font-size: {APP_FONT_SIZE_PX}px; font-weight: 500;"
)

# Modal dialogs: compact single-line controls (below full-page :data:`FORM_SINGLELINE_FIELD_HEIGHT_PX`).
MODAL_FIELD_HEIGHT_PX = 24

# Vertical gap between a field caption and its control (create/view/edit forms).
FORM_LABEL_FIELD_SPACING_PX = 4

FORM_LABEL_STYLE = (
    f"color: #64748b; font-size: {APP_FONT_SIZE_PX}px; font-weight: 600; "
    "letter-spacing: 0.5px; text-transform: uppercase;"
)

FORM_INPUT_STYLE = (
    f"font-size: {APP_FONT_SIZE_PX}px; padding: 2px 8px; border: 1px solid #e2e8f0; "
    "border-radius: 4px; background-color: #ffffff;"
    + LINEEDIT_PLACEHOLDER_SUBSTYLE
)

FORM_READONLY_INPUT_STYLE = (
    f"font-size: {APP_FONT_SIZE_PX}px; padding: 2px 8px; border: 1px solid #e2e8f0; "
    "border-radius: 4px; background-color: #f1f5f9; color: #64748b;"
    + LINEEDIT_PLACEHOLDER_SUBSTYLE
)

FORM_ERROR_LABEL_STYLE = (
    f"color: #dc2626; font-size: {APP_FONT_SIZE_PX}px; font-weight: 500;"
)

# --- Data tables (read-only list UX, same base size as forms) ---

DATA_TABLE_STYLESHEET = f"""
            QTableWidget {{
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                gridline-color: #e2e8f0;
                font-size: {APP_FONT_SIZE_PX}px;
            }}
            QTableWidget::item {{
                padding: 0px;
                margin: 0px;
                color: #0f172a;
                font-size: {APP_FONT_SIZE_PX}px;
            }}
            QTableWidget::item:selected {{
                background-color: #e0e7ff;
                color: #0f172a;
            }}
            QTableWidget::item:selected:active {{
                background-color: #e0e7ff;
                color: #0f172a;
            }}
            QHeaderView::section {{
                background: #f8fafc;
                color: #475569;
                font-weight: 600;
                font-size: {DATA_TABLE_HEADER_FONT_SIZE_PX}px;
                padding: 3px 6px;
                border: none;
                border-bottom: 2px solid #e2e8f0;
                border-right: 1px solid #cbd5e1;
            }}
            """

FILTER_EDIT_STYLE = (
    f"QLineEdit {{ padding: 2px 6px; font-size: {APP_FONT_SIZE_PX}px; "
    "border: 1px solid #e2e8f0; border-radius: 3px; background: #ffffff; }}"
    + LINEEDIT_PLACEHOLDER_SUBSTYLE
)

# --- List pages / settings / dashboard: compact navy toolbar (same as Org list) ---

LIST_PAGE_HEADER_TITLE_FONT_PX = 16
LIST_PAGE_HEADER_BUTTON_FONT_PX = 12
LIST_PAGE_HEADER_HEIGHT_PX = 52
LIST_PAGE_HEADER_BUTTON_PADDING_V_PX = 5
LIST_PAGE_HEADER_BUTTON_PADDING_H_PX = 16
LIST_PAGE_HEADER_LAYOUT_MARGINS = (16, 0, 16, 0)
LIST_PAGE_HEADER_LAYOUT_SPACING = 12

# Modal QDialog actions: same font size, weight, and padding as Dashboard Sign Out (list header buttons).
_MDL_BTN_FS = LIST_PAGE_HEADER_BUTTON_FONT_PX
_MDL_BTN_PV = LIST_PAGE_HEADER_BUTTON_PADDING_V_PX
_MDL_BTN_PH = LIST_PAGE_HEADER_BUTTON_PADDING_H_PX

MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET = (
    f"QPushButton {{ background: #0f172a; color: white; border: none; "
    f"border-radius: 6px; padding: {_MDL_BTN_PV}px {_MDL_BTN_PH}px; font-size: {_MDL_BTN_FS}px; font-weight: 500; }}"
    "QPushButton:hover { background: #1e293b; }"
    "QPushButton:pressed { background: #020617; }"
)
MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET = (
    f"QPushButton {{ background: #f1f5f9; color: #0f172a; border: 1px solid #e2e8f0; "
    f"border-radius: 6px; padding: {_MDL_BTN_PV}px {_MDL_BTN_PH}px; font-size: {_MDL_BTN_FS}px; font-weight: 500; }}"
    "QPushButton:hover { background: #e2e8f0; }"
    "QPushButton:pressed { background: #cbd5e1; }"
)

# Create / View / Edit footers — same typography as Dashboard Sign Out / modal actions.
FORM_PRIMARY_BUTTON_STYLESHEET = MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET
FORM_SECONDARY_BUTTON_STYLESHEET = MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET

# QDialogButtonBox (e.g. date picker): default = primary, other = secondary.
DIALOG_BUTTON_BOX_STYLESHEET = (
    "QDialog { background: #ffffff; } "
    f"QDialogButtonBox QPushButton {{ "
    f"border-radius: 6px; padding: {_MDL_BTN_PV}px {_MDL_BTN_PH}px; font-size: {_MDL_BTN_FS}px; font-weight: 500; }}"
    f"QDialogButtonBox QPushButton:default {{ background: #0f172a; color: white; border: none; }}"
    "QDialogButtonBox QPushButton:default:hover { background: #1e293b; }"
    "QDialogButtonBox QPushButton:default:pressed { background: #020617; }"
    f"QDialogButtonBox QPushButton:!default {{ background: #f1f5f9; color: #0f172a; border: 1px solid #e2e8f0; }}"
    "QDialogButtonBox QPushButton:!default:hover { background: #e2e8f0; }"
    "QDialogButtonBox QPushButton:!default:pressed { background: #cbd5e1; }"
)


def themed_modal_primary_button_stylesheet(
    background: str,
    hover: str,
    pressed: str,
    *,
    color: str = "white",
) -> str:
    """Primary modal button with list-header typography (Help → Check for update, etc.)."""
    b = LIST_PAGE_HEADER_BUTTON_FONT_PX
    pv = LIST_PAGE_HEADER_BUTTON_PADDING_V_PX
    ph = LIST_PAGE_HEADER_BUTTON_PADDING_H_PX
    return (
        f"QPushButton {{ background: {background}; color: {color}; border: none; "
        f"border-radius: 6px; padding: {pv}px {ph}px; font-size: {b}px; font-weight: 500; }}"
        f"QPushButton:hover {{ background: {hover}; }}"
        f"QPushButton:pressed {{ background: {pressed}; }}"
    )


def themed_list_page_header_stylesheet(
    *,
    widget_bg: str,
    label_color: str,
    button_bg: str,
    button_color: str,
    button_hover: str,
    button_pressed: str,
    title_font_px: int | None = None,
    button_font_px: int | None = None,
    button_padding_v_px: int | None = None,
    button_padding_h_px: int | None = None,
) -> str:
    """List / dashboard navy toolbar QSS (typography from module constants, colors from args).

    Optional ``*_px`` overrides shrink toolbars on specific pages (e.g. API: All in One)
    without changing global list headers.
    """
    t = LIST_PAGE_HEADER_TITLE_FONT_PX if title_font_px is None else title_font_px
    b = LIST_PAGE_HEADER_BUTTON_FONT_PX if button_font_px is None else button_font_px
    pv = (
        LIST_PAGE_HEADER_BUTTON_PADDING_V_PX
        if button_padding_v_px is None
        else button_padding_v_px
    )
    ph = (
        LIST_PAGE_HEADER_BUTTON_PADDING_H_PX
        if button_padding_h_px is None
        else button_padding_h_px
    )
    return (
        f"QWidget {{ background: {widget_bg}; }} "
        f"QLabel {{ color: {label_color}; font-size: {t}px; font-weight: 600; }} "
        f"QPushButton {{ "
        f"  background: {button_bg}; color: {button_color}; border: none; border-radius: 6px; "
        f"  padding: {pv}px {ph}px; font-size: {b}px; font-weight: 500; "
        f"}} "
        f"QPushButton:hover {{ background: {button_hover}; }} "
        f"QPushButton:pressed {{ background: {button_pressed}; }} "
    )


def list_page_header_push_button_stylesheet() -> str:
    """QPushButton only — same chrome as Refresh / Create / Filters on list headers (e.g. API: Projects)."""
    t = Theme
    b = LIST_PAGE_HEADER_BUTTON_FONT_PX
    pv = LIST_PAGE_HEADER_BUTTON_PADDING_V_PX
    ph = LIST_PAGE_HEADER_BUTTON_PADDING_H_PX
    return (
        f"QPushButton {{ "
        f"background: {t.HEADER_ACCENT}; color: {t.PANEL_TEXT_BRIGHT}; border: none; border-radius: 6px; "
        f"padding: {pv}px {ph}px; font-size: {b}px; font-weight: 500; "
        f"}} "
        f"QPushButton:hover {{ background: {t.HEADER_ACCENT_HOVER}; }} "
        f"QPushButton:pressed {{ background: {t.HEADER_ACCENT_PRESSED}; }} "
    )


_th = Theme
LIST_PAGE_HEADER_STYLESHEET = themed_list_page_header_stylesheet(
    widget_bg=_th.HEADER_NAV,
    label_color=_th.PANEL_TEXT_BRIGHT,
    button_bg=_th.HEADER_ACCENT,
    button_color=_th.PANEL_TEXT_BRIGHT,
    button_hover=_th.HEADER_ACCENT_HOVER,
    button_pressed=_th.HEADER_ACCENT_PRESSED,
)

# Create / View / Edit page top bar — same QSS, fonts, and colors as Org list strip.
FORM_PAGE_HEADER_STYLESHEET = LIST_PAGE_HEADER_STYLESHEET
