"""
services/customer_service.py

Customer domain service — CRUD and lookup operations.
IDs are UUIDs (strings), not integers.
"""

from services.api_client import APIClient
from services.session import Session


class CustomerService:
    """Customer management operations."""

    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _token(self) -> str:
        return Session.get_token()

    def get_all(self) -> list:
        """Return all customers, or an empty list on failure."""
        return self._api.get_customers(self._token()) or []

    def create(self, name: str, phone: str = None, address: str = None, gstin: str = None) -> dict | None:
        return self._api.create_customer(self._token(), name, phone, address, gstin)

    def update(
        self, customer_id: str, name: str, phone: str = None, address: str = None, gstin: str = None
    ) -> dict | None:
        """Update customer, preserving fields the desktop doesn't edit."""
        return self._api.update_customer(
            self._token(), customer_id, name, phone, address, gstin
        )

    def delete(self, customer_id: str) -> bool:
        return self._api.delete_customer(self._token(), customer_id)

    def search_by_phone(self, phone: str) -> dict | None:
        """Find a customer by phone number via backend search endpoint."""
        return self._api.search_customer_by_phone(self._token(), phone)

    def ensure_customer(self, name: str, phone: str, gstin: str | None = None) -> str | None:
        """
        Ensure a customer exists — look up by phone, create if not found. A GSTIN given for a
        customer already on file is saved to them (the buyer's tax details for the bill).
        Returns the customer ID (UUID string) or None on failure.
        """
        customer = self.search_by_phone(phone)
        if customer:
            if gstin and gstin != (customer.get("gstin") or ""):
                self.update(customer["id"], customer.get("name") or name, phone, customer.get("address"), gstin)
            return customer.get("id")

        new_customer = self.create(name=name, phone=phone, address="", gstin=gstin)
        return new_customer.get("id") if new_customer else None
