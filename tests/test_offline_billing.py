import json

import pytest
import requests

from database.outbox_repository import OutboxRepository
from services.inventory_service import InventoryService
from services.sales_service import SalesService
from ui.sales_screen import CartItem, SalesScreen

LINES = [{"item_id": "11111111-1111-1111-1111-111111111111", "quantity": 2, "price": 100.0}]


def test_queue_offline_sale_builds_a_sync_payload():
    ref = SalesService().queue_offline_sale(LINES, "Meena", "9876543210")
    (entry,) = OutboxRepository().get_pending()
    payload = json.loads(entry.payload)
    assert (entry.entity, entry.action) == ("sale", "create")
    assert payload["customer_name"] == "Meena" and payload["customer_phone"] == "9876543210"
    assert payload["items"] == [
        {"product_id": LINES[0]["item_id"], "quantity": 2, "price": 100.0}
    ]
    assert payload["id"][:8].upper() == ref  # the ref shown to the user


@pytest.fixture
def screen(qapp):
    s = SalesScreen()
    s._cart = [CartItem(LINES[0]["item_id"], "Chair", 100.0, 0.0, 2)]
    s.phone_input.setText("9876543210")
    s.customer_input.setText("Meena")
    return s


def test_create_bill_without_connection_saves_it_offline(screen, dialogs):
    screen._generate_invoice()  # server unreachable: is_online() is False
    assert [d[1] for d in dialogs][-1].startswith("Saved offline")
    assert len(OutboxRepository().get_pending()) == 1
    assert screen._cart == [] and screen.phone_input.text() == ""


def test_connection_lost_mid_request_also_saves_offline(screen, dialogs, monkeypatch):
    monkeypatch.setattr(SalesService, "is_online", lambda self: True)

    def drop(*a, **k):
        raise requests.ConnectionError("dropped")

    monkeypatch.setattr(screen._customer_service, "ensure_customer", drop)
    screen._generate_invoice()
    assert [d[1] for d in dialogs][-1].startswith("Saved offline")
    assert len(OutboxRepository().get_pending()) == 1


def test_buyer_search_offline_is_a_message_not_a_crash(screen, dialogs):
    screen._handle_customer_lookup()
    assert dialogs[-1][1] == "No internet"


class FakeApi:
    def __init__(self, items=None, fail=False):
        self.items, self.fail = items, fail

    def get_items(self, token):
        if self.fail:
            raise requests.ConnectionError("down")
        return self.items


def test_item_list_falls_back_to_the_last_known_copy():
    items = [{"name": "Chair", "id": "1"}]
    assert InventoryService(FakeApi(items)).get_items(allow_cached=True) == items
    offline = InventoryService(FakeApi(fail=True))
    assert offline.get_items(allow_cached=True) == items  # served from data/items_cache.json
    with pytest.raises(requests.ConnectionError):
        offline.get_items()  # other screens still see the error
