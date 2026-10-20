"""The React web app (frontend/) follows the project rules. The built bundle in frontend/dist is committed."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "frontend"
DIST = WEB / "dist"
SRC = WEB / "src"


def _sources():
    return [p for p in SRC.rglob("*") if p.suffix in {".ts", ".tsx", ".css", ".json"}]


def test_built_bundle_exists_and_every_asset_it_references_exists():
    for page in ("index.html", "app.html"):
        html = (DIST / page).read_text()
        refs = re.findall(r'(?:src|href)="(/assets/[^"]+)"', html)
        assert refs, f"{page} references no assets (run `make web-build`)"
        for ref in refs:
            assert (DIST / ref.lstrip("/")).is_file(), ref


def test_web_ui_loads_nothing_external_and_never_stores_tokens_persistently():
    """CSP is 'self' only: no CDN, no web fonts. Sessions live in sessionStorage, never localStorage."""
    for path in list(DIST.glob("*.html")) + list((DIST / "assets").glob("*.css")):
        text = path.read_text()
        assert not re.search(r"(?:src|href|url\()\s*=?\s*[\"']?https?://", text), f"external resource in {path.name}"
        assert "fonts.googleapis" not in text
    session = (SRC / "shared" / "api" / "session.ts").read_text()
    assert "sessionStorage" in session and not re.search(r"localStorage\.", session)
    assert "Authorization" in (SRC / "shared" / "api" / "client.ts").read_text()


def test_web_ui_never_calculates_money():
    """The browser renders backend figures; no APR / interest arithmetic in the UI code."""
    for path in _sources():
        if path.suffix in {".ts", ".tsx"}:
            assert not re.search(r"[*/]\s*365\b|\b365\s*[*/]", path.read_text()), f"day-count arithmetic in {path}"


def test_web_app_has_no_forbidden_claims():
    for path in _sources() + list(DIST.glob("*.html")):
        text = path.read_text().lower()
        for word in ("webank factoring", "immutable", "tamper-proof"):
            assert word not in text, f"{word} in {path.name}"


def test_there_is_one_web_app_with_a_landing_and_a_workspace_entry():
    assert (WEB / "index.html").is_file() and (WEB / "app.html").is_file()
    assert (SRC / "entries" / "landing.tsx").is_file() and (SRC / "entries" / "workspace.tsx").is_file()
    assert not (WEB.parent / "ui" / "web").exists(), "the old no-build UI was removed; do not bring a second UI back"
