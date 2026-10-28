"""Furniture or sculpture on the product form and the stock list, and the automatic code."""

import pytest
from PyQt6.QtWidgets import QDialog

from services.inventory_service import InventoryService
from services.stock_service import StockService
from ui.inventory_window import InventoryWindow
from ui.item_form import ItemDialog

ITEMS = [
    {"id": "i1", "name": "Teak Armchair", "sku": "FUR-0001", "item_type": "furniture", "selling_price": "18500", "current_stock": 2, "min_stock": 5, "unit": "pcs"},
    {"id": "i2", "name": "Hoysala Madhanika", "sku": "SCU-0001", "item_type": "sculpture", "selling_price": "48000", "current_stock": 1, "min_stock": 0, "unit": "pcs", "is_furniture": False},
    {"id": "i3", "name": "Old stool", "sku": "OLD-9", "selling_price": "900", "current_stock": 9, "min_stock": 5, "unit": "pcs"},  # made before types existed
]


@pytest.fixture
def stock(monkeypatch):
    calls = []
    monkeypatch.setattr(InventoryService, "get_items", lambda self, allow_cached=False: ITEMS)
    monkeypatch.setattr(StockService, "rows", lambda self, kind: [])
    monkeypatch.setattr(InventoryService, "create", lambda self, **d: calls.append(("create", d)) or {"name": d["name"], "sku": "SCU-0002" if d["item_type"] == "sculpture" else "FUR-0002"})
    monkeypatch.setattr(InventoryService, "update", lambda self, iid, **d: calls.append(("update", iid, d)) or {"id": iid})
    return calls


def test_a_new_product_gets_its_code_automatically(qapp):
    d = ItemDialog(None)
    assert not d.sku.isEnabled() and d.sku.text() == "" and "automatically" in d.sku.placeholderText()
    d.name.setText("Carved door")
    data = d.get_data()
    assert "sku" not in data and data["item_type"] == "furniture" and data["name"] == "Carved door"


def test_an_existing_codes_is_shown_but_cannot_be_changed(qapp):
    d = ItemDialog(None, ITEMS[0])
    assert d.sku.text() == "FUR-0001" and d.sku.isReadOnly()
    assert "sku" not in d.get_data()  # never sent, so an edit cannot change it
    assert d.item_type.currentData() == "furniture"
    assert ItemDialog(None, ITEMS[2]).item_type.currentData() == "furniture"  # an item from before types existed


def test_choosing_sculpture_turns_off_the_furniture_lab_option(qapp):
    d = ItemDialog(None)
    d.furniture.setChecked(True)
    d.item_type.setCurrentIndex(d.item_type.findData("sculpture"))
    assert not d.furniture.isEnabled() and not d.furniture.isChecked()
    data = d.get_data()
    assert data["item_type"] == "sculpture" and data["is_furniture"] is False
    d.item_type.setCurrentIndex(d.item_type.findData("furniture"))
    assert d.furniture.isEnabled()
    sculpture = ItemDialog(None, ITEMS[1])
    assert sculpture.item_type.currentData() == "sculpture" and not sculpture.furniture.isEnabled()


def test_the_type_can_start_from_the_filter_in_use(qapp):
    assert ItemDialog(None, default_type="sculpture").item_type.currentData() == "sculpture"
    assert ItemDialog(None, ITEMS[0], default_type="sculpture").item_type.currentData() == "furniture"  # an existing item keeps its own


def test_the_stock_list_shows_the_type_and_filters_by_it(qapp, stock):
    w = InventoryWindow()
    w.refresh_data()
    assert w.table.rowCount() == 3
    types = {w.table.item(r, w.COL_SKU).text(): w.table.item(r, w.COL_TYPE).text() for r in range(3)}
    assert types == {"FUR-0001": "Furniture", "SCU-0001": "Sculpture", "OLD-9": "Furniture"}
    w.type_filter.setCurrentIndex(w.type_filter.findData("sculpture"))
    assert [w.table.item(r, w.COL_NAME).text() for r in range(w.table.rowCount())] == ["Hoysala Madhanika"]
    w.type_filter.setCurrentIndex(w.type_filter.findData("furniture"))
    assert w.table.rowCount() == 2  # the old item without a type counts as furniture
    w.search_input.setText("stool")  # the search and the filter work together
    assert [w.table.item(r, w.COL_NAME).text() for r in range(w.table.rowCount())] == ["Old stool"]
    w.type_filter.setCurrentIndex(w.type_filter.findData(None))
    w.search_input.setText("scu-")  # by code
    assert w.table.rowCount() == 1


def test_adding_a_product_tells_you_its_new_code(qapp, stock, monkeypatch, dialogs):
    w = InventoryWindow()
    w.refresh_data()
    w.type_filter.setCurrentIndex(w.type_filter.findData("sculpture"))
    monkeypatch.setattr(ItemDialog, "exec", lambda self: (self.name.setText("Nandi in wood"), QDialog.DialogCode.Accepted)[-1])
    w.add_btn.click()
    sent = next(c for c in stock if c[0] == "create")[1]
    assert sent["item_type"] == "sculpture" and "sku" not in sent  # the filter chose the starting type
    assert dialogs[-1][0] == "information" and "SCU-0002" in dialogs[-1][2] and "Nandi in wood" in dialogs[-1][2]


def test_a_product_needs_only_a_name(qapp, stock, monkeypatch, dialogs):
    w = InventoryWindow()
    w.refresh_data()
    monkeypatch.setattr(ItemDialog, "exec", lambda self: QDialog.DialogCode.Accepted)  # name left blank
    w.add_btn.click()
    assert dialogs[-1][0] == "warning" and "name" in dialogs[-1][2] and not [c for c in stock if c[0] == "create"]


def test_editing_never_sends_the_code(qapp, stock, monkeypatch):
    w = InventoryWindow()
    w.refresh_data()
    monkeypatch.setattr(ItemDialog, "exec", lambda self: (self.item_type.setCurrentIndex(self.item_type.findData("sculpture")), QDialog.DialogCode.Accepted)[-1])
    w._edit_item(ITEMS[0])
    sent = next(c for c in stock if c[0] == "update")
    assert sent[1] == "i1" and sent[2]["item_type"] == "sculpture" and "sku" not in sent[2]
