"""
ui/components/glass.py

The building blocks of the glass workspace. They take every colour from the theme tokens, so
they look right in all three themes (light, dark and Heritage glass), and none of them fixes a
height: sizes come from layouts, size policies and stretch factors.

    GlassCard                 a frosted card: translucent fill, a bronze hairline, a warm shadow,
                              a soft sheen at the top, and a border that warms under the pointer
    ScrollableGlassPanel      a GlassCard whose body scrolls, with a footer pinned under it
    AnimatedSidebar           a side rail whose width animates between expanded and icon-only
    CommandTopBar             the top bar: Ctrl+K command search, connection chip, account menu
    BusyLine                  a thin gold line that glides under the top bar while the app loads
    ResponsiveSplitWorkspace  a main pane and a side pane: side by side when wide, stacked when not
    AsyncWorker               a backend call off the GUI thread, with loading/success/error signals
"""

from PyQt6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, QRectF, QSize, Qt, QTimer, pyqtProperty, pyqtSignal
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QBoxLayout, QFrame, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from ui.components.cards import elevate, glow_on_hover
from ui.components.navbar import Navbar
from ui.theme import Colors, rgba

QWIDGETSIZE_MAX = 16777215


# ---------------------------------------------------------------------------------- GlassCard
class GlassCard(QFrame):
    """A frosted card. Put content in `body` (a QVBoxLayout)."""

    RADIUS = 16

    def __init__(self, parent: QWidget | None = None, padding=(18, 16, 18, 16), spacing: int = 10, lift: bool = True):
        super().__init__(parent)
        self.setObjectName("glassCard")
        # the card paints itself; its labels must not paint the page colour over the glass
        self.setStyleSheet(
            "QFrame#glassCard { background: transparent; border: none; }"
            " QFrame#glassCard QLabel, QFrame#glassCard QCheckBox { background: transparent; }"
        )
        self._hover = 0.0
        self._lift = lift
        self._anim = QPropertyAnimation(self, b"hover", self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(*padding)
        self.body.setSpacing(spacing)
        elevate(self, blur=30, dy=8, alpha=90)  # a warm ambient shadow

    # an animatable 0..1 that warms the border
    def _get_hover(self) -> float:
        return self._hover

    def _set_hover(self, value: float) -> None:
        self._hover = value
        self.update()

    hover = pyqtProperty(float, _get_hover, _set_hover)

    def _glide_to(self, value: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(value)
        self._anim.start()

    def enterEvent(self, event):
        if self._lift:
            self._glide_to(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._lift:
            self._glide_to(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), self.RADIUS, self.RADIUS)
        p.fillPath(shape, rgba(Colors.GLASS_FILL))
        sheen = QLinearGradient(0, 0, 0, h * 0.55)  # light catching the top edge
        sheen.setColorAt(0.0, rgba(Colors.GLASS_SHEEN))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(shape, sheen)
        edge = rgba(Colors.GLASS_EDGE)
        gold = QColor(Colors.INPUT_FOCUS)
        t = self._hover  # the hairline warms toward gold under the pointer
        mixed = QColor(
            int(edge.red() + (gold.red() - edge.red()) * t * 0.6),
            int(edge.green() + (gold.green() - edge.green()) * t * 0.6),
            int(edge.blue() + (gold.blue() - edge.blue()) * t * 0.6),
            min(255, int(edge.alpha() + 70 * t)),
        )
        p.setPen(QPen(mixed, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(shape)
        p.end()


class ScrollableGlassPanel(GlassCard):
    """A glass card for tall forms and summaries: `body` scrolls (vertical only, frameless), and
    `footer` stays pinned under it, so a total and a main button are never pushed out of view."""

    def __init__(self, parent: QWidget | None = None, padding=(18, 16, 18, 8), footer_padding=(18, 10, 18, 14), spacing: int = 10):
        super().__init__(parent, padding=(0, 0, 0, 0), spacing=0, lift=False)
        root = self.body
        self.scroller = QScrollArea()
        self.scroller.setObjectName("glassScroll")
        self.scroller.setWidgetResizable(True)
        self.scroller.setFrameShape(QFrame.Shape.NoFrame)
        self.scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroller.setStyleSheet("QScrollArea#glassScroll { background: transparent; border: none; }")
        self.scroller.viewport().setAutoFillBackground(False)
        inner = QWidget()
        inner.setObjectName("glassInner")
        inner.setStyleSheet("QWidget#glassInner { background: transparent; }")
        content = QVBoxLayout(inner)
        content.setContentsMargins(*padding)
        content.setSpacing(spacing)
        self.scroller.setWidget(inner)
        self._inner = inner
        self._inline = False
        inner.installEventFilter(self)  # to follow the contents' height when the panel is inline
        root.addWidget(self.scroller, 1)

        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setStyleSheet(f"QFrame {{ color: rgba({Colors.GLASS_EDGE}); background: transparent; border: none; border-top: 1px solid rgba({Colors.GLASS_EDGE}); }}")
        root.addWidget(rule)
        pinned = QWidget()
        pinned.setObjectName("glassFooter")
        pinned.setStyleSheet("QWidget#glassFooter { background: transparent; }")
        self.footer = QVBoxLayout(pinned)
        self.footer.setContentsMargins(*footer_padding)
        self.footer.setSpacing(6)
        root.addWidget(pinned)
        self.body = content  # what callers fill: the part that scrolls

    def minimumSizeHint(self) -> QSize:
        """As wide as its contents need (plus the scroll bar), so nothing is cut at the right edge."""
        inner = self._inner.minimumSizeHint()
        bar = self.scroller.verticalScrollBar().sizeHint().width()
        return QSize(inner.width() + bar + 2, 160)

    def set_inline(self, inline: bool) -> None:
        """Inline: the panel is as tall as its contents and does not scroll by itself (the screen
        around it scrolls instead). Not inline: it fills the room it has and scrolls its body."""
        self._inline = inline
        self._follow_contents()

    def _follow_contents(self) -> None:
        self.scroller.setMinimumHeight(self._inner.minimumSizeHint().height() + 2 if self._inline else 0)

    def eventFilter(self, obj, event):
        if obj is self._inner and event.type() == QEvent.Type.LayoutRequest and self._inline:
            QTimer.singleShot(0, self._follow_contents)
        return False


# ------------------------------------------------------------------------------ AnimatedSidebar
class AnimatedSidebar(QFrame):
    """A side rail whose width glides between expanded and collapsed (icon-only). The caller
    switches what is inside it (labels, tooltips); `settled` says when the width has arrived."""

    collapsedChanged = pyqtSignal(bool)
    settled = pyqtSignal(bool)
    animated = True  # tests and reduced-motion setups can switch the glide off

    def __init__(self, expanded: int = 232, collapsed: int = 76, parent: QWidget | None = None):
        super().__init__(parent)
        self._expanded, self._collapsed_width = expanded, collapsed
        self._is_collapsed = False
        self._width = expanded
        self._apply(expanded)
        self._anim = QPropertyAnimation(self, b"railWidth", self)
        self._anim.setDuration(190)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(lambda: self.settled.emit(self._is_collapsed))

    def _apply(self, width: int) -> None:
        self._width = width
        self.setMinimumWidth(width)
        self.setMaximumWidth(width)

    def _get_rail_width(self) -> int:
        return self._width

    railWidth = pyqtProperty(int, _get_rail_width, _apply)

    def is_collapsed(self) -> bool:
        return self._is_collapsed

    def set_collapsed(self, collapsed: bool, animate: bool | None = None) -> None:
        if collapsed == self._is_collapsed and self.width() in (0, self._width):
            return
        self._is_collapsed = collapsed
        target = self._collapsed_width if collapsed else self._expanded
        self.collapsedChanged.emit(collapsed)
        glide = self.animated if animate is None else animate
        self._anim.stop()
        if not glide or not self.isVisible():
            self._apply(target)
            self.settled.emit(collapsed)
            return
        self._anim.setStartValue(self._width)
        self._anim.setEndValue(target)
        self._anim.start()


# ------------------------------------------------------------------------------- CommandTopBar
class CommandTopBar(Navbar):
    """The top bar: a Ctrl+K command search that warms when the pointer is on it, the
    connection chip, the bell and the account menu. (The loading line is BusyLine, below it.)"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        glow_on_hover(self.goto_btn, color=Colors.INPUT_FOCUS)


class BusyLine(QWidget):
    """A thin gold line that glides across while the app is loading in the background. It waits a
    moment before showing, so a quick load does not flicker, and it never blocks the interface."""

    DELAY_MS = 140

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._phase = 0.0
        self._active = False
        self._pending = QTimer(self)
        self._pending.setSingleShot(True)
        self._pending.timeout.connect(self._show_line)
        self._anim = QPropertyAnimation(self, b"phase", self)
        self._anim.setDuration(1100)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setLoopCount(-1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(0, 2)

    def minimumSizeHint(self) -> QSize:
        return QSize(0, 2)

    def _get_phase(self) -> float:
        return self._phase

    def _set_phase(self, value: float) -> None:
        self._phase = value
        self.update()

    phase = pyqtProperty(float, _get_phase, _set_phase)

    def set_busy(self, busy: bool) -> None:
        if busy:
            if not self._active and not self._pending.isActive():
                self._pending.start(self.DELAY_MS)
        else:
            self._pending.stop()
            if self._active:
                self._active = False
                self._anim.stop()
                self.update()

    def is_busy(self) -> bool:
        return self._active

    def _show_line(self) -> None:
        self._active = True
        self._anim.start()
        self.update()

    def paintEvent(self, event):
        if not self._active:
            return
        p = QPainter(self)
        w, h = self.width(), self.height()
        span = w * 0.30
        x = (self._phase * (w + span)) - span
        grad = QLinearGradient(x, 0, x + span, 0)
        gold = QColor(Colors.INPUT_FOCUS)
        clear = QColor(gold.red(), gold.green(), gold.blue(), 0)
        grad.setColorAt(0.0, clear)
        grad.setColorAt(0.5, gold)
        grad.setColorAt(1.0, clear)
        p.fillRect(0, 0, w, h, grad)
        p.end()


# ---------------------------------------------------------------------- ResponsiveSplitWorkspace
class ResponsiveSplitWorkspace(QWidget):
    """A main pane and a side pane. Wide: side by side, the side pane taking its share (about a
    quarter) between a minimum and a maximum width. Narrow: stacked, main above side, both full
    width (the screen scrolls)."""

    def __init__(self, main: QWidget, side: QWidget, breakpoint: int = 760, side_min: int = 350, side_max: int = 420, stacked_main_min: int = 300, gap: int = 16, parent: QWidget | None = None):
        super().__init__(parent)
        self._main, self._side = main, side
        self._breakpoint, self._side_min, self._side_max = breakpoint, side_min, side_max
        self._stacked_main_min = stacked_main_min
        self._box = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._box.setContentsMargins(0, 0, 0, 0)
        self._box.setSpacing(gap)
        self._box.addWidget(main, 3)
        self._box.addWidget(side, 1)
        self._wide = None
        self._arrange(True)

    def is_wide(self) -> bool:
        return bool(self._wide)

    def _arrange(self, wide: bool) -> None:
        if wide == self._wide:
            return
        self._wide = wide
        if wide:
            self._box.setDirection(QBoxLayout.Direction.LeftToRight)
            self._box.setStretchFactor(self._main, 3)
            self._box.setStretchFactor(self._side, 1)
            self._main.setMinimumHeight(0)
            self._side.setMaximumWidth(self._side_max)
            self._side.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
            self._fit_side()
            if hasattr(self._side, "set_inline"):
                self._side.set_inline(False)
        else:
            self._box.setDirection(QBoxLayout.Direction.TopToBottom)
            self._box.setStretchFactor(self._main, 0)
            self._box.setStretchFactor(self._side, 0)
            self._main.setMinimumHeight(self._stacked_main_min)  # a floor, so it does not collapse to a sliver
            self._side.setMinimumWidth(0)
            self._side.setMaximumWidth(QWIDGETSIZE_MAX)
            self._side.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            if hasattr(self._side, "set_inline"):
                self._side.set_inline(True)

    def _fit_side(self) -> None:
        """The side pane is never narrower than its contents need (or than side_min)."""
        self._side.setMinimumWidth(max(self._side_min, self._side.minimumSizeHint().width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._arrange(event.size().width() >= self._breakpoint)
        if self._wide:
            self._fit_side()  # the contents may have grown since the last time


# ---------------------------------------------------------------------------------- AsyncWorker
class AsyncWorker(QObject):
    """One backend call off the GUI thread (a QRunnable on the global QThreadPool, through
    ui.workers, which also gathers the server's error pop-ups for the GUI thread to show).

        worker = AsyncWorker(lambda: service.find(phone), parent=self)
        worker.loading.connect(button.setDisabled)
        worker.success.connect(show)
        worker.error.connect(explain)
        worker.start()
    """

    loading = pyqtSignal(bool)
    success = pyqtSignal(object)
    error = pyqtSignal(object)

    def __init__(self, fn, parent: QObject | None = None):
        super().__init__(parent)
        self._fn = fn

    def start(self) -> None:
        from ui.workers import run_async

        self.loading.emit(True)
        run_async(self._fn, self._done, self._failed)

    def _done(self, value) -> None:
        try:
            self.loading.emit(False)
            self.success.emit(value)
        except RuntimeError:  # the owner was closed while the call was out
            pass

    def _failed(self, exc) -> None:
        try:
            self.loading.emit(False)
            self.error.emit(exc)
        except RuntimeError:
            pass
