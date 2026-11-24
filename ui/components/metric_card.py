"""
ui/components/metric_card.py

Reusable MetricCard widget for a KPI: an icon in a tinted chip, the number large, and its name
beneath. A soft shadow lifts it off the page and deepens a little under the pointer.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from ui.components.cards import elevate, icon_chip, lift_on_hover
from ui.icons import EMOJI
from ui.theme import Colors, Fonts, Spacing


class MetricCard(QFrame):
    """A card showing a number and what it counts. `icon` is given as an emoji (see
    ui/icons.EMOJI) and drawn as a line icon in `color` on a soft tint of it."""

    def __init__(
        self, title: str, value: str = "0", color: str = "#8C5A2B", icon: str = ""
    ):
        super().__init__()
        self.setObjectName("metric")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._color = color
        self.setStyleSheet(f"""
            QFrame#metric {{
                background-color: {Colors.CARD_BG};
                border-radius: 16px;
                border: 1px solid {Colors.CARD_BORDER};
            }}
            QFrame#metric QLabel {{
                border: none;
                background: transparent;
            }}
        """)
        elevate(self, blur=22, dy=5, alpha=26)
        lift_on_hover(self)

        # The chip: a line icon in the card's colour (None when the card has no icon). Icon on the
        # left, the number and its name on the right: a card that stays short.
        row = QHBoxLayout(self)
        row.setContentsMargins(Spacing.MD + 4, Spacing.MD, Spacing.MD + 4, Spacing.MD)
        row.setSpacing(Spacing.MD)
        self.icon_lbl = None
        name = EMOJI.get(icon.lstrip()[:1]) if icon else None
        if name:
            self.icon_lbl = icon_chip(name, color, 46)
            row.addWidget(self.icon_lbl, 0, Qt.AlignmentFlag.AlignVCenter)

        words = QVBoxLayout()
        words.setSpacing(0)
        self.value_lbl = QLabel(str(value))
        self.value_lbl.setStyleSheet(f"""
            font-size: 28px;
            font-weight: 700;
            color: {Colors.TEXT_PRIMARY};
        """)
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet(f"""
            font-size: {Fonts.BODY}px;
            color: {Colors.TEXT_SECONDARY};
            font-weight: 500;
        """)
        words.addWidget(self.value_lbl)
        words.addWidget(self.title_lbl)
        row.addLayout(words, 1)

    def set_value(self, value) -> None:
        self.value_lbl.setText(str(value))
