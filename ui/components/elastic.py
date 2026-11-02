"""
ui/components/elastic.py

Tables that behave like a web table: each column is as wide as its content needs, and when
the window is wider the spare room is shared out, when it is narrower the columns give a
little (longest first) before any text is cut. Only when even the shortest form does not fit
does a scroll bar appear.

    make_elastic(table)

Columns set to Fixed (action buttons) keep their width. The widths are recalculated when rows
change and when the table is resized.
"""

from PyQt6.QtCore import QEvent, QObject, QTimer
from PyQt6.QtWidgets import QHeaderView, QTableView

PAD = 22  # room for cell padding around the text
MIN_TEXT = 70  # a column never gives up more than this to a squeeze


class ElasticColumns(QObject):
    def __init__(self, table: QTableView):
        super().__init__(table)
        self._table = table
        self._busy = False
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(0)
        self._timer.timeout.connect(self.fit)
        table.horizontalHeader().setStretchLastSection(False)
        table.viewport().installEventFilter(self)
        table.installEventFilter(self)  # a table first shown at its final size gets no resize
        model = table.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset, model.layoutChanged,
                       model.columnsInserted, model.columnsRemoved):
            signal.connect(self.refit)
        model.dataChanged.connect(self.refit)

    def refit(self, *_):
        self._timer.start()

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Resize, QEvent.Type.Show):
            self.refit()
        return False

    def fit(self) -> None:
        t = self._table
        if self._busy or not t.isVisible():
            return
        hh = t.horizontalHeader()
        flexible, fixed = [], 0
        for c in range(t.model().columnCount()):
            if t.isColumnHidden(c):
                continue
            if hh.sectionResizeMode(c) == QHeaderView.ResizeMode.Fixed:
                fixed += t.columnWidth(c)
            else:
                flexible.append(c)
        if not flexible:
            return
        content = {c: t.sizeHintForColumn(c) + PAD for c in flexible}
        ideal = {c: max(content[c], hh.sectionSizeHint(c)) for c in flexible}
        room = t.viewport().width() - fixed - 2  # 2px: the frame, so no scroll bar for a sliver
        total = sum(ideal.values())
        if total <= room:  # share the spare room in proportion to what each needs
            widths = {c: ideal[c] + (room - total) * ideal[c] // total for c in flexible}
        else:  # squeeze: long headers give first (they can be shortened with ...), then the cells
            widths = dict(ideal)
            squeeze = total - room
            for floor in ({c: min(ideal[c], max(content[c], MIN_TEXT)) for c in flexible},
                          {c: min(ideal[c], MIN_TEXT) for c in flexible}):
                give = {c: widths[c] - floor[c] for c in flexible}
                can = sum(give.values())
                take = min(squeeze, can)
                if can:
                    widths = {c: widths[c] - take * give[c] // can for c in flexible}
                squeeze -= take
        extra = sum(widths.values()) - room  # integer rounding can leave a pixel or two over
        if 0 < extra <= 6:
            widest = max(widths, key=widths.get)
            widths[widest] -= extra
        self._busy = True
        try:
            for c, w in widths.items():
                hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Interactive)
                if t.columnWidth(c) != w:
                    t.setColumnWidth(c, w)
        finally:
            self._busy = False


def make_elastic(table: QTableView) -> None:
    if table.property("elastic"):
        return
    table.setProperty("elastic", True)
    ElasticColumns(table)
