"""The card look: shadows that lift, icon chips, the hero panel, Stock's summary and status pills."""

from PyQt6.QtCore import QEvent
from PyQt6.QtWidgets import QGraphicsDropShadowEffect, QTableWidget, QTableWidgetItem, QWidget

from ui.components.cards import HeroCard, elevate, icon_chip, lift_on_hover
from ui.components.metric_card import MetricCard
from ui.components.pills import STOCK_TONES, PillDelegate
from ui.dashboard_window import DashboardWindow


def test_elevate_gives_a_warm_soft_shadow(qapp):
    w = QWidget()
    effect = elevate(w, blur=26, dy=6, alpha=34)
    assert isinstance(w.graphicsEffect(), QGraphicsDropShadowEffect)
    assert effect.blurRadius() == 26 and effect.yOffset() == 6
    assert effect.color().alpha() == 34 and effect.color().red() > effect.color().blue()  # brown, not grey


def test_a_card_lifts_under_the_pointer_and_settles_back(qapp):
    w = QWidget()
    effect = elevate(w, blur=20, dy=4, alpha=30)
    lift_on_hover(w)
    rest = (effect.blurRadius(), effect.yOffset(), effect.color().alpha())
    w.event(QEvent(QEvent.Type.Enter))
    from PyQt6.QtWidgets import QApplication

    QApplication.sendEvent(w, QEvent(QEvent.Type.Enter))
    assert effect.blurRadius() > rest[0] and effect.yOffset() > rest[1] and effect.color().alpha() > rest[2]
    QApplication.sendEvent(w, QEvent(QEvent.Type.Leave))
    assert (effect.blurRadius(), effect.yOffset(), effect.color().alpha()) == rest


def test_an_icon_chip_is_a_square_with_a_drawn_icon(qapp):
    chip = icon_chip("money", "#2B7149", 46)
    assert chip.width() == chip.height() == 46 and not chip.pixmap().isNull()


def test_a_metric_card_has_a_shadow_a_chip_and_keeps_its_old_api(qapp):
    card = MetricCard("Bills today", "7", "#2B7149", icon="\U0001F9FE")
    assert isinstance(card.graphicsEffect(), QGraphicsDropShadowEffect)
    assert card.icon_lbl is not None and card.title_lbl.text() == "Bills today"
    card.set_value(9)
    assert card.value_lbl.text() == "9"
    assert MetricCard("Margin", "0%", "#2B7149").icon_lbl is None


def test_the_hero_paints_its_own_gradient(qapp):
    hero = HeroCard()
    hero.resize(900, 280)
    image = hero.grab().toImage()
    dark = image.pixelColor(40, 140)  # the teak side
    assert dark.red() < 120 and dark.green() < 70 and dark.blue() < 40
    assert image.pixelColor(2, 2).alpha() < 255 or image.pixelColor(2, 2).red() > 200  # rounded corners show the page


class TestHome:
    def test_the_hero_holds_the_revenue_and_the_quick_actions(self, qapp):
        d = DashboardWindow()
        d._show_summary({"today_sales_count": 7, "today_revenue": 184600, "low_stock_count": 3, "pending_wages_total": 126000})
        assert d.revenue_lbl.text() == "₹1,84,600.00" and d.bills_hint.text() == "7 bills today"
        assert d.card_sales.value_lbl.text() == "7" and d.card_low_stock.value_lbl.text() == "3"
        assert d.card_wages.value_lbl.text() == "₹1,26,000.00"
        assert d.btn_new_bill.text() == "New bill" and d.btn_view_stock.text() == "View stock"

    def test_the_bills_line_reads_naturally(self, qapp):
        d = DashboardWindow()
        d._show_summary({"today_sales_count": 0})
        assert d.bills_hint.text() == "No bills yet today"
        d._show_summary({"today_sales_count": 1})
        assert d.bills_hint.text() == "1 bill today"

    def test_a_person_who_cannot_see_the_numbers_gets_the_hero_without_them(self, qapp, monkeypatch):
        from services.session import Session

        monkeypatch.setattr(Session, "can", staticmethod(lambda action, *a, **k: False))
        d = DashboardWindow()
        d._prepare()
        assert d.metrics_container.isHidden() and d.stat_cards.isHidden()
        assert d.greeting_lbl.text() and not d.hero.isHidden()

    def test_attention_rows_are_tall_enough_for_their_text(self, qapp):
        d = DashboardWindow()
        d._show_attention({"machines": [{"name": "Band saw", "tag": "M-02", "service_due_on": "2026-11-10", "service_overdue": True}]})
        row = d.attention_list.itemAt(0).widget()
        assert "min-height: 22px" in row.styleSheet() and "padding: 10px 14px" in row.styleSheet()


