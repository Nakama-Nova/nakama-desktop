import sys
from PyQt6.QtWidgets import QApplication
from ui.login_window import LoginWindow
from ui.theme import Theme


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(Theme.global_stylesheet())

    window = LoginWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()