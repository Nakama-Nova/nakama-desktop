"""
ui/components/row_details.py

A popup that shows one table row in full: every column as a heading with its whole value
below it, wrapped, so nothing is cut or has to be scrolled to. Reached by double-clicking a
row (where the screen has not given double-click another job) or right-click > View details.
Previous / Next (or the arrow keys) walk through the other rows; Copy puts the row on the
clipboard.

    make_inspectable(table)
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Colors, Fonts, Theme


def row_fields(table: QTableWidget, row: int) -> list[tuple[str, str]]:
    """(heading, full text) for each visible column that has a heading; button columns have none."""
    out = []
    for c in range(table.columnCount()):
        head = table.horizontalHeaderItem(c)
        head = head.text().strip() if head else ""
        if table.isColumnHidden(c) or not head:
            continue
        item = table.item(row, c)
        out.append((head, (item.text().strip() if item else "") or "—"))
    return out


class RowDetails(QDialog):
    def __init__(self, table: QTableWidget, row: int, parent=None):
        super().__init__(parent or table.window())
        self._table = table
        self._row = row
        self.setWindowTitle("Details")
        self.setMinimumWidth(460)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(12)

        self.title = QLabel()
        self.title.setWordWrap(True)
        self.title.setStyleSheet(Theme.subheading())
        outer.addWidget(self.title)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; }")
        self._scroll.setMinimumHeight(180)
        outer.addWidget(self._scroll, 1)

        buttons = QHBoxLayout()
        self.prev_btn = QPushButton("◀  Previous")
        self.next_btn = QPushButton("Next  ▶")
        self.position = QLabel()
        self.position.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        copy_btn = QPushButton("Copy")
        close_btn = QPushButton("Close")
        for b in (self.prev_btn, self.next_btn, copy_btn):
            b.setStyleSheet(Theme.btn_secondary())
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(Theme.btn_primary())
        close_btn.setDefault(True)
        self.prev_btn.clicked.connect(lambda: self.step(-1))
        self.next_btn.clicked.connect(lambda: self.step(1))
        copy_btn.clicked.connect(self.copy)
        close_btn.clicked.connect(self.accept)
        buttons.addWidget(self.prev_btn)
        buttons.addWidget(self.next_btn)
        buttons.addWidget(self.position)
        buttons.addStretch()
        buttons.addWidget(copy_btn)
        buttons.addWidget(close_btn)
        outer.addLayout(buttons)
        self._show_row()

    def _show_row(self) -> None:
        fields = row_fields(self._table, self._row)
        self.title.setText(fields[0][1] if fields else "Details")
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        v = QVBoxLayout(body)
        v.setContentsMargins(0, 0, 8, 0)
        v.setSpacing(10)
        self.values: dict[str, QLabel] = {}
        for head, text in fields:
            box = QFrame()
            box.setStyleSheet(
                f"QFrame {{ background-color: {Colors.CARD_BG}; border: 1px solid {Colors.CARD_BORDER};"
                " border-radius: 8px; } QLabel { border: none; background: transparent; }"
            )
            inner = QVBoxLayout(box)
            inner.setContentsMargins(12, 8, 12, 8)
            inner.setSpacing(2)
            label = QLabel(head)
            label.setStyleSheet(f"color: {Colors.TEXT_SECONDARY}; font-size: {Fonts.CAPTION}px; font-weight: 600;")
            value = QLabel(text)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setStyleSheet(f"color: {Colors.TEXT_PRIMARY}; font-size: {Fonts.BODY}px;")
            inner.addWidget(label)
            inner.addWidget(value)
            v.addWidget(box)
            self.values[head] = value
        v.addStretch()
        self._scroll.setWidget(body)
        rows = self._table.rowCount()
        self.prev_btn.setEnabled(self._row > 0)
        self.next_btn.setEnabled(self._row < rows - 1)
        self.position.setText(f"{self._row + 1} of {rows}")

    def step(self, by: int) -> None:
        row = self._row + by
        if 0 <= row < self._table.rowCount():
            self._row = row
            self._table.selectRow(row)
            self._show_row()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Left:
            self.step(-1)
        elif key == Qt.Key.Key_Right:
            self.step(1)
        else:
            super().keyPressEvent(event)

    def copy(self) -> None:
        text = "\n".join(f"{h}: {t}" for h, t in row_fields(self._table, self._row))
        QGuiApplication.clipboard().setText(text)


def open_details(table: QTableWidget, row: int) -> None:
    if 0 <= row < table.rowCount() and row_fields(table, row):
        table.selectRow(row)
        RowDetails(table, row).exec()


def make_inspectable(table: QTableWidget) -> None:
    """Double-click opens the popup unless the screen already uses double-click; the context
    menu always offers it."""
    if table.property("inspectable"):
        return
    table.setProperty("inspectable", True)
    if table.receivers(table.cellDoubleClicked) == 0:
        table.cellDoubleClicked.connect(lambda row, _col: open_details(table, row))
    if table.contextMenuPolicy() == Qt.ContextMenuPolicy.DefaultContextMenu:
        table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        def menu(pos):
            row = table.rowAt(pos.y())
            if row < 0:
                return
            m = QMenu(table)
            m.addAction("View details", lambda: open_details(table, row))
            m.exec(table.viewport().mapToGlobal(pos))

        table.customContextMenuRequested.connect(menu)
