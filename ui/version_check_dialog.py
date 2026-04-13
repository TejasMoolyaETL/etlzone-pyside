"""Polished dialogs for Help → Check for update."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.user_management.user_timepass.user_role_ui_helpers import _add_view_user_form_row
from app.user_management.users.user_view import READONLY_INPUT_STYLE
from ui.form_page_styles import (
    APP_FONT_SIZE_PX,
    MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET,
    MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET,
    MODAL_FIELD_HEIGHT_PX,
    themed_modal_primary_button_stylesheet,
)
from ui.theme import Theme

_fs = APP_FONT_SIZE_PX

_VERSION_DLG_PRIMARY_STYLESHEET = themed_modal_primary_button_stylesheet(
    Theme.BTN_PRIMARY_BG,
    Theme.BTN_PRIMARY_HOVER,
    Theme.BTN_PRIMARY_PRESSED,
)


def _header_bar(title: str) -> QFrame:
    bar = QFrame()
    bar.setFixedHeight(48)
    bar.setStyleSheet(
        f"QFrame {{ background-color: {Theme.HEADER_NAV}; border: none; "
        f"border-top-left-radius: 8px; border-top-right-radius: 8px; }}"
    )
    hl = QHBoxLayout(bar)
    hl.setContentsMargins(16, 0, 16, 0)
    lbl = QLabel(title)
    lbl.setStyleSheet(
        f"color: #ffffff; font-size: {_fs}px; font-weight: 600; border: none; background: transparent;"
    )
    hl.addWidget(lbl)
    hl.addStretch()
    return bar


def _primary_btn(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(_VERSION_DLG_PRIMARY_STYLESHEET)
    return b


def _secondary_btn(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
    return b


def _body_label(text: str, *, large: bool = False, muted: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    if large:
        lbl.setStyleSheet(
            f"color: {Theme.TEXT_PRIMARY}; font-size: {_fs}px; font-weight: 600; line-height: 1.4;"
        )
    elif muted:
        lbl.setStyleSheet(
            f"color: {Theme.TEXT_SECONDARY}; font-size: {_fs}px; font-weight: 400; line-height: 1.45;"
        )
    else:
        lbl.setStyleSheet(
            f"color: {Theme.TEXT_PRIMARY}; font-size: {_fs}px; font-weight: 400; line-height: 1.45;"
        )
    return lbl


def _version_row(label: str, value: str) -> QWidget:
    row = QWidget()
    rl = QHBoxLayout(row)
    rl.setContentsMargins(0, 0, 0, 0)
    rl.setSpacing(12)
    l = QLabel(label)
    l.setStyleSheet(
        f"color: {Theme.TEXT_SECONDARY}; font-size: {_fs}px; font-weight: 500; min-width: 108px;"
    )
    v = QLabel(value)
    v.setStyleSheet(f"color: {Theme.TEXT_PRIMARY}; font-size: {_fs}px; font-weight: 600;")
    v.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    rl.addWidget(l, 0)
    rl.addWidget(v, 1)
    return row


def show_version_check_needs_sign_in(parent: QWidget | None) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle("Check for updates")
    dlg.setModal(True)
    dlg.setMinimumWidth(400)
    dlg.setStyleSheet(f"QDialog {{ background: {Theme.BG_WHITE}; border-radius: 8px; }}")

    outer = QVBoxLayout(dlg)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(_header_bar("Check for updates"))

    body = QWidget()
    bl = QVBoxLayout(body)
    bl.setContentsMargins(20, 20, 20, 16)
    bl.setSpacing(12)
    bl.addWidget(_body_label("Sign in required", large=True))
    bl.addWidget(
        _body_label(
            "You need to be signed in to check whether a newer build is available.",
            muted=True,
        )
    )
    outer.addWidget(body)

    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background-color: {Theme.BORDER_DEFAULT}; max-height: 1px; border: none;")
    outer.addWidget(sep)

    btn_row = QWidget()
    br = QHBoxLayout(btn_row)
    br.setContentsMargins(20, 12, 20, 16)
    br.addStretch()
    ok = _primary_btn("OK")
    ok.clicked.connect(dlg.accept)
    br.addWidget(ok)
    outer.addWidget(btn_row)

    dlg.exec()


def show_version_check_error(parent: QWidget | None, message: str) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle("Check for updates")
    dlg.setModal(True)
    dlg.setMinimumWidth(400)
    dlg.setStyleSheet(f"QDialog {{ background: {Theme.BG_WHITE}; border-radius: 8px; }}")

    outer = QVBoxLayout(dlg)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(_header_bar("Could not check"))

    body = QWidget()
    bl = QVBoxLayout(body)
    bl.setContentsMargins(20, 20, 20, 16)
    bl.setSpacing(12)
    bl.addWidget(_body_label("Something went wrong", large=True))
    bl.addWidget(_body_label(message or "Please try again later.", muted=False))
    outer.addWidget(body)

    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background-color: {Theme.BORDER_DEFAULT}; max-height: 1px; border: none;")
    outer.addWidget(sep)

    btn_row = QWidget()
    br = QHBoxLayout(btn_row)
    br.setContentsMargins(20, 12, 20, 16)
    br.addStretch()
    ok = _primary_btn("OK")
    ok.clicked.connect(dlg.accept)
    br.addWidget(ok)
    outer.addWidget(btn_row)

    dlg.exec()


def show_version_check_up_to_date(parent: QWidget | None, message: str, *, current_version: str) -> None:
    dlg = QDialog(parent)
    dlg.setWindowTitle("Up to date")
    dlg.setModal(True)
    dlg.setMinimumWidth(400)
    dlg.setStyleSheet(f"QDialog {{ background: {Theme.BG_WHITE}; border-radius: 8px; }}")

    outer = QVBoxLayout(dlg)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)
    outer.addWidget(_header_bar("You're up to date"))

    body = QWidget()
    bl = QVBoxLayout(body)
    bl.setContentsMargins(20, 20, 20, 16)
    bl.setSpacing(14)
    bl.addWidget(_body_label(message or "You are up to date.", large=True))
    bl.addWidget(_version_row("Your version", f"v{current_version}"))
    bl.addWidget(
        _body_label(
            "No download is needed. Check again anytime from Help → Check for update.",
            muted=True,
        )
    )
    outer.addWidget(body)

    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background-color: {Theme.BORDER_DEFAULT}; max-height: 1px; border: none;")
    outer.addWidget(sep)

    btn_row = QWidget()
    br = QHBoxLayout(btn_row)
    br.setContentsMargins(20, 12, 20, 16)
    br.addStretch()
    ok = _primary_btn("OK")
    ok.clicked.connect(dlg.accept)
    br.addWidget(ok)
    outer.addWidget(btn_row)

    dlg.exec()


def show_version_check_update_available(
    parent: QWidget | None,
    *,
    current_version: str,
    latest_version: str,
    note: str,
) -> bool:
    """Show update dialog (Create API–style chrome). Returns True if user opens download."""
    dlg = QDialog(parent)
    dlg.setWindowTitle("Update available")
    dlg.setModal(True)
    dlg.setMinimumWidth(400)
    dlg.setMaximumWidth(480)
    dlg.setStyleSheet("QDialog { background: #ffffff; }")

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(6)

    form = QFormLayout()
    form.setContentsMargins(0, 0, 0, 0)
    form.setHorizontalSpacing(8)
    form.setVerticalSpacing(5)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    fh = MODAL_FIELD_HEIGHT_PX
    cur_edit = QLineEdit(f"v{current_version}")
    cur_edit.setReadOnly(True)
    cur_edit.setFixedHeight(fh)
    cur_edit.setMinimumWidth(220)
    cur_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    cur_edit.setStyleSheet(READONLY_INPUT_STYLE)
    _add_view_user_form_row(form, "Your version:", cur_edit)

    latest_disp = (latest_version or "").strip()
    if latest_disp and not latest_disp.startswith("v"):
        latest_disp = f"v{latest_disp}"
    if not latest_disp:
        latest_disp = "—"
    latest_edit = QLineEdit(latest_disp)
    latest_edit.setReadOnly(True)
    latest_edit.setFixedHeight(fh)
    latest_edit.setMinimumWidth(220)
    latest_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    latest_edit.setStyleSheet(READONLY_INPUT_STYLE)
    _add_view_user_form_row(form, "Latest version:", latest_edit)

    layout.addLayout(form)

    note_lbl = QLabel(note)
    note_lbl.setWordWrap(True)
    note_lbl.setStyleSheet(
        f"color: {Theme.TEXT_SECONDARY}; font-size: {_fs}px; font-weight: 400; line-height: 1.45;"
    )
    note_lbl.setTextInteractionFlags(
        Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.TextSelectableByKeyboard
    )
    layout.addWidget(note_lbl)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setFrameShadow(QFrame.Shadow.Plain)
    sep.setFixedHeight(1)
    sep.setStyleSheet("background-color: #cbd5e1; border: none; max-height: 1px;")
    layout.addWidget(sep)

    open_btn = QPushButton("Open download")
    open_btn.setMinimumWidth(108)
    open_btn.setDefault(True)
    open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    open_btn.setStyleSheet(MODAL_DIALOG_PRIMARY_BUTTON_STYLESHEET)
    open_btn.clicked.connect(dlg.accept)

    not_now_btn = QPushButton("Not now")
    not_now_btn.setMinimumWidth(88)
    not_now_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    not_now_btn.setStyleSheet(MODAL_DIALOG_SECONDARY_BUTTON_STYLESHEET)
    not_now_btn.clicked.connect(dlg.reject)

    btn_row = QWidget()
    btn_row.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
    br = QHBoxLayout(btn_row)
    br.setContentsMargins(0, 0, 0, 0)
    br.setSpacing(8)
    br.setAlignment(Qt.AlignmentFlag.AlignLeft)
    br.addWidget(open_btn)
    br.addWidget(not_now_btn)
    br.addStretch(1)
    layout.addWidget(btn_row)

    result = dlg.exec() == int(QDialog.DialogCode.Accepted)
    return result


def show_version_check_unexpected(parent: QWidget | None) -> None:
    show_version_check_error(parent, "The server returned an unexpected response. Please try again later.")
