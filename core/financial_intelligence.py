"""Deterministic, source-labelled SME analytical tools; never an automated credit decision.

Financial figures are synthetic in this MVP. Ratios use explicit formulas; unavailable
inputs produce null rather than invented estimates. Stress tests preserve input evidence.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean, median
from typing import Any, Dict, List

from config.settings import SANDBOX_INPUTS_DIR

SOURCE = SANDBOX_INPUTS_DIR / 'financial_analytics.json'


def load_ledger(path: Path = SOURCE) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _number(value: Any, label: str, lower: float = 0, upper: float = 1e10) -> float:
    if isinstance(value, bool):
        raise ValueError(f'{label} must be a finite number')
    try:
        n = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(f'{label} must be a finite number') from exc
    if not math.isfinite(n) or n < lower or n > upper:
        raise ValueError(f'{label} must be between {lower} and {upper}')
    return n


def _ratio(a: float, b: float, multiplier: float = 1) -> float | None:
    return round(a / b * multiplier, 3) if b > 0 else None


def financial_summary(data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    d = data if data is not None else load_ledger()
    bs, a = d['balance_sheet'], d['annual']
    ca = sum(_number(bs[k], k) for k in ('cash', 'accounts_receivable', 'inventory', 'other_current_assets'))
    cl = _number(bs['current_liabilities'], 'current_liabilities')
    sales, cogs = _number(a['revenue'], 'revenue'), _number(a['cogs'], 'cogs')
    op = _number(a['operating_expenses'], 'operating_expenses')
    ebitda = sales - cogs - op
    ebit = ebitda - _number(a['depreciation'], 'depreciation')
    interest = _number(a['interest'], 'interest')
    debt_service = interest + _number(a['principal_payments'], 'principal_payments')
    fixed = _number(bs['cash'], 'cash')
    months = d['monthly']
    expenses = [_number(x['expenses'], 'monthly_expenses') for x in months]
    revenues = [_number(x['revenue'], 'monthly_revenue') for x in months]
    marketing = [ _number(x['marketing'], 'marketing') for x in months]
    avg_burn = mean(expenses) if expenses else 0
    cash_runway = _ratio(fixed, avg_burn)
    # Simple population-based z-scores: descriptive diagnostic, not a trained fraud model.
    expense_mean = mean(expenses) if expenses else 0
    std = math.sqrt(sum((v-expense_mean)**2 for v in expenses)/len(expenses)) if expenses else 0
    anomalies = [{'month': row['month'], 'type': 'expense_outlier', 'z_score': round((val-expense_mean)/std, 3)}
                 for row, val in zip(months, expenses) if std > 0 and abs(val-expense_mean)/std >= 2]
    receivables = _number(bs['accounts_receivable'], 'accounts_receivable')
    inventory = _number(bs['inventory'], 'inventory')
    # DPO requires accounts payable, not all current liabilities; explicitly unavailable.
    dso = _ratio(receivables * 365, sales)
    dio = _ratio(inventory * 365, cogs)
    ratios = {
        'dso_days_estimate': dso,
        'dio_days_estimate': dio,
        'dpo_days': None,
        'cash_conversion_cycle_days': None,
        'net_working_capital_usd': round(ca - cl, 2),
        'receivables_to_revenue_pct': _ratio(receivables, sales, 100),
        'inventory_to_cogs_pct': _ratio(inventory, cogs, 100),
        'operating_margin_pct': _ratio(ebit, sales, 100),
        'current_ratio': _ratio(ca, cl),
        'quick_ratio': _ratio(ca - bs['inventory'], cl),
        'cash_ratio': _ratio(fixed, cl),
        'gross_margin_pct': _ratio(sales-cogs, sales, 100),
        'ebitda_margin_pct': _ratio(ebitda, sales, 100),
        'interest_coverage': _ratio(ebit, interest),
        'dscr_proxy': _ratio(ebitda, debt_service),
        'debt_to_equity': _ratio(_number(bs['total_debt'], 'total_debt'), _number(bs['equity'], 'equity')),
        'cash_runway_months_gross_expenses': cash_runway,
    }
    return {
        'synthetic': True, 'source_id': d['source_id'], 'currency': d['currency'],
        'ratios': ratios,
        'highlights': {'current_assets_usd': round(ca, 2), 'ebitda_usd': round(ebitda, 2),
                       'ebit_usd': round(ebit, 2), 'annual_debt_service_usd': round(debt_service, 2),
                       'avg_monthly_expenses_usd': round(avg_burn, 2),
                       'avg_monthly_marketing_usd': round(mean(marketing), 2) if marketing else None,
                       'net_monthly_cash_proxy_usd': round(mean(revenues) - avg_burn, 2) if revenues else None},
        'eda': {'monthly': [{'month': x['month'], 'revenue': x['revenue'], 'expenses': x['expenses'],
                             'marketing': x['marketing'], 'payroll': x['payroll'],
                             'supplier': x['supplier']} for x in months],
                'median_monthly_expenses_usd': round(median(expenses), 2) if expenses else None,
                'min_monthly_revenue_usd': min(revenues) if revenues else None,
                'max_monthly_revenue_usd': max(revenues) if revenues else None,
                'expense_outliers': anomalies},
        'definitions': {
            'working_capital': 'DSO and DIO use year-end balances / annual flow. DPO and CCC intentionally unavailable without verified trade payables.',
            'dscr_proxy': 'EBITDA / (annual interest + scheduled principal); not bank covenant DSCR or actual CFADS.',
            'cash_runway_months_gross_expenses': 'Cash / average gross monthly expenses; assumes zero future receipts.',
            'eda': 'Descriptive EDA on 12 synthetic months; z-score >= 2 flags review, not proof of fraud.',
        },
    }


def budget_stress(params: Dict[str, Any], data: Dict[str, Any] | None = None) -> Dict[str, Any]:
    d = data if data is not None else load_ledger()
    x = params
    marketing_pct = _number(x.get('marketing_increase_pct', 0), 'marketing_increase_pct', -100, 300)
    revenue_delay_pct = _number(x.get('receipts_delayed_pct', 0), 'receipts_delayed_pct', 0, 100)
    loan_amount = _number(x.get('new_loan_usd', 0), 'new_loan_usd')
    annual_apr_pct = _number(x.get('loan_apr_pct', 15), 'loan_apr_pct', 0, 100)
    months = int(_number(x.get('horizon_months', 3), 'horizon_months', 1, 12))
    if months != _number(x.get('horizon_months', 3), 'horizon_months', 1, 12):
        raise ValueError('horizon_months must be an integer')
    target_reserve = _number(x.get('minimum_reserve_usd', 20000), 'minimum_reserve_usd')
    ledger_monthly = d['monthly']
    avg_inflow = mean(float(m['revenue']) for m in ledger_monthly)
    avg_outflow = mean(float(m['expenses']) for m in ledger_monthly)
    avg_marketing = mean(float(m['marketing']) for m in ledger_monthly)
    initial = float(d['balance_sheet']['cash'])
    incremental_marketing = avg_marketing * marketing_pct / 100
    # Simple interest + interest-only during horizon; principal due is excluded and disclosed.
    monthly_interest = loan_amount * annual_apr_pct / 1200
    opening, balance = initial + loan_amount, initial + loan_amount
    weeks = []
    for month in range(1, months+1):
        cash_in = avg_inflow * (1-revenue_delay_pct/100)
        cash_out = avg_outflow + incremental_marketing + monthly_interest
        balance += cash_in - cash_out
        weeks.append({'month': month, 'inflows_usd': round(cash_in, 2),
                      'outflows_usd': round(cash_out, 2), 'closing_cash_usd': round(balance, 2)})
    baseline = initial + months * (avg_inflow-avg_outflow)
    return {'synthetic': True, 'source_id': d['source_id'], 'scenario': {'marketing_increase_pct': marketing_pct,
               'receipts_delayed_pct': revenue_delay_pct, 'new_loan_usd': loan_amount,
               'loan_apr_pct': annual_apr_pct, 'horizon_months': months, 'minimum_reserve_usd': target_reserve},
            'baseline_ending_cash_usd': round(baseline, 2), 'scenario_ending_cash_usd': round(balance, 2),
            'change_vs_baseline_usd': round(balance - baseline, 2),
            'minimum_cash_usd': round(min([opening]+[r['closing_cash_usd'] for r in weeks]), 2),
            'reserve_breach': min([opening]+[r['closing_cash_usd'] for r in weeks]) < target_reserve,
            'additional_marketing_monthly_usd': round(incremental_marketing, 2),
            'schedule': weeks,
            'limitations': ['Uses 12-month synthetic average receipts and expenses, not a causal marketing ROI model.',
                            'Delayed receipts are conservatively excluded in the chosen horizon, not shifted to later months.',
                            'New loan modeled as an upfront cash inflow and interest-only; principal repayment, fees, collateral and underwriting are excluded.']}


def project_feasibility(data: Dict[str, Any]) -> Dict[str, Any]:
    contract_value = _number(data.get('contract_value_usd'), 'contract_value_usd', 0.01)
    upfront = _number(data.get('upfront_cost_usd'), 'upfront_cost_usd')
    remaining = _number(data.get('remaining_cost_usd', 0), 'remaining_cost_usd')
    cash = _number(data.get('available_cash_usd'), 'available_cash_usd')
    reserve = _number(data.get('minimum_reserve_usd', 0), 'minimum_reserve_usd')
    advance_pct = _number(data.get('advance_payment_pct', 0), 'advance_payment_pct', 0, 100)
    late_pct = _number(data.get('stress_cost_overrun_pct', 0), 'stress_cost_overrun_pct', 0, 100)
    annual_rate = _number(data.get('loan_apr_pct', 15), 'loan_apr_pct', 0, 100)
    term = int(_number(data.get('financing_days', 90), 'financing_days', 1, 730))
    available = max(0, cash - reserve)
    advance = contract_value * advance_pct / 100
    initial_need = max(0, upfront - advance - available)
    stress_need = max(0, upfront * (1 + late_pct/100) - available)  # advance delayed/withheld
    # Aggregated team capacity only. Never scores or ranks individual employees.
    required_hours = _number(data.get('workforce_required_hours', 0), 'workforce_required_hours')
    available_hours = _number(data.get('workforce_available_hours', 0), 'workforce_available_hours')
    outsourced_rate = _number(data.get('outsourced_hourly_cost_usd', 0), 'outsourced_hourly_cost_usd')
    uncovered_hours = max(0, required_hours - available_hours)
    incremental_staff_cost = uncovered_hours * outsourced_rate
    estimated_cost = upfront + remaining + incremental_staff_cost
    simple_financing_interest = initial_need * annual_rate / 100 * term / 365
    profit = contract_value - estimated_cost - simple_financing_interest
    return {'synthetic': True, 'contract_value_usd': round(contract_value,2), 'advance_payment_usd': round(advance,2),
            'deployable_cash_usd': round(available,2), 'initial_funding_gap_usd': round(initial_need,2),
            'stress_gap_if_advance_delayed_and_cost_overruns_usd': round(stress_need,2),
            'workforce_readiness': {'uncovered_team_hours': round(uncovered_hours, 2),
                                    'indicative_outsourcing_cost_usd': round(incremental_staff_cost,2)},
            'estimated_profit_after_simple_financing_cost_usd': round(profit,2),
            'estimated_margin_pct': round(profit/contract_value*100,2),
            'human_review_required': True,
            'limitations': ['Assumes upfront costs precede milestone receipts; excludes taxes and guarantees.',
                            'Stress case assumes the advance is entirely delayed while upfront costs overrun.',
                            'Optional team capacity uses aggregated hours only; outsourced costs must not also be included in the other expense inputs.',
                            'Indicative simple interest only, not an offer, credit decision or bid recommendation.']}
