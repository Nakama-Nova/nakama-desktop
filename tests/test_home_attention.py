"""Home lists machines due for service and budgets near their limit, from the backend."""

from services.api_client import ForbiddenError
from services.report_service import ReportService
from ui.dashboard_window import DashboardWindow, attention_lines


MACHINES = [
    {"name": "Band saw", "tag": "M-02", "service_due_on": "2026-11-10", "service_overdue": True},
    {"name": "Lathe", "tag": "M-05", "service_due_on": "2026-11-30", "service_overdue": False},
]
BUDGETS = [
    {"category": "raw_materials", "period": "month", "state": "warning", "percent_used": "86.0", "remaining": "14000"},
    {"category": "machines", "period": "financial_year", "state": "over", "percent_used": "112", "remaining": "-6000"},
]


def test_lines_say_what_is_wrong_and_put_the_worst_first():
    rows = attention_lines({"machines": MACHINES, "budgets": BUDGETS})
    assert [r[1] for r in rows] == ["danger", "danger", "warning", "warning"]
    texts = [r[0] for r in rows]
    assert "Band saw (M-02): service was due 2026-11-10" in texts
    assert "Machines budget this financial year: over by ₹6,000" in texts
    assert "Raw materials budget this month: 86% used, ₹14,000 left" in texts
    assert {r[2] for r in rows} == {"machines", "budgets"}


def test_nothing_to_report_hides_the_panel(qapp, monkeypatch):
    monkeypatch.setattr(ReportService, "get_attention", lambda self, within_days=14: {"machines": [], "budgets": []})
    monkeypatch.setattr(ReportService, "get_dashboard_summary", lambda self: {})
    w = DashboardWindow()
    w._show_attention({"machines": [], "budgets": []})
    assert not w.attention_card.isVisibleTo(w)


def test_panel_shows_rows_and_clicking_one_opens_its_page(qapp):
    w = DashboardWindow()
    opened = []
    w._navigate = opened.append
    w._show_attention({"machines": MACHINES, "budgets": BUDGETS})
    assert w.attention_card.isVisibleTo(w)
    assert w.attention_list.count() == 4
    w.attention_list.itemAt(0).widget().click()
    assert opened == ["machines"]


def test_a_refused_or_unreachable_server_just_leaves_the_lists_empty(monkeypatch):
    svc = ReportService()

    def refuse(path, token, params=None, quiet=False):
        raise ForbiddenError(403, "no")

    monkeypatch.setattr(svc._api, "_get", refuse)
    assert svc.get_attention() == {"machines": [], "budgets": []}


def test_attention_asks_the_two_backend_routes(monkeypatch):
    svc = ReportService()
    asked = []

    def fake(path, token, params=None, quiet=False):
        asked.append((path, params))
        return []

    monkeypatch.setattr(svc._api, "_get", fake)
    svc.get_attention()
    assert asked == [("/machines/due", {"within_days": 14}), ("/budgets/warnings", None)]
