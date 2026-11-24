"""
services/report_service.py

Reporting domain service — dashboards, sales reports, inventory reports.
Aligned with actual backend routes:
  - GET /reports/sales        -> SalesReportResponse
  - GET /reports/inventory    -> List[InventoryReportResponse]
  - GET /dashboard/summary    -> {today_sales_count, today_revenue, low_stock_count, ...}
  - GET /machines/due         -> machines overdue for service or due soon
  - GET /budgets/warnings     -> budgets that are 80% used or over
"""

from services.api_client import APIClient
from services.session import Session


class ReportService:
    """Business reporting operations."""

    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _token(self) -> str:
        return Session.get_token()

    def get_sales_report(
        self, start_date: str = None, end_date: str = None
    ) -> dict | None:
        """
        GET /reports/sales
        Returns: {total_sales, total_orders, total_revenue, total_tax, total_discount}
        """
        return self._api.get_sales_report(self._token(), start_date, end_date)

    def get_gst_summary(self, start_date: str, end_date: str) -> dict | None:
        """GET /reports/gst-summary: {taxable_value, cgst_total, sgst_total, igst_total, total_tax}"""
        try:
            return self._api._get("/reports/gst-summary", self._token(), params={"start_date": start_date, "end_date": end_date}, quiet=True)
        except Exception:  # forbidden, offline or an older server: the panel says it could not load
            return None

    def get_inventory_report(self) -> list:
        """
        GET /reports/inventory
        Returns: [{item_id, name, sku, current_stock, min_stock, is_low_stock}, ...]
        """
        return self._api.get_inventory_report(self._token()) or []

    def get_dashboard_summary(self) -> dict | None:
        """
        GET /dashboard/summary
        Returns: {today_sales_count, today_revenue, low_stock_count, pending_wages_total, top_products}
        """
        return self._api.get_dashboard_summary(self._token())

    def get_attention(self, within_days: int = 14) -> dict:
        """
        What needs the owner's eye on Home: machines due for service and budgets close to
        or over their limit. Each list is empty when the server refuses it (the person may
        not hold that permission) or cannot be reached, so Home never shows an error for it.
        """
        out = {"machines": [], "budgets": []}
        for key, path, params in (
            ("machines", "/machines/due", {"within_days": within_days}),
            ("budgets", "/budgets/warnings", None),
        ):
            try:
                out[key] = self._api._get(path, self._token(), params=params, quiet=True) or []
            except Exception:  # forbidden, offline or an older server: leave it out
                out[key] = []
        return out

    def get_low_stock_items(self) -> list:
        """Filter inventory report for low-stock items only."""
        items = self.get_inventory_report()
        return [item for item in items if item.get("is_low_stock", False)]
