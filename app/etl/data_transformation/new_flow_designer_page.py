"""ETL: Data Transformation — DT: new Flow designer.

Implements Figma content area (node 4115:620) plus interactive canvas:
drag jobs, connect sequence arrows, reverse sequence.
Does not change the app left nav.
"""

from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QPolygonF,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

_ASSETS = Path(__file__).resolve().parents[3] / "assets" / "dt_new_flow"

_SAMPLE_PROJECTS: tuple[str, ...] = (
    "PROJ_CUSTOMER_SYNC",
    "PROJ_SALES_ANALYTICS",
    "PROJ_INVENTORY_SYNC",
    "PROJ_DATA_WAREHOUSE",
    "PROJ_MARKETING_ETL",
)

_HEADER_BG = "#0f1e36"
_HEADER_HEIGHT_PX = 56
_EXPLORER_WIDTH_PX = 252
_EXPLORER_BG = "#f8fafc"
_EXPLORER_HEADER_BG = "#eff6ff"
_EXPLORER_HEADER_BORDER = "#bfdbfe"
_EXPLORER_TITLE = "#1e40af"
_CANVAS_BG = "#fafafa"
_CONTENT_BG = "#f5f5f5"
_BTN_GHOST_BG = "rgba(255, 255, 255, 0.08)"
_BTN_BORDER = "#94a3b8"
_FOLDER_ORANGE = "#f59e0b"
_JOB_PURPLE = "#7c3aed"
_RAIL_WIDTH_PX = 44
_ICON_HEADER_PX = 13
_JOB_CARD_W = 160
_JOB_CARD_H = 60
_PORT_SIZE = 12
_EDGE_COLOR = QColor("#2563eb")
_EDGE_HIT_PX = 10


def _svg_pixmap(name: str, size: int) -> QPixmap:
    path = _ASSETS / name
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    if not path.is_file():
        return pm
    renderer = QSvgRenderer(str(path))
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    return pm


def _svg_icon(name: str, size: int = _ICON_HEADER_PX) -> QIcon:
    return QIcon(_svg_pixmap(name, size))


def _header_text_button(
    text: str,
    icon_name: str,
    *,
    accent: bool = False,
    enabled: bool = True,
) -> QPushButton:
    btn = QPushButton(text)
    btn.setIcon(_svg_icon(icon_name))
    btn.setIconSize(QSize(_ICON_HEADER_PX, _ICON_HEADER_PX))
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setEnabled(enabled)
    if accent:
        btn.setStyleSheet(
            "QPushButton {"
            " background: #16a34a; color: #ffffff; border: none; border-radius: 4px;"
            " padding: 7px 14px; font-size: 10px; font-weight: 600;"
            "}"
            "QPushButton:disabled { background: #16a34a; color: #ffffff; }"
        )
    else:
        btn.setStyleSheet(
            "QPushButton {"
            f" background: {_BTN_GHOST_BG}; color: #ffffff; border: 1px solid {_BTN_BORDER};"
            " border-radius: 4px; padding: 7px 14px; font-size: 10px; font-weight: 600;"
            "}"
            "QPushButton:hover:enabled { background: rgba(255,255,255,0.14); }"
            "QPushButton:disabled { color: #ffffff; }"
        )
    return btn


def _header_icon_button(tooltip: str, icon_name: str, *, enabled: bool = True) -> QToolButton:
    btn = QToolButton()
    btn.setIcon(_svg_icon(icon_name))
    btn.setIconSize(QSize(_ICON_HEADER_PX, _ICON_HEADER_PX))
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setEnabled(enabled)
    btn.setStyleSheet(
        "QToolButton {"
        f" background: {_BTN_GHOST_BG}; color: #ffffff; border: 1px solid {_BTN_BORDER};"
        " border-radius: 4px; padding: 7px 12px;"
        "}"
        "QToolButton:hover:enabled { background: rgba(255,255,255,0.14); }"
    )
    return btn


def _fade(widget: QWidget, opacity: float = 0.4) -> None:
    effect = QGraphicsOpacityEffect(widget)
    effect.setOpacity(opacity)
    widget.setGraphicsEffect(effect)


