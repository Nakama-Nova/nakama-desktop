"""
services/report_service.py

Reporting domain service — dashboards, sales reports, inventory reports.
Aligned with actual backend routes:
  - GET /reports/sales        -> SalesReportResponse
  - GET /reports/inventory    -> List[InventoryReportResponse]
  - GET /dashboard/summary    -> {today_sales_count, today_revenue, low_stock_count, ...}
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

    def get_low_stock_items(self) -> list:
        """Filter inventory report for low-stock items only."""
        items = self.get_inventory_report()
        return [item for item in items if item.get("is_low_stock", False)]
