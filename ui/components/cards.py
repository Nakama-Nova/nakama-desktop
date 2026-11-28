"""
ui/components/cards.py

What makes a card feel like a card on a modern page, for Qt: a soft shadow that lifts a little
when the pointer is over it, an icon in a tinted round-cornered chip, and a hero panel with a
gradient. Used by Home, the stat cards and the Stock summary.

    elevate(card)              soft shadow
    lift_on_hover(card)        the shadow deepens while the pointer is over the card
    icon_chip("money", color)  a 40px tinted square holding a line icon
    HeroCard()                 the deep-teak gradient panel at the top of Home
"""

from PyQt6.QtCore import QEvent, QObject, QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QLabel, QWidget

from ui import icons
from ui.theme import Colors, soft

SHADOW = "#5A2A06"  # the brand brown: a warm shadow, not a grey one


def elevate(widget: QWidget, blur: int = 26, dy: int = 6, alpha: int = 34) -> QGraphicsDropShadowEffect:
    """Give a card a soft, warm shadow."""
    effect = QGraphicsDropShadowEffect(widget)
    colour = QColor(SHADOW)
    colour.setAlpha(alpha)
    effect.setColor(colour)
    effect.setBlurRadius(blur)
    effect.setOffset(0, dy)
    widget.setGraphicsEffect(effect)
    return effect


class _Lift(QObject):
    """Deepens a card's shadow while the pointer is over it."""

    def __init__(self, widget: QWidget, effect: QGraphicsDropShadowEffect, extra_blur: int, extra_dy: int, extra_alpha: int):
        super().__init__(widget)
        self._effect = effect
        self._rest = (effect.blurRadius(), effect.yOffset(), effect.color().alpha())
        self._lift = (effect.blurRadius() + extra_blur, effect.yOffset() + extra_dy, min(255, effect.color().alpha() + extra_alpha))
        widget.installEventFilter(self)

    def _apply(self, blur, dy, alpha):
        colour = self._effect.color()
        colour.setAlpha(alpha)
        self._effect.setColor(colour)
        self._effect.setBlurRadius(blur)
        self._effect.setOffset(0, dy)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.Enter:
            self._apply(*self._lift)
        elif kind == QEvent.Type.Leave:
            self._apply(*self._rest)
        return False


def lift_on_hover(widget: QWidget, extra_blur: int = 14, extra_dy: int = 4, extra_alpha: int = 22) -> None:
    effect = widget.graphicsEffect()
    if isinstance(effect, QGraphicsDropShadowEffect):
        widget._lift = _Lift(widget, effect, extra_blur, extra_dy, extra_alpha)


def icon_chip(name: str, color: str, size: int = 40) -> QLabel:
    """A line icon on a soft tint of `color`, in a rounded square."""
    chip = QLabel()
    chip.setFixedSize(size, size)
    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    chip.setStyleSheet(f"background: {soft(color)}; border-radius: {size // 3}px; border: none;")
    chip.setPixmap(icons.pixmap(name, color, size // 2))
    return chip


class HeroCard(QFrame):
    """A deep-teak panel with a warm glow, for the first thing on Home. Paints its own gradient
    (children sit on top and must have transparent backgrounds)."""

    RADIUS = 18

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("hero")
        self.setMinimumHeight(272)
        elevate(self, blur=34, dy=10, alpha=60)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = float(self.width()), float(self.height())
        shape = QPainterPath()
        shape.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), self.RADIUS, self.RADIUS)
        p.setClipPath(shape)

        base = QLinearGradient(0, 0, w, h)
        base.setColorAt(0.0, QColor("#2A1306"))
        base.setColorAt(0.6, QColor("#4B2209"))
        base.setColorAt(1.0, QColor("#6A3410"))
        p.fillPath(shape, base)

        glow = QRadialGradient(QPointF(w * 0.80, h * 0.62), w * 0.34)  # gold light behind the carvings
        glow.setColorAt(0.0, QColor(217, 164, 65, 120))
        glow.setColorAt(1.0, QColor(217, 164, 65, 0))
        p.fillPath(shape, glow)

        p.setClipping(False)
        p.setPen(QPen(QColor(217, 164, 65, 110), 1))  # a gold hairline, like leaf on the frame
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(shape)
        p.end()
        super().paintEvent(event)


CARD_BORDER = Colors.CARD_BORDER


def glow_on_hover(widget: QWidget, color: str | None = None, blur: int = 22, alpha: int = 120) -> QGraphicsDropShadowEffect:
    """A soft gold glow that fades in around the widget while the pointer is over it (a button,
    the command search). For inputs use the focus ring that Theme.install provides instead."""
    from PyQt6.QtCore import QEasingCurve, QPropertyAnimation

    effect = QGraphicsDropShadowEffect(widget)
    colour = QColor(color or Colors.INPUT_FOCUS)
    colour.setAlpha(alpha)
    effect.setColor(colour)
    effect.setOffset(0, 0)
    effect.setBlurRadius(0)  # invisible until the pointer arrives
    widget.setGraphicsEffect(effect)
    anim = QPropertyAnimation(effect, b"blurRadius", widget)
    anim.setDuration(160)
    anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    class _Glow(QObject):
        def eventFilter(self, obj, event):
            kind = event.type()
            if kind in (QEvent.Type.Enter, QEvent.Type.Leave):
                anim.stop()
                anim.setStartValue(effect.blurRadius())
                anim.setEndValue(float(blur) if kind == QEvent.Type.Enter else 0.0)
                anim.start()
            return False

    widget._glow = _Glow(widget)
    widget.installEventFilter(widget._glow)
    return effect
