"""The committed React bundle and its source follow the project rules."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "ui" / "web"
SOURCES = [p for p in (WEB / "src").rglob("*") if p.suffix in {".ts", ".tsx", ".css"}]


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


def test_source_has_no_external_urls_and_no_forbidden_words():
    for path in SOURCES:
        text = path.read_text()
        assert not re.search(r"https?://", text), f"external URL in {path.name}"
        for word in ("WeBank Factoring", "immutable", "tamper-proof"):
            assert word.lower() not in text.lower(), f"{word} in {path.name}"


def test_design_system_colours_are_the_only_ones_used():
    css = (WEB / "src" / "styles.css").read_text()
    allowed = {"#0c0d0e", "#16181a", "#2a2d30", "#f4f4f3", "#8a8d90", "#c5a059", "#7fa88b", "#cc5f52", "#55585b"}
    used = {c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}\b", css)}
    assert used <= allowed, used - allowed
    assert not re.search(r"gradient|backdrop-filter|box-shadow:\s*0 0", css)


def test_no_chart_or_ui_library_dependencies():
    import json

    deps = json.loads((WEB / "package.json").read_text())["dependencies"]
    assert not {"recharts", "chart.js", "d3", "plotly.js", "antd", "@mui/material", "tailwindcss"} & set(deps)
