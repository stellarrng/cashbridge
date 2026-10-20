"""Contract drafting engine (v9): a complete, structured commercial contract in English, Vietnamese or both.

Deterministic clause library, no language model: every sentence below was written for this engine, and the inputs
are inserted only as data (validated, length-bounded, control characters refused). The output is one document model
(title, parties, recitals, numbered articles and sub-clauses, schedules, signature blocks) rendered three ways:
plain text (for the contract analyzer), the in-app preview, and a formatted Word file (contracts/docx_export.py).

Built for the export SMEs CashBridge serves:
* supply contracts carry an Incoterms(R) 2020 rule, the shipping documents a lender checks (invoice, packing list,
  bill of lading, certificate of origin) and a CISG statement;
* every contract permits the supplier to assign its receivables to a bank or factor (an anti-assignment clause would
  make the invoice unfinanceable) and requires call-back verification before a payee account may be altered
  (business-email-compromise fraud);
* construction contracts add retention, performance security and a defects-liability period.

It is a DRAFT for legal review, never legal advice: the cover note, header, watermark and checklist say so, defaults
that the user did not enter are listed as "to confirm", and nothing is signed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from contracts.words import amount_in_words, long_date, money

KINDS = ("supply", "services", "construction")
LANGS = ("en", "vi", "bilingual")
CURRENCIES = ("USD", "VND", "CNY", "EUR", "JPY")
INCOTERMS = ("EXW", "FCA", "CPT", "CIP", "DAP", "DPU", "DDP", "FAS", "FOB", "CFR", "CIF")
INSURANCE_TERMS = ("CIP", "CIF")
INSTITUTIONS = {
    "VIAC": ("the Vietnam International Arbitration Centre (VIAC)", "Trung tâm Trọng tài Quốc tế Việt Nam (VIAC)", "Ho Chi Minh City", "Thành phố Hồ Chí Minh"),
    "SIAC": ("the Singapore International Arbitration Centre (SIAC)", "Trung tâm Trọng tài Quốc tế Singapore (SIAC)", "Singapore", "Singapore"),
    "HKIAC": ("the Hong Kong International Arbitration Centre (HKIAC)", "Trung tâm Trọng tài Quốc tế Hồng Kông (HKIAC)", "Hong Kong", "Hồng Kông"),
    "CIETAC": ("the China International Economic and Trade Arbitration Commission (CIETAC)", "Ủy ban Trọng tài Kinh tế và Thương mại Quốc tế Trung Quốc (CIETAC)", "Shenzhen", "Thâm Quyến"),
}
MAX_TEXT = 1200
TODO = "[●]"
# Vietnamese labels for the open-items list (missing data and proposed defaults).
LABEL_VI = {
    "payment schedule": "lịch thanh toán", "contract date": "ngày ký hợp đồng", "dispute resolution": "phương thức giải quyết tranh chấp",
    "arbitration institution": "trung tâm trọng tài", "governing law": "luật áp dụng", "place of signing": "địa điểm ký",
    "payment term": "thời hạn thanh toán", "late-payment interest": "lãi chậm trả", "acceptance period": "thời hạn nghiệm thu",
    "warranty period": "thời hạn bảo hành", "liability cap": "mức giới hạn trách nhiệm", "Incoterms rule": "điều kiện Incoterms",
    "retention": "tỷ lệ tiền giữ lại", "defects-liability period": "thời hạn bảo hành công trình", "performance security": "bảo đảm thực hiện hợp đồng",
    "Incoterms named place": "địa điểm chỉ định theo Incoterms", "latest delivery (shipment) date": "ngày giao hàng (xếp hàng) muộn nhất",
    "service start and end dates": "ngày bắt đầu và kết thúc dịch vụ", "site address": "địa chỉ công trường", "completion date": "ngày hoàn thành",
    "Party A address": "địa chỉ Bên A", "Party A tax / registration number": "mã số thuế / số đăng ký Bên A",
    "Party A authorised representative": "người đại diện theo pháp luật / được ủy quyền của Bên A", "Party B address": "địa chỉ Bên B",
    "Party B tax / registration number": "mã số thuế / số đăng ký Bên B", "Party B authorised representative": "người đại diện theo pháp luật / được ủy quyền của Bên B",
}
CHECKLIST = [
    ("Complete every [●] item and confirm every proposed default", "Bổ sung mọi mục [●] và xác nhận mọi giá trị mặc định đề xuất"),
    ("Confirm party identities, registration numbers and signatory authority", "Xác minh thông tin pháp lý, mã số đăng ký và thẩm quyền ký của các bên"),
    ("Confirm the governing law, dispute forum and any mandatory local clauses with qualified counsel",
     "Xác nhận luật áp dụng, cơ quan giải quyết tranh chấp và các điều khoản bắt buộc theo pháp luật địa phương với luật sư"),
    ("Agree the Payee Account and verify it independently by telephone before any payment",
     "Thống nhất Tài khoản Nhận tiền và xác minh độc lập qua điện thoại trước mọi khoản thanh toán"),
    ("Attach and initial the detailed specifications (Schedule 1)", "Đính kèm và ký nháy thông số kỹ thuật chi tiết (Phụ lục 1)"),
    ("Have qualified counsel approve before signature", "Luật sư có chuyên môn phê duyệt trước khi ký"),
]


# --------------------------------------------------------------------------- validation
def _clean(value: Any, name: str, limit: int, required: bool = False) -> str:
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValueError(f"{name} is required")
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    text = value.strip()
    if len(text) > limit:
        raise ValueError(f"{name} exceeds {limit} characters")
    if any(ord(c) < 32 and c not in "\n\t" for c in text):
        raise ValueError(f"{name} contains control characters")
    return text


def _number(value: Any, name: str, lo: float, hi: float, default: Optional[float] = None) -> Optional[Decimal]:
    if value is None or value == "":
        return None if default is None else Decimal(str(default))
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not d.is_finite() or not Decimal(str(lo)) <= d <= Decimal(str(hi)):
        raise ValueError(f"{name} must be between {lo:g} and {hi:g}")
    return d


def _iso(value: Any, name: str) -> str:
    text = _clean(value, name, 10)
    if not text:
        return ""
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise ValueError(f"{name} must be a date (YYYY-MM-DD)") from exc


@dataclass
class Party:
    name: str
    address: str = ""
    tax_id: str = ""
    representative: str = ""
    title: str = ""
    email: str = ""
    phone: str = ""

    @classmethod
    def parse(cls, value: Any, role: str) -> "Party":
        if isinstance(value, str) or value is None:
            return cls(name=_clean(value, f"{role} name", 160, required=True))
        if not isinstance(value, dict):
            raise ValueError(f"{role} must be a name or an object")
        return cls(name=_clean(value.get("name"), f"{role} name", 160, required=True),
                   address=_clean(value.get("address"), f"{role} address", 300),
                   tax_id=_clean(value.get("tax_id"), f"{role} tax id", 40),
                   representative=_clean(value.get("representative"), f"{role} representative", 120),
                   title=_clean(value.get("title"), f"{role} title", 80),
                   email=_clean(value.get("email"), f"{role} email", 120),
                   phone=_clean(value.get("phone"), f"{role} phone", 40))


@dataclass
class Terms:
    kind: str
    lang: str
    supplier: Party
    customer: Party
    scope: str
    currency: str
    amount: Decimal
    milestones: List[Dict[str, Any]]
    contract_no: str
    contract_date: str
    place: str
    vat_pct: Optional[Decimal]
    payment_days: int
    late_interest_pct: Decimal
    acceptance_days: int
    warranty_months: int
    liability_cap_pct: Decimal
    governing_law: str
    governing_law_vi: str
    dispute: str
    institution: str
    incoterm: str = ""
    incoterm_place: str = ""
    delivery_date: str = ""
    start_date: str = ""
    end_date: str = ""
    site: str = ""
    completion_date: str = ""
    retention_pct: Decimal = Decimal("5")
    defects_months: int = 12
    performance_security_pct: Decimal = Decimal("10")
    prevailing: str = "en"
    defaulted: List[str] = field(default_factory=list)
    missing: List[str] = field(default_factory=list)


_DEFAULT_MILESTONES = {
    "supply": [("Advance payment after signing", "Tạm ứng sau khi ký hợp đồng", 30), ("Payment against shipping documents", "Thanh toán khi xuất trình chứng từ giao hàng", 70)],
    "services": [("Advance payment after signing", "Tạm ứng sau khi ký hợp đồng", 30), ("Payment on delivery of the deliverables", "Thanh toán khi bàn giao sản phẩm", 40),
                 ("Payment after written acceptance", "Thanh toán sau khi nghiệm thu bằng văn bản", 30)],
    "construction": [("Advance payment against an advance-payment guarantee", "Tạm ứng có bảo lãnh tạm ứng", 15), ("Progress payments on certified work", "Thanh toán theo khối lượng được xác nhận", 70),
                     ("Payment on taking-over of the works", "Thanh toán khi bàn giao công trình", 10), ("Release of retention after the defects-liability period", "Hoàn trả tiền giữ lại sau thời hạn bảo hành", 5)],
}


def parse_terms(data: Dict[str, Any]) -> Terms:
    defaulted: List[str] = []
    missing: List[str] = []

    def dflt(key: str, value: Any, label: str) -> Any:
        if data.get(key) in (None, ""):
            defaulted.append(label)
            return value
        return data.get(key)

    kind = _clean(data.get("contract_type", "supply"), "contract_type", 20).lower() or "supply"
    if kind not in KINDS:
        raise ValueError("contract_type must be supply, services or construction")
    lang = (_clean(data.get("language", "en"), "language", 10).lower() or "en")
    if lang not in LANGS:
        raise ValueError("language must be en, vi or bilingual")
    currency = (_clean(data.get("currency", "USD"), "currency", 3).upper() or "USD")
    if currency not in CURRENCIES:
        raise ValueError(f"currency must be one of {', '.join(CURRENCIES)}")
    amount = _number(data.get("amount"), "amount", 0.01, 1e10)
    if amount is None:
        raise ValueError("amount is required")
    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    raw_ms = data.get("milestones")
    if raw_ms in (None, []):
        defaulted.append("payment schedule")
        raw_ms = [{"event": en, "event_vi": vi, "percentage": pct} for en, vi, pct in _DEFAULT_MILESTONES[kind]]
    if not isinstance(raw_ms, list) or not 1 <= len(raw_ms) <= 8:
        raise ValueError("Provide between 1 and 8 payment milestones")
    milestones, allocated = [], Decimal("0")
    for i, row in enumerate(raw_ms):
        if not isinstance(row, dict):
            raise ValueError("Each milestone must be an object")
        pct = _number(row.get("percentage"), "milestone percentage", 0.01, 100)
        if pct is None:
            raise ValueError("Each milestone needs a percentage")
        event = _clean(row.get("event"), "milestone event", 180, required=True)
        # Amounts are cents-exact and add up to the price: the last milestone takes the rounding remainder.
        amt = (amount - allocated) if i == len(raw_ms) - 1 else (amount * pct / 100).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        allocated += amt
        milestones.append({"no": i + 1, "event": event, "event_vi": _clean(row.get("event_vi"), "milestone event (vi)", 180) or event,
                           "percentage": pct, "amount": amt})
    if abs(sum(m["percentage"] for m in milestones) - 100) > Decimal("0.001"):
        raise ValueError("Milestone percentages must total 100")

    contract_date = _iso(dflt("contract_date", date.today().isoformat(), "contract date"), "contract_date")
    supplier = Party.parse(data.get("supplier"), "supplier")
    customer = Party.parse(data.get("customer"), "customer")
    for who, p in (("Party A", supplier), ("Party B", customer)):
        for attr, label in (("address", "address"), ("tax_id", "tax / registration number"), ("representative", "authorised representative")):
            if not getattr(p, attr):
                missing.append(f"{who} {label}")

    dispute = (_clean(dflt("dispute", "arbitration", "dispute resolution"), "dispute", 20).lower())
    if dispute not in ("arbitration", "courts"):
        raise ValueError("dispute must be arbitration or courts")
    institution = _clean(dflt("arbitration_institution", "VIAC", "arbitration institution"), "arbitration_institution", 10).upper()
    if dispute == "arbitration" and institution not in INSTITUTIONS:
        raise ValueError(f"arbitration_institution must be one of {', '.join(INSTITUTIONS)}")
    law = _clean(dflt("governing_law", "the laws of the Socialist Republic of Vietnam", "governing law"), "governing_law", 160)
    law_vi = _clean(data.get("governing_law_vi"), "governing_law_vi", 160) or (
        "pháp luật nước Cộng hòa Xã hội Chủ nghĩa Việt Nam" if law == "the laws of the Socialist Republic of Vietnam" else law)

    seed = json.dumps({"s": supplier.name, "c": customer.name, "a": str(amount), "d": contract_date, "k": kind}, sort_keys=True)
    t = Terms(
        kind=kind, lang=lang, supplier=supplier, customer=customer,
        scope=_clean(data.get("scope"), "scope", MAX_TEXT, required=True), currency=currency, amount=amount, milestones=milestones,
        contract_no=_clean(data.get("contract_no"), "contract_no", 40) or f"CB-{contract_date.replace('-', '')}-{hashlib.sha256(seed.encode()).hexdigest()[:4].upper()}",
        contract_date=contract_date, place=_clean(dflt("place_of_signing", "Ho Chi Minh City", "place of signing"), "place_of_signing", 80),
        vat_pct=_number(data.get("vat_pct"), "vat_pct", 0, 30),
        payment_days=int(_number(dflt("payment_days", 30, "payment term"), "payment_days", 0, 180)),
        late_interest_pct=_number(dflt("late_interest_pct", 10, "late-payment interest"), "late_interest_pct", 0, 30),
        acceptance_days=int(_number(dflt("acceptance_days", 10, "acceptance period"), "acceptance_days", 1, 90)),
        warranty_months=int(_number(dflt("warranty_months", 12, "warranty period"), "warranty_months", 0, 120)),
        liability_cap_pct=_number(dflt("liability_cap_pct", 100, "liability cap"), "liability_cap_pct", 10, 500),
        governing_law=law, governing_law_vi=law_vi, dispute=dispute, institution=institution,
        prevailing=(_clean(data.get("prevailing_language"), "prevailing_language", 2).lower() or "en"),
        defaulted=defaulted, missing=missing)
    if t.prevailing not in ("en", "vi"):
        raise ValueError("prevailing_language must be en or vi")
    if kind == "supply":
        t.incoterm = _clean(dflt("incoterm", "FOB", "Incoterms rule"), "incoterm", 3).upper()
        if t.incoterm not in INCOTERMS:
            raise ValueError(f"incoterm must be one of {', '.join(INCOTERMS)}")
        t.incoterm_place = _clean(data.get("incoterm_place"), "incoterm_place", 120)
        if not t.incoterm_place:
            missing.append("Incoterms named place")
        t.delivery_date = _iso(data.get("delivery_date"), "delivery_date")
        if not t.delivery_date:
            missing.append("latest delivery (shipment) date")
    elif kind == "services":
        t.start_date, t.end_date = _iso(data.get("start_date"), "start_date"), _iso(data.get("end_date"), "end_date")
        if not t.start_date or not t.end_date:
            missing.append("service start and end dates")
        elif t.end_date < t.start_date:
            raise ValueError("end_date is before start_date")
    else:
        t.site = _clean(data.get("site"), "site", 200)
        t.completion_date = _iso(data.get("completion_date"), "completion_date")
        t.retention_pct = _number(dflt("retention_pct", 5, "retention"), "retention_pct", 0, 10)
        t.defects_months = int(_number(dflt("defects_months", 12, "defects-liability period"), "defects_months", 0, 60))
        t.performance_security_pct = _number(dflt("performance_security_pct", 10, "performance security"), "performance_security_pct", 0, 30)
        if not t.site:
            missing.append("site address")
        if not t.completion_date:
            missing.append("completion date")
    return t


# --------------------------------------------------------------------------- the clause library
def _p(en: str, vi: str) -> Dict[str, str]:
    return {"en": en, "vi": vi}


def _fmt_pct(d: Decimal) -> str:
    return f"{d.normalize():f}".rstrip(".") if d == d.to_integral() else f"{d:f}"


def build(t: Terms) -> Dict[str, Any]:
    A_en, A_vi = {"supply": ("the Seller", "Bên Bán"), "services": ("the Service Provider", "Bên Cung cấp Dịch vụ"),
                  "construction": ("the Contractor", "Nhà thầu")}[t.kind]
    B_en, B_vi = {"supply": ("the Buyer", "Bên Mua"), "services": ("the Client", "Bên Thuê Dịch vụ"),
                  "construction": ("the Employer", "Chủ đầu tư")}[t.kind]
    title = {"supply": _p("SUPPLY AGREEMENT", "HỢP ĐỒNG MUA BÁN HÀNG HÓA"), "services": _p("SERVICES AGREEMENT", "HỢP ĐỒNG DỊCH VỤ"),
             "construction": _p("CONSTRUCTION CONTRACT", "HỢP ĐỒNG THI CÔNG XÂY DỰNG")}[t.kind]
    scope_line = "; ".join(line.strip("-• \t") for line in t.scope.splitlines() if line.strip())
    price_en, price_vi = money(t.amount, t.currency, "en"), money(t.amount, t.currency, "vi")
    words_en, words_vi = amount_in_words(t.amount, t.currency, "en"), amount_in_words(t.amount, t.currency, "vi")
    or_todo = lambda v: v or TODO  # noqa: E731
    d_en = lambda iso: long_date(iso, "en") if iso else TODO  # noqa: E731
    d_vi = lambda iso: long_date(iso, "vi") if iso else TODO  # noqa: E731
    pct = _fmt_pct

    articles: List[Dict[str, Any]] = []

    def art(title_en: str, title_vi: str, *clauses: Tuple[str, str]) -> None:
        articles.append({"no": len(articles) + 1, "title": _p(title_en, title_vi),
                         "clauses": [{"no": f"{len(articles) + 1}.{i + 1}", "text": _p(en, vi)} for i, (en, vi) in enumerate(clauses)]})

    # 1. Definitions
    art("DEFINITIONS AND INTERPRETATION", "ĐỊNH NGHĨA VÀ GIẢI THÍCH",
        (f"In this Contract: \"Contract\" means this agreement and its Schedules; \"Contract Price\" means the amount stated in Article 3; "
         f"\"Business Day\" means a day on which banks are open in {t.place}; \"Payee Account\" means the bank account of {A_en} stated in, or "
         f"notified under, Article 15; \"Receivables\" means every amount payable to {A_en} under this Contract.",
         f"Trong Hợp đồng này: \"Hợp đồng\" là thỏa thuận này cùng các Phụ lục; \"Giá Hợp đồng\" là số tiền nêu tại Điều 3; \"Ngày Làm việc\" là ngày "
         f"các ngân hàng mở cửa tại {t.place}; \"Tài khoản Nhận tiền\" là tài khoản ngân hàng của {A_vi} được nêu hoặc thông báo theo Điều 15; "
         f"\"Khoản phải thu\" là mọi khoản tiền phải trả cho {A_vi} theo Hợp đồng này."),
        ("Headings are for convenience only. The Schedules form part of this Contract. If a Schedule conflicts with an Article, the Article prevails.",
         "Tiêu đề chỉ nhằm thuận tiện tra cứu. Các Phụ lục là bộ phận không tách rời của Hợp đồng. Nếu Phụ lục mâu thuẫn với một Điều, Điều đó được ưu tiên áp dụng."))

    # 2. Subject matter (type-specific)
    if t.kind == "supply":
        art("SUBJECT MATTER", "ĐỐI TƯỢNG HỢP ĐỒNG",
            (f"{A_en.capitalize()} shall sell and deliver, and {B_en} shall purchase, accept and pay for, the goods described in Schedule 1 "
             f"(the \"Goods\"): {scope_line}",
             f"{A_vi} bán và giao, {B_vi} mua, nhận và thanh toán cho hàng hóa mô tả tại Phụ lục 1 (\"Hàng hóa\"): {scope_line}"),
            ("The Goods shall be new, of the quantity, quality and specification in Schedule 1, and packed for export by sea in a manner adequate "
             "to protect them in normal transit. Each package shall be marked with the Contract number.",
             "Hàng hóa phải mới, đúng số lượng, chất lượng và quy cách tại Phụ lục 1, được đóng gói phù hợp cho vận chuyển đường biển quốc tế để "
             "bảo vệ hàng trong điều kiện vận chuyển thông thường. Mỗi kiện hàng ghi số Hợp đồng."))
    elif t.kind == "services":
        art("SERVICES", "DỊCH VỤ",
            (f"{A_en.capitalize()} shall perform the services and deliver the deliverables described in Schedule 1 (the \"Services\"): {scope_line}",
             f"{A_vi} thực hiện dịch vụ và bàn giao sản phẩm mô tả tại Phụ lục 1 (\"Dịch vụ\"): {scope_line}"),
            (f"The Services shall be performed from {d_en(t.start_date)} to {d_en(t.end_date)}, with the skill and care of a competent provider of "
             f"similar services and in accordance with applicable law.",
             f"Dịch vụ được thực hiện từ {d_vi(t.start_date)} đến {d_vi(t.end_date)}, với kỹ năng và sự cẩn trọng của một nhà cung cấp dịch vụ "
             f"tương tự có năng lực và phù hợp với pháp luật hiện hành."))
    else:
        art("THE WORKS", "CÔNG TRÌNH",
            (f"{A_en.capitalize()} shall execute and complete the works described in Schedule 1 (the \"Works\") at {or_todo(t.site)}: {scope_line}",
             f"{A_vi} thi công và hoàn thành công trình mô tả tại Phụ lục 1 (\"Công trình\") tại {or_todo(t.site)}: {scope_line}"),
            (f"{A_en.capitalize()} shall complete the Works by {d_en(t.completion_date)}, subject to extensions of time agreed in writing for "
             f"events for which {A_en} is not responsible.",
             f"{A_vi} hoàn thành Công trình chậm nhất vào {d_vi(t.completion_date)}, trừ khi được gia hạn bằng văn bản do các sự kiện mà "
             f"{A_vi} không chịu trách nhiệm."))

    # 3. Price
    vat_en = (f"The Contract Price excludes value-added tax, which {B_en} shall pay in addition at {pct(t.vat_pct)}%." if t.vat_pct is not None
              else "The Contract Price excludes value-added tax and other indirect taxes, which shall be added at the rate required by law.")
    vat_vi = (f"Giá Hợp đồng chưa bao gồm thuế giá trị gia tăng; {B_vi} thanh toán thêm thuế này theo thuế suất {pct(t.vat_pct)}%." if t.vat_pct is not None
              else "Giá Hợp đồng chưa bao gồm thuế giá trị gia tăng và các loại thuế gián thu khác; các khoản thuế này được cộng thêm theo thuế suất pháp luật quy định.")
    price_basis_en = {"supply": f"on {t.incoterm} {or_todo(t.incoterm_place)} terms (Incoterms® 2020)", "services": "for the Services",
                      "construction": "for the Works, subject only to variations agreed in writing"}[t.kind]
    price_basis_vi = {"supply": f"theo điều kiện {t.incoterm} {or_todo(t.incoterm_place)} (Incoterms® 2020)", "services": "cho Dịch vụ",
                      "construction": "cho Công trình, chỉ thay đổi theo các phát sinh được thỏa thuận bằng văn bản"}[t.kind]
    art("CONTRACT PRICE AND TAXES", "GIÁ HỢP ĐỒNG VÀ THUẾ",
        (f"The Contract Price is {price_en} ({words_en}) {price_basis_en}.", f"Giá Hợp đồng là {price_vi} (Bằng chữ: {words_vi}) {price_basis_vi}."),
        (vat_en, vat_vi),
        ("Each party bears its own bank charges. Charges of intermediary banks are borne by the party instructing the transfer.",
         "Mỗi bên tự chịu phí ngân hàng của mình. Phí ngân hàng trung gian do bên ra lệnh chuyển tiền chịu."))

    # 4. Payment
    art("PAYMENT", "THANH TOÁN",
        (f"{B_en.capitalize()} shall pay the Contract Price in the instalments set out in Schedule 2, each within {t.payment_days} days after "
         f"receipt of a valid invoice and the documents listed for that instalment, by bank transfer to the Payee Account.",
         f"{B_vi} thanh toán Giá Hợp đồng theo các đợt tại Phụ lục 2, mỗi đợt trong vòng {t.payment_days} ngày kể từ ngày nhận được hóa đơn hợp lệ "
         f"và các chứng từ quy định cho đợt đó, bằng chuyển khoản vào Tài khoản Nhận tiền."),
        (f"Payment is made when the amount is credited to the Payee Account. Payment to any other account does not discharge {B_en}.",
         f"Việc thanh toán được coi là hoàn thành khi tiền được ghi có vào Tài khoản Nhận tiền. Thanh toán vào tài khoản khác không giải trừ nghĩa vụ của {B_vi}."),
        (f"If {B_en} disputes part of an invoice in good faith, it shall notify {A_en} in writing within 7 days stating its reasons, and "
         f"pay the undisputed part on the due date.",
         f"Nếu {B_vi} có tranh chấp thiện chí đối với một phần hóa đơn, {B_vi} thông báo bằng văn bản cho {A_vi} trong vòng 7 ngày, nêu rõ lý do, "
         f"và thanh toán phần không tranh chấp đúng hạn."))

    # 5. Invoicing
    art("INVOICES", "HÓA ĐƠN",
        ("Each invoice shall state the Contract number, the instalment, the amount and currency, and the Payee Account, and shall be issued "
         "in the form required by applicable tax law (including electronic invoices where required).",
         "Mỗi hóa đơn ghi rõ số Hợp đồng, đợt thanh toán, số tiền và loại tiền, Tài khoản Nhận tiền, và được lập theo hình thức pháp luật về "
         "thuế quy định (kể cả hóa đơn điện tử khi bắt buộc)."),
        ("Quantities and descriptions on an invoice shall match the purchase order and the delivery documents for the same consignment or "
         "milestone, so that each invoice can be matched against its supporting documents.",
         "Số lượng và mô tả trên hóa đơn phải khớp với đơn đặt hàng và chứng từ giao hàng của cùng lô hàng hoặc mốc công việc, để mỗi hóa đơn "
         "có thể đối chiếu với chứng từ kèm theo."))

    # 6. Late payment
    art("LATE PAYMENT", "CHẬM THANH TOÁN",
        (f"On any amount not paid when due, {B_en} shall pay interest at {pct(t.late_interest_pct)}% per annum, calculated daily on a 365-day "
         f"basis from the due date until the date of actual payment, without prejudice to any other remedy.",
         f"Đối với khoản tiền chậm thanh toán, {B_vi} trả lãi chậm trả {pct(t.late_interest_pct)}%/năm, tính theo ngày trên cơ sở 365 ngày, "
         f"từ ngày đến hạn đến ngày thanh toán thực tế, không ảnh hưởng đến các biện pháp khắc phục khác."),
        (f"If an undisputed amount remains unpaid 15 days after written notice, {A_en} may suspend performance until it is paid; the time for "
         f"performance is extended accordingly.",
         f"Nếu khoản tiền không tranh chấp vẫn chưa được thanh toán sau 15 ngày kể từ ngày có thông báo bằng văn bản, {A_vi} có quyền tạm ngừng "
         f"thực hiện Hợp đồng cho đến khi được thanh toán; thời hạn thực hiện được kéo dài tương ứng."))

    # 7. Delivery / performance
    if t.kind == "supply":
        insurance = t.incoterm in INSURANCE_TERMS
        art("DELIVERY AND DOCUMENTS", "GIAO HÀNG VÀ CHỨNG TỪ",
            (f"Delivery shall be {t.incoterm} {or_todo(t.incoterm_place)} (Incoterms® 2020) not later than {d_en(t.delivery_date)}. Partial "
             f"shipments are allowed only with {B_en}'s written consent.",
             f"Giao hàng theo điều kiện {t.incoterm} {or_todo(t.incoterm_place)} (Incoterms® 2020) chậm nhất vào {d_vi(t.delivery_date)}. Chỉ "
             f"được giao hàng từng phần khi có chấp thuận bằng văn bản của {B_vi}."),
            (f"{A_en.capitalize()} shall provide the documents listed in Schedule 3" + (", including an insurance certificate" if insurance else "") +
             " within 5 Business Days after shipment.",
             f"{A_vi} cung cấp các chứng từ liệt kê tại Phụ lục 3" + (", bao gồm giấy chứng nhận bảo hiểm" if insurance else "") +
             " trong vòng 5 Ngày Làm việc sau khi giao hàng lên tàu."),
            (f"{A_en.capitalize()} shall notify {B_en} without delay of any expected delay in delivery, with its cause and the new expected date.",
             f"{A_vi} thông báo ngay cho {B_vi} về mọi dự kiến chậm giao hàng, nêu nguyên nhân và ngày giao dự kiến mới."))
    elif t.kind == "services":
        art("PERFORMANCE AND PERSONNEL", "THỰC HIỆN VÀ NHÂN SỰ",
            (f"{A_en.capitalize()} shall assign qualified personnel and shall replace any person {B_en} reasonably objects to in writing.",
             f"{A_vi} bố trí nhân sự có năng lực và thay thế người mà {B_vi} phản đối có lý do bằng văn bản."),
            (f"{B_en.capitalize()} shall provide timely access, information and decisions reasonably required; delays caused by {B_en} extend the "
             f"time for performance accordingly.",
             f"{B_vi} cung cấp kịp thời quyền tiếp cận, thông tin và quyết định cần thiết; chậm trễ do {B_vi} gây ra kéo dài thời hạn thực hiện tương ứng."))
    else:
        art("EXECUTION OF THE WORKS", "THI CÔNG CÔNG TRÌNH",
            (f"{B_en.capitalize()} shall give {A_en} access to the site on the commencement date. {A_en.capitalize()} shall comply with the approved "
             f"drawings, applicable building and safety regulations, and keep the site safe and orderly.",
             f"{B_vi} bàn giao mặt bằng cho {A_vi} vào ngày khởi công. {A_vi} tuân thủ bản vẽ được phê duyệt, quy chuẩn xây dựng và an toàn hiện "
             f"hành, và giữ công trường an toàn, ngăn nắp."),
            (f"Within 14 days after signing, {A_en} shall provide a performance security of {pct(t.performance_security_pct)}% of the Contract Price "
             f"in the form of a bank guarantee, valid until taking-over of the Works.",
             f"Trong vòng 14 ngày sau khi ký, {A_vi} nộp bảo đảm thực hiện hợp đồng bằng {pct(t.performance_security_pct)}% Giá Hợp đồng dưới hình "
             f"thức bảo lãnh ngân hàng, có hiệu lực đến khi bàn giao Công trình."),
            (f"{B_en.capitalize()} may retain {pct(t.retention_pct)}% of each progress amount as retention money, to be released with the final "
             f"instalment after the defects-liability period of {t.defects_months} months.",
             f"{B_vi} được giữ lại {pct(t.retention_pct)}% giá trị mỗi đợt thanh toán theo khối lượng làm tiền giữ lại, hoàn trả cùng đợt cuối sau "
             f"thời hạn bảo hành {t.defects_months} tháng."))

    # 8. Inspection and acceptance
    art("INSPECTION AND ACCEPTANCE", "KIỂM TRA VÀ NGHIỆM THU",
        (f"{B_en.capitalize()} shall inspect within {t.acceptance_days} days after delivery or completion and either accept in writing or notify "
         f"specific non-conformities in writing.",
         f"{B_vi} kiểm tra trong vòng {t.acceptance_days} ngày sau khi giao hàng hoặc hoàn thành và nghiệm thu bằng văn bản hoặc thông báo "
         f"bằng văn bản các điểm không phù hợp cụ thể."),
        (f"{A_en.capitalize()} shall remedy notified non-conformities within a reasonable period. Acceptance is deemed given if {B_en} does not "
         f"notify non-conformities within the period in Clause 8.1, or uses the Goods, deliverables or Works commercially.",
         f"{A_vi} khắc phục các điểm không phù hợp đã được thông báo trong thời hạn hợp lý. Việc nghiệm thu được coi là đã thực hiện nếu {B_vi} "
         f"không thông báo điểm không phù hợp trong thời hạn tại Khoản 8.1, hoặc đưa Hàng hóa, sản phẩm hoặc Công trình vào sử dụng thương mại."))

    # 9. Title / IP
    if t.kind == "supply":
        art("RISK AND TITLE", "RỦI RO VÀ QUYỀN SỞ HỮU",
            (f"Risk in the Goods passes to {B_en} in accordance with the agreed Incoterms® 2020 rule.",
             f"Rủi ro đối với Hàng hóa chuyển sang {B_vi} theo điều kiện Incoterms® 2020 đã thỏa thuận."),
            (f"Title to the Goods passes to {B_en} on full payment of the Contract Price for those Goods.",
             f"Quyền sở hữu Hàng hóa chuyển sang {B_vi} khi {B_vi} thanh toán đủ Giá Hợp đồng cho Hàng hóa đó."))
    elif t.kind == "services":
        art("INTELLECTUAL PROPERTY", "SỞ HỮU TRÍ TUỆ",
            ("Each party keeps the intellectual property it owned before this Contract.", "Mỗi bên giữ quyền sở hữu trí tuệ đã có trước Hợp đồng này."),
            (f"On full payment, {B_en} owns the deliverables created specifically for it and receives a non-exclusive licence to any pre-existing "
             f"material of {A_en} embedded in them, for its own business use.",
             f"Khi thanh toán đủ, {B_vi} sở hữu các sản phẩm được tạo ra riêng cho mình và được cấp quyền sử dụng không độc quyền đối với tài liệu "
             f"có sẵn của {A_vi} nằm trong sản phẩm, cho mục đích kinh doanh của chính mình."))
    else:
        art("TAKING-OVER AND OWNERSHIP", "BÀN GIAO VÀ QUYỀN SỞ HỮU",
            (f"The Works are taken over when {B_en} issues a taking-over certificate or is deemed to have accepted them under Article 8. Care of the "
             f"Works passes to {B_en} on taking-over.",
             f"Công trình được bàn giao khi {B_vi} cấp biên bản nghiệm thu bàn giao hoặc được coi là đã nghiệm thu theo Điều 8. Trách nhiệm bảo quản "
             f"Công trình chuyển sang {B_vi} khi bàn giao."),
            (f"Materials incorporated in the Works become the property of {B_en} when paid for.",
             f"Vật tư đã đưa vào Công trình thuộc sở hữu của {B_vi} khi đã được thanh toán."))

    # 10. Warranty
    warranty_months = t.defects_months if t.kind == "construction" else t.warranty_months
    art("WARRANTY", "BẢO HÀNH",
        (f"{A_en.capitalize()} warrants that the Goods, deliverables or Works conform to this Contract and are free from defects in design, "
         f"materials and workmanship for {warranty_months} months after acceptance.",
         f"{A_vi} bảo đảm Hàng hóa, sản phẩm hoặc Công trình phù hợp với Hợp đồng và không có khuyết tật về thiết kế, vật liệu và tay nghề trong "
         f"{warranty_months} tháng kể từ ngày nghiệm thu."),
        (f"For a defect notified within that period, {A_en} shall at its option repair, replace or re-perform within a reasonable time, or refund "
         f"the price of the defective part.",
         f"Đối với khuyết tật được thông báo trong thời hạn đó, {A_vi} lựa chọn sửa chữa, thay thế hoặc thực hiện lại trong thời hạn hợp lý, hoặc "
         f"hoàn trả giá của phần bị khuyết tật."))

    # 11. Liability
    art("LIMITATION OF LIABILITY", "GIỚI HẠN TRÁCH NHIỆM",
        (f"Each party's total liability under this Contract is limited to {pct(t.liability_cap_pct)}% of the Contract Price.",
         f"Tổng trách nhiệm của mỗi bên theo Hợp đồng này không vượt quá {pct(t.liability_cap_pct)}% Giá Hợp đồng."),
        ("Neither party is liable for loss of profit, loss of business or any indirect or consequential loss.",
         "Không bên nào chịu trách nhiệm đối với lợi nhuận bị mất, mất cơ hội kinh doanh hoặc thiệt hại gián tiếp."),
        ("The limits in this Article do not apply to fraud, wilful misconduct, death or personal injury caused by negligence, the obligation to "
         "pay the Contract Price, or any liability that cannot be limited by law.",
         "Các giới hạn tại Điều này không áp dụng đối với gian lận, cố ý vi phạm, thiệt hại về tính mạng hoặc sức khỏe do lỗi gây ra, nghĩa vụ "
         "thanh toán Giá Hợp đồng, hoặc trách nhiệm mà pháp luật không cho phép giới hạn."))

    # 12. Force majeure
    art("FORCE MAJEURE", "BẤT KHẢ KHÁNG",
        ("A party is not liable for failure to perform caused by an event beyond its reasonable control that it could not reasonably have foreseen "
         "or avoided, such as natural disaster, epidemic, war, or acts of government, provided it notifies the other party in writing within "
         "7 days and takes reasonable steps to mitigate.",
         "Một bên không chịu trách nhiệm về việc không thực hiện nghĩa vụ do sự kiện nằm ngoài khả năng kiểm soát hợp lý, không thể lường trước "
         "và không thể khắc phục dù đã áp dụng mọi biện pháp cần thiết, như thiên tai, dịch bệnh, chiến tranh hoặc quyết định của cơ quan nhà "
         "nước, với điều kiện bên đó thông báo bằng văn bản cho bên kia trong vòng 7 ngày và áp dụng biện pháp hợp lý để hạn chế thiệt hại."),
        ("Force majeure does not excuse an obligation to pay money that fell due before the event. If the event continues for more than 90 days, "
         "either party may terminate this Contract by written notice.",
         "Sự kiện bất khả kháng không miễn trừ nghĩa vụ thanh toán đã đến hạn trước khi xảy ra sự kiện. Nếu sự kiện kéo dài quá 90 ngày, mỗi bên "
         "có quyền chấm dứt Hợp đồng bằng thông báo bằng văn bản."))

    # 13. Confidentiality
    art("CONFIDENTIALITY AND DATA PROTECTION", "BẢO MẬT VÀ BẢO VỆ DỮ LIỆU",
        ("Each party shall keep confidential the terms of this Contract and all non-public information received from the other party, during "
         "this Contract and for 3 years after it ends, except disclosure to its professional advisers, financiers (subject to confidentiality), "
         "or as required by law.",
         "Mỗi bên giữ bí mật các điều khoản của Hợp đồng và mọi thông tin không công khai nhận được từ bên kia, trong thời hạn Hợp đồng và 3 năm "
         "sau khi Hợp đồng chấm dứt, trừ trường hợp cung cấp cho tư vấn chuyên môn, bên cấp vốn (với điều kiện bảo mật) hoặc theo yêu cầu của pháp luật."),
        ("Each party shall process personal data received under this Contract only for its performance and in accordance with applicable "
         "personal data protection law.",
         "Mỗi bên chỉ xử lý dữ liệu cá nhân nhận được theo Hợp đồng để thực hiện Hợp đồng và theo quy định của pháp luật về bảo vệ dữ liệu cá nhân."))

    # 14. Assignment of receivables (the financing clause)
    art("ASSIGNMENT OF RECEIVABLES AND FINANCING", "CHUYỂN GIAO QUYỀN YÊU CẦU THANH TOÁN VÀ TÀI TRỢ",
        (f"{A_en.capitalize()} may assign, or create security over, its Receivables to a bank, factor or other financier without the consent of "
         f"{B_en}. Otherwise, neither party may transfer its rights or obligations without the other party's prior written consent.",
         f"{A_vi} có quyền chuyển giao hoặc dùng các Khoản phải thu làm tài sản bảo đảm cho ngân hàng, đơn vị bao thanh toán hoặc bên cấp vốn "
         f"khác mà không cần sự đồng ý của {B_vi}. Ngoài trường hợp này, không bên nào được chuyển giao quyền hoặc nghĩa vụ khi chưa có chấp "
         f"thuận trước bằng văn bản của bên kia."),
        (f"After receiving a written notice of assignment signed by {A_en} and the financier, {B_en} shall pay the assigned Receivables only to the "
         f"account stated in that notice and shall confirm receipt of the notice within 5 Business Days.",
         f"Sau khi nhận được thông báo chuyển giao bằng văn bản có chữ ký của {A_vi} và bên cấp vốn, {B_vi} chỉ thanh toán các Khoản phải thu "
         f"đã chuyển giao vào tài khoản nêu trong thông báo và xác nhận đã nhận thông báo trong vòng 5 Ngày Làm việc."),
        (f"{B_en.capitalize()} may not set off against assigned Receivables any claim that does not arise under this Contract.",
         f"{B_vi} không được bù trừ vào Khoản phải thu đã chuyển giao bất kỳ khoản yêu cầu nào không phát sinh từ Hợp đồng này."))

    # 15. Payee account security
    art("PAYEE ACCOUNT SECURITY", "AN TOÀN TÀI KHOẢN NHẬN TIỀN",
        ("The Payee Account is the account stated in Schedule 2 or in a notice of assignment under Article 14.",
         "Tài khoản Nhận tiền là tài khoản nêu tại Phụ lục 2 hoặc tại thông báo chuyển giao theo Điều 14."),
        (f"A notice that purports to alter the Payee Account takes effect only after {B_en} has confirmed it by telephone with a named "
         f"representative of {A_en}, using a number stated in this Contract and not one taken from the notice, and 5 Business Days have passed.",
         f"Thông báo nhằm thay đổi Tài khoản Nhận tiền chỉ có hiệu lực sau khi {B_vi} xác minh qua điện thoại với người đại diện có tên của "
         f"{A_vi}, sử dụng số điện thoại ghi trong Hợp đồng này (không dùng số trong thông báo), và sau 5 Ngày Làm việc."),
        ("Each party shall promptly inform the other of any suspected fraudulent payment instruction it receives.",
         "Mỗi bên thông báo ngay cho bên kia về mọi chỉ thị thanh toán nghi ngờ gian lận mà mình nhận được."))

    # 16. Compliance
    art("COMPLIANCE", "TUÂN THỦ",
        ("Each party shall comply with applicable anti-bribery, anti-money-laundering, sanctions and export-control laws, and shall not offer or "
         "accept any improper payment in connection with this Contract.",
         "Mỗi bên tuân thủ pháp luật về phòng, chống hối lộ, phòng, chống rửa tiền, cấm vận và kiểm soát xuất khẩu, và không đưa hoặc nhận bất "
         "kỳ khoản thanh toán không chính đáng nào liên quan đến Hợp đồng."),)

    # 17. Termination
    art("TERM AND TERMINATION", "THỜI HẠN VÀ CHẤM DỨT",
        ("This Contract takes effect on signature by both parties and continues until all obligations have been performed.",
         "Hợp đồng có hiệu lực kể từ ngày hai bên ký và tiếp tục cho đến khi mọi nghĩa vụ được thực hiện xong."),
        ("Either party may terminate this Contract by written notice if the other party commits a material breach that is not remedied within "
         "30 days after written notice, or becomes insolvent or enters bankruptcy proceedings.",
         "Mỗi bên có quyền chấm dứt Hợp đồng bằng thông báo bằng văn bản nếu bên kia vi phạm nghiêm trọng và không khắc phục trong vòng 30 ngày "
         "kể từ ngày nhận thông báo bằng văn bản, hoặc mất khả năng thanh toán hoặc bị mở thủ tục phá sản."),
        (f"On termination, {B_en} shall pay for the Goods, deliverables or work accepted or delivered before termination. Articles 11, 13, 14, "
         f"18 and 19 survive termination.",
         f"Khi chấm dứt Hợp đồng, {B_vi} thanh toán cho Hàng hóa, sản phẩm hoặc khối lượng công việc đã được nghiệm thu hoặc giao trước thời "
         f"điểm chấm dứt. Các Điều 11, 13, 14, 18 và 19 vẫn có hiệu lực sau khi Hợp đồng chấm dứt."))

    # 18. Disputes
    if t.dispute == "arbitration":
        inst_en, inst_vi, seat_en, seat_vi = INSTITUTIONS[t.institution]
        lang_en = "English" if t.lang != "vi" else "Vietnamese"
        lang_vi = "tiếng Anh" if t.lang != "vi" else "tiếng Việt"
        art("DISPUTE RESOLUTION", "GIẢI QUYẾT TRANH CHẤP",
            ("The parties shall first try to resolve any dispute by negotiation between senior representatives within 30 days after a written "
             "request.",
             "Các bên trước hết giải quyết tranh chấp bằng thương lượng giữa đại diện cấp cao trong vòng 30 ngày kể từ ngày có yêu cầu bằng văn bản."),
            (f"A dispute not resolved by negotiation shall be finally resolved by arbitration administered by {inst_en} under its rules in force at "
             f"the time, by one arbitrator. The seat of arbitration is {seat_en} and the language is {lang_en}. The award is final and binding.",
             f"Tranh chấp không giải quyết được bằng thương lượng sẽ được giải quyết chung thẩm bằng trọng tài tại {inst_vi} theo quy tắc tố tụng "
             f"có hiệu lực tại thời điểm đó, bởi một trọng tài viên. Địa điểm trọng tài là {seat_vi}, ngôn ngữ trọng tài là {lang_vi}. Phán quyết "
             f"là chung thẩm và có giá trị ràng buộc."))
    else:
        art("DISPUTE RESOLUTION", "GIẢI QUYẾT TRANH CHẤP",
            ("The parties shall first try to resolve any dispute by negotiation between senior representatives within 30 days after a written "
             "request.",
             "Các bên trước hết giải quyết tranh chấp bằng thương lượng giữa đại diện cấp cao trong vòng 30 ngày kể từ ngày có yêu cầu bằng văn bản."),
            ("A dispute not resolved by negotiation shall be submitted to the competent court determined under the governing law.",
             "Tranh chấp không giải quyết được bằng thương lượng sẽ được đưa ra Tòa án có thẩm quyền theo pháp luật điều chỉnh."))

    # 19. Governing law
    cisg_en = (" The United Nations Convention on Contracts for the International Sale of Goods (CISG) applies to the extent it is applicable to "
               "this Contract; matters it does not govern are governed by the law stated above." if t.kind == "supply" else "")
    cisg_vi = (" Công ước của Liên Hợp Quốc về Hợp đồng mua bán hàng hóa quốc tế (CISG) được áp dụng trong phạm vi Công ước điều chỉnh Hợp đồng này; "
               "các vấn đề Công ước không điều chỉnh do pháp luật nêu trên điều chỉnh." if t.kind == "supply" else "")
    art("GOVERNING LAW", "LUẬT ÁP DỤNG",
        (f"This Contract is governed by {t.governing_law}.{cisg_en}", f"Hợp đồng này được điều chỉnh bởi {t.governing_law_vi}.{cisg_vi}"))

    # 20. Notices
    art("NOTICES", "THÔNG BÁO",
        ("Notices under this Contract shall be in writing and delivered by hand, courier or email to the addresses stated in the Parties section, "
         "or to another address notified in writing. An email notice is received when sent, unless the sender receives a delivery failure message.",
         "Thông báo theo Hợp đồng phải lập bằng văn bản và gửi trực tiếp, qua chuyển phát hoặc thư điện tử đến địa chỉ nêu tại phần Các Bên, hoặc "
         "địa chỉ khác được thông báo bằng văn bản. Thông báo qua thư điện tử được coi là đã nhận khi gửi đi, trừ khi bên gửi nhận được thông báo "
         "gửi không thành công."),)

    # 21. General
    prevail_en = "English" if t.prevailing == "en" else "Vietnamese"
    prevail_vi = "tiếng Anh" if t.prevailing == "en" else "tiếng Việt"
    general = [
        ("This Contract is the entire agreement of the parties on its subject matter and supersedes all prior discussions.",
         "Hợp đồng này là toàn bộ thỏa thuận của các bên về đối tượng Hợp đồng và thay thế mọi trao đổi trước đó."),
        ("Amendments are valid only if made in writing and signed by both parties. A failure to exercise a right is not a waiver of it.",
         "Mọi sửa đổi, bổ sung chỉ có hiệu lực khi lập thành văn bản và được hai bên ký. Việc không thực hiện một quyền không có nghĩa là từ bỏ quyền đó."),
        ("If any provision is invalid, the remaining provisions remain in force and the parties shall replace the invalid provision with a valid one "
         "of similar effect.",
         "Nếu có điều khoản vô hiệu, các điều khoản còn lại vẫn có hiệu lực và các bên thay thế điều khoản vô hiệu bằng điều khoản hợp lệ có hiệu "
         "lực tương tự."),
        ("This Contract is made in two originals, one for each party, and may be signed in counterparts or electronically where permitted by law.",
         "Hợp đồng được lập thành hai bản gốc, mỗi bên giữ một bản, và có thể được ký thành nhiều bản hoặc ký điện tử khi pháp luật cho phép."),
    ]
    if t.lang == "bilingual":
        general.append((f"This Contract is made in English and Vietnamese. If the versions differ, the {prevail_en} version prevails.",
                        f"Hợp đồng được lập bằng tiếng Anh và tiếng Việt. Trường hợp có khác biệt giữa hai bản, bản {prevail_vi} được ưu tiên áp dụng."))
    art("GENERAL PROVISIONS", "ĐIỀU KHOẢN CHUNG", *general)

    # Schedules
    sched1_rows = [line.strip("-• \t") for line in t.scope.splitlines() if line.strip()]
    docs_en = ["Commercial invoice (3 originals)", "Packing list", "Full set of clean on-board bills of lading", "Certificate of origin"]
    docs_vi = ["Hóa đơn thương mại (3 bản gốc)", "Phiếu đóng gói", "Bộ đầy đủ vận đơn đường biển sạch đã xếp hàng", "Giấy chứng nhận xuất xứ"]
    if t.kind == "supply" and t.incoterm in INSURANCE_TERMS:
        docs_en.append("Insurance certificate (110% of invoice value)")
        docs_vi.append("Giấy chứng nhận bảo hiểm (110% giá trị hóa đơn)")
    schedules = [
        {"no": 1, "title": _p({"supply": "DESCRIPTION OF THE GOODS", "services": "DESCRIPTION OF THE SERVICES", "construction": "DESCRIPTION OF THE WORKS"}[t.kind],
                              {"supply": "MÔ TẢ HÀNG HÓA", "services": "MÔ TẢ DỊCH VỤ", "construction": "MÔ TẢ CÔNG TRÌNH"}[t.kind]),
         "items": [_p(r, r) for r in sched1_rows] + [_p("Detailed specifications, drawings or quantities: to be attached and initialled by both parties.",
                                                         "Thông số kỹ thuật, bản vẽ hoặc khối lượng chi tiết: đính kèm và có chữ ký nháy của hai bên.")]},
        {"no": 2, "title": _p("PAYMENT SCHEDULE", "LỊCH THANH TOÁN"),
         "table": {"header": [_p("No.", "STT"), _p("Instalment", "Đợt thanh toán"), _p("%", "%"), _p("Amount", "Số tiền"), _p("Due", "Thời hạn")],
                   "rows": [[str(m["no"]), _p(m["event"], m["event_vi"]), pct(m["percentage"]) + "%", _p(money(m["amount"], t.currency, "en"), money(m["amount"], t.currency, "vi")),
                             _p(f"{t.payment_days} days after invoice and documents", f"{t.payment_days} ngày sau khi nhận hóa đơn và chứng từ")] for m in t.milestones],
                   "total": [_p("Total", "Tổng cộng"), "100%", _p(price_en, price_vi)]},
         "items": [_p("Payee Account: bank name, account name and number to be completed and initialled by both parties; changes only under Article 15.",
                      "Tài khoản Nhận tiền: tên ngân hàng, tên và số tài khoản do hai bên điền và ký nháy; chỉ thay đổi theo Điều 15.")]},
    ]
    if t.kind == "supply":
        schedules.append({"no": 3, "title": _p("SHIPPING DOCUMENTS", "CHỨNG TỪ GIAO HÀNG"), "items": [_p(e, v) for e, v in zip(docs_en, docs_vi)]})
    elif t.kind == "services":
        schedules.append({"no": 3, "title": _p("DELIVERABLES AND ACCEPTANCE CRITERIA", "SẢN PHẨM BÀN GIAO VÀ TIÊU CHÍ NGHIỆM THU"),
                          "items": [_p("Each deliverable, its due date and its objective acceptance criteria: to be listed and initialled by both parties.",
                                       "Từng sản phẩm, thời hạn bàn giao và tiêu chí nghiệm thu khách quan: do hai bên liệt kê và ký nháy.")]})
    else:
        schedules.append({"no": 3, "title": _p("PROGRAMME, SECURITY AND RETENTION", "TIẾN ĐỘ, BẢO ĐẢM VÀ TIỀN GIỮ LẠI"),
                          "items": [_p(f"Completion date: {d_en(t.completion_date)}.", f"Ngày hoàn thành: {d_vi(t.completion_date)}."),
                                    _p(f"Performance security: {pct(t.performance_security_pct)}% of the Contract Price (bank guarantee).",
                                       f"Bảo đảm thực hiện hợp đồng: {pct(t.performance_security_pct)}% Giá Hợp đồng (bảo lãnh ngân hàng)."),
                                    _p(f"Retention: {pct(t.retention_pct)}% of each progress amount; defects-liability period {t.defects_months} months.",
                                       f"Tiền giữ lại: {pct(t.retention_pct)}% mỗi đợt thanh toán theo khối lượng; thời hạn bảo hành {t.defects_months} tháng.")]})

    def party_rows(p: Party) -> List[Tuple[Dict[str, str], str]]:
        return [(_p("Address", "Địa chỉ"), or_todo(p.address)), (_p("Tax / registration no.", "Mã số thuế / đăng ký"), or_todo(p.tax_id)),
                (_p("Represented by", "Người đại diện"), or_todo(p.representative) + (f", {p.title}" if p.title else "")),
                (_p("Email", "Thư điện tử"), or_todo(p.email)), (_p("Telephone", "Điện thoại"), or_todo(p.phone))]

    open_items = [f"Enter: {m}" for m in t.missing] + [f"Confirm proposed default: {d}" for d in t.defaulted]
    open_items_detail = ([{"kind": "missing", "en": m, "vi": LABEL_VI.get(m, m)} for m in t.missing] +
                         [{"kind": "default", "en": d, "vi": LABEL_VI.get(d, d)} for d in t.defaulted])
    return {
        "title": title, "contract_no": t.contract_no, "contract_date": t.contract_date, "place": t.place, "lang": t.lang,
        "meta": _p(f"No. {t.contract_no} · {long_date(t.contract_date, 'en')} · {t.place}", f"Số: {t.contract_no} · {long_date(t.contract_date, 'vi')} · {t.place}"),
        "parties": [{"role": _p(f"PARTY A ({A_en.replace('the ', '').upper()})", f"BÊN A ({A_vi.upper()})"), "name": t.supplier.name, "rows": party_rows(t.supplier)},
                    {"role": _p(f"PARTY B ({B_en.replace('the ', '').upper()})", f"BÊN B ({B_vi.upper()})"), "name": t.customer.name, "rows": party_rows(t.customer)}],
        "recitals": [
            _p(f"{t.supplier.name} (\"{A_en.replace('the ', '').title()}\" or \"Party A\") wishes to {'sell' if t.kind == 'supply' else 'provide' if t.kind == 'services' else 'execute'} "
               f"the {'Goods' if t.kind == 'supply' else 'Services' if t.kind == 'services' else 'Works'} described in this Contract.",
               f"{t.supplier.name} (\"{A_vi}\" hoặc \"Bên A\") có nhu cầu {'bán' if t.kind == 'supply' else 'cung cấp' if t.kind == 'services' else 'thi công'} "
               f"{'Hàng hóa' if t.kind == 'supply' else 'Dịch vụ' if t.kind == 'services' else 'Công trình'} mô tả trong Hợp đồng này."),
            _p(f"{t.customer.name} (\"{B_en.replace('the ', '').title()}\" or \"Party B\") wishes to {'purchase' if t.kind == 'supply' else 'engage'} them on the terms below.",
               f"{t.customer.name} (\"{B_vi}\" hoặc \"Bên B\") có nhu cầu {'mua' if t.kind == 'supply' else 'thuê'} theo các điều khoản dưới đây."),
            _p("The parties therefore agree as follows.", "Vì vậy, hai bên thống nhất ký kết Hợp đồng với các điều khoản sau."),
        ],
        "articles": articles, "schedules": schedules,
        "signatures": [{"role": _p("FOR AND ON BEHALF OF PARTY A", "ĐẠI DIỆN BÊN A"), "name": t.supplier.name, "person": t.supplier.representative, "title": t.supplier.title},
                       {"role": _p("FOR AND ON BEHALF OF PARTY B", "ĐẠI DIỆN BÊN B"), "name": t.customer.name, "person": t.customer.representative, "title": t.customer.title}],
        "notice": _p("DRAFT FOR LEGAL REVIEW. Generated by CashBridge from the data entered, using a fixed clause library. It is not legal advice, has "
                     "not been reviewed by counsel and is not signed. Every bracketed [●] item and every proposed default must be completed or confirmed.",
                     "BẢN DỰ THẢO ĐỂ RÀ SOÁT PHÁP LÝ. Được CashBridge tạo từ dữ liệu đã nhập, dựa trên bộ điều khoản cố định. Đây không phải ý kiến tư vấn "
                     "pháp lý, chưa được luật sư rà soát và chưa được ký. Mọi mục [●] và mọi giá trị mặc định đề xuất phải được bổ sung hoặc xác nhận."),
        "open_items": open_items, "open_items_detail": open_items_detail,
        "checklist": [_p(en, vi) for en, vi in CHECKLIST],
    }


# --------------------------------------------------------------------------- plain text (analyzer, preview fallback)
def to_text(doc: Dict[str, Any], lang: str = "en") -> str:
    L = "vi" if lang == "vi" else "en"
    g = lambda x: x[L] if isinstance(x, dict) else x  # noqa: E731
    out = [g(doc["notice"]), "", g(doc["title"]), g(doc["meta"]), ""]
    for p in doc["parties"]:
        out.append(f"{g(p['role'])}: {p['name']}")
        out += [f"  {g(k)}: {v}" for k, v in p["rows"]]
    out.append("")
    out += [f"({chr(65 + i)}) {g(r)}" for i, r in enumerate(doc["recitals"])]
    for a in doc["articles"]:
        out += ["", f"{'ĐIỀU' if L == 'vi' else 'ARTICLE'} {a['no']}. {g(a['title'])}"]
        out += [f"{c['no']} {g(c['text'])}" for c in a["clauses"]]
    for s in doc["schedules"]:
        out += ["", f"{'PHỤ LỤC' if L == 'vi' else 'SCHEDULE'} {s['no']}. {g(s['title'])}"]
        if "table" in s:
            for r in s["table"]["rows"]:
                out.append(f"Milestone {r[0]}: {g(r[1])} - {r[2]} - {g(r[3])} - {g(r[4])}" if L == "en"
                           else f"Đợt {r[0]}: {g(r[1])} - {r[2]} - {g(r[3])} - {g(r[4])}")
        out += [f"- {g(i)}" for i in s.get("items", [])]
    out += [""] + [f"{g(s['role'])}: {s['name']} [NOT SIGNED]" for s in doc["signatures"]]
    return "\n".join(out)


def draft(data: Dict[str, Any]) -> Dict[str, Any]:
    terms = parse_terms(data)
    doc = build(terms)
    text = to_text(doc, "vi" if terms.lang == "vi" else "en")
    return {"synthetic_demo": True, "document_type": terms.kind, "language": terms.lang, "contract_no": terms.contract_no,
            "draft": text, "document": json.loads(json.dumps(doc, default=str)),
            "milestones": [{"event": m["event"], "percentage": float(m["percentage"]), "amount": float(m["amount"])} for m in terms.milestones],
            "status": "UNSIGNED_DRAFT_REQUIRES_LEGAL_REVIEW", "human_review_required": True,
            "open_items": doc["open_items"],
            "review_checklist": [en for en, _ in CHECKLIST]}
