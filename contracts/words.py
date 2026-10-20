"""Amounts and dates written out for contracts, in English and Vietnamese.

Vietnamese follows the reading used in contracts and on invoices: every three-digit group after the first is read in
full ("một nghìn không trăm mười lăm", "hai mươi nghìn không trăm linh một"), "mốt" for a final 1 after twenty, "lăm"
for a final 5 after ten. Groups that are entirely zero are skipped.
"""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

_EN_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve",
            "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
_EN_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_EN_SCALES = ["", "thousand", "million", "billion", "trillion"]
_VI_DIGITS = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]
_VI_SCALES = ["", "nghìn", "triệu", "tỷ", "nghìn tỷ"]

CURRENCY_WORDS = {
    "USD": {"en": ("United States dollars", "cents"), "vi": ("đô la Mỹ", "xu")},
    "EUR": {"en": ("euros", "cents"), "vi": ("euro", "xu")},
    "CNY": {"en": ("Chinese yuan", "fen"), "vi": ("nhân dân tệ", "xu")},
    "VND": {"en": ("Vietnamese dong", ""), "vi": ("đồng", "")},
    "JPY": {"en": ("Japanese yen", ""), "vi": ("yên Nhật", "")},
}
_EN_MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _en_group(n: int) -> str:
    h, rest = divmod(n, 100)
    words = []
    if h:
        words.append(_EN_ONES[h] + " hundred")
    if rest:
        if h:
            words.append("and")
        if rest < 20:
            words.append(_EN_ONES[rest])
        else:
            t, u = divmod(rest, 10)
            words.append(_EN_TENS[t] + ("-" + _EN_ONES[u] if u else ""))
    return " ".join(words)


def en_integer(n: int) -> str:
    if n < 0:
        raise ValueError("negative amounts are not written out")
    if n == 0:
        return "zero"
    groups, parts = [], []
    while n:
        n, g = divmod(n, 1000)
        groups.append(g)
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if not g:
            continue
        text = _en_group(g)
        if i == 0 and len(groups) > 1 and g < 100:
            text = "and " + text
        parts.append(text + (" " + _EN_SCALES[i] if _EN_SCALES[i] else ""))
    return " ".join(parts)


def _vi_group(n: int, full: bool) -> str:
    h, t, u = n // 100, (n // 10) % 10, n % 10
    words = []
    if full or h:
        words.append(_VI_DIGITS[h] + " trăm")
    if t == 0:
        if u and (full or h):
            words.append("linh " + _VI_DIGITS[u])
        elif u:
            words.append(_VI_DIGITS[u])
    elif t == 1:
        words.append("mười" + (" lăm" if u == 5 else " " + _VI_DIGITS[u] if u else ""))
    else:
        words.append(_VI_DIGITS[t] + " mươi" + (" mốt" if u == 1 else " lăm" if u == 5 else " " + _VI_DIGITS[u] if u else ""))
    return " ".join(words)


def vi_integer(n: int) -> str:
    if n < 0:
        raise ValueError("negative amounts are not written out")
    if n == 0:
        return "không"
    groups = []
    while n:
        n, g = divmod(n, 1000)
        groups.append(g)
    parts = []
    for i in range(len(groups) - 1, -1, -1):
        g = groups[i]
        if not g:
            continue
        parts.append(_vi_group(g, full=i != len(groups) - 1) + (" " + _VI_SCALES[i] if _VI_SCALES[i] else ""))
    return " ".join(parts)


def amount_in_words(amount: Decimal | float | str, currency: str, lang: str) -> str:
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole, cents = int(value), int((value - int(value)) * 100)
    major, minor = CURRENCY_WORDS.get(currency, {"en": (currency, "cents"), "vi": (currency, "xu")})[lang]
    if lang == "vi":
        text = f"{vi_integer(whole)} {major}"
        text += f" và {vi_integer(cents)} {minor}" if cents and minor else " chẵn"
    else:
        text = f"{en_integer(whole)} {major}"
        text += f" and {en_integer(cents)} {minor}" if cents and minor else " only"
    return text[0].upper() + text[1:]


def money(amount: Decimal | float | str, currency: str, lang: str) -> str:
    """USD 60,000.00 (English) or 60.000,00 USD (Vietnamese convention)."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    digits = 0 if currency in ("VND", "JPY") else 2
    text = f"{value:,.{digits}f}"
    if lang == "vi":
        return text.replace(",", "§").replace(".", ",").replace("§", ".") + f" {currency}"
    return f"{currency} {text}"


def long_date(iso: str, lang: str) -> str:
    d = date.fromisoformat(iso)
    return f"ngày {d.day:02d} tháng {d.month:02d} năm {d.year}" if lang == "vi" else f"{d.day} {_EN_MONTHS[d.month - 1]} {d.year}"
