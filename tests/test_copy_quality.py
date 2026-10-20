"""Product copy: every interface string exists in EN / VI / 中文, placeholders match, nothing misleading."""

import json
import re
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "ui" / "web" / "dist" / "assets"
ENTRY = re.compile(r'"([a-zA-Z0-9_.]+)":\s*\[\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*,\s*("(?:[^"\\]|\\.)*")\s*\]')


def _dictionary():
    text = (ASSETS / "i18n.js").read_text(encoding="utf-8")
    body = text[text.index("const D = {"): text.index("\n  };", text.index("const D = {"))]
    keys = re.findall(r'^\s*"([a-zA-Z0-9_.]+)":\s*\[', body, re.M) + re.findall(r'\],[ \t]*"([a-zA-Z0-9_.]+)":\s*\[', body)
    entries = {k: [json.loads(v) for v in vals] for k, *vals in ENTRY.findall(body)}
    return keys, entries


def test_every_key_is_defined_once_in_three_languages():
    keys, entries = _dictionary()
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    assert not dupes, dupes
    for key, (en, vi, zh) in entries.items():
        # ui.engineNote is shown only outside English, so its English text is empty on purpose.
        assert (en.strip() or key == "ui.engineNote") and vi.strip() and zh.strip(), key


def test_placeholders_match_across_languages():
    _, entries = _dictionary()
    for key, values in entries.items():
        sets = [set(re.findall(r"\{(\w+)\}", v)) for v in values]
        assert sets[0] == sets[1] == sets[2], key


def test_long_strings_are_actually_translated():
    _, entries = _dictionary()
    untranslated = [k for k, (en, vi, zh) in entries.items() if len(en) > 30 and (vi == en or zh == en)]
    assert not untranslated, untranslated


def test_every_key_used_by_the_pages_exists():
    _, entries = _dictionary()
    used = set()
    for name in ("app.js", "landing.js"):
        used |= set(re.findall(r'\bt\("([a-zA-Z0-9_.]+)"', (ASSETS / name).read_text(encoding="utf-8")))
    html = "".join((ASSETS.parent / p).read_text(encoding="utf-8") for p in ("index.html", "app.html"))
    used |= set(re.findall(r'data-i18n="([a-zA-Z0-9_.]+)"', html))
    missing = sorted(k for k in used if k not in entries and not k.endswith("."))  # "prefix." + variable keys are dynamic
    assert not missing, missing


def test_no_misleading_or_stiff_phrases():
    _, entries = _dictionary()
    banned = {0: ("tamper-proof", "guaranteed approval", "AI audits"),
              1: ("đường mô phỏng", "chứ không lập", "tự động kiểm toán", "đảm bảo được duyệt"),
              2: ("保证获批",)}
    for key, values in entries.items():
        for lang, phrases in banned.items():
            for phrase in phrases:
                assert phrase.lower() not in values[lang].lower(), (key, phrase)
