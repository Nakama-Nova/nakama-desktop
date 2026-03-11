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