class _ColorBadge(QWidget):
    """16×16 rounded badge with SVG glyph."""

    def __init__(
        self,
        *,
        bg: str,
        icon_name: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.setStyleSheet(f"background: {bg}; border-radius: 3px;")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        icon = QLabel()
        icon.setPixmap(_svg_pixmap(icon_name, 10))
        icon.setFixedSize(10, 10)
        icon.setStyleSheet("background: transparent;")
        lay.addWidget(icon)


class _RailTile(QFrame):
    """Canvas toolbar tile (Figma Canvas Toolbar)."""

    def __init__(
        self,
        *,
        tooltip: str,
        circle_bg: str,
        circle_fg: str = "#2563eb",
        text: str = "",
        icon_name: str = "",
        active: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setToolTip(tooltip)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        if active:
            self.setStyleSheet(
                "QFrame { background: #dbeafe; border: none; border-radius: 10px; }"
            )
            circle_bg = "#2563eb"
            circle_fg = "#ffffff"
            label_size = 8
        else:
            self.setStyleSheet(
                "QFrame { background: #ffffff; border: none; border-radius: 10px; }"
            )
            label_size = 8 if text in ("JB", "WF", "DF") else 10
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(0)

        circle = QLabel()
        circle.setFixedSize(28, 28)
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if icon_name:
            circle.setPixmap(_svg_pixmap(icon_name, 18))
            circle.setStyleSheet(
                f"background: {circle_bg}; border-radius: 10px; padding: 5px;"
            )
        else:
            circle.setText(text)
            circle.setStyleSheet(
                f"background: {circle_bg}; color: {circle_fg}; border-radius: 10px;"
                f" font-size: {label_size}px; font-weight: 700;"
            )
        lay.addWidget(circle, 0, Qt.AlignmentFlag.AlignHCenter)


class _Port(QFrame):
    """Connection port on a job card (out = start sequence, in = receive)."""

    pressed = Signal(object, str)  # card, side: "in"|"out"

    def __init__(self, side: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.side = side
        self.setFixedSize(_PORT_SIZE, _PORT_SIZE)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip(
            "Drag to another job to set run order"
            if side == "out"
            else "Drop a connection here (previous job → this job)"
        )
        color = "#2563eb" if side == "out" else "#64748b"
        self.setStyleSheet(
            f"QFrame {{ background: #ffffff; border: 2px solid {color}; border-radius: 6px; }}"
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            card = self.parentWidget()
            while card is not None and not isinstance(card, _JobCanvasCard):
                card = card.parentWidget()
            if card is not None:
                self.pressed.emit(card, self.side)
                event.accept()
                return
        super().mousePressEvent(event)


class _JobCanvasCard(QFrame):
    """Draggable job node with in/out ports for sequencing."""

    moved = Signal()
    selected = Signal(object)

    def __init__(
        self,
        job_id: str,
        name: str,
        *,
        accent: str,
        zap_icon: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.job_id = job_id
        self.job_name = name
        self._drag_offset: QPoint | None = None
        self.setFixedSize(_JOB_CARD_W, _JOB_CARD_H)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setObjectName("jobCanvasCard")
        self.setStyleSheet(
            "QFrame#jobCanvasCard {"
            " background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px;"
            "}"
            "QFrame#jobCanvasCard[selected='true'] {"
            " border: 2px solid #2563eb;"
            "}"
        )
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setOffset(0, 6)
        shadow.setColor(QColor(0, 0, 0, 20))
        self.setGraphicsEffect(shadow)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        accent_bar = QFrame()
        accent_bar.setFixedWidth(4)
        accent_bar.setStyleSheet(
            f"background: {accent}; border: none;"
            " border-top-left-radius: 7px; border-bottom-left-radius: 7px;"
        )
        root.addWidget(accent_bar)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        bl = QHBoxLayout(body)
        bl.setContentsMargins(10, 10, 12, 10)
        bl.setSpacing(10)

        zap = QLabel()
        zap.setFixedSize(16, 16)
        zap.setPixmap(_svg_pixmap(zap_icon, 16))
        zap.setStyleSheet("background: transparent; border: none;")
        bl.addWidget(zap)

        label = QLabel(name)
        label.setWordWrap(True)
        label.setStyleSheet(
            "font-size: 10px; font-weight: 700; color: #0f172a;"
            " background: transparent; border: none;"
        )
        bl.addWidget(label, 1)
        root.addWidget(body, 1)

        self.in_port = _Port("in", self)
        self.out_port = _Port("out", self)
        self._position_ports()

    def _position_ports(self) -> None:
        cy = (self.height() - _PORT_SIZE) // 2
        self.in_port.move(-_PORT_SIZE // 2, cy)
        self.out_port.move(self.width() - _PORT_SIZE // 2, cy)
        self.in_port.raise_()
        self.out_port.raise_()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_ports()

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def port_center_canvas(self, side: str) -> QPoint:
        port = self.in_port if side == "in" else self.out_port
        local = port.geometry().center()
        return self.mapToParent(local)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.position().toPoint())
            if isinstance(child, _Port) or (
                child is not None and isinstance(child.parentWidget(), _Port)
            ):
                super().mousePressEvent(event)
                return
            self._drag_offset = event.position().toPoint()
            self.raise_()
            self.selected.emit(self)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._drag_offset is None or not (event.buttons() & Qt.MouseButton.LeftButton):
            super().mouseMoveEvent(event)
            return
        parent = self.parentWidget()
        if parent is None:
            return
        global_pos = event.globalPosition().toPoint()
        parent_pos = parent.mapFromGlobal(global_pos) - self._drag_offset
        max_x = max(0, parent.width() - self.width() - _RAIL_WIDTH_PX - 16)
        max_y = max(0, parent.height() - self.height() - 28)
        x = max(8, min(parent_pos.x(), max_x))
        y = max(8, min(parent_pos.y(), max_y))
        self.move(x, y)
        self.moved.emit()
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        self._drag_offset = None
        super().mouseReleaseEvent(event)


class _CanvasHost(QWidget):
    """Interactive canvas: drag jobs, draw sequence arrows, reverse order."""

    sequence_changed = Signal(list)  # ordered job ids

    def __init__(
        self,
        toolbar: QWidget,
        cards: list[_JobCanvasCard],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"background: {_CANVAS_BG};")
        self.setMouseTracking(True)
        self._toolbar = toolbar
        self._cards = {c.job_id: c for c in cards}
        self._card_list = cards
        # Directed edges: src_id -> dst_id (execution order)
        self._edges: list[tuple[str, str]] = []
        self._link_from: _JobCanvasCard | None = None
        self._link_side: str | None = None
        self._link_cursor: QPoint | None = None
        self._placed = False

        self._toolbar.setParent(self)
        for card in cards:
            card.setParent(self)
            card.moved.connect(self.update)
            card.selected.connect(self._on_card_selected)
            card.in_port.pressed.connect(self._on_port_pressed)
            card.out_port.pressed.connect(self._on_port_pressed)

        self._hint = QLabel(
            "Drag jobs to move  ·  Drag from a blue port to connect  ·  "
            "Double-click arrow to reverse  ·  Right-click arrow to remove",
            self,
        )
        self._hint.setStyleSheet(
            "color: #94a3b8; font-size: 10px; background: transparent; padding: 4px 8px;"
        )
        self._hint.adjustSize()

        self._reverse_btn = QPushButton("Reverse sequence", self)
        self._reverse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reverse_btn.setStyleSheet(
            "QPushButton {"
            " background: #ffffff; color: #1e40af; border: 1px solid #bfdbfe;"
            " border-radius: 4px; padding: 4px 10px; font-size: 10px; font-weight: 600;"
            "}"
            "QPushButton:hover { background: #eff6ff; }"
            "QPushButton:disabled { color: #94a3b8; border-color: #e2e8f0; }"
        )
        self._reverse_btn.clicked.connect(self.reverse_sequence)
        self._reverse_btn.setEnabled(False)

        # Default sequence matching Figma left→right visual: daily then weekly
        if len(cards) >= 2:
            self._edges = [(cards[0].job_id, cards[1].job_id)]
            self._reverse_btn.setEnabled(True)

        self._toolbar.raise_()
        self._emit_sequence()

    def cards(self) -> list[_JobCanvasCard]:
        return self._card_list

    def execution_order(self) -> list[str]:
        """Topological-ish order from edges; falls back to card list order."""
        if not self._edges:
            return [c.job_id for c in self._card_list]
        incoming = {e[1] for e in self._edges}
        starts = [c.job_id for c in self._card_list if c.job_id not in incoming]
        order: list[str] = []
        seen: set[str] = set()
        queue = starts[:]
        successors = {src: dst for src, dst in self._edges}
        while queue:
            nid = queue.pop(0)
            if nid in seen:
                continue
            seen.add(nid)
            order.append(nid)
            nxt = successors.get(nid)
            if nxt and nxt not in seen:
                queue.append(nxt)
        for c in self._card_list:
            if c.job_id not in seen:
                order.append(c.job_id)
        return order

    def reverse_sequence(self) -> None:
        if not self._edges:
            return
        self._edges = [(dst, src) for src, dst in self._edges]
        self._reverse_btn.setEnabled(True)
        self.update()
        self._emit_sequence()

    def _emit_sequence(self) -> None:
        self.sequence_changed.emit(self.execution_order())

    def _on_card_selected(self, card: _JobCanvasCard) -> None:
        for c in self._card_list:
            c.set_selected(c is card)

    def _on_port_pressed(self, card: _JobCanvasCard, side: str) -> None:
        self._link_from = card
        self._link_side = side
        self._link_cursor = card.port_center_canvas(side)
        self.grabMouse()
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._link_from is not None:
            self._link_cursor = event.position().toPoint()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._link_from is not None and event.button() == Qt.MouseButton.LeftButton:
            target = self._hit_port(event.position().toPoint())
            if target is not None:
                t_card, t_side = target
                self._try_connect(self._link_from, self._link_side or "out", t_card, t_side)
            self._link_from = None
            self._link_side = None
            self._link_cursor = None
            self.releaseMouse()
            self.unsetCursor()
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._hit_edge(event.position().toPoint()) is not None:
            self.reverse_sequence()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.RightButton:
            idx = self._hit_edge(event.position().toPoint())
            if idx is not None:
                del self._edges[idx]
                self._reverse_btn.setEnabled(bool(self._edges))
                self.update()
                self._emit_sequence()
                event.accept()
                return
        super().mousePressEvent(event)

    def _try_connect(
        self,
        a: _JobCanvasCard,
        a_side: str,
        b: _JobCanvasCard,
        b_side: str,
    ) -> None:
        if a is b:
            return
        # Normalize so connection always runs out → in
        if a_side == "out" and b_side == "in":
            src, dst = a.job_id, b.job_id
        elif a_side == "in" and b_side == "out":
            src, dst = b.job_id, a.job_id
        else:
            # Same-side drag: treat as out→in from first to second
            src, dst = a.job_id, b.job_id
        # Replace any edge involving these two (single sequence link between pair)
        self._edges = [
            e for e in self._edges if not ({e[0], e[1]} == {src, dst})
        ]
        # Also drop other edges that would fork for simple 2-job demo (keep linear)
        self._edges = [e for e in self._edges if e[0] != src and e[1] != dst]
        self._edges.append((src, dst))
        self._reverse_btn.setEnabled(True)
        self._emit_sequence()

    def _hit_port(self, pos: QPoint) -> tuple[_JobCanvasCard, str] | None:
        for card in self._card_list:
            for side, port in (("in", card.in_port), ("out", card.out_port)):
                r = QRect(port.mapTo(self, QPoint(0, 0)), port.size()).adjusted(-6, -6, 6, 6)
                if r.contains(pos):
                    return card, side
        return None

    def _edge_points(self, src_id: str, dst_id: str) -> tuple[QPoint, QPoint] | None:
        src = self._cards.get(src_id)
        dst = self._cards.get(dst_id)
        if src is None or dst is None:
            return None
        return src.port_center_canvas("out"), dst.port_center_canvas("in")

    def _hit_edge(self, pos: QPoint) -> int | None:
        for i, (src, dst) in enumerate(self._edges):
            pts = self._edge_points(src, dst)
            if pts is None:
                continue
            p1, p2 = pts
            if self._dist_to_segment(pos, p1, p2) <= _EDGE_HIT_PX:
                return i
        return None

    @staticmethod
    def _dist_to_segment(p: QPoint, a: QPoint, b: QPoint) -> float:
        ax, ay = float(a.x()), float(a.y())
        bx, by = float(b.x()), float(b.y())
        px, py = float(p.x()), float(p.y())
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        for src, dst in self._edges:
            pts = self._edge_points(src, dst)
            if pts is None:
                continue
            self._draw_arrow(painter, pts[0], pts[1])

        if self._link_from is not None and self._link_cursor is not None:
            start = self._link_from.port_center_canvas(self._link_side or "out")
            pen = QPen(QColor("#93c5fd"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawLine(start, self._link_cursor)

        painter.end()

    def _draw_arrow(self, painter: QPainter, start: QPoint, end: QPoint) -> None:
        pen = QPen(_EDGE_COLOR, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(_EDGE_COLOR)

        # Shorten line so arrowhead doesn't overlap ports
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length
        pad = 4
        s = QPoint(int(start.x() + ux * pad), int(start.y() + uy * pad))
        e = QPoint(int(end.x() - ux * (pad + 8)), int(end.y() - uy * (pad + 8)))
        painter.drawLine(s, e)

        # Arrow head
        tip = QPoint(int(end.x() - ux * pad), int(end.y() - uy * pad))
        left = QPoint(
            int(tip.x() - ux * 10 - uy * 5),
            int(tip.y() - uy * 10 + ux * 5),
        )
        right = QPoint(
            int(tip.x() - ux * 10 + uy * 5),
            int(tip.y() - uy * 10 - ux * 5),
        )
        painter.drawPolygon(QPolygonF([tip, left, right]))

        # Sequence badge mid-edge
        mid = QPoint((s.x() + e.x()) // 2, (s.y() + e.y()) // 2 - 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#eff6ff"))
        painter.drawRoundedRect(mid.x() - 18, mid.y() - 8, 36, 16, 4, 4)
        painter.setPen(QColor("#1e40af"))
        painter.drawText(QRect(mid.x() - 18, mid.y() - 8, 36, 16), Qt.AlignmentFlag.AlignCenter, "1 → 2")

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        margin = 12
        tw = self._toolbar.width()
        self._toolbar.setGeometry(
            max(0, self.width() - tw - margin),
            0,
            tw,
            self.height(),
        )
        if not self._placed:
            cy = max(40, (self.height() - _JOB_CARD_H) // 2)
            positions = (120, 320)
            for card, x in zip(self._card_list, positions):
                card.move(x, cy)
            self._placed = True
        for card in self._card_list:
            card.raise_()
        self._toolbar.raise_()
        self._hint.move(12, max(0, self.height() - 24))
        self._hint.raise_()
        self._reverse_btn.adjustSize()
        self._reverse_btn.move(
            max(12, self.width() - tw - margin - self._reverse_btn.width() - 12),
            12,
        )
        self._reverse_btn.raise_()
        self.update()


class NewFlowDesignerPage(QWidget):
    """Figma-aligned designer workspace for DT: new Flow (4115:620)."""

    sign_out_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("newFlowDesignerPage")
        self.setStyleSheet(f"#newFlowDesignerPage {{ background: {_CONTENT_BG}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_designer_header())

        workspace = QWidget()
        wl = QHBoxLayout(workspace)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(1)
        split.setStyleSheet("QSplitter::handle { background: #e2e8f0; }")

        explorer = self._build_project_explorer()
        explorer.setMinimumWidth(200)
        explorer.setMaximumWidth(360)
        split.addWidget(explorer)

        cards = [
            _JobCanvasCard(
                "job_daily",
                "JOB_DAILY_LOAD",
                accent="#2563eb",
                zap_icon="zap_blue.svg",
            ),
            _JobCanvasCard(
                "job_weekly",
                "JOB_WEEKLY_FULL",
                accent="#16a34a",
                zap_icon="zap_green.svg",
            ),
        ]
        rail = self._build_right_rail()
        self.canvas_host = _CanvasHost(rail, cards)
        self.canvas_host.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.canvas_host.sequence_changed.connect(self._on_sequence_changed)
        split.addWidget(self.canvas_host)

        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([_EXPLORER_WIDTH_PX, 900])

        wl.addWidget(split, 1)
        root.addWidget(workspace, 1)
        self._reload_projects()
        self._on_sequence_changed(self.canvas_host.execution_order())

    def _on_sequence_changed(self, order: list[str]) -> None:
        names = {
            c.job_id: c.job_name for c in self.canvas_host.cards()
        }
        label = " → ".join(names.get(i, i) for i in order)
        self._seq_label.setText(f"Run order: {label}" if order else "Run order: (none)")

    def _build_designer_header(self) -> QWidget:
        header = QFrame()
        header.setFixedHeight(_HEADER_HEIGHT_PX)
        header.setStyleSheet(f"background: {_HEADER_BG}; border: none;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(24, 0, 24, 0)
        hl.setSpacing(6)

        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.setContentsMargins(0, 0, 0, 0)
        title = QLabel("ETL: Designer")
        title.setStyleSheet("font-size: 16px; font-weight: 700; color: #ffffff;")
        title_col.addWidget(title)
        self._seq_label = QLabel("Run order: —")
        self._seq_label.setStyleSheet("font-size: 9px; color: #94a3b8;")
        title_col.addWidget(self._seq_label)
        hl.addLayout(title_col)
        hl.addStretch()

        self.execute_btn = _header_text_button("Execute", "play.svg", accent=True, enabled=False)
        self.validate_btn = _header_text_button("Validate", "check.svg", enabled=False)
        self.save_btn = _header_text_button("Save", "save.svg", enabled=False)
        self.undo_btn = _header_icon_button("Undo", "undo.svg", enabled=False)
        self.redo_btn = _header_icon_button("Redo", "redo.svg", enabled=False)
        self.sign_out_btn = _header_text_button("Sign out", "logout.svg", enabled=True)
        self.sign_out_btn.clicked.connect(self.sign_out_requested.emit)

        for muted in (
            self.execute_btn,
            self.validate_btn,
            self.save_btn,
            self.undo_btn,
            self.redo_btn,
        ):
            _fade(muted, 0.4)

        for w in (
            self.execute_btn,
            self.validate_btn,
            self.save_btn,
            self.undo_btn,
            self.redo_btn,
            self.sign_out_btn,
        ):
            hl.addWidget(w)
        return header

    def _tree_row(
        self,
        name: str,
        *,
        indent_px: int = 10,
        chevron: str = "chevron_down.svg",
        badge_bg: str = _FOLDER_ORANGE,
        badge_icon: str = "folder.svg",
        text_color: str = "#0f172a",
        font_weight: int = 600,
    ) -> QWidget:
        row = QFrame()
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet(
            "QFrame { background: transparent; border: none; border-radius: 3px; }"
            "QFrame:hover { background: #eff6ff; }"
        )
        rl = QHBoxLayout(row)
        rl.setContentsMargins(indent_px, 5, 10, 5)
        rl.setSpacing(2)

        chev = QLabel()
        chev.setFixedSize(10, 10)
        chev.setPixmap(_svg_pixmap(chevron, 10))
        chev.setStyleSheet("background: transparent;")
        rl.addWidget(chev)
        rl.addWidget(_ColorBadge(bg=badge_bg, icon_name=badge_icon))

        label = QLabel(name)
        label.setStyleSheet(
            f"font-size: 10px; font-weight: {font_weight}; color: {text_color};"
            " background: transparent; border: none;"
        )
        rl.addWidget(label, 1)
        return row

    def _build_project_explorer(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("projectExplorer")
        panel.setStyleSheet(
            f"#projectExplorer {{ background: {_EXPLORER_BG}; border-right: 1px solid #e2e8f0; }}"
        )
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QFrame()
        header.setFixedHeight(36)
        header.setStyleSheet(
            f"background: {_EXPLORER_HEADER_BG}; border-bottom: 1px solid {_EXPLORER_HEADER_BORDER};"
        )
        hh = QHBoxLayout(header)
        hh.setContentsMargins(10, 0, 12, 0)
        title = QLabel("PROJECT EXPLORER")
        title.setStyleSheet(
            f"font-size: 9px; font-weight: 700; color: {_EXPLORER_TITLE}; letter-spacing: 0.5px;"
        )
        hh.addWidget(title)
        hh.addStretch()

        self.refresh_btn = QToolButton()
        self.refresh_btn.setIcon(_svg_icon("refresh.svg", 12))
        self.refresh_btn.setIconSize(QSize(12, 12))
        self.refresh_btn.setToolTip("Refresh")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setAutoRaise(True)
        self.refresh_btn.setStyleSheet(
            "QToolButton { border: none; padding: 2px; }"
            "QToolButton:hover { background: #dbeafe; border-radius: 8px; }"
        )
        self.refresh_btn.clicked.connect(self._reload_projects)
        hh.addWidget(self.refresh_btn)
        layout.addWidget(header)

        tree_area = QWidget()
        tree_area.setMinimumHeight(40)
        tree_area.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        tree_l = QVBoxLayout(tree_area)
        tree_l.setContentsMargins(0, 4, 0, 4)
        tree_l.setSpacing(0)

        tree_l.addWidget(
            self._tree_row(
                "PROJ_CUSTOMER_SYNC",
                indent_px=10,
                chevron="chevron_down.svg",
                badge_bg=_FOLDER_ORANGE,
                badge_icon="folder.svg",
                text_color="#0f172a",
                font_weight=600,
            )
        )
        tree_l.addWidget(
            self._tree_row(
                "JOB_DAILY_LOAD",
                indent_px=26,
                chevron="chevron_down.svg",
                badge_bg=_JOB_PURPLE,
                badge_icon="zap.svg",
                text_color="#1e293b",
                font_weight=500,
            )
        )
        tree_l.addWidget(
            self._tree_row(
                "JOB_WEEKLY_FULL",
                indent_px=26,
                chevron="chevron_right.svg",
                badge_bg=_JOB_PURPLE,
                badge_icon="zap.svg",
                text_color="#475569",
                font_weight=400,
            )
        )
        tree_l.addStretch()
        layout.addWidget(tree_area, 1)

        divider = QFrame()
        divider.setFixedHeight(1)
        divider.setStyleSheet("background: #e2e8f0; border: none;")
        layout.addWidget(divider)

        projects_wrap = QWidget()
        pl = QVBoxLayout(projects_wrap)
        pl.setContentsMargins(10, 12, 10, 12)
        pl.setSpacing(8)

        projects_lbl = QLabel("PROJECTS")
        projects_lbl.setStyleSheet(
            f"font-size: 9px; font-weight: 700; color: {_EXPLORER_TITLE}; letter-spacing: 0.5px;"
        )
        pl.addWidget(projects_lbl)

        self.projects_list = QVBoxLayout()
        self.projects_list.setSpacing(0)
        self.projects_list.setContentsMargins(0, 0, 0, 0)
        pl.addLayout(self.projects_list)
        pl.addStretch()
        layout.addWidget(projects_wrap)
        return panel

    def _build_project_row(self, name: str) -> QWidget:
        row = QFrame()
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet(
            "QFrame { background: transparent; border: none; border-radius: 3px; }"
            "QFrame:hover { background: #eff6ff; }"
        )
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 5, 10, 5)
        rl.setSpacing(6)
        rl.addWidget(_ColorBadge(bg=_FOLDER_ORANGE, icon_name="folder.svg"))
        label = QLabel(name)
        label.setStyleSheet(
            "font-size: 10px; color: #0f172a; background: transparent; border: none;"
        )
        rl.addWidget(label, 1)
        return row

    def _build_right_rail(self) -> QWidget:
        rail = QFrame()
        rail.setObjectName("canvasToolbar")
        rail.setFixedWidth(_RAIL_WIDTH_PX)
        rail.setStyleSheet(
            "#canvasToolbar {"
            " background: #f8fafc; border-left: 1px solid #e2e8f0;"
            "}"
        )
        rl = QVBoxLayout(rail)
        rl.setContentsMargins(6, 10, 6, 10)
        rl.setSpacing(6)

        specs: tuple[tuple, ...] = (
            ("Job", "#dbeafe", "#2563eb", "JB", "", True, False),
            ("Work Flow", "#dbeafe", "#2563eb", "WF", "", False, True),
            ("Data Flow", "#ffedd5", "#c2410c", "DF", "", False, True),
            ("SQL / script", "#f3f4f6", "#63738c", "</>", "", False, True),
            ("Add source", "#dbeafe", "#2563eb", "", "database.svg", False, True),
            ("Add target", "#ede9fe", "#6d28d9", "", "download.svg", False, True),
            ("Conditions", "#dcfce7", "#15803d", "", "filter.svg", False, True),
        )
        for tip, bg, fg, text, icon, active, muted in specs:
            tile = _RailTile(
                tooltip=tip,
                circle_bg=bg,
                circle_fg=fg,
                text=text,
                icon_name=icon,
                active=active,
            )
            if muted:
                _fade(tile, 0.3)
            rl.addWidget(tile)
        rl.addStretch()
        return rail

    def _reload_projects(self) -> None:
        while self.projects_list.count():
            item = self.projects_list.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        for name in _SAMPLE_PROJECTS:
            self.projects_list.addWidget(self._build_project_row(name))

    def go_to_nav_item(self, _nav_item: str) -> None:
        return
