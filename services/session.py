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
from fnmatch import fnmatchcase
from typing import Callable

from services.builtin_roles import BUILTIN_ACTIONS

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
    def role(cls) -> str | None:
        return cls._role

    @role.setter
    def role(cls, value: str | None) -> None:
        cls._role = value


class Session(metaclass=_SessionMeta):
    """Application-wide session singleton (class-level state)."""

    _token: str | None = None
    _role: str | None = None  # the role's key: a built-in one or any custom role
    _allowed: list[str] | None = None  # actions from GET /iam/me; None = not known (old server)
    _by_plant_unit: dict[str, list[str]] = {}
    _remember: bool = True  # False: the login lives only until the program closes
    _last_sync_at: datetime | None = None

    @classmethod
    def get_token(cls) -> str | None:
        return cls._token

    @classmethod
    def set_remember(cls, remember: bool) -> None:
        """Whether the sign-in is kept on this PC for next time ("Remember me")."""
        cls._remember = remember
        if not remember:
            _persist_token(None)
            _persist_role(None)

    @classmethod
    def set_token(cls, token: str) -> None:
        cls._token = token
        if cls._remember:
            _persist_token(token)

    @classmethod
    def get_role(cls) -> str | None:
        return cls._role

    @classmethod
    def set_role(cls, role: str | None) -> None:
        cls._role = getattr(role, "value", role) or None  # a UserRole member is also fine
        if cls._remember:
            _persist_role(cls._role)

    @classmethod
    def set_permissions(cls, me: dict | None) -> None:
        """Keep what GET /iam/me said. None (an old server: 404) means "not known": can()
        then answers from the built-in role table, as when roles were a fixed list."""
        if me is None:
            cls._allowed, cls._by_plant_unit = None, {}
            return
        cls._allowed = list(me.get("allowed") or [])
        cls._by_plant_unit = dict(me.get("by_plant_unit") or {})
        if me.get("role"):
            cls.set_role(me["role"])

    @classmethod
    def refresh_permissions(cls, api=None) -> None:
        """Ask the server what this user may do. A 404 means an old server; a server that
        cannot be reached keeps whatever was known (or the built-in table)."""
        from services.api_client import APIClient, APIError

        try:
            cls.set_permissions((api or APIClient()).get_my_permissions(cls._token))
        except APIError:
            logger.warning("Could not read /iam/me; keeping the permissions already known")
        except Exception:
            logger.warning("Server unreachable; keeping the permissions already known")

    @classmethod
    def can(cls, action: str, plant_unit_id: str | None = None) -> bool:
        """May the signed-in user do `action` (e.g. "payroll:payment:create")? A wildcard on
        either side matches ("payroll:*" asks: any payroll action). With a plant unit, what
        was granted for that unit counts too."""
        allowed = cls._allowed
        if allowed is None:  # old server: the role decides
            allowed = BUILTIN_ACTIONS.get(cls._role or "", ())
        patterns = list(allowed)
        if plant_unit_id is not None:
            patterns += cls._by_plant_unit.get(str(plant_unit_id), [])
        return any(fnmatchcase(action, p) or fnmatchcase(p, action) for p in patterns)

    @classmethod
    def can_any(cls, *actions: str) -> bool:
        return any(cls.can(a) for a in actions)

    @classmethod
    def clear_token(cls) -> None:
        cls._token = None
        cls._role = None
        cls._allowed, cls._by_plant_unit = None, {}
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

        cls._role = role or None
        if expired and cls._role is None:
            return False  # nothing to show offline without knowing what they may use
        cls._token = token
        cls.refresh_permissions()  # server unreachable: the built-in table covers built-in roles
        return True
