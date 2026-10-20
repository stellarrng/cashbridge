"""The committed no-build web app (ui/web/dist) follows the project rules."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "ui" / "web"


DIST = WEB / "dist"


def test_built_bundle_exists_and_every_asset_it_references_exists():
    for page in ("index.html", "app.html"):
        html = (DIST / page).read_text()
        refs = re.findall(r'(?:src|href)="(/assets/[^"]+)"', html)
        assert refs, f"{page} references no assets"
        for ref in refs:
            assert (DIST / ref.lstrip("/")).is_file(), ref


def test_web_ui_loads_nothing_external_and_never_stores_tokens_persistently():
    """CSP is 'self' only: no CDN, no web fonts. Sessions live in sessionStorage, never localStorage."""
    for path in list(DIST.glob("*.html")) + list((DIST / "assets").glob("*.*")):
        if path.suffix not in {".html", ".css", ".js"}:
            continue
        text = path.read_text()
        assert not re.search(r"(?:src|href|url\()\s*=?\s*[\"']?https?://", text), f"external resource in {path.name}"
        assert "fonts.googleapis" not in text
        assert "localStorage.setItem(\"cb.session" not in text and "localStorage.setItem('cb.session" not in text
    api = (DIST / "assets" / "api.js").read_text()
    assert "sessionStorage" in api and "Authorization" in api


def test_web_ui_never_calculates_money():
    """The browser renders backend figures; no APR / interest arithmetic in the UI code."""
    js = (DIST / "assets" / "app.js").read_text()
    assert not re.search(r"[*/]\s*365|365\s*[*/]", js) and "* 0.8" not in js


def test_web_app_has_no_forbidden_claims():
    for path in list(DIST.glob("*.html")) + list((DIST / "assets").glob("*.*")):
        text = path.read_text()
        for word in ("WeBank Factoring", "immutable", "tamper-proof"):
            assert word.lower() not in text.lower(), f"{word} in {path.name}"


def test_there_is_one_web_app_and_no_build_step():
    """No vendored chart/UI library, and no leftover React/Vite project whose build would overwrite dist."""
    assert sorted(p.name for p in (DIST / "assets").iterdir()) == [
        "api.js", "app.css", "app.js", "base.css", "charts.js", "config.js", "i18n.js", "landing.css", "landing.js", "premium-ui.css"]
    for leftover in ("src", "package.json", "vite.config.ts", "index.html"):
        assert not (WEB / leftover).exists(), leftover
