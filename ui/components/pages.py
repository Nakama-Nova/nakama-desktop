"""
ui/components/pages.py

The window's stack of screens, where a screen that does not fit scrolls instead of being cut off.

A screen is laid out for the room it needs. In a window or on a screen smaller than that, the
part that does not fit used to be clipped with no way to reach it (on a 1366x768 laptop, New
Bill's Create button was below the visible area). Each screen now sits in a scroll area that
shows a scroll bar only when the screen's own minimum size is bigger than the space it has;
otherwise it fills the space exactly as before.

The stack still hands out the screens themselves: widget(i) and currentWidget() return the
screen, not the scroll area around it, so the code that refreshes or searches the current screen
did not need to change.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QScrollArea, QStackedWidget, QWidget

from ui.theme import Colors


class ScrollingPages(QStackedWidget):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._pages: list[QWidget] = []

    def addWidget(self, page: QWidget) -> int:
        scroll = QScrollArea()
        scroll.setObjectName("pageScroll")
        scroll.setWidgetResizable(True)  # the screen fills the area, and grows past it only when it must
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"QScrollArea#pageScroll {{ background: {Colors.BG}; border: none; }}")
        scroll.setWidget(page)
        self._pages.append(page)
        return super().addWidget(scroll)

    def widget(self, index: int) -> QWidget | None:
        return self._pages[index] if 0 <= index < len(self._pages) else None

    def currentWidget(self) -> QWidget | None:
        return self.widget(self.currentIndex())

    def indexOf(self, page: QWidget) -> int:
        return self._pages.index(page) if page in self._pages else -1

    def setCurrentWidget(self, page: QWidget) -> None:
        index = self.indexOf(page)
        if index >= 0:
            self.setCurrentIndex(index)
