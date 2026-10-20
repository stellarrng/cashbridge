"""Conservative, explainable green-finance pre-screening for the synthetic demo.

NOT a taxonomy certification, environmental verification, or credit decision.
No LLM-generated evidence is accepted as a verification result.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Any, Dict

SUPPORTED = {
    "rooftop_solar": {"title": "Rooftop solar installation", "evidence": ["equipment_quote", "site_assessment", "electricity_baseline", "generation_estimate"]},
    "energy_efficiency": {"title": "Energy-efficient machinery", "evidence": ["equipment_quote", "energy_audit", "electricity_baseline", "savings_estimate"]},
}


def _amount(value: Any, name: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError(f"{name} must be a number") from None
    if not result.is_finite() or result < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return result


def assess_green_project(project: Dict[str, Any]) -> Dict[str, Any]:
    """Screen a candidate project using transparent, demo-only rules.

    Missing evidence is never interpreted as a positive result. Submitted files
    are marked 'provided', not 'verified'. A human reviewer must validate them.
    """
    kind = project.get("activity_type")
    if kind not in SUPPORTED:
        raise ValueError("Unsupported green activity type")
    rule = SUPPORTED[kind]
    required = rule["evidence"]
    supplied = project.get("evidence", {})
    if not isinstance(supplied, dict):
        raise ValueError("evidence must be an object")
    documentation = [
        {"id": key, "label": key.replace("_", " ").title(),
         "status": "provided_unverified" if supplied.get(key) is True else "missing"}
        for key in required
    ]
    supplied_count = sum(row["status"] == "provided_unverified" for row in documentation)
    completion = round(100 * supplied_count / len(documentation))

    cost = _amount(project.get("project_cost_usd", 0), "project_cost_usd")
    requested = _amount(project.get("requested_loan_usd", 0), "requested_loan_usd")
    baseline = _amount(project.get("baseline_kwh_year", 0), "baseline_kwh_year")
    renewable = _amount(project.get("expected_generation_kwh_year", 0), "expected_generation_kwh_year")
    savings = _amount(project.get("expected_savings_pct", 0), "expected_savings_pct")
    emission_factor = _amount(project.get("illustrative_emission_factor_kg_per_kwh", 0), "illustrative_emission_factor_kg_per_kwh")
    if savings > 100:
        raise ValueError("expected_savings_pct cannot exceed 100")
    if emission_factor > 10:
        raise ValueError("illustrative emission factor is outside demo range")

    if kind == "rooftop_solar":
        affected_kwh = renewable
        impact_basis = "Expected solar electricity generated; illustrative avoided grid emissions only"
        impact_ready = renewable > 0
    else:
        affected_kwh = baseline * savings / Decimal("100")
        impact_basis = "Estimated baseline consumption multiplied by forecast savings percentage"
        impact_ready = baseline > 0 and savings > 0
    impact_tonnes = affected_kwh * emission_factor / Decimal("1000")
    issues = []
    if cost <= 0 or requested <= 0 or requested > cost:
        issues.append("Loan request must be positive and no greater than the stated project cost")
    if supplied_count != len(required):
        issues.append("Required environmental/project evidence is missing")
    if not impact_ready or emission_factor <= 0:
        issues.append("Impact assumptions or emission factor are missing")
    issues.append("Applicable local green taxonomy and lender criteria must be checked by a reviewer")
    return {
        "project_id": str(project.get("project_id", "")),
        "name": str(project.get("name", rule["title"])),
        "activity_type": kind,
        "activity_name": rule["title"],
        "project_cost_usd": float(cost),
        "requested_loan_usd": float(requested),
        "documentation_completeness_pct": completion,
        "evidence": documentation,
        "illustrative_annual_impact_tco2e": round(float(impact_tonnes), 2) if impact_ready and emission_factor > 0 else None,
        "impact_basis": impact_basis,
        "impact_is_verified": False,
        "green_taxonomy_verified": False,
        "bank_credit_approved": False,
        "status": "NEEDS_HUMAN_REVIEW" if cost > 0 and 0 < requested <= cost else "INCOMPLETE",
        "issues": issues,
        "disclaimer": "Synthetic pre-screening only; not a green certification, assured impact figure, or bank credit approval.",
    }


def green_project_economics(project: dict, electricity_price_usd_per_kwh: float, annual_opex_usd: float = 0) -> dict:
    """Simple, transparently assumed green-upgrade ROI; no sustainability certification."""
    import math
    for label, number in [('electricity_price_usd_per_kwh', electricity_price_usd_per_kwh),
                          ('annual_opex_usd', annual_opex_usd)]:
        if isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) or number < 0:
            raise ValueError(f'{label} must be a finite non-negative number')
    if electricity_price_usd_per_kwh > 10 or annual_opex_usd > 1e9:
        raise ValueError('Energy price or annual opex outside allowed demo range')
    if project['activity_type'] == 'rooftop_solar':
        savings_kwh = min(float(project['baseline_kwh_year']), float(project['expected_generation_kwh_year']))
    elif project['activity_type'] == 'energy_efficiency':
        savings_kwh = float(project['baseline_kwh_year']) * float(project['expected_savings_pct']) / 100
    else:
        raise ValueError('Unsupported green project type')
    gross = savings_kwh * electricity_price_usd_per_kwh
    net = gross - annual_opex_usd
    cost = float(project['project_cost_usd'])
    return {'synthetic':True, 'project_id':project['project_id'],
        'annual_energy_savings_kwh':round(savings_kwh,2),
        'assumed_electricity_price_usd_per_kwh':electricity_price_usd_per_kwh,
        'estimated_gross_savings_usd_per_year':round(gross,2),
        'estimated_net_savings_usd_per_year':round(net,2),
        'simple_payback_years':round(cost/net,2) if net>0 else None,
        'limitation':'Indicative energy savings and simple payback; excludes tax, financing, depreciation, intermittency, verification and change in tariffs.'}


COMMISSIONING_WEEKS = 4  # savings and loan repayments start this many weeks after the capex is paid


def green_cash_impact(closing_by_week: list, buffer_usd: float, project: dict, capex_week: int, financed_pct: float,
                      loan_apr_pct: float, tenor_months: int, electricity_price_usd_per_kwh: float,
                      annual_opex_usd: float = 0.0) -> dict:
    """What a green investment does to the 13-week cash forecast, cash-funded vs loan-funded.

    Deterministic arithmetic on the existing forecast: the owner-funded part of the capex leaves in
    ``capex_week``; a green loan pays the rest directly to the supplier; energy savings (net of opex) and
    the loan's level monthly instalment (spread weekly) both start after commissioning. Everything is an
    ESTIMATE: no tariff path, no degradation, no tax. It does not certify the project as green.
    """
    import math
    weeks = [float(x) for x in closing_by_week]
    if not weeks or len(weeks) > 52:
        raise ValueError("forecast weeks missing")
    if not isinstance(capex_week, int) or isinstance(capex_week, bool) or not 1 <= capex_week <= len(weeks):
        raise ValueError(f"capex_week must be 1-{len(weeks)}")
    for name, v, hi in (("financed_pct", financed_pct, 100), ("loan_apr_pct", loan_apr_pct, 60)):
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= hi:
            raise ValueError(f"{name} must be between 0 and {hi}")
    if not isinstance(tenor_months, int) or isinstance(tenor_months, bool) or not 6 <= tenor_months <= 120:
        raise ValueError("tenor_months must be 6-120")
    eco = green_project_economics(project, electricity_price_usd_per_kwh, annual_opex_usd)
    cost = float(project["project_cost_usd"])
    weekly_saving = eco["estimated_net_savings_usd_per_year"] / 52.0
    start = capex_week + COMMISSIONING_WEEKS

    def scenario(pct: float) -> dict:
        loan = cost * pct / 100.0
        own = cost - loan
        r = loan_apr_pct / 100.0 / 12.0
        monthly = (loan / tenor_months if r == 0 else loan * r / (1 - (1 + r) ** -tenor_months)) if loan else 0.0
        weekly_payment = monthly * 12.0 / 52.0
        out, delta = [], 0.0
        for i, base in enumerate(weeks, start=1):
            if i == capex_week:
                delta -= own
            if i >= start:
                delta += weekly_saving - weekly_payment
            out.append(round(base + delta, 2))
        below_buffer = [i + 1 for i, v in enumerate(out) if v < buffer_usd]
        return {"financed_pct": pct, "loan_usd": round(loan, 2), "owner_cash_usd": round(own, 2),
                "monthly_instalment_usd": round(monthly, 2), "closing_by_week": out, "min_closing_usd": round(min(out), 2),
                "weeks_below_buffer": below_buffer, "first_negative_week": next((i + 1 for i, v in enumerate(out) if v < 0), None),
                "extra_funding_to_hold_buffer_usd": round(max(0.0, buffer_usd - min(out)) - max(0.0, buffer_usd - min(weeks)), 2)}

    base = {"closing_by_week": [round(x, 2) for x in weeks], "min_closing_usd": round(min(weeks), 2),
            "weeks_below_buffer": [i + 1 for i, v in enumerate(weeks) if v < buffer_usd],
            "first_negative_week": next((i + 1 for i, v in enumerate(weeks) if v < 0), None)}
    return {"synthetic": True, "project_id": project["project_id"], "buffer_usd": buffer_usd, "capex_week": capex_week,
            "savings_start_week": start if start <= len(weeks) else None, "weekly_net_saving_usd": round(weekly_saving, 2),
            "loan_apr_pct": loan_apr_pct, "tenor_months": tenor_months,
            "without_project": base, "cash_funded": scenario(0.0), "loan_funded": scenario(float(financed_pct)),
            "is_estimate": True, "green_certified": False,
            "limitation": "Estimate on the current 13-week forecast. Excludes tariff changes, degradation, tax, and lender approval; "
                          "not a green-taxonomy certification. Payback and impact need independent verification."}
