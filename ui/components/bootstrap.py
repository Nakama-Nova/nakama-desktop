"""
ui/components/bootstrap.py

Bootstrap-style building blocks on top of ui/theme.py: Button, Badge, Alert, Card and a
12-column responsive Grid12. Plain widgets, so they drop into any existing layout.
"""

from PyQt6.QtCore import QEvent, QObject, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.theme import Colors, Fonts, Radius, Spacing, Theme


def Button(text: str, role: str = "primary", size: str = "md", outline: bool = False) -> QPushButton:
    """A Bootstrap button: role is primary/secondary/success/danger/warning/info/light/dark,
    size is sm/md/lg."""
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(Theme.btn(role, size, outline))
    return btn


class Badge(QLabel):
    """A small pill label, e.g. Badge("New", "success")."""

    def __init__(self, text: str = "", role: str = "primary", pill: bool = True):
        super().__init__(text)
        self.setStyleSheet(Theme.badge(role, pill))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set_role(self, role: str) -> None:
        self.setStyleSheet(Theme.badge(role))


class Alert(QLabel):
    """A message box in a contextual role, e.g. Alert("Saved", "success")."""

    def __init__(self, text: str = "", role: str = "primary"):
        super().__init__(text)
        self.setWordWrap(True)
        self.setStyleSheet(Theme.alert(role))
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def set_role(self, role: str) -> None:
        self.setStyleSheet(Theme.alert(role))


class Card(QFrame):
    """A bordered, rounded panel with an optional header. Put content in `body`."""

    def __init__(self, title: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(
            f"""
            QFrame#card {{
                background-color: {Colors.CARD_BG};
                border: 1px solid {Colors.CARD_BORDER};
                border-radius: {Radius.LG}px;
            }}
            QFrame#card QLabel {{ border: none; background: transparent; }}
            """
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.header = None
        if title:
            self.header = QLabel(title)
            self.header.setStyleSheet(
                f"font-size: {Fonts.BODY}px; font-weight: 600; color: {Colors.TEXT_PRIMARY};"
                f" padding: 12px {Spacing.MD}px; border-bottom: 1px solid {Colors.CARD_BORDER};"
                f" background-color: {Colors.TABLE_HEADER_BG};"
                f" border-top-left-radius: {Radius.LG}px; border-top-right-radius: {Radius.LG}px;"
            )
            outer.addWidget(self.header)
        self.body = QVBoxLayout()
        self.body.setContentsMargins(Spacing.MD, Spacing.MD, Spacing.MD, Spacing.MD)
        self.body.setSpacing(Spacing.SM)
        outer.addLayout(self.body)


class Grid12(QWidget):
    """A responsive 12-column grid, like Bootstrap's row/col.

    grid.add(widget, lg=3, md=6, sm=12): the widget spans 3 of 12 columns on a wide grid
    (>= 992px), 6 on a medium one (>= 768px) and 12 (full width) on a narrow one.
    Widgets wrap onto new rows when a row's spans pass 12.
    """

    LG_MIN = 992
    MD_MIN = 768

    def __init__(self, gap: int = Spacing.MD, parent: QWidget | None = None):
        super().__init__(parent)
        self._items: list[tuple[QWidget, dict[str, int]]] = []
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(gap)
        for col in range(12):
            self._grid.setColumnStretch(col, 1)
            self._grid.setColumnMinimumWidth(col, 0)
        self._mode = ""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

    def add(self, widget: QWidget, lg: int = 3, md: int = 6, sm: int = 12) -> None:
        self._items.append((widget, {"lg": lg, "md": md, "sm": sm}))
        self._place(self._mode_for(self.width()), force=True)

    def mode(self) -> str:
        return self._mode

    def _mode_for(self, width: int) -> str:
        if width >= self.LG_MIN:
            return "lg"
        return "md" if width >= self.MD_MIN else "sm"

    def _place(self, mode: str, force: bool = False) -> None:
        if mode == self._mode and not force:
            return
        self._mode = mode
        for widget, _ in self._items:
            self._grid.removeWidget(widget)
        row = col = 0
        for widget, spans in self._items:
            span = max(1, min(12, spans[mode]))
            if col + span > 12:
                row += 1
                col = 0
            self._grid.addWidget(widget, row, col, 1, span)
            widget.show()
            col += span

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place(self._mode_for(event.size().width()))


class BootstrapBehaviour(QObject):
    """Things a style sheet cannot do, applied app-wide by Theme.install():
    a soft focus ring around the focused form control, and striped table rows."""

    FIELDS = (QLineEdit, QAbstractSpinBox, QComboBox, QPlainTextEdit, QTextEdit)

    def eventFilter(self, obj, event):
        kind = event.type()
        if kind == QEvent.Type.FocusIn or kind == QEvent.Type.FocusOut:
            if isinstance(obj, QWidget):
                self._ring(obj, kind == QEvent.Type.FocusIn)
        elif kind == QEvent.Type.Polish and isinstance(obj, QTableWidget):
            obj.setAlternatingRowColors(True)
        return False

    @classmethod
    def _field_of(cls, widget: QWidget) -> QWidget | None:
        """The control to ring: a spin box's or combo box's inner editor rings its owner."""
        if not isinstance(widget, cls.FIELDS):
            return None
        parent = widget.parentWidget()
        if isinstance(parent, (QAbstractSpinBox, QComboBox)):
            return parent
        return widget

    def _ring(self, widget: QWidget, focused: bool) -> None:
        field = self._field_of(widget)
        if field is None:
            return
        effect = field.graphicsEffect()
        if focused:
            if effect is None:
                ring = QGraphicsDropShadowEffect(field)
                ring.setOffset(0, 0)
                ring.setBlurRadius(10)
                ring.setColor(QColor(Colors.INPUT_FOCUS))
                ring.setProperty("focusRing", True)
                field.setGraphicsEffect(ring)
        elif effect is not None and effect.property("focusRing"):
            field.setGraphicsEffect(None)
