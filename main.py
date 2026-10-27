import os
import sys

import requests
from pathlib import Path

# Installed build: the program folder may be read-only, so keep the local database,
# invoices and the .env (server address) in the user's own folder. Must run before
# the imports below, which read ./.env and ./data when they load.
if getattr(sys, "frozen", False):
    _home = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "VrikshaStudios"
    _home.mkdir(parents=True, exist_ok=True)
    os.chdir(_home)

from PyQt6.QtWidgets import QApplication, QMessageBox
from ui.login_window import LoginWindow
from ui.fonts import load_brand_fonts
from ui.theme import Theme
from services.api_client import APIClient, ForbiddenError, APIError, SessionExpiredError
from services.session import Session


def exception_hook(exctype, value, traceback):
    """Global handler for unhandled exceptions."""
    if issubclass(exctype, SessionExpiredError):
        return  # already reported: the user was signed out with an explanation
    if issubclass(exctype, requests.Timeout):
        QMessageBox.warning(
            None,
            "Server not answering",
            "The server is taking too long to answer. Check the connection and try again.",
        )
    elif issubclass(exctype, requests.RequestException):
        QMessageBox.warning(
            None, "No connection", "Cannot reach the server. Check the connection and try again."
        )
    elif issubclass(exctype, ForbiddenError):
        QMessageBox.warning(None, "Permission Denied 🛡️", str(value))
    elif issubclass(exctype, APIError):
        if not value.reported:
            QMessageBox.critical(None, "Server Error ❌", str(value))
    else:
        sys.__excepthook__(exctype, value, traceback)


def main():
    sys.excepthook = exception_hook

    app = QApplication(sys.argv)
    load_brand_fonts()
    app.setStyleSheet(Theme.global_stylesheet())

    # An expired login is kept only when the server is down: the counter still bills
    # offline, and the server turns the stale token away once it is reachable.
    if Session.restore(allow_expired=lambda: not APIClient().health_check()):
        from ui.main_window import MainWindow

        window = MainWindow()
    else:
        window = LoginWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
