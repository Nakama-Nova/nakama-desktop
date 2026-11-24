"""The finishing pass: no emoji left in labels, metric cards with line icons, tables that fill."""

import re

from PyQt6.QtWidgets import QHeaderView, QLabel, QLineEdit, QTableWidget

from ui.components.metric_card import MetricCard
from ui.dashboard_window import DashboardWindow
from ui.main_window import MainWindow

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⬀-⯿✅❌➕✖✔]")


def window(qapp):
    w = MainWindow()
    w._sync_timer.stop()
    w._conn_timer.stop()
    return w


def test_no_screen_shows_an_emoji_in_a_label_or_a_placeholder(qapp):
    w = window(qapp)
    bad = []
    for i in range(w.content_stack.count()):
        view = w.content_stack.widget(i)
        for lbl in view.findChildren(QLabel):
            if EMOJI.search(lbl.text()):
                bad.append((type(view).__name__, lbl.text()))
        for edit in view.findChildren(QLineEdit):
            if EMOJI.search(edit.placeholderText()):
                bad.append((type(view).__name__, edit.placeholderText()))
    assert not bad, bad
    w.close()


def test_a_metric_card_draws_its_icon_in_the_cards_colour(qapp):
    card = MetricCard("Today's Revenue", "0", "#2B7149", icon="\U0001F4B0")
    assert card.icon_lbl is not None and not card.icon_lbl.pixmap().isNull()
    assert card.title_lbl.text() == "Today's Revenue"  # the words only, no emoji in them
    plain = MetricCard("Margin", "0%", "#2B7149")
    assert plain.icon_lbl is None


def test_the_greeting_is_plain_words(qapp):
    d = DashboardWindow()
    d._prepare()
    assert d.greeting_lbl.text() in ("Good morning", "Good afternoon", "Good evening")


def test_a_table_with_no_stretching_column_lets_the_last_one_fill(qapp):
    from ui.theme import Theme

    t = QTableWidget(2, 3)
    t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    Theme.style_table(t)
    t.resize(900, 300)
    t.show()
    for _ in range(10):
        qapp.processEvents()
    header = t.horizontalHeader()
    assert header.stretchLastSection()
    assert header.sectionSize(2) > header.sectionSize(0) * 2  # the last column took the room
    t.close()


def test_a_table_that_already_stretches_a_column_is_left_alone(qapp):
    from ui.inventory_window import InventoryWindow

    s = InventoryWindow()
    s.resize(1200, 700)
    s.show()
    for _ in range(10):
        qapp.processEvents()
    assert not s.table.horizontalHeader().stretchLastSection()
    s.close()


def test_the_filter_strip_is_hidden_until_it_has_chips(qapp):
    from ui.components.interactive import ChipBar

    bar = ChipBar()
    assert bar.isHidden()
    bar.set_chips([("all", "All", 3)])
    assert not bar.isHidden()
    bar.set_chips([])
    assert bar.isHidden()
