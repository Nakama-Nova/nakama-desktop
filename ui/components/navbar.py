"""
ui/components/navbar.py

The top navbar of the main window: the current page's title with a small breadcrumb on
the left, and whatever the window puts on the right (notifications, who is signed in,
sign out).
"""

from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.theme import Colors, Fonts, Spacing

NAVBAR_HEIGHT = 64


class Navbar(QFrame):
    def __init__(self, crumb: str = "Vriksha Studio", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("navbar")
        self.setFixedHeight(NAVBAR_HEIGHT)
        self.setStyleSheet(
            f"QFrame#navbar {{ background-color: {Colors.NAVBAR_BG}; border: none;"
            f" border-bottom: 1px solid {Colors.CARD_BORDER}; }}"
            "QFrame#navbar QLabel { background: transparent; border: none; }"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(Spacing.LG, 0, Spacing.LG, 0)
        row.setSpacing(Spacing.SM)

        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addStretch()
        self.crumb_lbl = QLabel(crumb)
        self.crumb_lbl.setStyleSheet(f"font-size: {Fonts.CAPTION}px; color: {Colors.TEXT_MUTED};")
        self.title_lbl = QLabel("")
        self.title_lbl.setStyleSheet(
            f"font-size: {Fonts.HEADING_MD + 2}px; font-weight: 600; color: {Colors.TEXT_PRIMARY};"
        )
        titles.addWidget(self.crumb_lbl)
        titles.addWidget(self.title_lbl)
        titles.addStretch()
        row.addLayout(titles)
        row.addStretch()
        self.right = row

    def set_title(self, text: str) -> None:
        self.title_lbl.setText(text)

    def add_right(self, widget: QWidget) -> None:
        self.right.addWidget(widget)
