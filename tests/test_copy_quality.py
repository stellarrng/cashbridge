"""Product copy: every interface string exists in EN / VI / 中文, placeholders match, nothing misleading."""

import json
import re
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "frontend" / "src"
LOCALES = SRC / "shared" / "i18n" / "locales"
LANGS = ("en", "vi", "zh")


def _dictionary():
    """key -> [en, vi, zh]"""
    tables = [json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8")) for lang in LANGS]
    assert tables[0].keys() == tables[1].keys() == tables[2].keys(), "locale files define different keys"
    return {key: [t[key] for t in tables] for key in tables[0]}


def test_every_key_is_defined_in_three_languages():
    for key, (en, vi, zh) in _dictionary().items():
        # ui.engineNote is shown only outside English, so its English text is empty on purpose.
        assert (en.strip() or key == "ui.engineNote") and vi.strip() and zh.strip(), key


def test_placeholders_match_across_languages():
    for key, values in _dictionary().items():
        sets = [set(re.findall(r"\{(\w+)\}", v)) for v in values]
        assert sets[0] == sets[1] == sets[2], key


def test_long_strings_are_actually_translated():
    untranslated = [k for k, (en, vi, zh) in _dictionary().items() if len(en) > 30 and (vi == en or zh == en)]
    assert not untranslated, untranslated


def test_every_key_used_by_the_pages_exists():
    entries = _dictionary()
    prefixes = {k.split(".")[0] for k in entries}
    used = set()
    for path in SRC.rglob("*.ts*"):
        text = path.read_text(encoding="utf-8")
        used |= set(re.findall(r'\bt\("([a-zA-Z0-9_.]+)"', text))
        # keys kept in lists / tables and passed to t() later (nav titles, landing bullets...)
        used |= {s for s in re.findall(r'"([a-z0-9]+\.[A-Za-z0-9_.]+)"', text) if s.split(".")[0] in prefixes}
    # "prefix." + variable keys are dynamic; "sme.lan"-style demo ids are not copy
    missing = sorted(k for k in used if k not in entries and not k.endswith(".") and not k.startswith(("sme.", "bank.")))
    assert not missing, missing


def test_no_misleading_or_stiff_phrases():
    banned = {0: ("tamper-proof", "guaranteed approval", "AI audits"),
              1: ("đường mô phỏng", "chứ không lập", "tự động kiểm toán", "đảm bảo được duyệt"),
              2: ("保证获批",)}
    for key, values in _dictionary().items():
        for lang, phrases in banned.items():
            for phrase in phrases:
                assert phrase.lower() not in values[lang].lower(), (key, phrase)
