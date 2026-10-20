"""Guardrails for the least-privilege, role-specific workspace navigation (React source in frontend/src)."""
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "frontend" / "src" / "features"
NAV = SRC / "workspace" / "nav.ts"
SHELL = SRC / "workspace" / "WorkspaceApp.tsx"
HOME = SRC / "auth" / "home.ts"


def test_role_specific_navigation_is_based_on_server_permissions():
    ts = NAV.read_text()
    assert "const ACCOUNTANT" in ts and "const DIRECTOR" in ts
    assert "export function navigationFor(user: SessionUser)" in ts
    assert 'user.permissions.includes("sme:approve")' in ts and 'user.permissions.includes("sme:prepare")' in ts
    assert "if (approve && !prepare) return DIRECTOR;" in ts
    assert "if (prepare && !approve) return ACCOUNTANT;" in ts


def test_route_is_restricted_to_displayed_navigation_and_falls_back_to_role_home():
    assert "navigationFor(user).flatMap((g) => [...g[1]])" in NAV.read_text()
    shell = SHELL.read_text()
    assert "allowedScreens(user).includes(route.name) ? route.name : home" in shell
    assert "window.location.replace(\"#\" + home)" in shell


def test_demo_persona_switch_returns_to_new_roles_home():
    ts = HOME.read_text()
    assert 'user.permissions.includes("sme:approve") ? "core" : "overview"' in ts
