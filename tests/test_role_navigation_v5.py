"""Guardrails for the least-privilege role-specific no-build workspace."""
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / 'ui/web/dist/assets/app.js'


def test_role_specific_navigation_is_based_on_server_permissions():
    js = APP.read_text()
    assert 'const ACCOUNTANT_NAV' in js
    assert 'const DIRECTOR_NAV' in js
    assert 'function navigationForUser()' in js
    assert 'can("sme:approve") && !can("sme:prepare")' in js
    assert 'can("sme:prepare") && !can("sme:approve")' in js
    assert 'const groups = navigationForUser();' in js


def test_route_is_restricted_to_displayed_navigation_and_falls_back_to_role_home():
    js = APP.read_text()
    assert 'navigationForUser().flatMap((group) => group[1])' in js
    assert 'const target = allowed.includes(name) ? name : home;' in js
    assert 'state.current = target === name ? hash : target;' in js


def test_demo_persona_switch_returns_to_new_roles_home():
    js = APP.read_text()
    assert 's.user.permissions.includes("sme:approve") ? "core" : "overview"' in js
