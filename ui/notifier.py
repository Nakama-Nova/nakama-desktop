"""
ui/notifier.py

Desktop notifications: every minute the PC asks the server what is new (website orders,
money received, stock running low, finished 3D scans). New things show as a Windows
pop-up when the window is not in front, add to the count on the 🔔 button, and are kept
in a list you can open. Clicking a pop-up or a list entry opens the screen it is about.
"""

from pathlib import Path

from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
)

from services import notifications_service as ns
from ui.theme import Colors, Theme

POLL_EVERY_MS = 60_000
FIRST_POLL_MS = 3_000


class _PollThread(QThread):
    got = pyqtSignal(object)

    def __init__(self, service: ns.NotificationsService, since):
        super().__init__()
        self._service, self._since = service, since

    def run(self):
        try:
            self.got.emit(self._service.fetch(self._since))
        except Exception:
            pass  # offline, signed out or not allowed: try again next minute, say nothing


class Notifier(QObject):
    AUTOSTART = True  # tests switch it off

    changed = pyqtSignal()  # the unread count or the list changed
    open_screen = pyqtSignal(str)  # a notification asked for this screen ("orders", "stock", ...)

    def __init__(self, window, service=None, state_path: Path | None = None):
        super().__init__(window)
        self._window = window
        self._service = service or ns.NotificationsService()
        self._state_path = state_path
        self.state = ns.load_state(state_path)
        self._thread: _PollThread | None = None
        self._tray: QSystemTrayIcon | None = None
        self._tray_target = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)

    # ------------------------------------------------------------ polling
    def start(self):
        if not self.AUTOSTART:
            return
        self._timer.start(POLL_EVERY_MS)
        QTimer.singleShot(FIRST_POLL_MS, self.poll)

    def stop(self):
        self._timer.stop()

    def poll(self):
        if self._thread is not None and self._thread.isRunning():
            return
        self._thread = _PollThread(self._service, self.state["since"])
        self._thread.got.connect(self.receive)
        self._thread.start()

    def receive(self, feed: dict):
        """A server answer arrived (on the screen's thread)."""
        new = ns.absorb(self.state, feed)
        ns.save_state(self.state, self._state_path)
        if new:
            self._announce(new)
        self.changed.emit()

    # ------------------------------------------------------------ showing
    def _announce(self, new: list[dict]):
        title, body = ns.popup_text(new)
        if self._window.isActiveWindow():
            self._window.statusBar().showMessage(title, 8000)  # they are looking at the app already
            return
        if not self.state["popups"] or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if self._tray is None:
            icon = QApplication.windowIcon()
            if icon.isNull():
                icon = self._window.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
            self._tray = QSystemTrayIcon(icon, self)
            self._tray.setToolTip("Vriksha Studio")
            self._tray.messageClicked.connect(self._clicked)
            self._tray.show()
        self._tray_target = new[0]["screen"] if len(new) == 1 else None
        self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Information, 10_000)

    def _clicked(self):
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()
        if self._tray_target:
            self.open_screen.emit(self._tray_target)
        else:
            self.show_list()

    # --------------------------------------------------------------- the list
    @property
    def unread(self) -> int:
        return self.state["unread"]

    def mark_read(self):
        if self.state["unread"]:
            self.state["unread"] = 0
            ns.save_state(self.state, self._state_path)
            self.changed.emit()

    def set_popups(self, on: bool):
        self.state["popups"] = bool(on)
        ns.save_state(self.state, self._state_path)

    def show_list(self):
        dialog = NotificationsDialog(self._window, self)
        self.mark_read()
        dialog.exec()


class NotificationsDialog(QDialog):
    def __init__(self, parent, notifier: Notifier):
        super().__init__(parent)
        self._notifier = notifier
        self.setWindowTitle("Notifications")
        self.setMinimumSize(460, 420)
        self.setStyleSheet(f"background-color: {Colors.BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        self.empty = QLabel("Nothing new yet. Website orders, money received, low stock and finished 3D scans show here.")
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        root.addWidget(self.empty)
        self.list = QListWidget()
        self.list.setStyleSheet(Theme.table_style())
        self.list.itemActivated.connect(self._open)
        root.addWidget(self.list)
        recent = notifier.state["recent"]
        self.empty.setVisible(not recent)
        for n in recent:
            entry = QListWidgetItem(f"{n['title']}\n{n['body']}   ·   {ns.local_time(n['created_at'])}")
            entry.setData(Qt.ItemDataRole.UserRole, n["screen"])
            self.list.addItem(entry)
        self.popups = QCheckBox("Show a pop-up when something new comes in and the window is not in front")
        self.popups.setChecked(notifier.state["popups"])
        self.popups.toggled.connect(notifier.set_popups)
        root.addWidget(self.popups)
        close = QPushButton("Close")
        close.setStyleSheet(Theme.btn_secondary())
        close.clicked.connect(self.accept)
        root.addWidget(close)

    def _open(self, entry: QListWidgetItem):
        self._notifier.open_screen.emit(entry.data(Qt.ItemDataRole.UserRole))
        self.accept()
