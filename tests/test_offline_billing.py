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


# --- a bill is never recorded twice when the connection drops mid-request ------------


def _go_online(screen, monkeypatch):
    monkeypatch.setattr(SalesService, "is_online", lambda self: True)
    monkeypatch.setattr(screen._customer_service, "ensure_customer", lambda n, p: "cust-1")


def test_online_sale_request_carries_a_client_id(monkeypatch):
    from services.api_client import APIClient

    sent = {}

    def fake_post(self, path, token, json=None, **kw):
        sent["path"], sent["json"] = path, json
        return {"invoice_number": "INV-1"}

    monkeypatch.setattr(APIClient, "_post", fake_post)
    SalesService().create_sale([{"item_id": "x", "quantity": 1}], "cust-1", "abc-123")
    assert sent["path"] == "/sales" and sent["json"]["client_id"] == "abc-123"


def test_queue_offline_sale_can_reuse_the_online_client_id():
    SalesService().queue_offline_sale(LINES, "Meena", "9876543210", client_id="abc-123")
    (entry,) = OutboxRepository().get_pending()
    assert entry.id == "abc-123"  # the sync engine's idempotency key


def test_lost_response_queues_the_same_id_the_server_may_have_recorded(
    screen, dialogs, monkeypatch
):
    _go_online(screen, monkeypatch)
    sent = {}

    def lost(self, items, customer_id=None, client_id=None):
        sent["client_id"] = client_id
        raise requests.ConnectionError("response lost after the server committed")

    monkeypatch.setattr(SalesService, "create_sale", lost)
    screen._generate_invoice()

    assert sent["client_id"]
    (entry,) = OutboxRepository().get_pending()
    assert entry.id == sent["client_id"]


def test_retrying_the_same_bill_reuses_its_id_but_a_changed_cart_gets_a_new_one(
    screen, dialogs, monkeypatch
):
    _go_online(screen, monkeypatch)
    ids = []

    def fail(self, items, customer_id=None, client_id=None):
        ids.append(client_id)
        return None  # the server answered with an error: the bill stays on screen

    monkeypatch.setattr(SalesService, "create_sale", fail)
    screen._generate_invoice()
    screen._generate_invoice()  # same cart: a retry of the same bill
    screen._cart[0].quantity = 3  # different bill
    screen._generate_invoice()

    assert ids[0] == ids[1] != ids[2]


def test_a_finished_bill_does_not_donate_its_id_to_the_next_one(
    screen, dialogs, monkeypatch
):
    _go_online(screen, monkeypatch)
    ids = []

    def ok(self, items, customer_id=None, client_id=None):
        ids.append(client_id)
        return {"invoice_number": "INV-1"}

    monkeypatch.setattr(SalesService, "create_sale", ok)
    monkeypatch.setattr(SalesService, "fetch_and_save_pdf", lambda self, n: None)
    screen._generate_invoice()
    screen._cart = [CartItem(LINES[0]["item_id"], "Chair", 100.0, 0.0, 2)]
    screen.phone_input.setText("9876543210")
    screen.customer_input.setText("Meena")
    screen._generate_invoice()  # an identical-looking second sale is a new sale

    assert len(ids) == 2 and ids[0] != ids[1]
