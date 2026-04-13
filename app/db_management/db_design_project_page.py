"""DB Design Project page - draggable tables on a canvas."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QPointF, Qt, QRectF, QSizeF, Signal
from PySide6.QtCore import QTimer
from PySide6.QtGui import QBrush, QColor, QDrag, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QCheckBox,
    QFrame,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsProxyWidget,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ui.auto_hide_message import show_auto_hiding_message
from ui.data_table import DATA_TABLE_HORIZONTAL_HEADER_HEIGHT_PX
from ui.form_page_styles import (
    LIST_PAGE_HEADER_HEIGHT_PX,
    LIST_PAGE_HEADER_LAYOUT_MARGINS,
    LIST_PAGE_HEADER_LAYOUT_SPACING,
    LIST_PAGE_HEADER_STYLESHEET,
    LIST_PAGE_HEADER_TITLE_FONT_PX,
    placeholder_enter,
)
from ui.styles import CONTEXT_MENU_STYLESHEET
from ui.theme import Theme

FIELD_HEADERS = ("Column Name", "Display Label", "Data Type", "Nullable", "Primary Key", "Default Value")
DATA_TYPES = ("VARCHAR", "INT", "BIGINT", "DECIMAL", "DATE", "DATETIME", "BOOLEAN", "TEXT", "FLOAT", "BLOB")
COL_NAME, COL_LABEL, COL_TYPE, COL_NULLABLE, COL_PK, COL_DEFAULT = range(6)

DEFAULT_TABLES: list[tuple[str, list[tuple[str, str, str, bool, bool, str]]]] = [
    (
        "product",
        [
            ("id", "ID", "INT", False, True, ""),
            ("name", "Name", "VARCHAR", False, False, ""),
            ("description", "Description", "TEXT", True, False, ""),
            ("price", "Price", "DECIMAL", False, False, ""),
            ("created_at", "Created At", "DATETIME", True, False, ""),
        ],
    ),
    (
        "order",
        [
            ("id", "ID", "INT", False, True, ""),
            ("product_id", "Product ID", "INT", False, False, ""),
            ("order_date", "Order Date", "DATE", False, False, ""),
            ("customer_id", "Customer ID", "INT", False, False, ""),
            ("total_amount", "Total Amount", "DECIMAL", False, False, ""),
            ("status", "Status", "VARCHAR", False, False, ""),
        ],
    ),
]

LINK_PARENT_BG = QColor("#dbeafe")  # light blue
LINK_CHILD_BG = QColor("#e2e8f0")  # light grey
REL_MIME = "application/x-etl-link"


class _RelationshipArrow(QGraphicsPathItem):
    """Draws a line from child row to parent row with an arrowhead pointing to parent."""

    def __init__(
        self,
        child_proxy: QGraphicsProxyWidget,
        child_row: int,
        parent_proxy: QGraphicsProxyWidget,
        parent_row: int,
        get_pos_fn,
        parent_item=None,
    ) -> None:
        super().__init__(parent_item)
        self._child_proxy = child_proxy
        self._child_row = child_row
        self._parent_proxy = parent_proxy
        self._parent_row = parent_row
        self._get_pos = get_pos_fn
        self.setPen(QPen(QColor("#2563eb"), 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        self.setBrush(QBrush(QColor("#3b82f6")))
        self.setZValue(10)
        self.update_geometry()

    def update_geometry(self) -> None:
        p1 = self._get_pos(self._child_proxy, self._child_row, "right")
        p2 = self._get_pos(self._parent_proxy, self._parent_row, "left")
        path = QPainterPath()
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        length = (dx * dx + dy * dy) ** 0.5
        arrow_size = 14
        if length > arrow_size:
            tip_offset = dx / length * arrow_size, dy / length * arrow_size
            line_end = p2.x() - tip_offset[0], p2.y() - tip_offset[1]
            path.moveTo(p1)
            path.lineTo(line_end[0], line_end[1])
            ux, uy = dx / length, dy / length
            perp_x, perp_y = -uy * arrow_size * 0.6, ux * arrow_size * 0.6
            arrow = QPainterPath()
            arrow.moveTo(p2)
            arrow.lineTo(line_end[0] + perp_x, line_end[1] + perp_y)
            arrow.lineTo(line_end[0] - perp_x, line_end[1] - perp_y)
            arrow.closeSubpath()
            path.addPath(arrow)
        else:
            path.moveTo(p1)
            path.lineTo(p2)
        self.setPath(path)
        self.update()


class _DataTypeButton(QPushButton):
    """Button that opens a menu for data type selection - works in QGraphicsProxyWidget."""

    value_changed = Signal(str)

    def __init__(self, value: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(70)
        self.setAutoFillBackground(True)
        self.setStyleSheet(
            "QPushButton { "
            "  text-align: left; padding: 2px 6px; font-size: 10px; "
            "  background: white; border: 1px solid #e2e8f0; border-radius: 4px; "
            "  color: #334155; "
            "} "
            "QPushButton:hover { border-color: #3b82f6; background: #f8fafc; } "
        )
        self._value = value or (DATA_TYPES[0] if DATA_TYPES else "")
        self.setText(self._value)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._show_menu)

    def _show_menu(self) -> None:
        menu = QMenu(self)
        menu.setWindowFlags(menu.windowFlags() | Qt.WindowType.NoDropShadowWindowHint)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        for dt in DATA_TYPES:
            action = menu.addAction(dt)
            action.triggered.connect(lambda checked, v=dt: self._set_value(v))
        menu.exec(self.mapToGlobal(QPoint(0, self.height())))

    def _set_value(self, value: str) -> None:
        self._value = value
        self.setText(value)
        self.value_changed.emit(value)

    def value(self) -> str:
        return self._value

    def setValue(self, value: str) -> None:
        self._value = value or (DATA_TYPES[0] if DATA_TYPES else "")
        self.setText(self._value)


def _make_data_type_cell(value: str = "", table: QTableWidget | None = None, row: int = -1, col: int = -1) -> _DataTypeButton:
    btn = _DataTypeButton(value)
    if table is not None and row >= 0 and col >= 0:
        def _sync_item(v, r=row, c=col):
            item = table.item(r, c)
            if item:
                item.setData(Qt.ItemDataRole.UserRole, v)
        btn.value_changed.connect(_sync_item)
    return btn


class _CheckBoxCell(QWidget):
    """Checkbox-like widget that draws a visible tick when checked."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._checked = checked

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool) -> None:
        if self._checked != checked:
            self._checked = checked
            self.update()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setChecked(not self._checked)
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        if self._checked:
            p.setBrush(QBrush(QColor("#3b82f6")))
            p.setPen(QPen(QColor("#3b82f6")))
        else:
            p.setBrush(QBrush(QColor("white")))
            p.setPen(QPen(QColor("#cbd5e1")))
        p.drawRoundedRect(r, 3, 3)
        if self._checked:
            p.setPen(QPen(QColor("white"), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.drawLine(3, 7, 6, 10)
            p.drawLine(6, 10, 11, 3)
        p.end()


class _CheckBoxCellContainer(QWidget):
    """Container that centers the checkbox in the cell."""

    def __init__(self, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._checkbox = _CheckBoxCell(checked=checked)
        layout.addWidget(self._checkbox)

    def isChecked(self) -> bool:
        return self._checkbox.isChecked()

    def setChecked(self, checked: bool) -> None:
        self._checkbox.setChecked(checked)


def _make_checkbox_cell(checked: bool = False) -> _CheckBoxCellContainer:
    return _CheckBoxCellContainer(checked=checked)


class _LinkableTableWidget(QTableWidget):
    """Table that supports Column Name drag and accepts link drops."""

    def __init__(self, page: DbDesignProjectPage, parent=None) -> None:
        super().__init__(parent)
        self._page = page

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasFormat(REL_MIME):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasFormat(REL_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasFormat(REL_MIME):
            return
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        index = self.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        container = self.parent().parent() if self.parent() else None
        if not isinstance(container, _DraggableTableWidget) or not container._proxy:
            return
        src = getattr(self._page, "_link_drag_source", None)
        if src and (src[0] is not container._proxy or src[1] != row):
            self._page.create_link_to(container._proxy, row)
        event.acceptProposedAction()


class _DraggableTableWidget(QWidget):
    """Table with name, drag handle, and context menu."""

    def __init__(self, table: QTableWidget, page: DbDesignProjectPage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._table = table
        self._page = page
        self._proxy: QGraphicsProxyWidget | None = None
        self._drag_pos: QPoint | None = None
        self.setStyleSheet(
            "QWidget { background: white; border: 1px solid #e2e8f0; border-radius: 8px; } "
        )
        self.setAutoFillBackground(True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header_bar = QWidget()
        header_bar.setObjectName("dbDesignTableHeaderStrip")
        _th = Theme
        header_bar.setStyleSheet(
            LIST_PAGE_HEADER_STYLESHEET
            + (
                f"QWidget#dbDesignTableHeaderStrip {{ border-radius: 8px 8px 0 0; }}"
                f"QLineEdit {{ background: transparent; color: {_th.PANEL_TEXT_BRIGHT}; border: none; "
                f"padding: 6px 8px; font-size: {LIST_PAGE_HEADER_TITLE_FONT_PX}px; font-weight: 600; }}"
                f"QLineEdit::placeholder {{ color: {_th.PANEL_TEXT}; }}"
            )
        )
        header_bar.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        header_bar_layout = QHBoxLayout(header_bar)
        header_bar_layout.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        header_bar_layout.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        self._handle = QFrame()
        self._handle.setObjectName("dragHandle")
        self._handle.setFixedSize(22, 22)
        self._handle.setStyleSheet(
            "QFrame#dragHandle { "
            "  background: rgba(255,255,255,0.15); border: none; border-radius: 6px; "
            "} "
            "QFrame#dragHandle:hover { background: rgba(255,255,255,0.25); } "
            "QLabel { color: white; font-size: 14px; } "
        )
        handle_layout = QHBoxLayout(self._handle)
        handle_layout.setContentsMargins(0, 0, 0, 0)
        handle_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grip = QLabel("⋮⋮")
        grip.setStyleSheet("color: rgba(255,255,255,0.9); font-size: 10px; font-weight: bold;")
        handle_layout.addWidget(grip)
        self._handle.setCursor(Qt.CursorShape.SizeAllCursor)
        self._handle.setToolTip("Drag to move")
        self._handle.installEventFilter(self)
        header_bar_layout.addWidget(self._handle)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText(placeholder_enter("table name"))
        self._name_edit.setMinimumWidth(80)
        header_bar_layout.addWidget(self._name_edit, 1)
        layout.addWidget(header_bar)

        self._cols_expanded = False
        self._toggle_btn = QPushButton("▶")
        self._toggle_btn.setFixedSize(20, 20)
        self._toggle_btn.setStyleSheet(
            "QPushButton { "
            "  background: #f1f5f9; color: #475569; border: none; border-radius: 6px; "
            "  font-size: 8px; font-weight: 600; "
            "} "
            "QPushButton:hover { background: #e2e8f0; color: #1e293b; } "
        )
        self._toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._toggle_btn.setToolTip("Hide/show columns")
        self._toggle_btn.clicked.connect(self._toggle_columns)

        table.horizontalHeader().setMinimumSectionSize(80)

        self._table_wrapper = QWidget()
        self._table_wrapper.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        wrapper_layout = QVBoxLayout(self._table_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(table)
        self._corner_widget = QWidget(self._table_wrapper)
        self._corner_widget.setStyleSheet("background: #f8fafc;")
        self._corner_widget.setAutoFillBackground(True)
        corner_layout = QHBoxLayout(self._corner_widget)
        corner_layout.setContentsMargins(2, 2, 2, 2)
        corner_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        corner_layout.addWidget(self._toggle_btn)
        self._corner_widget.raise_()
        layout.addWidget(self._table_wrapper, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        table.customContextMenuRequested.connect(self._show_table_context_menu)
        table.horizontalHeader().sectionResized.connect(lambda: QTimer.singleShot(0, self._apply_table_size))
        table.verticalHeader().sectionResized.connect(lambda: QTimer.singleShot(0, self._apply_table_size))
        table.setAcceptDrops(True)
        table.setDragEnabled(False)
        table.viewport().installEventFilter(self)
        table.installEventFilter(self)
        self._link_drag_start: tuple[int, QPoint] | None = None
        for col in range(1, table.columnCount()):
            table.setColumnHidden(col, True)

    def get_table(self) -> QTableWidget:
        return self._table

    def get_table_name(self) -> str:
        return self._name_edit.text().strip()

    def show_table_context_menu_at(self, global_pos: QPoint) -> None:
        viewport_pos = self._table.viewport().mapFromGlobal(global_pos)
        self._show_table_context_menu(viewport_pos)

    def set_proxy(self, proxy: QGraphicsProxyWidget) -> None:
        self._proxy = proxy

    def _toggle_columns(self) -> None:
        self._cols_expanded = not self._cols_expanded
        for col in range(1, self._table.columnCount()):
            self._table.setColumnHidden(col, not self._cols_expanded)
        self._toggle_btn.setText("▼" if self._cols_expanded else "▶")
        if self._cols_expanded:
            self._table.resizeColumnsToContents()
        self._table.resizeRowsToContents()
        QTimer.singleShot(0, self._apply_table_size)

    def _apply_table_size(self) -> None:
        visible_width = 0
        for c in range(self._table.columnCount()):
            if not self._table.isColumnHidden(c):
                w = self._table.columnWidth(c)
                if w <= 0 and c == COL_NAME:
                    w = 80
                visible_width += w
        vh = self._table.verticalHeader()
        vh_width = vh.width() if vh.isVisible() else 0
        hh = self._table.horizontalHeader()
        total_width = max(100, visible_width + vh_width + 2)
        row_heights = [max(self._table.rowHeight(r), 20) for r in range(self._table.rowCount())]
        total_height = (hh.height() if hh.isVisible() else 0) + sum(row_heights) + 2
        self._table.setFixedWidth(total_width)
        self._table.setFixedHeight(total_height)
        self._table_wrapper.setFixedWidth(total_width)
        self._table_wrapper.setFixedHeight(total_height)
        if not self._cols_expanded:
            self.setFixedWidth(max(total_width, 130))
        else:
            self.setMaximumWidth(16777215)
            self.setMinimumWidth(0)
        self._table_wrapper.adjustSize()
        self.adjustSize()
        self._table.updateGeometry()
        self._table_wrapper.updateGeometry()
        self.updateGeometry()
        vh = self._table.verticalHeader()
        hh = self._table.horizontalHeader()
        cw = max(24, vh.width() if vh.isVisible() else 0)
        ch = max(24, hh.height() if hh.isVisible() else 0)
        self._corner_widget.setGeometry(0, 0, cw, ch)
        self._corner_widget.raise_()
        if self._page:
            self._page.update_relationship_lines()

    def _show_table_context_menu(self, pos: QPoint) -> None:
        index = self._table.indexAt(pos)
        row = index.row() if index.isValid() else -1
        col = index.column() if index.isValid() else -1

        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        if row >= 0 and col >= 0 and self._page.is_row_linked(self._proxy, row):
            menu.addAction("Remove link", lambda: self._page.remove_link_from_row(self._proxy, row))
            menu.addSeparator()
        if row >= 0:
            menu.addAction("Add row above", lambda r=row: self._add_row_above(r))
            menu.addAction("Add row below", lambda r=row: self._add_row_below(r))
            remove_row_action = menu.addAction("Remove row", lambda r=row: self._remove_row_at(r))
            remove_row_action.setEnabled(self._table.rowCount() > 1)
            menu.addSeparator()
        sort_menu = menu.addMenu("Sort by column")
        for col in range(self._table.columnCount()):
            h = self._table.horizontalHeaderItem(col)
            label = h.text() if h else f"Column {col}"
            sort_menu.addAction(label, lambda c=col: self._sort_by_column(c))
        menu.addSeparator()
        menu.addAction("Duplicate table", self._duplicate_table)
        menu.addAction("Delete table", self._delete_table)
        global_pos = self._table.viewport().mapToGlobal(pos)
        menu.exec(global_pos)

    def _add_row_above(self, row: int) -> None:
        self._page.add_row_to_table_at(self._proxy, row)

    def _add_row_below(self, row: int) -> None:
        self._page.add_row_to_table_at(self._proxy, row + 1)

    def _remove_row_at(self, row: int) -> None:
        if 0 <= row < self._table.rowCount():
            self._page.remove_row_from_table(self._proxy, row)
            self._table.removeRow(row)
            QTimer.singleShot(0, self._apply_table_size)

    def _add_column(self) -> None:
        col = self._table.columnCount()
        self._table.insertColumn(col)
        self._table.setHorizontalHeaderItem(col, QTableWidgetItem(f"Column {col + 1}"))
        for row in range(self._table.rowCount()):
            self._table.setItem(row, col, QTableWidgetItem(""))
        self._table.resizeColumnsToContents()

    def _remove_column(self) -> None:
        if self._table.columnCount() <= 1:
            return
        col = self._table.currentColumn()
        if col >= 0:
            self._table.removeColumn(col)
        else:
            self._table.removeColumn(self._table.columnCount() - 1)

    def _sort_by_column(self, col: int) -> None:
        self._table.sortItems(col, Qt.SortOrder.AscendingOrder)

    def _duplicate_table(self) -> None:
        self._page.duplicate_table(self._proxy)

    def _delete_table(self) -> None:
        name = self.get_table_name().strip()
        table = self.get_table()
        has_data = bool(name)
        for row in range(table.rowCount()):
            col_item = table.item(row, COL_NAME)
            if col_item and col_item.text().strip():
                has_data = True
                break
        if not has_data:
            self._page.delete_table(self._proxy)
        else:
            msg = QMessageBox(self._page)
            msg.setWindowTitle("Confirm Delete")
            msg.setText(f"Delete table '{name or 'Untitled'}'?")
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg.setDefaultButton(QMessageBox.StandardButton.No)
            msg.setMinimumSize(380, 140)
            msg.setStyleSheet(
                "QMessageBox { font-size: 14px; min-width: 360px; } "
                "QMessageBox QLabel { font-size: 14px; min-height: 40px; } "
                "QPushButton { min-width: 90px; min-height: 36px; font-size: 13px; } "
            )
            if msg.exec() == QMessageBox.StandardButton.Yes:
                self._page.delete_table(self._proxy)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._table.viewport():
            if event.type() == event.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                index = self._table.indexAt(pos)
                if index.isValid() and index.column() == COL_NAME:
                    self._link_drag_start = (index.row(), pos)
                    self._table.viewport().grabMouse()
                else:
                    self._link_drag_start = None
            elif event.type() == event.Type.MouseMove:
                if self._link_drag_start is not None and self._proxy and event.buttons() & Qt.MouseButton.LeftButton:
                    pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                    delta = pos - self._link_drag_start[1]
                    if delta.manhattanLength() > 10:
                        row = self._link_drag_start[0]
                        mime = QMimeData()
                        mime.setData(REL_MIME, QByteArray(b"1"))
                        drag = QDrag(self._table)
                        drag.setMimeData(mime)
                        idx = self._table.model().index(row, COL_NAME)
                        rect = self._table.visualRect(idx)
                        if rect.isValid() and rect.width() > 4 and rect.height() > 4:
                            pm = self._table.viewport().grab(rect)
                            if not pm.isNull():
                                drag.setPixmap(pm)
                                drag.setHotSpot(QPoint(rect.width() // 2, rect.height() // 2))
                        self._page._link_drag_source = (self._proxy, row)
                        drag.exec(Qt.DropAction.CopyAction)
                        self._link_drag_start = None
                        if hasattr(self._page, "_link_drag_source"):
                            delattr(self._page, "_link_drag_source")
                        self._table.viewport().releaseMouse()
                        return True
                elif not (event.buttons() & Qt.MouseButton.LeftButton):
                    self._link_drag_start = None
            elif event.type() == event.Type.MouseButtonRelease:
                self._table.viewport().releaseMouse()
                self._link_drag_start = None
        if obj is self._handle:
            if event.type() == event.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                self._drag_pos = event.globalPosition().toPoint()
                self._handle.grabMouse()
                return True
            if event.type() == event.Type.MouseMove and self._drag_pos is not None and self._proxy:
                delta = event.globalPosition().toPoint() - self._drag_pos
                self._drag_pos = event.globalPosition().toPoint()
                new_pos = self._proxy.pos() + QPointF(delta.x(), delta.y())
                clamped_pos = self._page.get_drag_position(self._proxy, new_pos)
                self._proxy.setPos(clamped_pos)
                self._page.update_relationship_lines()
                return True
            if event.type() == event.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
                if self._proxy:
                    self._page.snap_table_aside_if_overlapping(self._proxy)
                    self._page.update_relationship_lines()
                self._drag_pos = None
                self._handle.releaseMouse()
                return True
        return super().eventFilter(obj, event)


class DbDesignProjectPage(QWidget):
    """DB Design Project page with draggable tables on a canvas."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._table_proxies: list[QGraphicsProxyWidget] = []
        self._relationship_lines: list[_RelationshipArrow] = []
        self._add_offset = QPointF(30, 30)
        self._build_ui()
        QTimer.singleShot(0, self._add_default_tables)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QWidget()
        toolbar.setStyleSheet(LIST_PAGE_HEADER_STYLESHEET)
        toolbar.setFixedHeight(LIST_PAGE_HEADER_HEIGHT_PX)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(*LIST_PAGE_HEADER_LAYOUT_MARGINS)
        toolbar_layout.setSpacing(LIST_PAGE_HEADER_LAYOUT_SPACING)
        add_table_btn = QPushButton("+ Add Table")
        add_table_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_table_btn.clicked.connect(self._add_table)
        toolbar_layout.addWidget(add_table_btn)
        validate_btn = QPushButton("Validate")
        validate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        validate_btn.clicked.connect(self._validate_and_show)
        toolbar_layout.addWidget(validate_btn)
        toolbar_layout.addStretch()
        layout.addWidget(toolbar)

        self._message_label = QLabel()
        self._message_label.setWordWrap(True)
        self._message_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self._message_label.setVisible(False)
        self._message_label.setStyleSheet("padding: 8px 16px; font-size: 13px;")
        layout.addWidget(self._message_label)

        self._scene = QGraphicsScene()
        self._scene.setBackgroundBrush(QBrush(QColor("#f1f5f9")))
        self._view = QGraphicsView(self._scene)
        self._view.setStyleSheet(
            "QGraphicsView { background: #f1f5f9; border: none; }"
        )
        self._view.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self._view.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._show_context_menu)
        self._view.setFrameShape(QFrame.Shape.NoFrame)
        layout.addWidget(self._view, 1)

    def _add_default_tables(self) -> None:
        pos = QPointF(30, 30)
        for name, fields in DEFAULT_TABLES:
            proxy = self._add_table_at_position(pos, initial_data=(name, fields))
            if proxy:
                pos = proxy.pos() + QPointF(proxy.boundingRect().width() + 40, 0)

    def get_drag_position(self, proxy: QGraphicsProxyWidget, new_pos: QPointF) -> QPointF:
        br = proxy.boundingRect()
        w, h = br.width(), br.height()
        top_left = self._view.mapToScene(0, 0)
        bottom_right = self._view.mapToScene(
            self._view.viewport().width(),
            self._view.viewport().height(),
        )
        visible = QRectF(top_left, bottom_right).normalized()
        clamped_x = max(visible.left(), min(visible.right() - w, new_pos.x()))
        clamped_y = max(visible.top(), min(visible.bottom() - h, new_pos.y()))
        return QPointF(clamped_x, clamped_y)

    def get_row_scene_pos(self, proxy: QGraphicsProxyWidget, row: int, side: str = "center") -> QPointF:
        """Return scene position of the given row. side: 'left', 'right', or 'center'."""
        widget = proxy.widget()
        if not isinstance(widget, _DraggableTableWidget):
            return proxy.scenePos()
        table = widget.get_table()
        if row < 0 or row >= table.rowCount():
            return proxy.scenePos()
        hh = table.horizontalHeader()
        vh = table.verticalHeader()
        y = hh.height() + vh.sectionPosition(row) + vh.sectionSize(row) / 2
        if side == "left":
            x = 0
        elif side == "right":
            x = table.width()
        else:
            x = table.width() / 2
        pt = table.mapTo(widget, QPoint(int(x), int(y)))
        return proxy.mapToScene(QPointF(pt))

    def update_relationship_lines(self) -> None:
        for line in self._relationship_lines:
            line.update_geometry()
        if self._relationship_lines:
            self._scene.update()

    def is_row_linked(self, proxy: QGraphicsProxyWidget, row: int) -> bool:
        for ln in self._relationship_lines:
            if (ln._child_proxy is proxy and ln._child_row == row) or (ln._parent_proxy is proxy and ln._parent_row == row):
                return True
        return False

    def create_link_to(self, proxy: QGraphicsProxyWidget, row: int) -> bool:
        child_source = getattr(self, "_link_drag_source", None)
        if child_source is None:
            return False
        child_proxy, child_row = child_source
        if child_proxy is proxy and child_row == row:
            return False
        self.remove_link_from_row(child_proxy, child_row)
        self.remove_link_from_row(proxy, row)
        line = _RelationshipArrow(child_proxy, child_row, proxy, row, self.get_row_scene_pos)
        self._scene.addItem(line)
        self._relationship_lines.append(line)
        if hasattr(self, "_link_drag_source"):
            delattr(self, "_link_drag_source")
        self._apply_link_styles()
        return True

    def remove_link_from_row(self, proxy: QGraphicsProxyWidget, row: int) -> None:
        for ln in self._relationship_lines[:]:
            if (ln._child_proxy is proxy and ln._child_row == row) or (ln._parent_proxy is proxy and ln._parent_row == row):
                self._scene.removeItem(ln)
                self._relationship_lines.remove(ln)
        self._apply_link_styles()

    def remove_row_from_table(self, proxy: QGraphicsProxyWidget, row: int) -> None:
        """Remove links for deleted row and adjust indices for rows below."""
        for ln in self._relationship_lines[:]:
            if ln._child_proxy is proxy and ln._child_row == row:
                self._scene.removeItem(ln)
                self._relationship_lines.remove(ln)
            elif ln._parent_proxy is proxy and ln._parent_row == row:
                self._scene.removeItem(ln)
                self._relationship_lines.remove(ln)
        for ln in self._relationship_lines:
            if ln._child_proxy is proxy and ln._child_row > row:
                ln._child_row -= 1
            if ln._parent_proxy is proxy and ln._parent_row > row:
                ln._parent_row -= 1
        self._apply_link_styles()

    def _get_row_link_type(self, proxy: QGraphicsProxyWidget, row: int) -> str:
        """Return 'child', 'parent', or '' for the given row."""
        for ln in self._relationship_lines:
            if ln._child_proxy is proxy and ln._child_row == row:
                return "child"
            if ln._parent_proxy is proxy and ln._parent_row == row:
                return "parent"
        return ""

    def _apply_link_styles(self) -> None:
        """Apply parent (blue) and child (grey) background to linked rows, and update row headers."""
        for p in self._table_proxies:
            w = p.widget()
            if not isinstance(w, _DraggableTableWidget):
                continue
            table = w.get_table()
            for r in range(table.rowCount()):
                for c in range(table.columnCount()):
                    item = table.item(r, c)
                    if item is not None:
                        item.setData(Qt.ItemDataRole.BackgroundRole, None)
            for ln in self._relationship_lines:
                for proxy, r, bg in [
                    (ln._child_proxy, ln._child_row, LINK_CHILD_BG),
                    (ln._parent_proxy, ln._parent_row, LINK_PARENT_BG),
                ]:
                    if proxy is p and 0 <= r < table.rowCount():
                        for c in range(table.columnCount()):
                            item = table.item(r, c)
                            if item is None:
                                item = QTableWidgetItem()
                                table.setItem(r, c, item)
                            item.setData(Qt.ItemDataRole.BackgroundRole, QBrush(bg))
            for r in range(table.rowCount()):
                link_type = self._get_row_link_type(p, r)
                suffix = " (P)" if link_type == "parent" else (" (C)" if link_type == "child" else "")
                label = str(r + 1) + suffix
                h = table.verticalHeaderItem(r)
                if h is None:
                    h = QTableWidgetItem()
                    table.setVerticalHeaderItem(r, h)
                h.setText(label)

    def snap_table_aside_if_overlapping(self, proxy: QGraphicsProxyWidget) -> None:
        br = proxy.boundingRect()
        current_rect = QRectF(proxy.pos(), QSizeF(br.width(), br.height()))
        for other in self._table_proxies:
            if other is proxy:
                continue
            other_rect = QRectF(other.pos(), other.boundingRect().size())
            if current_rect.intersects(other_rect):
                safe_pos = self._find_non_overlapping_pos(
                    proxy.pos(), br.width(), br.height(), exclude_proxy=proxy
                )
                proxy.setPos(safe_pos)
                break

    def _show_context_menu(self, pos: QPoint) -> None:
        item = self._view.itemAt(pos)
        proxy = None
        if item is not None:
            if isinstance(item, QGraphicsProxyWidget):
                proxy = item
            else:
                parent = item
                while parent is not None:
                    if isinstance(parent, QGraphicsProxyWidget):
                        proxy = parent
                        break
                    parent = parent.parentItem()
        if proxy is not None:
            widget = proxy.widget()
            if isinstance(widget, _DraggableTableWidget):
                global_pos = self._view.mapToGlobal(pos)
                widget.show_table_context_menu_at(global_pos)
                return
        scene_pos = self._view.mapToScene(pos)
        menu = QMenu(self)
        menu.setStyleSheet(CONTEXT_MENU_STYLESHEET)
        add_action = menu.addAction("Add Table here")
        add_action.triggered.connect(lambda: self._add_table_at(scene_pos))
        menu.exec(self._view.mapToGlobal(pos))

    def _add_table_at(self, pos: QPointF | None = None) -> None:
        if pos is None:
            pos = self._add_offset
        self._add_table_at_position(pos)

    def _add_table(self) -> None:
        self._add_table_at_position(self._add_offset)

    def _find_non_overlapping_pos(
        self, pos: QPointF, width: float, height: float, exclude_proxy: QGraphicsProxyWidget | None = None
    ) -> QPointF:
        candidate = pos
        for _ in range(20):
            rect = QRectF(candidate, QSizeF(width, height))
            overlaps = any(
                p is not exclude_proxy and rect.intersects(QRectF(p.pos(), p.boundingRect().size()))
                for p in self._table_proxies
            )
            if not overlaps:
                return candidate
            candidate += QPointF(30, 30)
        return candidate

    def add_row_to_table_at(self, proxy: QGraphicsProxyWidget, row: int) -> None:
        container = proxy.widget()
        if not isinstance(container, _DraggableTableWidget):
            return
        table = container.get_table()
        table.insertRow(row)
        for c in range(table.columnCount()):
            if c == COL_TYPE and c < len(FIELD_HEADERS):
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, "")
                item.setData(Qt.ItemDataRole.UserRole, "VARCHAR")
                table.setItem(row, c, item)
                table.setCellWidget(row, c, _make_data_type_cell("VARCHAR", table, row, c))
            elif c == COL_NULLABLE and c < len(FIELD_HEADERS):
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, "")
                item.setData(Qt.ItemDataRole.UserRole, "0")
                table.setItem(row, c, item)
                table.setCellWidget(row, c, _make_checkbox_cell())
            elif c == COL_PK and c < len(FIELD_HEADERS):
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, "")
                item.setData(Qt.ItemDataRole.UserRole, "0")
                table.setItem(row, c, item)
                table.setCellWidget(row, c, _make_checkbox_cell())
            else:
                table.setItem(row, c, QTableWidgetItem(""))
        table.resizeColumnsToContents()
        table.resizeRowsToContents()
        QTimer.singleShot(0, container._apply_table_size)
        QTimer.singleShot(0, self._apply_link_styles)

    def duplicate_table(self, proxy: QGraphicsProxyWidget) -> None:
        container = proxy.widget()
        if not isinstance(container, _DraggableTableWidget):
            return
        table = container.get_table()
        name = container.get_table_name()
        pos = proxy.pos() + QPointF(40, 40)
        self._add_table_at_position(pos, copy_from=(table, name))

    def delete_table(self, proxy: QGraphicsProxyWidget) -> None:
        if proxy in self._table_proxies:
            self._table_proxies.remove(proxy)
        for ln in self._relationship_lines[:]:
            if ln._child_proxy is proxy or ln._parent_proxy is proxy:
                self._scene.removeItem(ln)
                self._relationship_lines.remove(ln)
        if hasattr(self, "_link_drag_source") and self._link_drag_source[0] is proxy:
            delattr(self, "_link_drag_source")
        self._apply_link_styles()
        self._scene.removeItem(proxy)
        proxy.deleteLater()

    def _get_cell_value(self, table: QTableWidget, row: int, col: int):
        """Get value from cell - handles both item and widget."""
        w = table.cellWidget(row, col)
        if isinstance(w, _DataTypeButton):
            return w.value()
        if isinstance(w, (QCheckBox, _CheckBoxCell, _CheckBoxCellContainer)):
            return "1" if w.isChecked() else "0"
        item = table.item(row, col)
        return item.text() if item else ""

    def _add_table_at_position(
        self,
        pos: QPointF,
        copy_from: tuple[QTableWidget, str] | None = None,
        initial_data: tuple[str, list[tuple[str, str, str, bool, bool, str]]] | None = None,
    ) -> QGraphicsProxyWidget | None:
        table = _LinkableTableWidget(self)
        table.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        table.setColumnCount(len(FIELD_HEADERS))
        table.setHorizontalHeaderLabels(FIELD_HEADERS)
        table.verticalHeader().setVisible(True)
        table.verticalHeader().setDefaultSectionSize(24)
        table.verticalHeader().setMinimumSectionSize(20)
        table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.setShowGrid(False)
        table.setFrameShape(QFrame.Shape.NoFrame)
        table.setWordWrap(True)
        table.horizontalHeader().setVisible(True)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setMinimumSectionSize(80)
        table.horizontalHeader().setDefaultSectionSize(100)

        if copy_from:
            src_table, src_name = copy_from
            data_rows = src_table.rowCount()
            table.setRowCount(data_rows)
            for row in range(data_rows):
                src_row = row
                for c in range(min(src_table.columnCount(), table.columnCount())):
                    val = self._get_cell_value(src_table, src_row, c)
                    if c == COL_TYPE:
                        item = QTableWidgetItem()
                        item.setData(Qt.ItemDataRole.DisplayRole, "")
                        item.setData(Qt.ItemDataRole.UserRole, val)
                        table.setItem(row, c, item)
                        table.setCellWidget(row, c, _make_data_type_cell(val, table, row, c))
                    elif c == COL_NULLABLE:
                        item = QTableWidgetItem()
                        item.setData(Qt.ItemDataRole.DisplayRole, "")
                        item.setData(Qt.ItemDataRole.UserRole, val)
                        table.setItem(row, c, item)
                        table.setCellWidget(row, c, _make_checkbox_cell(val == "1"))
                    elif c == COL_PK:
                        item = QTableWidgetItem()
                        item.setData(Qt.ItemDataRole.DisplayRole, "")
                        item.setData(Qt.ItemDataRole.UserRole, val)
                        table.setItem(row, c, item)
                        table.setCellWidget(row, c, _make_checkbox_cell(val == "1"))
                    else:
                        table.setItem(row, c, QTableWidgetItem(val))
        elif initial_data:
            table_name, fields = initial_data
            table.setRowCount(len(fields))
            for row, (col_name, display_label, data_type, nullable, pk, default) in enumerate(fields):
                table.setItem(row, COL_NAME, QTableWidgetItem(col_name))
                table.setItem(row, COL_LABEL, QTableWidgetItem(display_label))
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, "")
                item.setData(Qt.ItemDataRole.UserRole, data_type)
                table.setItem(row, COL_TYPE, item)
                table.setCellWidget(row, COL_TYPE, _make_data_type_cell(data_type, table, row, COL_TYPE))
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, "")
                item.setData(Qt.ItemDataRole.UserRole, "1" if nullable else "0")
                table.setItem(row, COL_NULLABLE, item)
                table.setCellWidget(row, COL_NULLABLE, _make_checkbox_cell(nullable))
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, "")
                item.setData(Qt.ItemDataRole.UserRole, "1" if pk else "0")
                table.setItem(row, COL_PK, item)
                table.setCellWidget(row, COL_PK, _make_checkbox_cell(pk))
                table.setItem(row, COL_DEFAULT, QTableWidgetItem(default))
        else:
            table.setRowCount(1)
            for row in range(1):
                for c in range(len(FIELD_HEADERS)):
                    if c == COL_TYPE:
                        item = QTableWidgetItem()
                        item.setData(Qt.ItemDataRole.DisplayRole, "")
                        item.setData(Qt.ItemDataRole.UserRole, "VARCHAR")
                        table.setItem(row, c, item)
                        table.setCellWidget(row, c, _make_data_type_cell("VARCHAR", table, row, c))
                    elif c == COL_NULLABLE:
                        item = QTableWidgetItem()
                        item.setData(Qt.ItemDataRole.DisplayRole, "")
                        item.setData(Qt.ItemDataRole.UserRole, "0")
                        table.setItem(row, c, item)
                        table.setCellWidget(row, c, _make_checkbox_cell())
                    elif c == COL_PK:
                        item = QTableWidgetItem()
                        item.setData(Qt.ItemDataRole.DisplayRole, "")
                        item.setData(Qt.ItemDataRole.UserRole, "0")
                        table.setItem(row, c, item)
                        table.setCellWidget(row, c, _make_checkbox_cell())
                    else:
                        table.setItem(row, c, QTableWidgetItem(""))

        table.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        table.resizeColumnsToContents()
        table.resizeRowsToContents()
        table.setStyleSheet(
            "QTableWidget { "
            "  border: none; border-top: 1px solid #e2e8f0; background: white; "
            "  font-size: 10px; "
            "} "
            "QTableWidget::item { "
            "  border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; "
            "  padding: 4px 8px; font-size: 10px; color: #334155; "
            "} "
            "QTableWidget::item:selected { background: #eff6ff; color: #1e40af; } "
            "QHeaderView::section { "
            "  padding: 4px 8px; font-size: 11px; font-weight: 600; color: #475569; "
            "  background: #f8fafc; border: none; border-right: 1px solid #e2e8f0; "
            "  border-bottom: 1px solid #e2e8f0; "
            "} "
            "QTableWidget QTableCornerButton::section { background: #f8fafc; } "
        )
        table.horizontalHeader().setFixedHeight(DATA_TABLE_HORIZONTAL_HEADER_HEIGHT_PX)

        container = _DraggableTableWidget(table, self)
        if copy_from:
            container._name_edit.setText(copy_from[1] + " (copy)")
        elif initial_data:
            container._name_edit.setText(initial_data[0])
        proxy = self._scene.addWidget(container)
        proxy.setWindowFrameMargins(0, 0, 0, 0)
        proxy.setFlag(QGraphicsItem.GraphicsItemFlag.ItemClipsChildrenToShape, False)
        container.set_proxy(proxy)
        br = proxy.boundingRect()
        safe_pos = self._find_non_overlapping_pos(pos, br.width(), br.height())
        proxy.setPos(safe_pos)
        proxy.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        proxy.setZValue(1)

        self._table_proxies.append(proxy)
        self._add_offset = safe_pos + QPointF(40, 40)

        def _fit_and_apply() -> None:
            table.resizeColumnsToContents()
            table.resizeRowsToContents()
            container._apply_table_size()
            self._apply_link_styles()

        QTimer.singleShot(0, _fit_and_apply)
        return proxy

    def _validate_and_show(self) -> None:
        errs = self.validate_tables()
        _msg_pad = "padding: 8px 16px;"
        if not errs:
            show_auto_hiding_message(
                self,
                self._message_label,
                "All tables are valid.",
                error=False,
                style_sheet=f"color: #16a34a; font-size: 13px; font-weight: 500; {_msg_pad}",
            )
        else:
            show_auto_hiding_message(
                self,
                self._message_label,
                "\n".join(errs),
                error=True,
                style_sheet=f"color: #dc2626; font-size: 13px; font-weight: 500; {_msg_pad}",
            )

    def validate_tables(self) -> list[str]:
        errors: list[str] = []
        for p in self._table_proxies:
            w = p.widget()
            if isinstance(w, _DraggableTableWidget):
                name = w.get_table_name()
                table = w.get_table()
                if not name:
                    errors.append("Table has no name")
                for row in range(table.rowCount()):
                    col_name_item = table.item(row, COL_NAME)
                    col_name = (col_name_item.text() if col_name_item else "").strip()
                    if not col_name and any(
                        (table.item(row, c) and table.item(row, c).text().strip())
                        or table.cellWidget(row, c)
                        for c in range(table.columnCount())
                    ):
                        errors.append(f"Row {row} in '{name or 'unnamed'}': Column Name is required")
        return errors

    def get_tables_data(self) -> list[dict]:
        errs = self.validate_tables()
        if errs:
            show_auto_hiding_message(
                self,
                self._message_label,
                "\n".join(errs),
                error=True,
                style_sheet="color: #dc2626; font-size: 13px; font-weight: 500; padding: 8px 16px;",
            )
            return []
        show_auto_hiding_message(self, self._message_label, "")
        result = []
        for p in self._table_proxies:
            w = p.widget()
            if isinstance(w, _DraggableTableWidget):
                name = w.get_table_name()
                table = w.get_table()
                fields = []
                for row in range(table.rowCount()):
                    col_name_item = table.item(row, COL_NAME)
                    col_name = (col_name_item.text() if col_name_item else "").strip()
                    if not col_name:
                        continue
                    label_item = table.item(row, COL_LABEL)
                    label = (label_item.text() if label_item else "").strip()
                    type_val = self._get_cell_value(table, row, COL_TYPE)
                    null_w = table.cellWidget(row, COL_NULLABLE)
                    nullable = null_w.isChecked() if isinstance(null_w, (QCheckBox, _CheckBoxCell, _CheckBoxCellContainer)) else False
                    pk_w = table.cellWidget(row, COL_PK)
                    pk = pk_w.isChecked() if isinstance(pk_w, (QCheckBox, _CheckBoxCell, _CheckBoxCellContainer)) else False
                    default_item = table.item(row, COL_DEFAULT)
                    default = (default_item.text() if default_item else "").strip()
                    fields.append({
                        "name": col_name,
                        "label": label,
                        "type": type_val,
                        "nullable": nullable,
                        "primary_key": pk,
                        "default": default,
                    })
                result.append({"name": name, "fields": fields})
        return result
