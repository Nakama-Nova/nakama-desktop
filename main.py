import sys
from PyQt6.QtWidgets import QApplication, QMessageBox
from ui.login_window import LoginWindow
from ui.theme import Theme
from services.api_client import ForbiddenError, APIError
from services.session import Session


def exception_hook(exctype, value, traceback):
    """Global handler for unhandled exceptions."""
    if issubclass(exctype, ForbiddenError):
        QMessageBox.warning(None, "Permission Denied 🛡️", str(value))
    elif issubclass(exctype, APIError):
        QMessageBox.critical(None, "Server Error ❌", str(value))
    else:
        sys.__excepthook__(exctype, value, traceback)


def main():
    sys.excepthook = exception_hook

    app = QApplication(sys.argv)
    app.setStyleSheet(Theme.global_stylesheet())

    if Session.restore():
        from ui.main_window import MainWindow

        window = MainWindow()
    else:
        window = LoginWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
