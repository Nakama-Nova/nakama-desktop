"""
ui/icons.py

One set of line icons for the sidebar, drawn from SVG text (no image files), in whatever
colour the button needs. They look the same on every PC, unlike emoji, which depend on the
fonts installed and clash with the brown and gold.
"""

from functools import lru_cache

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QImage, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

# 24x24 strokes, 1.6 wide, round caps
_PATHS = {
    "home": '<path d="M3 11l9-8 9 8M5 10v10h5v-6h4v6h5V10"/>',
    "bill": '<path d="M6 3h12v18l-3-2-3 2-3-2-3 2zM9 8h6M9 12h6"/>',
    "box": '<path d="M3 7l9-4 9 4v10l-9 4-9-4zM3 7l9 4 9-4M12 11v10"/>',
    "book": '<path d="M5 4h11a3 3 0 013 3v13H8a3 3 0 01-3-3zM5 17a3 3 0 013-3h11"/>',
    "list": '<path d="M8 6h12M8 12h12M8 18h12M4 6h.01M4 12h.01M4 18h.01"/>',
    "tool": '<path d="M14 6a4 4 0 005 5l-9 9a2.5 2.5 0 01-4-4zM15 3l-2 2"/>',
    "people": '<circle cx="9" cy="8" r="3.2"/><path d="M3 20c0-3.5 2.7-5.5 6-5.5s6 2 6 5.5M16 5.5a3 3 0 010 5.8M18 14.8c2 .7 3 2.4 3 5.2"/>',
    "person": '<circle cx="12" cy="8" r="3.6"/><path d="M5 20c0-4 3-6 7-6s7 2 7 6"/>',
    "money": '<rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.6"/>',
    "chart": '<path d="M4 20V4M4 20h16M8 16v-5M13 16V8M18 16v-8"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
    "cart": '<path d="M3 4h2l2.2 11h10.6L20 7H6M9 20h.01M17 20h.01"/>',
    "pin": '<path d="M12 21s7-6 7-11a7 7 0 00-14 0c0 5 7 11 7 11z"/><circle cx="12" cy="10" r="2.4"/>',
    "cube": '<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9zM12 12l8-4.5M12 12L4 7.5M12 12v9"/>',
    "palette": '<path d="M12 3a9 9 0 100 18c1.5 0 2-1 1.5-2-.6-1.3.2-3 2-3H18a3 3 0 003-3c0-5-4-10-9-10z"/><circle cx="8" cy="11" r="1"/><circle cx="12" cy="7.5" r="1"/><circle cx="16" cy="10" r="1"/>',
    "clock": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
    "target": '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="4.5"/><circle cx="12" cy="12" r=".6"/>',
    "ledger": '<path d="M6 3h12v18H6zM9 8h6M9 12h6M9 16h3"/>',
    "key": '<circle cx="8" cy="15" r="3.5"/><path d="M10.5 12.5L20 3M16 7l3 3"/>',
    "arrow-up": '<path d="M12 19V5M6 11l6-6 6 6"/>',
    "restore": '<path d="M4 20h16M6 20V10l6-6 6 6v10M10 20v-5h4v5"/>',
}

# Sidebar label -> icon
FOR_LABEL = {
    "Home": "home",
    "New Bill": "bill",
    "Bill History": "list",
    "Orders": "book",
    "Buyers": "people",
    "Letters": "mail",
    "Stock": "box",
    "Materials": "box",
    "Purchases": "cart",
    "Places": "pin",
    "3D Lab": "cube",
    "Restoration": "restore",
    "Designs": "palette",
    "Machines and tools": "tool",
    "Attendance": "clock",
    "Wages": "money",
    "Staff": "person",
    "Expenses": "money",
    "Profit": "chart",
    "Budgets": "target",
    "Accounts": "ledger",
    "Reports": "chart",
    "Roles": "key",
}


def _svg(name: str, color: str) -> bytes:
    body = _PATHS.get(name, _PATHS["box"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    ).encode()


@lru_cache(maxsize=None)
def pixmap(name: str, color: str, size: int = 18, ratio: float = 2.0) -> QPixmap:
    """The icon as a sharp pixmap: drawn at `ratio` times the size so it stays crisp on a high-DPI screen."""
    px = int(size * ratio)
    image = QImage(px, px, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    QSvgRenderer(QByteArray(_svg(name, color))).render(painter, QRectF(0, 0, px, px))
    painter.end()
    out = QPixmap.fromImage(image)
    out.setDevicePixelRatio(ratio)
    return out


def icon(name: str, color: str, size: int = 18) -> QIcon:
    return QIcon(pixmap(name, color, size))


def for_label(label: str) -> str:
    return FOR_LABEL.get(label, "box")
