"""Empty lists say what is missing in a compact row, near the top, and every list does."""

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QTableWidget

from ui.components.carvings import EmptyState, attach_empty_state
from ui.main_window import MainWindow


def settle():
    for _ in range(20):
        QCoreApplication.processEvents()


def test_the_carvings_are_small_and_sit_beside_the_words(qapp):
    table = QTableWidget(0, 3)
    table.resize(900, 500)
    watcher = attach_empty_state(table, "Nothing in stock yet", "Add your first product.")
    table.show()
    settle()
    state = watcher.state
    assert state.carvings.height() == EmptyState.CARVING_HEIGHT <= 100  # not the old 132px poster
    assert state.carvings.geometry().right() < state.title_lbl.x()  # the words are to the right of the carvings
    assert state.title_lbl.y() < 150  # near the top of the list, not centred in a tall table
    table.close()


def test_words_only_when_asked(qapp):
    table = QTableWidget(0, 2)
    table.resize(600, 300)
    watcher = attach_empty_state(table, "Nothing here yet", "", show_carvings=False)
    table.show()
    settle()
    assert watcher.state.carvings.isHidden() and watcher.state.title_lbl.text() == "Nothing here yet"
    table.close()


def test_a_short_list_drops_the_carvings_and_keeps_the_words(qapp):
    from PyQt6.QtWidgets import QWidget

    holder = QWidget()
    holder.resize(500, 300)
    state = EmptyState("None yet", "Add one.", parent=holder)  # a child, sized by its list like the real thing
    state.setGeometry(0, 0, 500, 90)
    holder.show()
    settle()
    assert state.carvings.isHidden() and state.title_lbl.isVisible()
    state.setGeometry(0, 0, 500, 200)
    settle()
    assert not state.carvings.isHidden()
    holder.close()


def test_every_list_on_a_screen_gets_an_empty_state(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    w._conn_timer.stop()
    w._switch_page(11, refresh=False)  # Wages: the pay list, then Recent pay-outs
    w.resize(1400, 900)
    w.show()
    settle()
    view = w.content_stack.currentWidget()
    tables = view.findChildren(QTableWidget)
    assert len(tables) >= 2
    shown = [t for t in tables if t.rowCount() == 0 and t.isVisible()]
    assert shown
    for t in shown:
        states = t.viewport().findChildren(EmptyState)
        assert states and not states[0].isHidden()
    w.close()
