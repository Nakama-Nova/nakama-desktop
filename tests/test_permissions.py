"""Permissions: Session.can, the old-server fallback, and that the 7 built-in roles see
exactly the menus and buttons they did when roles were a fixed list."""

import pytest

from services.api_client import APIClient, APIError
from services.builtin_roles import BUILTIN_ACTIONS
from services.iam_service import IamService, allowed_in, policy_document
from services.session import Session

# What each built-in role's menu looked like before dynamic roles (the old hardcoded lists).
OLD_MENU = {
    "owner": {"Home", "New Bill", "Bill History", "Orders", "Buyers", "Letters", "Stock", "Materials", "Purchases",
              "Places", "3D Lab", "Restoration", "Designs", "Machines and tools", "Attendance", "Leave", "Wages", "Staff",
              "Expenses", "Profit", "Budgets", "Accounts", "Reports"},
    "sales": {"Home", "New Bill", "Bill History", "Orders", "Buyers", "Letters", "Stock", "Places", "Attendance"},
    "achari": {"Home", "Stock", "Attendance", "Wages", "3D Lab", "Machines and tools"},
    "artisan": {"Home", "Stock", "Attendance", "Wages", "3D Lab", "Restoration", "Designs"},
    "accountant": {"Accounts"},
    "worker": {"Home", "Stock", "Attendance", "Wages", "3D Lab"},
}
OLD_MENU["manager"] = OLD_MENU["owner"] - {"Staff", "Restoration", "Designs"}

# role -> actions the screens check, with the old answer (owner/manager/... lists in the old code)
OLD_BUTTONS = {
    "payroll:payment:create": {"owner", "manager"},
    "items:item:write": {"owner", "manager"},
    "reports:report:read": {"owner", "manager"},
    "reports:dashboard:read": {"owner", "manager"},
    "expenses:expense:void": {"owner"},
    "lab:part:edit": {"owner", "manager"},
    "attendance:record:read_all": {"owner", "manager", "sales"},
    "sales:customer:write": {"owner", "manager", "sales"},
    "sales:sale:create": {"owner", "manager", "sales"},
    "inventory:raw_material:delete": {"owner"},
    "sales:sale:edit": {"owner", "manager"},
    "sales:sale:delete": {"owner"},
    "sales:order:update": {"owner", "manager"},
    "sales:order:payment_edit": {"owner"},
    "inventory:stock_location:transfer": {"owner", "manager"},
    "plants:plant_unit:write": {"owner"},
    "machines:machine:write": {"owner", "manager"},
    "budgets:budget:write": {"owner"},
    "restoration:cost:read": {"owner"},
    "restoration:project:access": {"owner", "artisan"},
    "finance:balance_sheet:read": {"owner", "accountant"},
    "letters:quotation:issue": {"owner", "manager", "sales"},
    "letters:purchase_receipt:issue": {"owner", "manager"},
    "letters:completion_certificate:issue": {"owner"},
}
ROLES = sorted(BUILTIN_ACTIONS)


def sign_in_as(monkeypatch, role, allowed=None):
    """A signed-in user; `allowed` is what /iam/me said (None = an old server, the role decides)."""
    monkeypatch.setattr(Session, "_role", role)
    monkeypatch.setattr(Session, "_allowed", allowed)
    monkeypatch.setattr(Session, "_by_plant_unit", {})


def server_allowed(role):
    """What PR 124's /iam/me returns for a built-in role (its defaults, wildcards kept)."""
    return list(BUILTIN_ACTIONS[role])


def menu(role):
    from ui.main_window import MainWindow

    return {label for _, label, _ in MainWindow.NAV_ITEMS if MainWindow._can_see(label)}


@pytest.mark.parametrize("fresh", [True, False], ids=["server-permissions", "old-server-fallback"])
@pytest.mark.parametrize("role", ROLES)
def test_builtin_role_menu_is_unchanged(monkeypatch, role, fresh):
    sign_in_as(monkeypatch, role, server_allowed(role) if fresh else None)
    expected = set(OLD_MENU[role])
    got = menu(role) - {"Roles"}  # Roles is the new screen: the server decides who sees it
    assert got == expected


@pytest.mark.parametrize("fresh", [True, False], ids=["server-permissions", "old-server-fallback"])
@pytest.mark.parametrize("role", ROLES)
def test_builtin_role_buttons_are_unchanged(monkeypatch, role, fresh):
    sign_in_as(monkeypatch, role, server_allowed(role) if fresh else None)
    for action, roles in OLD_BUTTONS.items():
        assert Session.can(action) == (role in roles), (role, action)


def test_roles_menu_follows_iam_role_read(monkeypatch):
    sign_in_as(monkeypatch, "sales", server_allowed("sales"))
    assert "Roles" not in menu("sales")
    sign_in_as(monkeypatch, "manager", server_allowed("manager"))
    assert "Roles" in menu("manager")


