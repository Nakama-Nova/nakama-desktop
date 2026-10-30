"""
ui/components/carvings.py

Wood-carving decoration from the brand images: CarvingRow draws a mirrored pair facing
each other with a god sculpture between them (the same arrangement as the website), and
EmptyState puts that row, a title and a message where a table has nothing to show.
"""

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QLabel, QPushButton, QSizePolicy, QTableWidget, QVBoxLayout, QWidget

from ui.assets import carving_path, load_image, scaled_pixmap
from ui.theme import Colors, Fonts, Spacing, Theme

# name -> (side carving, god in the middle). The photos face right, so the left one is
# drawn as it is and the right one mirrored: the pair looks inward at the god.
SETS = {
    "temple": ("yali-painted", "ganesha-painted"),
    "horse": ("horse-painted", "ganesha-painted"),
    "dark": ("yali-dark", "balaji"),
    "dark-horse": ("horse-dark", "ganesha-dark"),
    "pillar": ("pillar-a", "balaji"),
}

SIDE_SCALE = 0.82  # the pair is a little shorter than the god between them


class CarvingRow(QWidget):
    """[carving] [god] [mirrored carving], bottom-aligned, scaled to this widget's height
    (and shrunk to fit if the width is short). Sharp on high-DPI screens."""

    def __init__(self, set_name: str = "temple", gap: int = Spacing.MD, parent: QWidget | None = None):
        super().__init__(parent)
        self._side, self._god = SETS[set_name]
        self._gap = gap
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(64)

    def _aspect(self, name: str) -> float:
        image = load_image(carving_path(name))
        return image.width() / image.height() if not image.isNull() and image.height() else 0.5

    def layout_boxes(self) -> list[tuple[str, bool, QRectF]]:
        """(carving name, mirrored, rectangle) for the three pieces, in this widget's
        coordinates."""
        width, height = self.width(), self.height()
        god_h = float(height)
        side_h = god_h * SIDE_SCALE
        side_w = side_h * self._aspect(self._side)
        god_w = god_h * self._aspect(self._god)
        gap = float(self._gap)
        total = 2 * side_w + god_w + 2 * gap
        if total > width > 0:
            k = width / total
            god_h, side_h, side_w, god_w, gap = (v * k for v in (god_h, side_h, side_w, god_w, gap))
            total = float(width)
        x = (width - total) / 2
        base = float(height)
        return [
            (self._side, False, QRectF(x, base - side_h, side_w, side_h)),
            (self._god, False, QRectF(x + side_w + gap, base - god_h, god_w, god_h)),
            (self._side, True, QRectF(x + side_w + gap + god_w + gap, base - side_h, side_w, side_h)),
        ]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        dpr = self.devicePixelRatioF()
        for name, mirrored, rect in self.layout_boxes():
            if rect.height() < 4:
                continue
            # a soft ground shadow anchors each piece
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(42, 26, 16, 34))
            painter.drawEllipse(QPointF(rect.center().x(), rect.bottom() - 1), rect.width() * 0.42, 4.0)
            pixmap = scaled_pixmap(carving_path(name), round(rect.height()), mirrored, dpr)
            if not pixmap.isNull():
                painter.drawPixmap(
                    QPointF(rect.center().x() - pixmap.width() / dpr / 2, rect.bottom() - pixmap.height() / dpr),
                    pixmap,
                )


class EmptyState(QWidget):
    """What a screen shows when its list is empty: the carving trio, a title and a hint.
    Under COMPACT_BELOW pixels tall it drops the carvings and keeps the words."""

    COMPACT_BELOW = 240
    CARVING_HEIGHT = 132

    def __init__(self, title: str, message: str = "", set_name: str = "temple", action: QPushButton | None = None,
                 parent: QWidget | None = None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.LG, Spacing.MD, Spacing.LG, Spacing.MD)
        root.setSpacing(Spacing.SM)
        root.addStretch(1)

        self.carvings = CarvingRow(set_name)
        self.carvings.setFixedHeight(self.CARVING_HEIGHT)
        self.carvings.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        root.addWidget(self.carvings)

        self.title_lbl = QLabel(title)
        self.title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_lbl.setStyleSheet(Theme.heading(Fonts.HEADING_MD) + "background: transparent; border: none;")
        root.addWidget(self.title_lbl)

        self.message_lbl = QLabel(message)
        self.message_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.message_lbl.setWordWrap(True)
        self.message_lbl.setStyleSheet(
            f"font-size: {Fonts.BODY}px; color: {Colors.TEXT_SECONDARY}; background: transparent; border: none;"
        )
        self.message_lbl.setVisible(bool(message))
        root.addWidget(self.message_lbl)

        if action is not None:
            root.addWidget(action, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.carvings.setVisible(event.size().height() >= self.COMPACT_BELOW)


class _TableWatcher(QObject):
    """Keeps an EmptyState over a table's body, visible exactly while the table has no rows.

    The EmptyState is built the first time the table is on screen and empty, so screens
    that are never opened (or always have rows) cost nothing. It looks at the table when
    its body is shown, resized or repainted (adding or removing rows repaints it) rather
    than listening to the model, whose signals also fire while the table is torn down."""

    EMPTY_MIN_HEIGHT = 300

    def __init__(self, table: QTableWidget, make_state):
        super().__init__(table)
        self._table, self._make_state = table, make_state
        self.state: EmptyState | None = None
        table.viewport().installEventFilter(self)

    def sync(self):
        empty = self._table.rowCount() == 0
        if self.state is None:
            if not (empty and self._table.isVisible()):
                return
            self.state = self._make_state()
        # An empty list gets room for the carvings even when its screen would squeeze it.
        floor = self.EMPTY_MIN_HEIGHT if empty else 0
        if self._table.minimumHeight() != floor and self._table.minimumHeight() in (0, self.EMPTY_MIN_HEIGHT):
            self._table.setMinimumHeight(floor)
        if self.state.geometry() != self._table.viewport().rect():
            self.state.setGeometry(self._table.viewport().rect())
        if self.state.isHidden() == empty:
            self.state.setVisible(empty)
            self.state.raise_()

    def _out_of_date(self) -> bool:
        empty = self._table.rowCount() == 0
        if self.state is None:
            return empty and self._table.isVisible()
        return empty == self.state.isHidden()

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.Paint:
            if self._out_of_date():
                QTimer.singleShot(0, self._deferred_sync)
        elif kind == QEvent.Type.Resize or kind == QEvent.Type.Show:
            if self.state is not None or self._out_of_date():
                QTimer.singleShot(0, self._deferred_sync)
        return False

    def _deferred_sync(self):
        try:
            self.sync()
        except RuntimeError:  # the table was deleted before this ran
            pass


def attach_empty_state(table: QTableWidget, title: str, message: str = "", set_name: str = "temple",
                       action: QPushButton | None = None) -> _TableWatcher:
    """Show an EmptyState over `table` while it has no rows. Returns the watcher; its
    `state` is the EmptyState once the table has first been shown empty."""
    watcher = _TableWatcher(
        table, lambda: EmptyState(title, message, set_name, action, parent=table.viewport())
    )
    watcher.sync()
    return watcher
