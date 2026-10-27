"""
ui/updater.py

Tells the user when a newer version is published and installs it on request:
a banner at the top of the window, a Windows notification when the window is
not in front, and an "Update now" button that downloads, checks and runs the
installer (which restarts the app). Nothing is installed without a click.
"""

from PyQt6.QtCore import QObject, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
)

from services import update_service as svc
from services.version import APP_VERSION, is_release_build
from ui.theme import Colors, Theme

FIRST_CHECK_MS = 8_000  # shortly after start, once the screens have loaded
CHECK_EVERY_MS = 6 * 60 * 60 * 1000


class _CheckThread(QThread):
    done = pyqtSignal(object, str)  # UpdateInfo or None, error text

    def run(self):
        try:
            self.done.emit(svc.check_for_update(), "")
        except svc.UpdateError as e:
            self.done.emit(None, str(e))


class _DownloadThread(QThread):
    progress = pyqtSignal(int, int)
    ready = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, info):
        super().__init__()
        self._info = info
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            path = svc.download_installer(
                self._info, progress=self.progress.emit, cancelled=lambda: self._cancel
            )
            self.ready.emit(path)
        except svc.UpdateError as e:
            self.failed.emit(str(e))


class UpdateBanner(QFrame):
    """The strip above the screens: 'Version 1.2.0 is available. [Update now] [Later]'."""

    update_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setStyleSheet(
            f"QFrame {{ background-color: {Colors.WARNING_BG}; border-bottom: 1px solid {Colors.BRAND_GOLD}; }}"
            f"QLabel {{ color: {Colors.BRAND_BROWN}; font-weight: 600; background: transparent; border: none; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 8, 20, 8)
        self.text = QLabel("")
        row.addWidget(self.text)
        row.addStretch()
        self.update_btn = QPushButton("⬆  Update now")
        self.update_btn.setStyleSheet(Theme.btn_primary())
        self.update_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.update_btn.clicked.connect(self.update_clicked.emit)
        later = QPushButton("Later")
        later.setStyleSheet(Theme.btn_secondary())
        later.clicked.connect(self.hide)
        row.addWidget(self.update_btn)
        row.addWidget(later)
        self.hide()

    def show_update(self, info) -> None:
        self.text.setText(f"A new version ({info.version}) is available. You are on {APP_VERSION}.")
        self.text.setToolTip(info.notes or "")
        self.show()


class Updater(QObject):
    """Owns the checks and the install. `quit_app` is replaceable for tests."""

    def __init__(self, window, banner: UpdateBanner, quit_app=None):
        super().__init__(window)
        self._window = window
        self._banner = banner
        self._quit = quit_app or QApplication.quit
        self._info = None
        self._check_thread = None
        self._download = None
        self._shown_for: str | None = None
        banner.update_clicked.connect(self.install)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check)

    # ----- starting
    def start(self) -> None:
        """Begin the background checks (installed release builds only)."""
        if not is_release_build():
            return
        QTimer.singleShot(FIRST_CHECK_MS, self.check)
        self._timer.start(CHECK_EVERY_MS)

    # ----- checking
    def check(self, manual: bool = False) -> None:
        if self._check_thread and self._check_thread.isRunning():
            return
        if manual and not is_release_build():
            QMessageBox.information(
                self._window,
                "Updates",
                "This is a development copy. Updates are for the installed program.",
            )
            return
        self._check_thread = _CheckThread()
        self._check_thread.done.connect(lambda info, err: self._checked(info, err, manual))
        self._check_thread.start()

    def _checked(self, info, error: str, manual: bool) -> None:
        if error:
            if manual:
                QMessageBox.warning(self._window, "Updates", error)
            return
        if info is None:
            if manual:
                QMessageBox.information(self._window, "Updates", f"You are up to date (version {APP_VERSION}).")
            return
        self._info = info
        self._banner.show_update(info)
        if self._shown_for != info.version:  # tell Windows once per version
            self._shown_for = info.version
            self._notify(info)

    def _notify(self, info) -> None:
        """A Windows notification, useful when the window is behind other programs."""
        if self._window.isActiveWindow() or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(
            QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), self._window
        )
        tray.messageClicked.connect(self._window.raise_)
        tray.show()
        tray.showMessage(
            "Vriksha Studio: update available",
            f"Version {info.version} is ready to install. Open the app and press Update now.",
        )
        QTimer.singleShot(15_000, tray.hide)

    # ----- installing
    def install(self) -> None:
        info = self._info
        if not info or (self._download and self._download.isRunning()):
            return
        ask = QMessageBox.question(
            self._window,
            "Update",
            f"Install version {info.version} now?\n\nThe app will close for about a minute and open again by itself."
            " Finish any bill you are working on first.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ask != QMessageBox.StandardButton.Yes:
            return
        dialog = QProgressDialog("Downloading the update...", "Cancel", 0, 100, self._window)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setAutoClose(False)
        dialog.setMinimumDuration(0)
        self._download = _DownloadThread(info)
        self._download.progress.connect(lambda done, total: dialog.setValue(int(100 * done / total) if total else 0))
        self._download.ready.connect(lambda path: self._downloaded(path, dialog))
        self._download.failed.connect(lambda msg: self._failed(msg, dialog))
        dialog.canceled.connect(self._download.cancel)
        self._download.start()

    def _downloaded(self, path: str, dialog) -> None:
        dialog.close()
        try:
            svc.launch_installer(path)
        except OSError:
            QMessageBox.warning(self._window, "Update", "The installer could not be started.")
            return
        self._quit()

    def _failed(self, message: str, dialog) -> None:
        dialog.close()
        if "cancelled" not in message:
            QMessageBox.warning(self._window, "Update", message)
