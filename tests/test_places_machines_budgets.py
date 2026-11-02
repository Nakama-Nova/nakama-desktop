"""Places (stock by location), machines and tools, budgets, and the backend changes the desktop follows
(no brands, a fresh token after a password change)."""

from datetime import date, timedelta

import pytest
from PyQt6.QtWidgets import QDialog, QPushButton

from services.api_client import APIClient
from services.enums import UserRole
from services.places_service import PlacesService
from services.registers_service import RegistersService
from services.session import Session
from services.staff_service import StaffService
from services.stock_service import StockService
from ui.budgets_screen import BudgetCard, BudgetsScreen, SetBudgetDialog, period_label, usage_text
from ui.item_form import ItemDialog
from ui.machines_screen import MachineDialog, MachinesScreen, due_state
from ui.main_window import MainWindow
from ui.places_screen import MoveStockDialog, PlacesScreen

SHOP, UNIT = "loc-shop", "loc-unit"
PLACES = [
    {"id": SHOP, "name": "Shop", "code": "SHP", "kind": "shop", "has_till": True, "radius_m": 50, "is_active": True},
    {"id": UNIT, "name": "Carving unit", "code": "U1", "kind": "plant", "has_till": False, "radius_m": 100, "is_active": True},
]
LEVELS = [
    {"location_id": SHOP, "location_name": "Shop", "item_id": "i1", "raw_material_id": None, "name": "Teak Armchair", "quantity": "8"},
    {"location_id": UNIT, "location_name": "Carving unit", "item_id": None, "raw_material_id": "m1", "name": "Teak plank", "quantity": "12.5"},
    {"location_id": None, "location_name": None, "item_id": "i2", "raw_material_id": None, "name": "Study Table", "quantity": "3"},
]


@pytest.fixture
def places(monkeypatch):
    monkeypatch.setattr(PlacesService, "places", lambda self: PLACES)
    monkeypatch.setattr(PlacesService, "levels", lambda self: LEVELS)
    monkeypatch.setattr(PlacesService, "transfers", lambda self, limit=50: [])


# ------------------------------------------------------------------ places
def test_the_place_chips_filter_what_is_listed_and_search_narrows_it(qapp, places):
    w = PlacesScreen()
    w.refresh_data()
    assert w.table.rowCount() == 3
    w.chips.choose("none")  # what has no place yet
    assert [w.table.item(r, w.COL_NAME).text() for r in range(w.table.rowCount())] == ["Study Table"]
    w.chips.choose(UNIT)
    assert w.table.item(0, w.COL_NAME).text() == "Teak plank"
    w.chips.choose("all")
    w.search.setText("arm")
    assert w.table.rowCount() == 1 and w.table.item(0, w.COL_NAME).text() == "Teak Armchair"
    w.search.setText("")
    w.kind_filter.setCurrentIndex(2)  # materials only
    assert w.table.rowCount() == 1
    assert w.places_table.rowCount() == 2


def test_a_refresh_keeps_the_chosen_place(qapp, places):
    w = PlacesScreen()
    w.refresh_data()
    w.chips.choose(SHOP)
    w.refresh_data()
    assert w.chips.current() == SHOP and w.table.rowCount() == 1


def test_the_move_dialog_limits_the_amount_and_shows_the_result(qapp):
    d = MoveStockDialog(None, PLACES, LEVELS, preset=LEVELS[0])
    assert d.from_box.currentText() == "Shop" and d.thing_box.currentText().startswith("Teak Armchair")
    assert d.to_box.findText("Shop") == -1  # not to the place it comes from
    assert d.qty.maximum() == 8 and d.qty.decimals() == 0
    d.qty.setValue(3)
    d.to_box.setCurrentIndex(d.to_box.findText("Carving unit"))
    assert "Shop 8 → 5" in d.preview.text() and "Carving unit 0 → 3" in d.preview.text()
    data = d.get_data()
    assert data["item_id"] == "i1" and data["raw_material_id"] is None
    assert (data["from_location_id"], data["to_location_id"], data["quantity"]) == (SHOP, UNIT, 3)


def test_unplaced_stock_can_be_placed_and_a_material_takes_decimals(qapp):
    d = MoveStockDialog(None, PLACES, LEVELS, preset=LEVELS[2])
    assert d.from_box.currentText() == "Not placed yet" and d.get_data()["from_location_id"] is None
    d = MoveStockDialog(None, PLACES, LEVELS, preset=LEVELS[1])
    assert d.qty.decimals() == 2 and d.qty.maximum() == 12.5 and d.get_data()["raw_material_id"] == "m1"


def test_double_clicking_a_row_opens_the_move_dialog_for_it(qapp, places, monkeypatch):
    opened, moved = [], []

    def accept(self):
        opened.append(self.thing_box.currentText())
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(MoveStockDialog, "exec", accept)
    monkeypatch.setattr(PlacesService, "move", lambda self, **kw: moved.append(kw))
    w = PlacesScreen()
    w.refresh_data()
    w._row_double_clicked(1, 0)
    assert opened[0].startswith("Teak plank") and moved[0]["raw_material_id"] == "m1"


