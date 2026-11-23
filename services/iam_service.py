"""
services/iam_service.py

Roles and policies on the server (/iam). A role is a label plus policies; a policy is a list
of allowed actions. The server refuses anything above the caller's own rights (403 with a
message worth showing), so this layer only shapes the requests.
"""

from fnmatch import fnmatchcase

from services.api_client import APIClient
from services.session import Session

# The built-in roles, shown when the server cannot list roles (too old, or no iam:role:read).
BUILTIN_ROLES = [
    ("Owner", "owner"),
    ("Manager", "manager"),
    ("Sales", "sales"),
    ("Achari (carpenter)", "achari"),
    ("Worker", "worker"),
    ("Artisan (restoration)", "artisan"),
    ("Accountant", "accountant"),
]


def policy_document(actions: list[str]) -> dict:
    return {"version": 1, "statements": [{"effect": "Allow", "actions": sorted(actions), "resources": ["*"]}]}


def allowed_in(document: dict, known: list[str]) -> set[str]:
    """Which of the known actions a policy document allows (its wildcards expanded)."""
    patterns = [a for st in document.get("statements", []) if st.get("effect") == "Allow" for a in st.get("actions", [])]
    return {a for a in known if any(fnmatchcase(a, p) for p in patterns)}


class IamService:
    def __init__(self, api: APIClient | None = None):
        self._api = api or APIClient()

    def _t(self) -> str:
        return Session.get_token()

    def roles(self) -> list:
        return self._api._get("/iam/roles", self._t()) or []

    def role_choices(self) -> list[tuple[str, str]]:
        """(label, key) for a role dropdown: the server's roles, else the built-in ones."""
        if Session.can("iam:role:read"):
            try:
                rows = self.roles()
                if rows:
                    return [(r["label"], r["key"]) for r in rows]
            except Exception:  # old server (404), refused, or unreachable: use the built-in list
                pass
        return list(BUILTIN_ROLES)

    def actions(self) -> list:
        return self._api._get("/iam/actions", self._t()) or []

    def policies(self) -> list:
        return self._api._get("/iam/policies", self._t()) or []

    def create_policy(self, name: str, actions: list[str]) -> dict:
        return self._api._post("/iam/policies", self._t(), json={"name": name, "document": policy_document(actions)})

    def update_policy(self, policy_id: str, name: str, actions: list[str]) -> dict:
        return self._api._put(f"/iam/policies/{policy_id}", self._t(), json={"name": name, "document": policy_document(actions)})

    def create_role(self, label: str, description: str, policy_ids: list[str]) -> dict:
        return self._api._post("/iam/roles", self._t(), json={"label": label, "description": description or None, "policy_ids": policy_ids})

    def update_role(self, role_id: str, label: str, description: str, policy_ids: list[str]) -> dict:
        return self._api._put(f"/iam/roles/{role_id}", self._t(), json={"label": label, "description": description or None, "policy_ids": policy_ids})

    def delete_role(self, role_id: str) -> bool:
        return self._api._delete(f"/iam/roles/{role_id}", self._t())

    def set_user_roles(self, user_id: str, assignments: list[dict]) -> dict:
        """Replace a person's EXTRA roles: [{"role_key": ..., "plant_unit_id": ... or None}]."""
        return self._api._put(f"/iam/users/{user_id}/roles", self._t(), json=assignments)
