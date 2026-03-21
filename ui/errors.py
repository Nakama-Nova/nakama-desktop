"""
ui/errors.py

Global UI error handlers and decorators.
"""

from functools import wraps
from PyQt6.QtWidgets import QMessageBox
from services.api_client import ForbiddenError


def handle_permissions(func):
    """Decorator to catch ForbiddenError and show a themed warning box."""

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except ForbiddenError:
            QMessageBox.warning(
                self if hasattr(self, "window") else None,
                "Access Denied",
                "You don’t have permission to perform this action.",
                QMessageBox.StandardButton.Ok,
            )
            return None

    return wrapper
