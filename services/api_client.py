"""
services/api_client.py

Thin HTTP transport layer. Handles only network calls and token injection.
No business logic lives here — domain services call these methods.

Routes aligned with actual backend API endpoints:
  - /auth/login
  - /items (GET, POST)
  - /customers (GET, POST), /customers/{id} (PUT, DELETE), /customers/search
  - /sales (GET, POST), /sales/{id}, /sales/{id}/items
  - /invoices/{number}/pdf
  - /reports/sales, /reports/inventory
  - /dashboard/summary
  - /sync/push, /sync/pull
"""

import json
import os
import sys
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")

# (connect, read) seconds. Without these a stalled server freezes the whole window
# for ever, because every call runs on the screen's own thread.
REQUEST_TIMEOUT = (5, 30)
UPLOAD_TIMEOUT = (5, 120)  # photos and models are bigger


def insecure_remote(url: str) -> bool:
    """True for plain http:// to a server outside this PC and the shop's own network."""
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme != "http":
        return False
    host = (parsed.hostname or "").lower()
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local"):
        return False
    parts = host.split(".")
    if len(parts) == 4 and all(p.isdigit() for p in parts):
        a, b = int(parts[0]), int(parts[1])
        if a == 10 or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31) or a == 127:
            return False
    return True


class APIError(Exception):
    """Raised when an API call fails."""

    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        self.reported = False  # already shown to the user via the global hook
        super().__init__(f"{self._plain(detail) or 'API Error'} ({status_code})")

    @staticmethod
    def _plain(detail: str) -> str:
        """The server's own reason ("Supplier is on past purchases...") instead of raw JSON."""
        try:
            d = json.loads(detail)["detail"]
        except (ValueError, KeyError, TypeError):
            return str(detail)
        if isinstance(d, str):
            return d
        if isinstance(d, dict) and isinstance(d.get("message"), str):
            return d["message"]
        if isinstance(d, list) and d and isinstance(d[0], dict):
            loc = ".".join(str(x) for x in d[0].get("loc", [])[1:])
            return f"{loc}: {d[0].get('msg', 'invalid')}" if loc else d[0].get("msg", "invalid")
        return str(detail)


class ForbiddenError(APIError):
    """Raised when the user doesn't have permission for an action (403)."""

    pass


