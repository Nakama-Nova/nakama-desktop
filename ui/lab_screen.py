"""
ui/lab_screen.py

3D Lab: furniture pieces with their parts. "Open" shows the read-only Lab in
the browser (every part, build order, sizes, cutting list). Owner and manager
can also edit the parts, or set up another piece as furniture.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from services.enums import UserRole
from services.lab_service import LabService
from services.session import Session
from ui.errors import handle_permissions
from ui.theme import Colors, Fonts, Theme


class LabScreen(QWidget):
    COL_NAME, COL_SKU, COL_PARTS, COL_SIZES, COL_ACTIONS = range(5)

    def __init__(self):
        super().__init__()
        self._service = LabService()
        self._can_edit = Session.is_authorized([UserRole.OWNER, UserRole.MANAGER])
        self.setStyleSheet(Theme.content_bg())
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        header_row = QHBoxLayout()
        header = QLabel("🧊  3D Lab")
        header.setStyleSheet(Theme.heading(Fonts.HEADING_LG))
        header_row.addWidget(header)
        header_row.addStretch()
        self.setup_btn = QPushButton("➕  Set up a piece")
        self.setup_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setup_btn.setStyleSheet(Theme.btn_primary())
        self.setup_btn.clicked.connect(self._setup_piece)
        self.setup_btn.setVisible(self._can_edit)
        header_row.addWidget(self.setup_btn)
        layout.addLayout(header_row)

        hint = QLabel(
            "Pick a piece to see every part, the build order and the cutting list. "
            "You can try Small, Medium, Large or your own measurements; nothing is saved."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {Colors.TEXT_SECONDARY};")
        layout.addWidget(hint)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Piece", "Code", "Parts", "Sizes", ""])
        self.table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            self.COL_ACTIONS, QHeaderView.ResizeMode.Fixed
        )
        self.table.setColumnWidth(self.COL_ACTIONS, 230)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setStyleSheet(Theme.table_style())
        layout.addWidget(self.table)

    @handle_permissions
    def refresh_data(self):
        self._populate(self._service.list_furniture())

    def _populate(self, pieces: list[dict]):
        self.table.setRowCount(len(pieces))
        self.table.verticalHeader().setDefaultSectionSize(48)
        for row, p in enumerate(pieces):
            sizes = ", ".join({"S": "Small", "M": "Medium", "L": "Large"}[s] for s in p["sizes"])
            values = [p["name"], p["sku"], str(p["parts"]), sizes or "Standard only"]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col == self.COL_PARTS:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, col, item)

            box = QWidget()
            h = QHBoxLayout(box)
            h.setContentsMargins(4, 2, 4, 2)
            open_btn = QPushButton("🧊 Open")
            open_btn.setFixedHeight(30)
            open_btn.setStyleSheet(Theme.btn_table_action())
            open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            open_btn.clicked.connect(lambda _, pid=p["id"]: self._open(pid, False))
            h.addWidget(open_btn)
            if self._can_edit:
                edit_btn = QPushButton("✏️ Edit parts")
                edit_btn.setFixedHeight(30)
                edit_btn.setStyleSheet(Theme.btn_table_action())
                edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                edit_btn.clicked.connect(lambda _, pid=p["id"]: self._open(pid, True))
                h.addWidget(edit_btn)
            self.table.setCellWidget(row, self.COL_ACTIONS, box)

    @handle_permissions
    def _open(self, item_id: str, edit: bool):
        if not self._service.open(item_id, edit):
            QMessageBox.warning(
                self, "3D Lab", "Could not open the Lab. Check the connection and try again."
            )

    @handle_permissions
    def _setup_piece(self):
        """Owner/manager: choose any catalogue item to define its parts."""
        items = self._service.all_items()
        if not items:
            QMessageBox.information(self, "3D Lab", "No items found. Add the piece in Stock first.")
            return
        labels = [f"{i['name']}  ({i['sku']})" for i in items]
        choice, ok = QInputDialog.getItem(
            self, "Set up a piece", "Which piece?", labels, 0, False
        )
        if ok:
            self._open(items[labels.index(choice)]["id"], True)
