"""Shared test hygiene: clear failed-attempt counters between tests (memory store) so one test cannot throttle another."""

import pytest

from security import auth


@pytest.fixture(autouse=True)
def _clear_login_throttle():
    yield
    manager = auth._manager
    if manager is not None and isinstance(manager.state, auth.MemorySessionState):
        with manager.state._lock:
            manager.state._failures.clear()
