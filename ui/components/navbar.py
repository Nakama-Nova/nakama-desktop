"""
ui/components/navbar.py

The top bar of the main window. The page's own heading says where you are, so the bar does
not repeat it. It carries what belongs to the whole desk instead: a quick "Go to" search
(Ctrl+K), whether the server is reachable (and how many bills are waiting to send), the
notifications bell, and the account menu (change password, sign out).
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QWidget,
)

from ui.theme import Colors, Fonts, Radius, Spacing, shade, tint

NAVBAR_HEIGHT = 52


def connection_text(online: bool, waiting: int) -> str:
    """What the connection chip says. Offline is reassuring: nothing waiting is lost."""
    if online:
        return "Online" if not waiting else f"Online, sending {waiting} bill{'s' if waiting != 1 else ''}"
    if waiting:
        return f"Offline, {waiting} bill{'s' if waiting != 1 else ''} waiting to send"
    return "Offline, bills are kept on this PC"


class Navbar(QFrame):
    goto_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("navbar")
        self.setFixedHeight(NAVBAR_HEIGHT)
        self.title = ""  # the current page; shown as the page's own heading, not here
        self.setStyleSheet(
            f"QFrame#navbar {{ background-color: {Colors.NAVBAR_BG}; border: none;"
            f" border-bottom: 1px solid {Colors.CARD_BORDER}; }}"
            "QFrame#navbar QLabel { background: transparent; border: none; }"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(Spacing.LG, 0, Spacing.LG, 0)
        row.setSpacing(Spacing.SM + 2)

        self.goto_btn = QPushButton("  Go to a screen…   (Ctrl+K)")
        self.goto_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.goto_btn.setToolTip("Jump to any screen (Ctrl+K)")
        self.goto_btn.setFixedWidth(280)
        self.goto_btn.setStyleSheet(
            f"QPushButton {{ background: {Colors.BG}; color: {Colors.TEXT_MUTED};"
            f" border: 1px solid {Colors.CARD_BORDER}; border-radius: {Radius.MD}px;"
            f" padding: 6px 12px; text-align: left; font-size: {Fonts.BODY}px; }}"
            f"QPushButton:hover {{ border-color: {Colors.BRAND_GOLD}; color: {Colors.TEXT_PRIMARY}; }}"
        )
        self.goto_btn.clicked.connect(self.goto_requested)
        row.addWidget(self.goto_btn)
        row.addStretch()

        self.busy_lbl = QLabel("Loading…")
        self.busy_lbl.setStyleSheet(f"font-size: {Fonts.CAPTION}px; color: {Colors.TEXT_MUTED};")
        self.busy_lbl.hide()
        row.addWidget(self.busy_lbl)

        self.conn_lbl = QLabel("")
        self.conn_lbl.setToolTip("Bills made while offline wait on this PC and send themselves when the server is back.")
        self.conn_lbl.setFixedHeight(24)
        row.addWidget(self.conn_lbl, 0, Qt.AlignmentFlag.AlignVCenter)
        self.set_connection(True, 0)
        self.right = row

    def set_title(self, text: str) -> None:
        self.title = text

    def set_busy(self, busy: bool) -> None:
        self.busy_lbl.setVisible(busy)

    def set_connection(self, online: bool, waiting: int) -> None:
        base = Colors.SUCCESS if online and not waiting else Colors.ORANGE
        self.conn_lbl.setText("●  " + connection_text(online, waiting))
        self.conn_lbl.setStyleSheet(
            f"font-size: {Fonts.CAPTION + 1}px; font-weight: 600; color: {shade(base, 0.25)};"
            f" background: {tint(base, 0.88)}; border-radius: 11px; padding: 3px 10px;"
        )

    def add_right(self, widget: QWidget) -> None:
        self.right.addWidget(widget)

    def make_account_button(self, role_text: str, on_password, on_sign_out) -> QToolButton:
        """The signed-in person's menu: their role, change password, sign out."""
        btn = QToolButton()
        btn.setText(role_text)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        btn.setStyleSheet(
            f"QToolButton {{ background: {Colors.CARD_BG}; color: {Colors.TEXT_PRIMARY};"
            f" border: 1px solid {Colors.CARD_BORDER}; border-radius: 15px; padding: 5px 14px;"
            f" font-size: {Fonts.BODY}px; font-weight: 600; }}"
            f"QToolButton:hover {{ border-color: {Colors.BRAND_GOLD}; }}"
            "QToolButton::menu-indicator { image: none; }"
        )
        menu = QMenu(btn)
        menu.addAction("Change my password", on_password)
        menu.addSeparator()
        menu.addAction("Sign out", on_sign_out)
        btn.setMenu(menu)
        self.account_menu = menu
        return btn
