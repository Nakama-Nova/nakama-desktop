from PyQt6.QtWidgets import (
    QWidget, QLabel, QLineEdit, QPushButton,
    QVBoxLayout, QMessageBox
)

from services.auth_service import login
from ui.main_window import MainWindow

class LoginWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Nakama Desktop Login")
        self.setGeometry(500, 300, 300, 200)

        layout = QVBoxLayout()

        self.username = QLineEdit()
        self.username.setPlaceholderText("Username")

        self.password = QLineEdit()
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)

        self.button = QPushButton("Login")
        self.button.clicked.connect(self.handle_login)

        layout.addWidget(QLabel("Login"))
        layout.addWidget(self.username)
        layout.addWidget(self.password)
        layout.addWidget(self.button)

        self.setLayout(layout)

    def handle_login(self):
        username = self.username.text()
        password = self.password.text()

        result = login(username, password)

        if result:
            self.main_window = MainWindow()
            self.main_window.show()
            self.close()
        else:
            QMessageBox.warning(self, "Error", "Invalid credentials")