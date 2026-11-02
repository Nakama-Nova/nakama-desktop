"""
ui/components/interactive.py

Small pieces that make a list screen feel alive: a bar of filter chips with live counts,
a usage bar that changes colour as a budget is used up, and a row of table action buttons.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QFrame,
    QWidget,
)

from ui.theme import Colors, Fonts, Spacing, Theme

STATE_COLOURS = {
    "ok": Colors.SUCCESS,
    "warning": Colors.ORANGE,
    "over": Colors.DANGER,
    "no_budget": Colors.TEXT_MUTED,
}


class ChipBar(QScrollArea):
    """A row of chips; click one to filter by it. Each shows how many rows it would leave.

        bar.set_chips([("all", "All", 12), ("down", "Down", 2)])
        bar.changed.connect(lambda key: ...)

    The chosen chip is kept across set_chips() while it still exists, so a refresh does not
    throw away the user's filter."""

    changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.setFixedHeight(48)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        self._row = QHBoxLayout(inner)
        self._row.setContentsMargins(0, 4, 0, 4)
        self._row.setSpacing(Spacing.SM)
        self.setWidget(inner)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        self._current = ""

    @staticmethod
    def _css() -> str:
        return f"""
            QPushButton {{
                background-color: {Colors.CARD_BG};
                color: {Colors.TEXT_SECONDARY};
                border: 1px solid {Colors.INPUT_BORDER};
                border-radius: 15px;
                padding: 5px 14px;
                font-size: {Fonts.BODY_SM}px;
                font-weight: 600;
            }}
            QPushButton:hover {{ border-color: {Colors.BRAND_GOLD}; color: {Colors.BRAND_BROWN}; }}
            QPushButton:checked {{
                background-color: {Colors.BRAND_BROWN};
                border-color: {Colors.BRAND_BROWN};
                color: #FFFFFF;
            }}
        """

    def current(self) -> str:
        return self._current

    def set_chips(self, chips: list[tuple[str, str, int]]) -> None:
        for b in self._buttons.values():
            self._group.removeButton(b)
            b.deleteLater()
        self._buttons.clear()
        while self._row.count():
            self._row.takeAt(0)
        keys = [k for k, _, _ in chips]
        if self._current not in keys:
            self._current = keys[0] if keys else ""
        for key, label, count in chips:
            b = QPushButton(f"{label}  ·  {count}")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(self._css())
            b.setChecked(key == self._current)
            b.clicked.connect(lambda _=False, k=key: self.choose(k))
            self._group.addButton(b)
            self._buttons[key] = b
            self._row.addWidget(b)
        self._row.addStretch()

    def choose(self, key: str) -> None:
        if key not in self._buttons:
            return
        self._buttons[key].setChecked(True)
        if key != self._current:
            self._current = key
            self.changed.emit(key)


class UsageBar(QProgressBar):
    """How much of a budget is used: green, then amber from 80%, red when it is all used."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setFixedHeight(12)
        self.setRange(0, 100)
        self.set_usage(0, "no_budget")

    def set_usage(self, percent: float, state: str) -> None:
        colour = STATE_COLOURS.get(state, Colors.TEXT_MUTED)
        self.setValue(max(0, min(100, int(round(percent)))))
        self.setStyleSheet(
            f"QProgressBar {{ background-color: {Colors.TABLE_HEADER_BG}; border: none;"
            " border-radius: 6px; }"
            f"QProgressBar::chunk {{ background-color: {colour}; border-radius: 6px; }}"
        )


def action_buttons(actions: list[tuple[str, object, str]]) -> QWidget:
    """A row of small buttons for a table cell: (text, slot, tooltip). One-symbol buttons
    (🕘, 🗑️) stay narrow."""
    box = QWidget()
    h = QHBoxLayout(box)
    h.setContentsMargins(4, 4, 4, 4)
    h.setSpacing(6)
    for text, slot, tip in actions:
        b = QPushButton(text)
        b.setFixedHeight(30)
        b.setStyleSheet(Theme.btn_table_action())
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip(tip)
        if len(text) <= 2:
            b.setFixedWidth(40)
        b.clicked.connect(lambda _=False, s=slot: s())
        h.addWidget(b)
    return box