def test_sales_staff_can_look_but_not_move_or_add(qapp, monkeypatch):
    monkeypatch.setattr(Session, "_role", UserRole.SALES)
    w = PlacesScreen()
    assert w.move_btn.isHidden() and w.add_place_btn.isHidden() and w.table.isColumnHidden(w.COL_ACTIONS)


def test_the_move_goes_to_the_server_as_a_transfer(qapp, monkeypatch):
    sent = {}
    monkeypatch.setattr(APIClient, "_post", lambda self, path, token, json=None, **k: sent.update(path=path, json=json) or {})
    PlacesService().move(item_id="i1", raw_material_id=None, from_location_id=SHOP, to_location_id=UNIT, quantity=3)
    assert sent["path"] == "/stock/transfers" and sent["json"]["quantity"] == "3" and sent["json"]["to_location_id"] == UNIT


# ------------------------------------------------------------------ machines and tools
def in_days(n):
    return (date.today() + timedelta(days=n)).isoformat()


MACHINES = [
    {"id": "a", "tag": "M-1", "name": "Table saw", "status": "active", "book_value": "42000", "maintenance_spent": "1500", "service_due_on": in_days(-3), "service_overdue": True},
    {"id": "b", "tag": "M-2", "name": "Lathe", "status": "down", "book_value": "9000", "maintenance_spent": "0", "service_due_on": None, "service_overdue": False},
    {"id": "c", "tag": "M-3", "name": "Router", "status": "active", "book_value": None, "maintenance_spent": "0", "service_due_on": in_days(5), "service_overdue": False},
    {"id": "d", "tag": "M-4", "name": "Old planer", "status": "retired", "book_value": "0", "maintenance_spent": "0", "service_due_on": in_days(-90), "service_overdue": True},
]
TOOLS = [
    {"id": "t1", "tag": "T-1", "name": "Chisel", "category": "Carving", "status": "available", "condition": "good", "held_by": None},
    {"id": "t2", "tag": "T-2", "name": "Mallet", "category": "Carving", "status": "issued", "condition": "worn", "held_by": "u1"},
    {"id": "t3", "tag": "T-3", "name": "Plane", "category": "Hand tool", "status": "broken", "condition": "damaged", "held_by": None},
]
STAFF = [{"id": "u1", "full_name": "Asha", "username": "asha"}]


@pytest.fixture
def registers(monkeypatch):
    monkeypatch.setattr(PlacesService, "places", lambda self: PLACES)
    monkeypatch.setattr(RegistersService, "machines", lambda self: MACHINES)
    monkeypatch.setattr(RegistersService, "tools", lambda self: TOOLS)
    monkeypatch.setattr(RegistersService, "staff", lambda self: STAFF)


def test_a_retired_machine_is_never_due_and_a_near_one_is_soon():
    assert [due_state(m) for m in MACHINES] == ["overdue", "", "soon", ""]


def test_machine_chips_filter_and_the_banner_names_the_trouble(qapp, registers):
    w = MachinesScreen()
    w.refresh_data()
    assert w.m_table.rowCount() == 4
    w.m_chips.choose("due")
    assert [w.m_table.item(r, w.M_TAG).text() for r in range(w.m_table.rowCount())] == ["M-1", "M-3"]
    w.m_chips.choose("down")
    assert w.m_table.rowCount() == 1 and w.m_table.item(0, w.M_NAME).text() == "Lathe"
    w.m_chips.choose("all")
    w.m_search.setText("rout")
    assert w.m_table.rowCount() == 1
    assert not w.alert.isHidden() and "Table saw" in w.alert.text() and "Lathe" in w.alert.text()


def test_a_stopped_machine_offers_working_again_and_a_working_one_offers_stopped(qapp, registers):
    w = MachinesScreen()
    w.refresh_data()

    def texts(row):
        return [b.text() for b in w.m_table.cellWidget(row, w.M_ACTIONS).findChildren(QPushButton)]

    assert "⛔ Stopped" in texts(0) and "✅ Working" not in texts(0)
    assert "✅ Working" in texts(1) and "⛔ Stopped" not in texts(1)


def test_tool_chips_show_who_has_what(qapp, registers):
    w = MachinesScreen()
    w.refresh_data()
    w.t_chips.choose("issued")
    assert w.t_table.rowCount() == 1 and w.t_table.item(0, w.T_WITH).text() == "Asha"
    w.t_chips.choose("all")
    w.t_search.setText("hand")  # by category
    assert w.t_table.rowCount() == 1 and w.t_table.item(0, w.T_NAME).text() == "Plane"


def test_the_achari_sees_tools_only(qapp, registers, monkeypatch):
    monkeypatch.setattr(Session, "_role", UserRole.ACHARI)
    w = MachinesScreen()
    w.refresh_data()
    assert w.tabs.count() == 1 and w.add_btn.isHidden() and w.t_table.isColumnHidden(w.T_ACTIONS)
    assert w.t_table.rowCount() == 3


