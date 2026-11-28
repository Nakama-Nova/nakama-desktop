"""
ui/settings_dialog.py

Settings for this computer: the server address (with a connection test), how a new bill starts,
whether a bill's PDF opens by itself, notifications, updates, and where the data is kept.
Opened from the account menu or with Ctrl+, and saved with one button.

The server address is read from .env when the program starts, so changing it asks for a restart
and says so; the other settings take effect when saved.
"""

from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from services import app_settings
from services.api_client import APIClient, BASE_URL
from services.sales_service import SalesService
from services.version import APP_VERSION, is_release_build
from ui.icons import IconButton
from ui.theme import Colors, Fonts, Spacing, Theme

PAYMENT_CHOICES = (("Cash", "cash"), ("Not paid yet", "none"))


def _section(title: str) -> QLabel:
    lbl = QLabel(title)
    lbl.setStyleSheet(Theme.subheading())
    return lbl


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"font-size: {Fonts.BODY_SM}px; color: {Colors.TEXT_MUTED};")
    return lbl


def _rule() -> QFrame:
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background: {Colors.CARD_BORDER}; border: none;")
    return line


class SettingsDialog(QDialog):
    def __init__(self, parent=None, notifier=None, updater=None):
        super().__init__(parent)
        self._notifier, self._updater = notifier, updater
        self.setWindowTitle("Settings")
        self.setMinimumWidth(660)
        self.setStyleSheet(
            f"QDialog {{ background: {Colors.BG}; }}"
            f" * {{ font-family: '{Fonts.FAMILY}', 'Segoe UI'; }}"
            f" QLabel, QCheckBox {{ background: transparent; font-size: {Fonts.BODY}px; }}"
        )
        self.restart_needed = False

        root = QVBoxLayout(self)
        root.setContentsMargins(Spacing.XL, Spacing.LG, Spacing.XL, Spacing.LG)
        root.setSpacing(Spacing.SM)

        title = QLabel("Settings")
        title.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        root.addWidget(title)
        root.addWidget(_hint("These are for this computer only. Nothing here changes the shop's data."))

        values = app_settings.load()

        # ── Server ──
        root.addWidget(_section("Server"))
        self.server = QLineEdit(app_settings.read_server_address(BASE_URL))
        self.server.setPlaceholderText("https://your-server.example.com")
        self.server.setStyleSheet(Theme.input_style())
        self.server.textChanged.connect(self._server_edited)
        row = QHBoxLayout()
        row.addWidget(self.server, 1)
        self.test_btn = IconButton("Test connection")
        self.test_btn.setStyleSheet(Theme.btn("secondary", "md", outline=True))
        self.test_btn.clicked.connect(self._test_connection)
        row.addWidget(self.test_btn)
        root.addLayout(row)
        self.server_note = _hint("")
        root.addWidget(self.server_note)
        self._server_edited(self.server.text())

        root.addWidget(_rule())

        # ── Appearance ──
        root.addWidget(_section("Appearance"))
        look = QFormLayout()
        look.setHorizontalSpacing(Spacing.LG)
        self.theme = QComboBox()
        self.theme.addItem("Light", "light")
        self.theme.addItem("Dark", "dark")
        self.theme.addItem("Heritage glass", "glass")
        self.theme.setCurrentIndex(max(0, self.theme.findData(values["theme"])))
        self.theme.setStyleSheet(Theme.input_style())
        look.addRow(QLabel("Colours", styleSheet=Theme.label()), self.theme)
        root.addLayout(look)
        root.addWidget(_hint("The new look is used the next time the program starts."))

        root.addWidget(_rule())

        # ── New bills ──
        root.addWidget(_section("New bills"))
        form = QFormLayout()
        form.setHorizontalSpacing(Spacing.LG)
        self.payment = QComboBox()
        for label, value in PAYMENT_CHOICES:
            self.payment.addItem(label, value)
        self.payment.setCurrentIndex(max(0, self.payment.findData(values["default_payment"])))
        self.payment.setStyleSheet(Theme.input_style())
        form.addRow(QLabel("Paid by starts as", styleSheet=Theme.label()), self.payment)
        root.addLayout(form)
        self.open_pdf = QCheckBox("Open the bill's PDF as soon as it is created")
        self.open_pdf.setChecked(values["open_bill_pdf"])
        root.addWidget(self.open_pdf)
        root.addWidget(_hint("Either way, the PDF is kept and can be opened again from Bill History."))

        root.addWidget(_rule())

        # ── Notifications ──
        root.addWidget(_section("Notifications"))
        self.popups = QCheckBox("Show a Windows notification when the program is in the background")
        popups_on = bool(notifier.state.get("popups", True)) if notifier is not None else True
        self.popups.setChecked(popups_on)
        self.popups.setEnabled(notifier is not None)
        root.addWidget(self.popups)

        root.addWidget(_rule())

        # ── Updates ──
        root.addWidget(_section("Updates"))
        self.auto_updates = QCheckBox("Check for a newer version in the background")
        installed = is_release_build()
        self.auto_updates.setChecked(values["auto_updates"])
        self.auto_updates.setEnabled(installed)
        root.addWidget(self.auto_updates)
        update_row = QHBoxLayout()
        self.check_btn = IconButton("Check now")
        self.check_btn.setStyleSheet(Theme.btn("secondary", "sm", outline=True))
        self.check_btn.setEnabled(updater is not None)
        self.check_btn.clicked.connect(lambda: updater.check(manual=True))
        update_row.addWidget(self.check_btn)
        update_row.addWidget(_hint("Nothing installs without your click." if installed else "This is a development copy; updates are for the installed program."), 1)
        root.addLayout(update_row)

        root.addWidget(_rule())

        # ── About ──
        root.addWidget(_section("About"))
        self.version_lbl = QLabel(f"Version {APP_VERSION}" + ("" if installed else "  (development copy)"))
        root.addWidget(self.version_lbl)
        self.data_dir = Path("data").resolve()
        self.bills_dir = SalesService.INVOICE_DIR
        for label, folder in (("Data and settings", self.data_dir), ("Saved bills", self.bills_dir)):
            line = QHBoxLayout()
            name = QLabel(f"{label}:")
            name.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
            name.setFixedWidth(130)
            path = QLabel(str(folder))
            path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            path.setStyleSheet(f"font-size: {Fonts.BODY_SM}px; color: {Colors.TEXT_PRIMARY};")
            path.setToolTip(str(folder))
            open_btn = IconButton("Open folder")
            open_btn.setStyleSheet(Theme.btn("secondary", "sm", outline=True))
            open_btn.clicked.connect(lambda _=False, f=folder: self._open_folder(f))
            line.addWidget(name)
            line.addWidget(path, 1)
            line.addWidget(open_btn)
            root.addLayout(line)

        # ── Buttons ──
        root.addSpacing(Spacing.SM)
        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = IconButton("Cancel")
        cancel.setStyleSheet(Theme.btn("secondary", "md", outline=True))
        cancel.clicked.connect(self.reject)
        self.save_btn = IconButton("Save settings")
        self.save_btn.setStyleSheet(Theme.btn("primary", "md"))
        self.save_btn.clicked.connect(self._save)
        self.save_btn.setDefault(True)
        buttons.addWidget(cancel)
        buttons.addWidget(self.save_btn)
        root.addLayout(buttons)

    # ------------------------------------------------------------------ server
    def _server_edited(self, text: str) -> None:
        clean = app_settings.clean_server_address(text)
        if not text.strip():
            note, colour = "Enter the address of your server.", Colors.TEXT_MUTED
        elif clean is None:
            note, colour = "The address must start with http:// or https://", Colors.RED
        elif app_settings.is_unencrypted_remote(clean):
            note, colour = "This address is not encrypted (http://). Passwords and bills could be seen on the network.", Colors.ORANGE
        else:
            note, colour = "Changing the address takes effect after you restart the program.", Colors.TEXT_MUTED
        self.server_note.setText(note)
        self.server_note.setStyleSheet(f"font-size: {Fonts.BODY_SM}px; color: {colour};")

    def _test_connection(self) -> None:
        clean = app_settings.clean_server_address(self.server.text())
        if clean is None:
            QMessageBox.warning(self, "Test connection", "Enter an address that starts with http:// or https:// first.")
            return
        self.test_btn.setEnabled(False)
        self.test_btn.setText("Testing…")
        try:
            ok = APIClient(base_url=clean).health_check()
        finally:
            self.test_btn.setEnabled(True)
            self.test_btn.setText("Test connection")
        if ok:
            QMessageBox.information(self, "Test connection", f"Connected to {clean}.")
        else:
            QMessageBox.warning(
                self,
                "Test connection",
                f"Could not reach {clean}.\n\nCheck the address, and that this computer is online.",
            )

    # ------------------------------------------------------------------ folders
    @staticmethod
    def _open_folder(folder: Path) -> None:
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    # ------------------------------------------------------------------ saving
    def collect(self) -> dict:
        return {
            "default_payment": self.payment.currentData(),
            "open_bill_pdf": self.open_pdf.isChecked(),
            "auto_updates": self.auto_updates.isChecked(),
            "theme": self.theme.currentData(),
        }

    def _save(self) -> None:
        address = self.server.text().strip()
        changed_server = False
        if address:
            clean = app_settings.clean_server_address(address)
            if clean is None:
                QMessageBox.warning(self, "Settings", "The server address must start with http:// or https://")
                return
            changed_server = clean != app_settings.read_server_address(BASE_URL).rstrip("/")
        theme_changed = self.theme.currentData() != app_settings.get("theme")
        try:
            app_settings.save(self.collect())
            if changed_server:
                app_settings.write_server_address(address)
        except OSError as exc:
            QMessageBox.critical(
                self, "Settings", f"The settings could not be saved: {exc.strerror or exc}\n\nFolder: {self.data_dir}"
            )
            return
        if self._notifier is not None:
            self._notifier.set_popups(self.popups.isChecked())
        if self._updater is not None:
            self._updater.set_automatic(self.auto_updates.isChecked())
        self.restart_needed = changed_server or theme_changed
        if self.restart_needed:
            what = " and ".join(
                [w for w, on in (("server address", changed_server), ("look", theme_changed)) if on]
            )
            QMessageBox.information(
                self,
                "Restart to apply",
                f"The new {what} {'is' if not (changed_server and theme_changed) else 'are'} used the next time the program starts. "
                "Close it and open it again.",
            )
        self.accept()
