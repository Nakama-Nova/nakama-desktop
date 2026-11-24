"""
ui/components/pills.py

A status written in a table cell becomes a coloured pill, the way a web table shows it.
The cell keeps its plain text (searching, sorting and tests still see "Running low"); only the
painting changes.

    table.setItemDelegateForColumn(col, PillDelegate(STOCK_TONES, table))
"""

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate, QStyleOptionViewItem

# text -> (text colour, pill colour)
STOCK_TONES = {
    "In stock": ("#1F6B43", "#E1F0E7"),
    "Running low": ("#8F5F00", "#FBEFCF"),
    "Out of stock": ("#B3261E", "#F9E1DE"),
}


class PillDelegate(QStyledItemDelegate):
    HEIGHT = 24
    PAD = 12

    def __init__(self, tones: dict[str, tuple[str, str]], parent=None):
        super().__init__(parent)
        self._tones = tones

    def _text(self, index) -> str:
        return str(index.data(Qt.ItemDataRole.DisplayRole) or "")

    def paint(self, painter: QPainter, option, index):
        text = self._text(index)
        tone = self._tones.get(text)
        if tone is None:
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""  # the row's own background and selection, without its text
        widget = option.widget
        style = widget.style() if widget is not None else None
        if style is not None:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, painter, widget)

        font = painter.font()
        font.setBold(True)
        font.setPixelSize(12)
        metrics = QFontMetrics(font)  # measured in the pill's own, smaller bold font
        width = min(metrics.horizontalAdvance(text) + 2 * self.PAD, option.rect.width() - 8)
        rect = QRectF(
            option.rect.center().x() - width / 2, option.rect.center().y() - self.HEIGHT / 2, width, self.HEIGHT
        )
        fg, bg = tone
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(bg))
        painter.drawRoundedRect(rect, self.HEIGHT / 2, self.HEIGHT / 2)
        painter.setFont(font)
        painter.setPen(QColor(fg))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, metrics.elidedText(text, Qt.TextElideMode.ElideRight, int(width - self.PAD)))
        painter.restore()

    def sizeHint(self, option, index):
        base = super().sizeHint(option, index)
        if self._text(index) in self._tones:
            return QSize(option.fontMetrics.horizontalAdvance(self._text(index)) + 2 * self.PAD + 8, max(base.height(), self.HEIGHT + 8))
        return base
