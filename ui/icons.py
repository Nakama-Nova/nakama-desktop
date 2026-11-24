"""
ui/icons.py

One set of line icons for the sidebar, drawn from SVG text (no image files), in whatever
colour the button needs. They look the same on every PC, unlike emoji, which depend on the
fonts installed and clash with the brown and gold.
"""

import re
from functools import lru_cache

from PyQt6.QtCore import QByteArray, QEvent, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PyQt6.QtWidgets import QPushButton
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
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "refresh": '<path d="M20 11a8 8 0 00-14.5-4M4 4v4h4M4 13a8 8 0 0014.5 4M20 20v-4h-4"/>',
    "edit": '<path d="M4 20l1-4L16 5l3 3L8 19zM14 7l3 3"/>',
    "save": '<path d="M5 4h11l3 3v13H5zM8 4v5h7V4M8 20v-6h8v6"/>',
    "trash": '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "camera": '<path d="M4 8h3l2-3h6l2 3h3v11H4z"/><circle cx="12" cy="13" r="3.5"/>',
    "video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3"/>',
    "logout": '<path d="M10 4H5v16h5M14 8l4 4-4 4M18 12H9"/>',
    "link": '<path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1"/>',
    "tag": '<path d="M3 12V4h8l10 10-8 8zM7.5 8h.01"/>',
    "file": '<path d="M6 3h8l4 4v14H6zM14 3v4h4M9 13h6M9 17h6"/>',
    "ban": '<circle cx="12" cy="12" r="8.5"/><path d="M6 6l12 12"/>',
    "alert": '<path d="M12 4l9 16H3zM12 10v4M12 17h.01"/>',
    "bell": '<path d="M6 17V11a6 6 0 0112 0v6l1.5 2h-15zM10 21h4"/>',
    "swap": '<path d="M7 7h12l-3-3M17 17H5l3 3"/>',
    "eye": '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "search": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    "image": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.5"/><path d="M3 17l5-5 4 4 3-3 6 6"/>',
    "globe": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c3 3 3 14 0 17M12 3.5c-3 3-3 14 0 17"/>',
    "calendar": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
    "shield": '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    "printer": '<path d="M7 9V4h10v5M7 17H4v-7h16v7h-3M7 14h10v6H7z"/>',
    "undo": '<path d="M9 14L4 9l5-5M4 9h10a6 6 0 010 12h-3"/>',
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
def pixmap(name: str, color: str, size: int = 18, ratio: float = 2.0, gap: int = 0) -> QPixmap:
    """The icon as a sharp pixmap: drawn at `ratio` times the size so it stays crisp on a high-DPI
    screen. `gap` adds empty room on its right (the space between a button's icon and its text)."""
    px = int(size * ratio)
    image = QImage(px + int(gap * ratio), px, QImage.Format.Format_ARGB32_Premultiplied)
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


# A leading emoji in a button's text -> the line icon that replaces it
EMOJI = {
    "➕": "plus", "\U0001f504": "refresh", "✏": "edit", "\U0001f5d1": "trash",
    "⚠": "alert", "\U0001f50d": "search", "\U0001f9fe": "bill", "✅": "check",
    "\U0001f4be": "save", "\U0001f4b0": "money", "\U0001f4dc": "file", "\U0001f558": "clock",
    "\U0001f552": "clock", "✉": "mail", "\U0001f477": "person", "\U0001f9ca": "cube",
    "\U0001f91d": "swap", "\U0001f4cd": "pin", "\U0001f464": "person", "\U0001f4e6": "box",
    "\U0001f3a8": "palette", "\U0001f4b8": "money", "\U0001f4f7": "camera", "\U0001f4cb": "list",
    "\U0001f333": "box", "\U0001f3db": "restore", "\U0001f4b9": "chart", "\U0001f511": "key",
    "⬆": "arrow-up", "\U0001f514": "bell", "\U0001f3af": "target", "\U0001fab5": "box",
    "\U0001f4d2": "ledger", "\U0001f3f7": "tag", "\U0001f5bc": "image", "\U0001f3a5": "video",
    "\U0001f6ab": "ban", "\U0001f6e0": "tool", "\U0001f6d2": "cart", "\U0001f465": "people",
    "\U0001f4ca": "chart", "\U0001f4b5": "money", "↔": "swap", "\U0001f4c8": "chart",
    "\U0001f441": "eye", "✕": "x", "✖": "x", "\U0001f6aa": "logout",
    "\U0001f517": "link", "\U0001f4c4": "file", "\U0001f527": "tool", "⛔": "ban",
    "↩": "undo", "\U0001f3e0": "home", "\U0001f310": "globe", "\U0001f4c5": "calendar",
    "\U0001f3ed": "tool", "\U0001f6e1": "shield", "\U0001f5a8": "printer",
}

