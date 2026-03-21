"""
ui/attendance_screen.py

Workforce/Attendance screen. Simple UI for Check In / Check Out.
"""

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QComboBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from datetime import datetime

from ui.theme import Theme, Colors, Fonts
from services.workforce_service import AttendanceService
from services.session import Session
from services.enums import UserRole
from ui.errors import handle_permissions


class AttendanceScreen(QWidget):
    def __init__(self):
        super().__init__()
        self._service = AttendanceService()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Header
        header = QLabel("👷 Workforce & Attendance")
        header.setStyleSheet(f"font-size: 24px; font-weight: bold; color: {Colors.TEXT_PRIMARY};")
        layout.addWidget(header)

        # Action Bar (Check In / Check Out)
        self.action_card = QWidget()
        self.action_card.setStyleSheet(f"background-color: {Colors.CARD_BG}; border-radius: 12px; border: 1px solid {Colors.CARD_BORDER};")
        action_layout = QHBoxLayout(self.action_card)
        action_layout.setContentsMargins(20, 20, 20, 20)

        role = Session.get_role()
        is_admin = role in [UserRole.OWNER, UserRole.MANAGER, UserRole.SALES]

        if is_admin:
            action_layout.addWidget(QLabel("Select Worker:"))
            self.user_combo = QComboBox()
            self.user_combo.setFixedWidth(200)
            action_layout.addWidget(self.user_combo)
            
            self.btn_check_in = QPushButton("✅ Check In")
            self.btn_check_in.clicked.connect(self._handle_check_in)
            action_layout.addWidget(self.btn_check_in)
        else:
            action_layout.addWidget(QLabel("Your daily attendance tracking area."))
            action_layout.addStretch()

        self.btn_check_out = QPushButton("🚪 Check Out")
        self.btn_check_out.clicked.connect(self._handle_check_out)
        self.btn_check_out.setEnabled(False) # Enabled if an open record exists
        action_layout.addWidget(self.btn_check_out)

        layout.addWidget(self.action_card)

        # History Table
        layout.addWidget(QLabel("Recent Attendance History"))
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Date", "User", "Check In", "Check Out", "Hours", "Wage"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.refresh_data()

    @handle_permissions
    def refresh_data(self):
        role = Session.get_role()
        is_admin = role in [UserRole.OWNER, UserRole.MANAGER, UserRole.SALES]

        # 1. Load users if admin
        if is_admin:
            users = self._service.get_users()
            self.user_combo.clear()
            for u in users:
                self.user_combo.addItem(u.get("full_name") or u.get("username"), u.get("id"))

        # 2. Load attendance history
        if is_admin:
            records = self._service.get_all_attendance()
        else:
            records = self._service.get_my_attendance()

        self.table.setRowCount(len(records))
        open_record_id = None

        for i, r in enumerate(records):
            status = r.get("status")
            check_in = r.get("check_in")
            check_out = r.get("check_out")
            
            # Formatting
            date_str = r.get("date", "")
            user_str = r.get("user", {}).get("full_name") or "User"
            in_str = datetime.fromisoformat(check_in).strftime("%H:%M") if check_in else "-"
            out_str = datetime.fromisoformat(check_out).strftime("%H:%M") if check_out else "-"
            hours = str(r.get("total_hours", "0.00"))
            
            # Wage extraction (check nested DailyWage response)
            wage_data = r.get("wage_entry") or {}
            wage = str(wage_data.get("amount", "0.00"))

            self.table.setItem(i, 0, QTableWidgetItem(date_str))
            self.table.setItem(i, 1, QTableWidgetItem(user_str))
            self.table.setItem(i, 2, QTableWidgetItem(in_str))
            self.table.setItem(i, 3, QTableWidgetItem(out_str))
            self.table.setItem(i, 4, QTableWidgetItem(hours))
            self.table.setItem(i, 5, QTableWidgetItem(f"₹{wage}"))

            # Check for today's open record for the logged in user or selected user
            if not check_out:
                 # In a real app, logic would be more complex to match current selection
                 # For now, let's enable check-out if ANY open record exists (simple)
                 open_record_id = r.get("id")

        if open_record_id:
            self.btn_check_out.setEnabled(True)
            self._current_attendance_id = open_record_id
        else:
            self.btn_check_out.setEnabled(False)

    @handle_permissions
    def _handle_check_in(self):
        user_id = self.user_combo.currentData()
        if not user_id:
            return
        
        result = self._service.check_in(user_id)
        if result:
            QMessageBox.information(self, "Success", "Worker checked in successfully.")
            self.refresh_data()

    @handle_permissions
    def _handle_check_out(self):
        if not hasattr(self, "_current_attendance_id"):
            return
        
        result = self._service.check_out(self._current_attendance_id)
        if result:
            QMessageBox.information(self, "Success", f"Checked out. Hours: {result.get('total_hours')}")
            self.refresh_data()
