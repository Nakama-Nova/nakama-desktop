"""
ui/components/goto_dialog.py

Ctrl+K: type a few letters of a screen's name and press Enter to open it. Lists only the
screens the signed-in person may use (the sidebar's own list).
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

from ui.theme import Colors, Fonts, Radius, Spacing, Theme


class GoToDialog(QDialog):
    def __init__(self, entries: list[tuple[str, int]], parent=None):
        """entries: (screen name, page index) in sidebar order."""
        super().__init__(parent)
        self.setWindowTitle("Go to a screen")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.chosen: int | None = None
        self._entries = entries
        self.setStyleSheet(f"QDialog {{ background: {Colors.CARD_BG}; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(Spacing.LG, Spacing.LG, Spacing.LG, Spacing.LG)
        lay.setSpacing(Spacing.SM)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Type a screen name, for example Stock or Wages")
        self.search.setStyleSheet(Theme.input_style())
        self.search.textChanged.connect(self._filter)
        lay.addWidget(self.search)

        self.list = QListWidget()
        self.list.setStyleSheet(
            f"QListWidget {{ border: 1px solid {Colors.CARD_BORDER}; border-radius: {Radius.MD}px;"
            f" font-size: {Fonts.BODY}px; outline: 0; }}"
            f"QListWidget::item {{ padding: 8px 12px; }}"
            f"QListWidget::item:selected {{ background: {Colors.SIDEBAR_ACTIVE}; color: {Colors.TEXT_PRIMARY}; }}"
        )
        self.list.itemActivated.connect(self._pick)
        self.list.itemClicked.connect(self._pick)
        lay.addWidget(self.list)

        self.empty = QLabel("No screen with that name.")
        self.empty.setStyleSheet(f"color: {Colors.TEXT_MUTED};")
        self.empty.hide()
        lay.addWidget(self.empty)
        self._filter("")
        self.search.setFocus()

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        self.list.clear()
        for name, index in self._entries:
            if needle in name.lower():
                item = QListWidgetItem(name)
                item.setData(Qt.ItemDataRole.UserRole, index)
                self.list.addItem(item)
        self.empty.setVisible(self.list.count() == 0)
        if self.list.count():
            self.list.setCurrentRow(0)

    def _pick(self, item: QListWidgetItem) -> None:
        self.chosen = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.list.currentItem():
            self._pick(self.list.currentItem())
            return
        if event.key() in (Qt.Key.Key_Down, Qt.Key.Key_Up):
            self.list.keyPressEvent(event)
            return
        super().keyPressEvent(event)
