"""
ui/errors.py

Global UI error handlers and decorators.
"""

import inspect
from functools import wraps
from PyQt6.QtWidgets import QMessageBox
from services.api_client import ForbiddenError


def handle_permissions(func):
    """Decorator to catch ForbiddenError and show a themed warning box."""

    # Qt's clicked(bool) always passes `checked`. A plain method drops it
    # silently, but this wrapper takes *args, so without trimming, every
    # decorated button handler raised "takes 1 positional argument".
    params = list(inspect.signature(func).parameters.values())[1:]  # skip self
    takes_varargs = any(p.kind is p.VAR_POSITIONAL for p in params)
    max_positional = sum(
        p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD) for p in params
    )

    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if not takes_varargs:
            args = args[:max_positional]
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
