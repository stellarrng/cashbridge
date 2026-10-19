"""The committed React bundle and its source follow the project rules."""

import re
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "ui" / "web"
SOURCES = [p for p in (WEB / "src").rglob("*") if p.suffix in {".ts", ".tsx", ".css"}]


def test_built_bundle_exists_and_every_asset_it_references_exists():
    index = (WEB / "dist" / "index.html").read_text()
    refs = re.findall(r'(?:src|href)="(/assets/[^"]+)"', index)
    assert refs, "index.html references no bundle"
    for ref in refs:
        assert (WEB / "dist" / ref.lstrip("/")).is_file(), ref


def test_fonts_are_local_or_system_fallback_not_fetched():
    """A React build can bundle fonts; our offline no-npm fallback uses system fonts."""
    index = (WEB / "dist" / "index.html").read_text()
    if 'content="zero-build-fallback"' in index:
        css = (WEB / "dist" / "assets" / "demo.css").read_text()
        assert "system-ui" in css and "fonts.googleapis" not in css
        assert not re.search(r"https?://", index + css)
        assert (WEB / "dist" / "assets" / "demo.js").is_file()
    else:
        assert list((WEB / "dist" / "assets").glob("*.woff2"))
        css = next((WEB / "dist" / "assets").glob("*.css")).read_text()
        assert "fonts.googleapis" not in css
        assert "http" not in re.sub(r"url\(data:[^)]*\)", "", css)


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