def test_a_custom_role_gets_exactly_what_the_server_lists(monkeypatch):
    sign_in_as(monkeypatch, "shop_supervisor", ["sales:sale:*", "items:item:read"])
    assert Session.can("sales:sale:create") and Session.can("sales:sale:delete")
    assert not Session.can("sales:order:read") and not Session.can("payroll:payment:create")
    assert menu("shop_supervisor") == {"Home", "New Bill", "Bill History", "Stock"}


def test_can_wildcards(monkeypatch):
    sign_in_as(monkeypatch, "x", ["payroll:payment:create", "sales:*"])
    assert Session.can("payroll:*")  # any payroll action
    assert Session.can("sales:order:read")
    assert not Session.can("finance:*")
    sign_in_as(monkeypatch, "x", ["*"])
    assert Session.can("anything:at:all")
    sign_in_as(monkeypatch, "x", [])
    assert not Session.can("sales:sale:create")


def test_plant_unit_grants_count_only_for_that_unit(monkeypatch):
    sign_in_as(monkeypatch, "x", ["items:item:read"])
    monkeypatch.setattr(Session, "_by_plant_unit", {"p1": ["inventory:stock_location:transfer"]})
    assert not Session.can("inventory:stock_location:transfer")
    assert Session.can("inventory:stock_location:transfer", plant_unit_id="p1")
    assert not Session.can("inventory:stock_location:transfer", plant_unit_id="p2")


def test_unknown_custom_role_on_an_old_server_can_do_nothing(monkeypatch):
    sign_in_as(monkeypatch, "shop_supervisor", None)
    assert not Session.can("items:item:read")


class FakeApi:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def get_my_permissions(self, token):
        if self.error:
            raise self.error
        return self.result


def test_refresh_stores_what_iam_me_says(monkeypatch):
    sign_in_as(monkeypatch, "worker", None)
    Session.refresh_permissions(FakeApi({"role": "shop_supervisor", "allowed": ["sales:*"], "by_plant_unit": {"p": ["a:b:c"]}}))
    assert Session.get_role() == "shop_supervisor"
    assert Session.can("sales:sale:create") and not Session.can("items:item:read")
    assert Session.can("a:b:c", plant_unit_id="p")


def test_old_server_404_falls_back_to_the_role_list(monkeypatch):
    sign_in_as(monkeypatch, "sales", ["items:item:read"])
    Session.refresh_permissions(FakeApi(None))  # get_my_permissions gives None on a 404
    assert Session._allowed is None
    assert Session.can("sales:sale:create")


def test_get_my_permissions_turns_404_into_none(monkeypatch):
    api = APIClient()

    def missing(*a, **k):
        raise APIError(404, "Not Found")

    monkeypatch.setattr(api, "_get", missing)
    assert api.get_my_permissions("t") is None

    def broken(*a, **k):
        raise APIError(500, "boom")

    monkeypatch.setattr(api, "_get", broken)
    with pytest.raises(APIError):
        api.get_my_permissions("t")


def test_a_server_that_cannot_be_reached_keeps_what_was_known(monkeypatch):
    sign_in_as(monkeypatch, "manager", ["sales:*"])
    Session.refresh_permissions(FakeApi(error=ConnectionError("down")))
    assert Session._allowed == ["sales:*"]


def test_logging_out_forgets_permissions(monkeypatch):
    sign_in_as(monkeypatch, "manager", ["sales:*"])
    monkeypatch.setattr("services.session._persist_token", lambda t: None)
    monkeypatch.setattr("services.session._persist_role", lambda r: None)
    Session.clear_token()
    assert Session._allowed is None and not Session.can("sales:sale:create")


def test_role_dropdown_uses_server_roles_and_falls_back(monkeypatch):
    sign_in_as(monkeypatch, "manager", server_allowed("manager"))
    svc = IamService(api=APIClient())
    monkeypatch.setattr(svc, "roles", lambda: [{"label": "Shop supervisor", "key": "shop_supervisor"}])
    assert svc.role_choices() == [("Shop supervisor", "shop_supervisor")]

    def old_server():
        raise APIError(404, "Not Found")

    monkeypatch.setattr(svc, "roles", old_server)
    assert ("Worker", "worker") in svc.role_choices()
    sign_in_as(monkeypatch, "worker", server_allowed("worker"))  # no iam:role:read: no call at all
    monkeypatch.setattr(svc, "roles", lambda: pytest.fail("must not ask"))
    assert ("Owner", "owner") in svc.role_choices()


def test_policy_document_round_trip():
    doc = policy_document(["sales:sale:create", "items:item:read"])
    assert doc["statements"][0]["effect"] == "Allow"
    known = ["sales:sale:create", "sales:sale:read", "items:item:read", "payroll:payment:create"]
    assert allowed_in(doc, known) == {"sales:sale:create", "items:item:read"}
    assert allowed_in({"statements": [{"effect": "Allow", "actions": ["sales:*"]}]}, known) == {"sales:sale:create", "sales:sale:read"}
