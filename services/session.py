"""
services/session.py

Encapsulated session state. Provides controlled access to the auth token
and sync metadata instead of a bare mutable class attribute.

Backward compatibility: Session.token still works via a custom metaclass
descriptor, so existing code doesn't break during migration.

Persistence: the token and role are also written to the OS credential
store (via `keyring` — Windows Credential Manager / macOS Keychain /
Linux Secret Service) so a restart doesn't force a re-login. Keyring
access is best-effort: if no backend is available (e.g. a headless CI
box), persistence is silently skipped and the in-memory session still
works exactly as before.
"""

import base64
import json
import logging
import time
from datetime import datetime
from typing import Callable

from services.enums import UserRole

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "NakamaDesk"
_KEYRING_TOKEN_KEY = "auth_token"
_KEYRING_ROLE_KEY = "auth_role"


def _keyring():
    """Import keyring lazily so a missing/broken backend can't break startup."""
    try:
        import keyring as _kr

        return _kr
    except Exception:
        logger.warning("keyring unavailable — session will not persist across restarts")
        return None


def _delete_password_quietly(kr, service: str, key: str) -> None:
    """delete_password raises if there's nothing to delete — that's the
    expected case on every fresh start / already-cleared session, not an
    error worth logging a traceback for."""
    try:
        kr.delete_password(service, key)
    except kr.errors.PasswordDeleteError:
        pass


def _persist_token(token: str | None) -> None:
    kr = _keyring()
    if kr is None:
        return
    try:
        if token:
            kr.set_password(_KEYRING_SERVICE, _KEYRING_TOKEN_KEY, token)
        else:
            _delete_password_quietly(kr, _KEYRING_SERVICE, _KEYRING_TOKEN_KEY)
    except Exception:
        logger.exception("Failed to persist session token to keyring")


def _persist_role(role: str | None) -> None:
    kr = _keyring()
    if kr is None:
        return
    try:
        if role:
            kr.set_password(_KEYRING_SERVICE, _KEYRING_ROLE_KEY, role)
        else:
            _delete_password_quietly(kr, _KEYRING_SERVICE, _KEYRING_ROLE_KEY)
    except Exception:
        logger.exception("Failed to persist session role to keyring")


def _token_payload(token: str) -> dict:
    """The JWT's claims, decoded without checking the signature (the server's job)."""
    payload_segment = token.split(".")[1]
    padded = payload_segment + "=" * (-len(payload_segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def _is_token_expired(token: str) -> bool:
    """
    Best-effort local expiry check by decoding the JWT's `exp` claim —
    no signature verification (that's the backend's job), just enough to
    avoid restoring a session that's obviously stale. Treats a token we
    can't parse as expired, so we fail safe back to the login screen.
    """
    try:
        exp = _token_payload(token).get("exp")
        return exp is None or time.time() >= exp
    except Exception:
        return True


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
        _persist_token(token)

    @classmethod
    def get_role(cls) -> UserRole | None:
        return cls._role

    @classmethod
    def set_role(cls, role: str | UserRole | None) -> None:
        if isinstance(role, str):
            cls._role = UserRole(role)
        else:
            cls._role = role
        _persist_role(cls._role.value if cls._role else None)

    @classmethod
    def clear_token(cls) -> None:
        cls._token = None
        cls._role = None
        _persist_token(None)
        _persist_role(None)

    @classmethod
    def get_user_id(cls) -> str | None:
        """Id of the signed-in user (the token's `sub`), or None if unknown."""
        if not cls._token:
            return None
        try:
            sub = _token_payload(cls._token).get("sub")
        except Exception:
            return None
        return str(sub) if sub else None

    @classmethod
    def is_authenticated(cls) -> bool:
        return cls._token is not None

    @classmethod
    def get_last_sync(cls) -> datetime | None:
        return cls._last_sync_at

    @classmethod
    def set_last_sync(cls, ts: datetime) -> None:
        cls._last_sync_at = ts

    @classmethod
    def is_authorized(cls, allowed_roles: list[UserRole] | UserRole) -> bool:
        """Check if the current user has one of the allowed roles."""
        if not cls._role:
            return False
        if isinstance(allowed_roles, UserRole):
            return cls._role == allowed_roles
        return cls._role in allowed_roles

    @classmethod
    def restore(cls, allow_expired: Callable[[], bool] | None = None) -> bool:
        """
        Attempt to restore a previously persisted session (called once at
        app startup, before deciding whether to show the login screen).

        An expired token is normally discarded. If `allow_expired` is given and
        returns True (the caller found the server unreachable), it is kept instead:
        signing in needs the server, but the counter must still open and bill
        offline. The server rejects the stale token later, which sends the user
        to sign in again.

        Returns True if a session was restored.
        """
        kr = _keyring()
        if kr is None:
            return False
        try:
            token = kr.get_password(_KEYRING_SERVICE, _KEYRING_TOKEN_KEY)
        except Exception:
            logger.exception("Failed to read persisted session token from keyring")
            return False

        if not token:
            return False
        expired = _is_token_expired(token)
        if expired and not (allow_expired and allow_expired()):
            _persist_token(None)
            _persist_role(None)
            return False

        role = None
        try:
            role = kr.get_password(_KEYRING_SERVICE, _KEYRING_ROLE_KEY)
        except Exception:
            logger.exception("Failed to read persisted session role from keyring")

        if role:
            try:
                cls._role = UserRole(role)
            except ValueError:
                cls._role = None
        if expired and cls._role is None:
            return False  # nothing to show offline without knowing what they may use
        cls._token = token
        return True
