from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QStackedWidget, QLabel
)
from PyQt6.QtCore import Qt

from ui.dashboard_window import DashboardWindow
from ui.inventory_window import InventoryWindow
from ui.sales_screen import SalesScreen

class PlaceholderWindow(QWidget):
    def __init__(self, title):
        super().__init__()
        layout = QVBoxLayout()
        label = QLabel(title)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        self.setLayout(layout)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Nakama Furniture ERP")
        self.resize(1000, 600)

        # Main widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar setup
        self.sidebar = QWidget()
        self.sidebar.setFixedWidth(200)
        self.sidebar.setStyleSheet("background-color: #2c3e50; color: white;")
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(10, 20, 10, 20)
        sidebar_layout.setSpacing(10)

        main_layout.addWidget(self.sidebar)

        # Stacked widget for main content
        self.content_stack = QStackedWidget()
        main_layout.addWidget(self.content_stack)

        # Initialize screens (Screens act as reusable components)
        self.dashboard_view = DashboardWindow()
        self.inventory_view = InventoryWindow()
        self.sales_view = SalesScreen()
        self.purchases_view = PlaceholderWindow("Purchases Screen (Coming Soon)")

        # Add screens to stack
        self.content_stack.addWidget(self.dashboard_view)
        self.content_stack.addWidget(self.inventory_view)
        self.content_stack.addWidget(self.sales_view)
        self.content_stack.addWidget(self.purchases_view)

        # Navigation buttons
        self.btn_dashboard = self._create_nav_button("Dashboard", 0)
        self.btn_inventory = self._create_nav_button("Inventory", 1)
        self.btn_sales = self._create_nav_button("Sales", 2)
        self.btn_purchases = self._create_nav_button("Purchases", 3)

        sidebar_layout.addWidget(self.btn_dashboard)
        sidebar_layout.addWidget(self.btn_inventory)
        sidebar_layout.addWidget(self.btn_sales)
        sidebar_layout.addWidget(self.btn_purchases)
        sidebar_layout.addStretch()

        # Set default view
        self.content_stack.setCurrentIndex(0)

    def _create_nav_button(self, text, index):
        btn = QPushButton(text)
        btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                padding: 10px;
                text-align: left;
                font-size: 14px;
                color: white;
            }
            QPushButton:hover {
                background-color: #34495e;
            }
        """)
        btn.clicked.connect(lambda _, idx=index: self.content_stack.setCurrentIndex(idx))
        return btn
