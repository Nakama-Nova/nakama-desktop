"""
ui/components/metric_card.py

Reusable MetricCard widget for displaying KPI values: a Bootstrap-style card with a
coloured accent on its left edge, a small title and a large value.
"""

from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel
from ui.theme import Colors, Fonts, Radius, Spacing


class MetricCard(QFrame):
    """A styled card displaying an icon+title and a large value."""

    def __init__(
        self, title: str, value: str = "0", color: str = "#8C5A2B", icon: str = ""
    ):
        super().__init__()
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._color = color

        self.setStyleSheet(f"""
            MetricCard {{
                background-color: {Colors.CARD_BG};
                border-radius: {Radius.LG}px;
                border: 1px solid {Colors.CARD_BORDER};
                border-left: 4px solid {color};
            }}
            MetricCard:hover {{
                border-color: {color};
            }}
            QLabel {{
                border: none;
                background: transparent;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(Spacing.MD + 4, Spacing.MD, Spacing.MD, Spacing.MD)
        layout.setSpacing(Spacing.XS)

        # Title row (with optional emoji icon)
        display_title = f"{icon}  {title}" if icon else title
        self.title_lbl = QLabel(display_title)
        self.title_lbl.setStyleSheet(f"""
            font-size: {Fonts.BODY_SM}px;
            color: {Colors.TEXT_SECONDARY};
            font-weight: 600;
        """)

        self.value_lbl = QLabel(str(value))
        self.value_lbl.setStyleSheet(f"""
            font-size: 28px;
            font-weight: bold;
            color: {color};
        """)

        layout.addWidget(self.title_lbl)
        layout.addWidget(self.value_lbl)

    def set_value(self, value) -> None:
        self.value_lbl.setText(str(value))
