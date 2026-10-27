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
import requests
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
        # user id -> id of that person's attendance record with no check-out yet
        self._open_by_user: dict[str, str] = {}
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
            self.user_combo.currentIndexChanged.connect(self._update_check_out_button)
            action_layout.addWidget(self.user_combo)
            
            self.btn_check_in = QPushButton("✅ Check In")
            self.btn_check_in.clicked.connect(self._handle_check_in)
            action_layout.addWidget(self.btn_check_in)
        else:
            action_layout.addWidget(
                QLabel("Your attendance history. The owner, a manager or the counter records check-in and check-out.")
            )
            action_layout.addStretch()

        self.btn_check_out = QPushButton("🚪 Check Out")
        self.btn_check_out.clicked.connect(self._handle_check_out)
        self.btn_check_out.setEnabled(False)  # Enabled if the selected worker is checked in
        self.btn_check_out.setVisible(is_admin)  # the server refuses it for other roles
        action_layout.addWidget(self.btn_check_out)

        layout.addWidget(self.action_card)

        # History Table
        layout.addWidget(QLabel("Recent Attendance History"))
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Date", "User", "Check In", "Check Out", "Hours", "Wage"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        try:
            self.refresh_data()
        except requests.RequestException:
            # No connection at startup: the main window must still open (the
            # counter can bill offline). The screen reloads when it is visited.
            pass

    @handle_permissions
    def refresh_data(self):
        role = Session.get_role()
        is_admin = role in [UserRole.OWNER, UserRole.MANAGER, UserRole.SALES]

        # 1. Load users if admin (keeping whoever was selected)
        if is_admin:
            users = self._service.get_users()
            selected = self.user_combo.currentData()
            self.user_combo.blockSignals(True)
            self.user_combo.clear()
            for u in users:
                self.user_combo.addItem(u.get("full_name") or u.get("username"), u.get("id"))
            if selected is not None:
                idx = self.user_combo.findData(selected)
                if idx >= 0:
                    self.user_combo.setCurrentIndex(idx)
            self.user_combo.blockSignals(False)

        # 2. Load attendance history
        if is_admin:
            records = self._service.get_all_attendance()
        else:
            records = self._service.get_my_attendance()

        self.table.setRowCount(len(records))
        open_records: dict[str, dict] = {}

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

            # An open record belongs to one person: remember it per user, newest wins
            uid = str(r.get("user_id") or "")
            if not check_out and uid:
                best = open_records.get(uid)
                if best is None or (check_in or "") >= (best.get("check_in") or ""):
                    open_records[uid] = r

        self._open_by_user = {uid: r["id"] for uid, r in open_records.items()}
        self._update_check_out_button()

    def _selected_user_id(self) -> str | None:
        combo = getattr(self, "user_combo", None)
        data = combo.currentData() if combo is not None else None
        return str(data) if data else None

    def _update_check_out_button(self, *_):
        """Check Out is for the worker chosen in the box, and only if they are in."""
        uid = self._selected_user_id()
        self.btn_check_out.setEnabled(uid is not None and uid in self._open_by_user)

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
        attendance_id = self._open_by_user.get(self._selected_user_id() or "")
        if not attendance_id:
            return  # the selected worker has nobody to check out

        result = self._service.check_out(attendance_id)
        if result:
            QMessageBox.information(self, "Success", f"Checked out. Hours: {result.get('total_hours')}")
            self.refresh_data()
