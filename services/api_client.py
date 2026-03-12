import requests

BASE_URL = "http://127.0.0.1:8000"


class APIClient:

    def login(self, username: str, password: str) -> dict | None:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            data={"username": username, "password": password},
        )
        return response.json() if response.status_code == 200 else None

    def get_items(self, token: str) -> list | None:
        """Fetch all inventory items from the backend."""
        response = requests.get(
            f"{BASE_URL}/items",
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.json() if response.status_code == 200 else None

    def create_sale(self, token: str, items: list, customer_id: int | None = None) -> dict | None:
        """
        POST /sales
        Payload matches backend SaleCreate: items + optional customer_id.
        items: [{"item_id": int, "quantity": int}, ...]
        Returns SaleResponse JSON containing id and invoice_number.
        """
        payload = {"items": items}
        if customer_id is not None:
            payload["customer_id"] = customer_id
        response = requests.post(
            f"{BASE_URL}/sales",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.json() if response.status_code in (200, 201) else None

    def get_invoice_pdf(self, token: str, invoice_number: str) -> bytes | None:
        """
        GET /invoices/{invoice_number}/pdf
        Returns raw PDF bytes or None on failure.
        """
        response = requests.get(
            f"{BASE_URL}/invoices/{invoice_number}/pdf",
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.content if response.status_code == 200 else None

    # --- Customer Management ---

    def get_customers(self, token: str) -> list | None:
        response = requests.get(
            f"{BASE_URL}/customers",
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.json() if response.status_code == 200 else None

    def create_customer(self, token: str, name: str, phone: str = None, address: str = None) -> dict | None:
        payload = {"name": name, "phone": phone, "address": address}
        response = requests.post(
            f"{BASE_URL}/customers",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.json() if response.status_code in (200, 201) else None

    def search_customer_by_phone(self, token: str, phone: str) -> dict | None:
        response = requests.get(
            f"{BASE_URL}/customers/search",
            params={"phone": phone},
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.json() if response.status_code == 200 else None

    def get_customer_by_phone(self, token: str, phone: str) -> dict | None:
        """Helper to find a customer by phone number from the full list."""
        customers = self.get_customers(token)
        if not customers:
            return None
        return next((c for c in customers if c.get("phone") == phone), None)

    def update_customer(self, token: str, customer_id: int, name: str, phone: str = None, address: str = None) -> dict | None:
        payload = {"name": name, "phone": phone, "address": address}
        response = requests.put(
            f"{BASE_URL}/customers/{customer_id}",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.json() if response.status_code == 200 else None

    def delete_customer(self, token: str, customer_id: int) -> bool:
        response = requests.delete(
            f"{BASE_URL}/customers/{customer_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.status_code == 200

    # --- Sales History ---

    def get_sales(self, token: str, customer_id: int = None, date: str = None) -> list | None:
        params = {}
        if customer_id: params["customer_id"] = customer_id
        if date: params["date"] = date
        response = requests.get(
            f"{BASE_URL}/sales",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.json() if response.status_code == 200 else None

    def get_sale_details(self, token: str, sale_id: int) -> dict | None:
        response = requests.get(
            f"{BASE_URL}/sales/{sale_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.json() if response.status_code == 200 else None

    def get_sale_items(self, token: str, sale_id: int) -> list | None:
        response = requests.get(
            f"{BASE_URL}/sales/{sale_id}/items",
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.json() if response.status_code == 200 else None

    # --- Reports ---

    def get_reports_daily(self, token: str) -> dict | None:
        response = requests.get(
            f"{BASE_URL}/reports/sales/daily",
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.json() if response.status_code == 200 else None

    def get_reports_summary(self, token: str) -> dict | None:
        response = requests.get(
            f"{BASE_URL}/reports/sales/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.json() if response.status_code == 200 else None

    def get_dashboard_summary(self, token: str) -> dict | None:
        response = requests.get(
            f"{BASE_URL}/dashboard/summary",
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.json() if response.status_code == 200 else None

    def get_low_stock_items(self, token: str) -> list | None:
        response = requests.get(
            f"{BASE_URL}/reports/inventory/low-stock",
            headers={"Authorization": f"Bearer {token}"},
        )
        return response.json() if response.status_code == 200 else None