def test_the_machine_form_sends_only_what_was_filled(qapp):
    d = MachineDialog(None, PLACES)
    d.tag.setText(" M-9 ")
    d.name.setText("Band saw")
    d.every.setValue(90)
    data = d.get_data()
    assert data["tag"] == "M-9" and data["maintenance_every_days"] == 90
    assert data["purchase_date"] is None and data["purchase_cost"] is None and data["useful_life_years"] is None
    assert "status" not in data  # status is only changed when editing


# ------------------------------------------------------------------ budgets
def test_usage_words_follow_the_80_percent_rule():
    assert usage_text(1000, 500)[1:] == ("ok", "50% used · ₹500.00 left")
    assert usage_text(1000, 800)[1] == "warning"
    assert usage_text(1000, 1200)[1:] == ("over", "120% used · ₹200.00 over")
    assert usage_text(0, 50)[1] == "no_budget"


def test_period_names_read_plainly():
    assert period_label("month", "2026-11-01") == "November 2026"
    assert period_label("financial_year", "2026-04-01") == "Year 2026–27"


def status(category, period, start, amount, spent, state, pct=None):
    return {
        "id": f"b-{category}-{period}" if amount is not None else None,
        "category": category, "period": period, "period_start": start, "period_end": start,
        "amount": amount, "spent": spent, "remaining": None if amount is None else str(float(amount) - float(spent)),
        "percent_used": pct, "state": state, "current_value": "100000", "notes": None,
    }


CURRENT = [
    status("machines", "month", "2026-11-01", "50000", "42000", "warning", "84"),
    status("raw_materials", "month", "2026-11-01", None, "1000", "no_budget"),
]


def test_budget_cards_and_the_warning_banner(qapp, monkeypatch):
    monkeypatch.setattr(RegistersService, "current_budgets", lambda self: CURRENT)
    monkeypatch.setattr(RegistersService, "all_budgets", lambda self: [CURRENT[0]])
    w = BudgetsScreen()
    w.refresh_data()
    assert len(w.grid.findChildren(BudgetCard)) == 2
    assert not w.alert.isHidden() and "machines" in w.alert.text().lower()
    assert w.table.rowCount() == 1 and w.table.item(0, w.COL_STATE).text() == "Nearly used"
    w.refresh_data()  # a second refresh replaces the cards instead of piling them up
    assert len(w.findChildren(BudgetCard)) == 2


def test_the_budget_dialog_previews_the_bar_as_you_type(qapp):
    d = SetBudgetDialog(None, CURRENT[0])
    d.amount.setValue(40000)
    assert d.bar.value() == 100 and "over" in d.words.text()
    d.amount.setValue(100000)
    assert d.bar.value() == 42 and "left" in d.words.text()
    assert d.get_data() == ("machines", "month", "2026-11-01", 100000, "")


def test_a_manager_can_see_budgets_but_not_set_them(qapp, monkeypatch):
    monkeypatch.setattr(Session, "_role", UserRole.MANAGER)
    monkeypatch.setattr(RegistersService, "current_budgets", lambda self: CURRENT)
    monkeypatch.setattr(RegistersService, "all_budgets", lambda self: [CURRENT[0]])
    w = BudgetsScreen()
    w.refresh_data()
    assert w.table.isColumnHidden(w.COL_ACTIONS)
    assert all(card.set_btn.isHidden() for card in w.findChildren(BudgetCard))


@pytest.mark.parametrize(
    "role,machines,places_,budgets",
    [
        (UserRole.OWNER, True, True, True),
        (UserRole.MANAGER, True, True, True),
        (UserRole.SALES, False, True, False),
        (UserRole.ACHARI, True, False, False),  # the achari sees tools inside "Machines and tools"
        (UserRole.WORKER, False, False, False),
    ],
)
def test_who_sees_the_new_screens(qapp, monkeypatch, role, machines, places_, budgets):
    monkeypatch.setattr(Session, "_role", role)
    w = MainWindow()
    w._sync_timer.stop()
    labels = {label for _, label, _ in w._get_allowed_nav_items()}
    assert ("Machines and tools" in labels, "Places" in labels, "Budgets" in labels) == (machines, places_, budgets)


# ------------------------------------------------------------------ what the backend dropped or changed
def test_brands_are_gone_from_the_product_form(qapp):
    d = ItemDialog(None, None, [])
    assert not hasattr(d, "brand") and "brand_id" not in d.get_data()


def test_changing_my_password_keeps_the_fresh_sign_in_the_server_hands_back(qapp, monkeypatch):
    stored = []
    monkeypatch.setattr(Session, "set_token", classmethod(lambda cls, t: stored.append(t)))
    monkeypatch.setattr(APIClient, "_post", lambda self, path, token, json=None, **k: {"message": "Password changed", "access_token": "fresh"})
    StaffService().change_my_password("old", "new-password")
    assert stored == ["fresh"]


def test_confirming_a_purchase_can_name_the_receiving_place(qapp, monkeypatch):
    seen = []
    monkeypatch.setattr(APIClient, "_patch", lambda self, path, token, json=None: seen.append(path) or {})
    StockService().confirm_purchase("p1", UNIT)
    StockService().confirm_purchase("p2")
    assert seen == [f"/purchases/p1/confirm?location_id={UNIT}", "/purchases/p2/confirm"]
