"""With the server down the app must still open (the counter bills offline)."""

from ui.attendance_screen import AttendanceScreen
from conftest import settle
from ui.main_window import MainWindow



def test_main_window_opens_without_a_server(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    assert w.content_stack.count() == 21


def test_opening_a_screen_offline_shows_a_notice_not_a_crash(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    w._switch_page(2)  # Stock: refresh hits the dead server
    settle()
    assert "No connection" in w.statusBar().currentMessage()


def test_workforce_screen_builds_without_a_server(qapp):
    AttendanceScreen()


def test_keyboard_shortcuts_move_around_and_find_the_search_box(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    w.show()
    assert len(w._shortcuts) == 11  # F5, Ctrl+F, Ctrl+1..9
    second = next(i for i, b in w._nav_mapping.items() if b is w._nav_buttons[1])
    w._go_to_nth(2)
    assert w.content_stack.currentIndex() == second
    w._switch_page(18, refresh=False)  # Places has a search box
    w._focus_search()
    assert w.focusWidget() is w.places_view.search


def test_tables_fit_their_window_and_the_sidebar_folds_when_it_is_narrow(qapp):
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

    w = MainWindow()
    w._sync_timer.stop()
    w.show()
    w.resize(1100, 700)
    settle()
    assert w._compact and w.sidebar.width() == 80
    assert w._nav_buttons[0].text().strip() == w._nav_buttons[0].property("icon_text")
    w.resize(1500, 800)
    settle()
    assert not w._compact and w.sidebar.width() == 232
    assert w._nav_buttons[0].property("label_text") in w._nav_buttons[0].text()

    w._switch_page(10, refresh=False)  # Staff
    table = w.staff_view.table if hasattr(w.staff_view, "table") else w.content_stack.currentWidget().findChild(QTableWidget)
    table.setRowCount(3)
    for r in range(3):
        for c in range(table.columnCount() - 1):
            table.setItem(r, c, QTableWidgetItem("A fairly long cell " * 2))
    for _ in range(3):
        qapp.processEvents()
    assert table.horizontalScrollBar().maximum() == 0


def test_a_row_opens_in_a_popup_with_every_value_in_full(qapp, monkeypatch):
    from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem

    from ui.components import row_details
    from ui.components.row_details import RowDetails, make_inspectable, row_fields

    t = QTableWidget(0, 3)
    t.setHorizontalHeaderLabels(["Name", "Note", ""])  # the last column holds buttons
    for r, (name, note) in enumerate([("Teak armchair", "x" * 300), ("Study table", "")]):
        t.insertRow(r)
        t.setItem(r, 0, QTableWidgetItem(name))
        t.setItem(r, 1, QTableWidgetItem(note))
    assert row_fields(t, 0)[1] == ("Note", "x" * 300)
    assert row_fields(t, 1)[1] == ("Note", "—")  # empty reads as a dash
    assert len(row_fields(t, 0)) == 2  # no heading, no field

    opened = []
    monkeypatch.setattr(RowDetails, "exec", lambda self: opened.append(self.title.text()))
    make_inspectable(t)
    t.cellDoubleClicked.emit(1, 0)
    assert opened == ["Study table"]

    d = RowDetails(t, 0)
    assert d.values["Note"].text() == "x" * 300 and d.values["Note"].wordWrap()
    assert not d.prev_btn.isEnabled() and d.next_btn.isEnabled()
    d.step(1)
    assert d.title.text() == "Study table" and d.position.text() == "2 of 2"
    d.copy()
    assert "Name: Study table" in qapp.clipboard().text()

    used = QTableWidget(1, 1)  # a screen that already uses double-click keeps it
    used.setHorizontalHeaderLabels(["Name"])
    used.cellDoubleClicked.connect(lambda r, c: None)
    make_inspectable(used)
    assert used.receivers(used.cellDoubleClicked) == 1