_COLOR = re.compile(r"(?<![\w-])color:\s*([^;}]+)")


def _block(sheet: str, selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", sheet)
    return m.group(1) if m else ""


def _colour_in(sheet: str, selector: str | None) -> str | None:
    """The text colour a style sheet gives a button in one state (selector None: any plain rule)."""
    if selector:
        body = _block(sheet, selector)
    else:
        body = _block(sheet, "QPushButton") or _block(sheet, "QToolButton")
        if not body and "{" not in sheet:
            body = sheet  # a bare "color: x; ..." set on the button itself
    m = _COLOR.search(body)
    if m and QColor(m.group(1).strip()).isValid():
        return QColor(m.group(1).strip()).name()
    return None


class IconButton(QPushButton):
    """A push button that shows a leading emoji in its text as a line icon instead.

    Write the text as always ("✏️  Edit", "🔄  Refresh"); the emoji is removed and the matching
    icon is drawn in the button's own text colour (its style sheet, or the nearest parent's), so
    it follows solid, outline and disabled looks. A button with no emoji is an ordinary button,
    and one given an icon with setIcon() keeps it."""

    ICON_SIZE = 16
    ICON_GAP = 6

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._auto_icon: str | None = None
        self.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        self.setText(self.text())

    def setText(self, text: str) -> None:
        name, rest = None, text or ""
        head = rest.lstrip()
        if head and head[0] in EMOJI:
            name = EMOJI[head[0]]
            rest = head[1:].lstrip("️ ")
        super().setText(rest)
        if name is not None or self._auto_icon is not None:
            self._auto_icon = name
            self._refresh_icon()

    def _colours(self) -> tuple[str, str, str]:
        normal = hover = off = None
        widget = self
        while widget is not None and normal is None:
            sheet = widget.styleSheet()
            if sheet:
                normal = _colour_in(sheet, "QPushButton") or _colour_in(sheet, None)
                hover = _colour_in(sheet, "QPushButton:hover")
                off = _colour_in(sheet, "QPushButton:disabled")
            widget = widget.parentWidget()
        base = normal or self.palette().buttonText().color().name()
        return base, hover or base, off or "#B7A58D"

    def _refresh_icon(self) -> None:
        if self._auto_icon is None:
            return
        normal, hover, off = self._colours()
        gap = self.ICON_GAP if self.text() else 0  # room before the words; none for an icon-only button
        self.setIconSize(QSize(self.ICON_SIZE + gap, self.ICON_SIZE))
        built = QIcon()
        built.addPixmap(pixmap(self._auto_icon, normal, self.ICON_SIZE, 2.0, gap), QIcon.Mode.Normal)
        built.addPixmap(pixmap(self._auto_icon, hover, self.ICON_SIZE, 2.0, gap), QIcon.Mode.Active)
        built.addPixmap(pixmap(self._auto_icon, off, self.ICON_SIZE, 2.0, gap), QIcon.Mode.Disabled)
        self.setIcon(built)

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_icon()  # parents are known now, so a style set on a parent is found

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange and self._auto_icon is not None:
            self._refresh_icon()