class TestPills:
    def table(self):
        t = QTableWidget(3, 1)
        t.setItemDelegateForColumn(0, PillDelegate(STOCK_TONES, t))
        for r, text in enumerate(("In stock", "Running low", "Out of stock")):
            t.setItem(r, 0, QTableWidgetItem(text))
        t.resize(300, 200)
        return t

    def test_the_cells_keep_their_text_and_the_delegate_only_changes_painting(self, qapp):
        t = self.table()
        t.show()
        t.grab()  # paints without error
        assert [t.item(r, 0).text() for r in range(3)] == ["In stock", "Running low", "Out of stock"]
        t.close()

    def test_each_status_is_drawn_in_its_own_colour(self, qapp):
        t = self.table()
        t.show()
        image = t.viewport().grab().toImage()
        t.close()
        colours = []
        for row in range(3):
            y = t.visualItemRect(t.item(row, 0)).center().y()
            x = t.columnViewportPosition(0) + t.columnWidth(0) // 2
            colours.append(image.pixelColor(x, y - 9).name())  # inside the pill, above its text
        assert colours == ["#e1f0e7", "#fbefcf", "#f9e1de"]  # green, amber and red pills

    def test_an_unknown_text_is_painted_the_normal_way(self, qapp):
        t = QTableWidget(1, 1)
        t.setItemDelegateForColumn(0, PillDelegate(STOCK_TONES, t))
        t.setItem(0, 0, QTableWidgetItem("something else"))
        t.show()
        t.grab()
        t.close()


class TestStockSummary:
    def items(self):
        return [
            {"id": "a", "name": "Panel", "current_stock": 6, "min_stock": 10, "selling_price": 1000},
            {"id": "b", "name": "Sofa", "current_stock": 0, "min_stock": 6, "selling_price": 5000},
            {"id": "c", "name": "Lamp", "current_stock": 14, "min_stock": 12, "selling_price": 100},
            {"id": "d", "name": "Table", "current_stock": 2, "min_stock": 5, "selling_price": 2000},
        ]

    def test_the_cards_count_low_out_and_value(self, qapp):
        from ui.inventory_window import InventoryWindow

        w = InventoryWindow()
        w._show_summary(self.items())
        assert w.card_products.value_lbl.text() == "4"
        assert w.card_low.value_lbl.text() == "2"  # panel (6 of 10) and table (2 of 5)
        assert w.card_out.value_lbl.text() == "1"  # the sofa
        assert w.card_value.value_lbl.text() == "₹11,400"  # 6*1000 + 14*100 + 2*2000, before GST

    def test_the_status_column_draws_pills_and_the_text_is_unchanged(self, qapp):
        from ui.inventory_window import InventoryWindow

        w = InventoryWindow()
        assert isinstance(w.table.itemDelegateForColumn(w.COL_STATUS), PillDelegate)
        w._all_items = self.items()
        w._populate_table(self.items())
        assert [w.table.item(r, w.COL_STATUS).text() for r in range(4)] == ["Running low", "Out of stock", "In stock", "Running low"]