class APIClient:
    """Low-level HTTP client for the Nakama backend."""

    def __init__(self, base_url: str = BASE_URL):
        self._base_url = base_url

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _fail(response, quiet: bool = False) -> APIError:
        """Build the APIError and, unless it's a 404 (a normal "not found") or a
        background call, surface it through the global exception hook so the user
        sees why a screen is empty instead of failing silently."""
        err = APIError(response.status_code, response.text)
        if not quiet and response.status_code != 404:
            sys.excepthook(type(err), err, None)
            err.reported = True
        return err

    def _get(
        self, path: str, token: str, params: dict | None = None, quiet: bool = False
    ) -> Any:
        response = requests.get(
            f"{self._base_url}{path}",
            headers=self._headers(token),
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 403:
            raise ForbiddenError(
                403, "Access Denied: You don't have permission for this action."
            )
        if response.status_code != 200:
            raise self._fail(response, quiet)
        return response.json()

    def _post(
        self,
        path: str,
        token: str,
        json: dict | None = None,
        data: dict | None = None,
        params: dict | None = None,
        quiet: bool = False,
    ) -> Any:
        response = requests.post(
            f"{self._base_url}{path}",
            headers=self._headers(token),
            json=json,
            data=data,
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 403:
            raise ForbiddenError(
                403, "Access Denied: You don't have permission for this action."
            )
        if response.status_code not in (200, 201, 204):
            raise self._fail(response, quiet)
        return response.json() if response.status_code != 204 else {}

    def _put(self, path: str, token: str, json: dict) -> Any:
        response = requests.put(
            f"{self._base_url}{path}",
            headers=self._headers(token),
            json=json,
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 403:
            raise ForbiddenError(
                403, "Access Denied: You don't have permission for this action."
            )
        if response.status_code != 200:
            raise self._fail(response)
        return response.json()

    def _delete(self, path: str, token: str) -> bool:
        response = requests.delete(
            f"{self._base_url}{path}",
            headers=self._headers(token),
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 403:
            raise ForbiddenError(
                403, "Access Denied: You don't have permission for this action."
            )
        if response.status_code == 409:  # "in use": tell the user why
            raise self._fail(response)
        return response.status_code in (200, 204)

    def _patch(self, path: str, token: str, json: dict | None = None) -> Any:
        response = requests.patch(
            f"{self._base_url}{path}",
            headers=self._headers(token),
            json=json,
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 403:
            raise ForbiddenError(
                403, "Access Denied: You don't have permission for this action."
            )
        if response.status_code != 200:
            raise self._fail(response)
        return response.json()

    def _upload(self, path: str, token: str, file_path: str, alt: str = "") -> Any:
        """Send one file as multipart (product photos and models)."""
        ext = os.path.splitext(file_path)[1].lower()
        content_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".glb": "model/gltf-binary",
        }.get(ext, "application/octet-stream")  # the server checks the type
        with open(file_path, "rb") as f:
            response = requests.post(
                f"{self._base_url}{path}",
                headers=self._headers(token),
                files={"file": (os.path.basename(file_path), f, content_type)},
                data={"alt": alt} if alt else None,
                timeout=UPLOAD_TIMEOUT,
            )
        if response.status_code == 403:
            raise ForbiddenError(
                403, "Access Denied: You don't have permission for this action."
            )
        if response.status_code not in (200, 201):
            raise self._fail(response)
        return response.json()

    def _get_bytes(self, path: str, token: str) -> bytes | None:
        response = requests.get(
            f"{self._base_url}{path}",
            headers=self._headers(token),
            timeout=UPLOAD_TIMEOUT,
        )
        if response.status_code == 403:
            raise ForbiddenError(
                403, "Access Denied: You don't have permission for this action."
            )
        return response.content if response.status_code == 200 else None

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------
    def login(self, username: str, password: str) -> dict | None:
        response = requests.post(
            f"{self._base_url}/auth/login",
            data={"username": username, "password": password},
            timeout=REQUEST_TIMEOUT,
        )
        if response.status_code == 429:
            # too many wrong passwords: say so instead of "wrong password"
            raise APIError(429, response.text)
        return response.json() if response.status_code == 200 else None

    # ------------------------------------------------------------------
    # Items  (ItemResponse fields: id, sku, name, selling_price,
    #         purchase_price, gst_percent, current_stock, min_stock, ...)
    # ------------------------------------------------------------------
    def get_items(self, token: str) -> list | None:
        """Every item: the API returns at most 100 per call, so read page by page."""
        items: list = []
        try:
            while True:
                page = self._get(
                    "/items/", token, params={"limit": 100, "offset": len(items)}
                )
                items.extend(page)
                if len(page) < 100:
                    return items
        except ForbiddenError:
            raise
        except APIError:
            return None

    # ------------------------------------------------------------------
    # 3D Lab  (furniture parts; the viewer/editor are web pages on the backend)
    # ------------------------------------------------------------------
    def get_lab_items(self, token: str) -> list | None:
        try:
            return self._get("/lab/items", token)
        except ForbiddenError:
            raise
        except APIError:
            return None

    def create_lab_link(self, token: str, item_id: str, mode: str = "view") -> dict | None:
        """POST /lab/links -> {url, path, expires_in}: a 10-minute link that opens the Lab."""
        try:
            return self._post("/lab/links", token, json={"item_id": item_id, "mode": mode})
        except ForbiddenError:
            raise
        except APIError:
            return None

    # ------------------------------------------------------------------
    # Customers  (CustomerResponse fields: id, name, phone, email,
    #             address, pincode, gstin, customer_type, created_at)
    # ------------------------------------------------------------------
    def get_customers(self, token: str) -> list | None:
        try:
            return self._get("/customers", token)
        except ForbiddenError:
            raise
        except APIError:
            return None

    def create_customer(
        self, token: str, name: str, phone: str = None, address: str = None
    ) -> dict | None:
        try:
            return self._post(
                "/customers",
                token,
                json={"name": name, "phone": phone, "address": address},
            )
        except ForbiddenError:
            raise
        except APIError:
            return None

    def search_customer_by_phone(self, token: str, phone: str) -> dict | None:
        try:
            return self._get("/customers/search", token, params={"phone": phone})
        except APIError:
            return None

    def get_customer_by_phone(self, token: str, phone: str) -> dict | None:
        customers = self.get_customers(token)
        if not customers:
            return None
        return next((c for c in customers if c.get("phone") == phone), None)

    def update_customer(
        self,
        token: str,
        customer_id: str,
        name: str,
        phone: str = None,
        address: str = None,
    ) -> dict | None:
        try:
            return self._put(
                f"/customers/{customer_id}",
                token,
                json={"name": name, "phone": phone, "address": address},
            )
        except APIError:
            return None

    def delete_customer(self, token: str, customer_id: str) -> bool:
        return self._delete(f"/customers/{customer_id}", token)

    # ------------------------------------------------------------------
    # Sales  (SaleResponse fields: id, invoice_number, customer_id,
    #         total_amount, created_at, items: [SaleItemResponse])
    # ------------------------------------------------------------------
    def create_sale(
        self, token: str, items: list, customer_id: str | None = None
    ) -> dict | None:
        """
        POST /sales
        items: [{"item_id": "<uuid>", "quantity": int}, ...]
        """
        payload: dict[str, Any] = {"items": items}
        if customer_id is not None:
            payload["customer_id"] = customer_id
        try:
            return self._post("/sales", token, json=payload)
        except ForbiddenError:
            raise
        except APIError:
            return None

    def get_sales(
        self, token: str, customer_id: str = None, date: str = None
    ) -> list | None:
        params: dict[str, Any] = {}
        if customer_id:
            params["customer_id"] = customer_id
        if date:
            params["date"] = date
        try:
            return self._get("/sales", token, params=params or None)
        except APIError:
            return None

    def get_sale_details(self, token: str, sale_id: str) -> dict | None:
        try:
            return self._get(f"/sales/{sale_id}", token)
        except APIError:
            return None

    def get_sale_items(self, token: str, sale_id: str) -> list | None:
        try:
            return self._get(f"/sales/{sale_id}/items", token)
        except APIError:
            return None

    # ------------------------------------------------------------------
    # Invoices
    # ------------------------------------------------------------------
    def get_invoice_pdf(self, token: str, invoice_number: str) -> bytes | None:
        return self._get_bytes(f"/invoices/{invoice_number}/pdf", token)

    # ------------------------------------------------------------------
    # Reports  (actual backend routes)
    #   GET /reports/sales          -> SalesReportResponse
    #   GET /reports/inventory      -> List[InventoryReportResponse]
    #   GET /dashboard/summary      -> {today_sales_count, today_revenue, low_stock_count, ...}
    # ------------------------------------------------------------------
    def get_sales_report(
        self, token: str, start_date: str = None, end_date: str = None
    ) -> dict | None:
        """GET /reports/sales — SalesReportResponse"""
        params: dict[str, str] = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        try:
            return self._get("/reports/sales", token, params=params or None)
        except APIError:
            return None

    def get_inventory_report(self, token: str) -> list | None:
        """GET /reports/inventory — List[InventoryReportResponse]"""
        try:
            return self._get("/reports/inventory", token)
        except APIError:
            return None

    def get_dashboard_summary(self, token: str) -> dict | None:
        """GET /dashboard/summary"""
        try:
            return self._get("/dashboard/summary", token)
        except APIError:
            return None

    # ------------------------------------------------------------------
    # Attendance / Workforce
    # ------------------------------------------------------------------
    def get_users(self, token: str) -> list | None:
        """GET /auth/ — list all users (admin only)"""
        try:
            return self._get("/auth/", token)
        except APIError:
            return None

    def check_in(self, token: str, user_id: str) -> dict | None:
        """POST /attendance/check-in"""
        try:
            return self._post("/attendance/check-in", token, params={"user_id": user_id})
        except ForbiddenError:
            raise
        except APIError:
            return None

    def check_out(self, token: str, attendance_id: str) -> dict | None:
        """POST /attendance/check-out"""
        try:
            return self._post(
                "/attendance/check-out", token, params={"attendance_id": attendance_id}
            )
        except ForbiddenError:
            raise
        except APIError:
            return None

    def get_my_attendance(self, token: str) -> list | None:
        """GET /attendance/my"""
        try:
            return self._get("/attendance/my", token)
        except APIError:
            return None

    def get_all_attendance(
        self,
        token: str,
        user_id: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> list | None:
        """GET /attendance/all"""
        params: dict[str, Any] = {}
        if user_id:
            params["user_id"] = user_id
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        try:
            return self._get("/attendance/all", token, params=params or None)
        except APIError:
            return None

    # ------------------------------------------------------------------
    # Sync endpoints
    # ------------------------------------------------------------------
    def push_sync(self, token: str, operations: list[dict]) -> dict | None:
        """POST /sync/push — upload outbox operations."""
        try:
            return self._post(
                "/sync/push", token, json={"operations": operations}, quiet=True
            )
        except APIError:
            return None

    def pull_sync(self, token: str, last_sync: str) -> dict | None:
        """GET /sync/pull — download incremental updates."""
        try:
            return self._get(
                "/sync/pull", token, params={"last_sync": last_sync}, quiet=True
            )
        except APIError:
            return None

    def health_check(self) -> bool:
        """Check if the backend is reachable."""
        try:
            response = requests.get(f"{self._base_url}/health", timeout=3)
            return response.status_code == 200
        except requests.RequestException:  # refused, DNS, timeout...
            return False
