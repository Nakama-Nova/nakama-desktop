"""Qt's clicked(bool) passes `checked`; decorated handlers must not choke on it."""

from services.api_client import ForbiddenError
from ui.errors import handle_permissions


class Screen:
    def __init__(self):
        self.calls = []

    @handle_permissions
    def no_args(self):
        self.calls.append("no_args")
        return "ok"

    @handle_permissions
    def one_arg(self, row):
        self.calls.append(("one_arg", row))

    @handle_permissions
    def forbidden(self):
        raise ForbiddenError(403, "nope")


def test_extra_checked_argument_is_dropped():
    s = Screen()
    assert s.no_args(False) == "ok"  # what clicked(bool) sends
    assert s.no_args() == "ok"
    assert s.calls == ["no_args", "no_args"]


def test_real_arguments_are_kept():
    s = Screen()
    s.one_arg(7)
    assert s.calls == [("one_arg", 7)]


def test_forbidden_shows_a_warning_not_a_crash(qapp, dialogs):
    assert Screen().forbidden(False) is None
    assert dialogs and dialogs[0][0] == "warning"
