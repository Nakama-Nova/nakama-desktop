"""
services/session.py

Encapsulated session state. Provides controlled access to the auth token
and sync metadata instead of a bare mutable class attribute.

Backward compatibility: Session.token still works via a custom metaclass
descriptor, so existing code doesn't break during migration.
"""

from services.enums import UserRole


class _SessionMeta(type):
    """Metaclass providing backward-compatible `Session.token` access."""

    @property
    def token(cls) -> str | None:
        return cls._token

    @token.setter
    def token(cls, value: str | None) -> None:
        cls._token = value

    @property
    def role(cls) -> UserRole | None:
        return cls._role

    @role.setter
    def role(cls, value: UserRole | None) -> None:
        cls._role = value


class Session(metaclass=_SessionMeta):
    """Application-wide session singleton (class-level state)."""

    _token: str | None = None
    _role: UserRole | None = None
    _last_sync_at: datetime | None = None

    @classmethod
    def get_token(cls) -> str | None:
        return cls._token

    @classmethod
    def set_token(cls, token: str) -> None:
        cls._token = token

    @classmethod
    def get_role(cls) -> UserRole | None:
        return cls._role

    @classmethod
    def set_role(cls, role: str | UserRole | None) -> None:
        if isinstance(role, str):
            cls._role = UserRole(role)
        else:
            cls._role = role

    @classmethod
    def clear_token(cls) -> None:
        cls._token = None
        cls._role = None

    @classmethod
    def is_authenticated(cls) -> bool:
        return cls._token is not None

    @classmethod
    def get_last_sync(cls) -> datetime | None:
        return cls._last_sync_at

    @classmethod
    def set_last_sync(cls, ts: datetime) -> None:
        cls._last_sync_at = ts