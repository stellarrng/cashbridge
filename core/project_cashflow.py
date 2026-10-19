"""Evidence-linked project cash waterfall; synthetic financing estimates only.

Payment/cost events have explicit relative day offsets. This module does not
pretend cash arrives at signing unless an event says so. Inferred milestones
are flagged as assumptions, and no financing/credit action is ever executed.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any
from core.financial_intelligence import _number


def project_cash_waterfall(data: dict[str, Any]) -> dict[str, Any]:
    total = _number(data.get('contract_value_usd'), 'contract_value_usd', .01)
    cash = _number(data.get('available_cash_usd'), 'available_cash_usd')
    reserve = _number(data.get('minimum_reserve_usd', 0), 'minimum_reserve_usd')
    overrun = _number(data.get('cost_overrun_pct', 0), 'cost_overrun_pct', 0, 300)
    delay = _number(data.get('payment_delay_days', 0), 'payment_delay_days', 0, 365)
    apr = _number(data.get('illustrative_apr_pct', 15), 'illustrative_apr_pct', 0, 100)
    payments = data.get('receipts')
    expenses = data.get('costs')
    if not isinstance(payments, list) or not isinstance(expenses, list) or not payments or not expenses:
        raise ValueError('Provide nonempty receipts[] and costs[] with days and amounts or percentages')
    if len(payments)>24 or len(expenses)>40:
        raise ValueError('Too many milestones or expense events')
    events = defaultdict(lambda: {'receipts':0.0,'costs':0.0,'sources':[]})
    receipt_total=0
    for i,r in enumerate(payments):
        if not isinstance(r,dict): raise ValueError('Each receipt event must be an object')
        day = int(_number(r.get('day'), f'receipts[{i}].day', 0, 730))
        if day != _number(r.get('day'), f'receipts[{i}].day', 0, 730): raise ValueError('day must be an integer')
        if ('amount_usd' in r)==('percentage' in r): raise ValueError('Each receipt requires exactly one of amount_usd or percentage')
        amount = (_number(r['amount_usd'], 'amount_usd') if 'amount_usd' in r
                  else total*_number(r['percentage'],'percentage',0,100)/100)
        payment_day = day + int(delay if day > 0 else 0)
        events[payment_day]['receipts'] += amount
        events[payment_day]['sources'].append(str(r.get('label',f'Receipt {i+1}'))[:100])
        receipt_total+=amount
    if abs(receipt_total-total) > max(.05,total*.000001):
        raise ValueError('Receipts must sum to contract value; missing money is not silently invented')
    for i,c in enumerate(expenses):
        if not isinstance(c,dict): raise ValueError('Each cost event must be an object')
        day = int(_number(c.get('day'), f'costs[{i}].day',0,1095))
        if day != _number(c.get('day'), f'costs[{i}].day',0,1095): raise ValueError('day must be integer')
        amount=_number(c.get('amount_usd'),f'costs[{i}].amount_usd')*(1+overrun/100)
        events[day]['costs']+=amount
        events[day]['sources'].append(str(c.get('label',f'Expense {i+1}'))[:100])
    balance=cash
    minimum=cash
    rows=[]
    peak_gap=max(0, reserve-cash)
    for day,ev in sorted(events.items()):
        balance += ev['receipts']-ev['costs']
        minimum=min(minimum,balance)
        peak_gap=max(peak_gap,reserve-balance)
        rows.append({'day':day, 'receipts_usd':round(ev['receipts'],2), 'costs_usd':round(ev['costs'],2),
                     'cash_before_financing_usd':round(balance,2), 'reserve_shortfall_usd':round(max(0,reserve-balance),2),
                     'sources':ev['sources']})
    # Illustrative upper bound: fully drawn peak gap for full project duration.
    duration=max(events)-min(0,min(events))
    simple_interest=peak_gap*apr/100*duration/365
    return {'synthetic':True,'source_id':'uploaded:project_milestones:user_confirmed',
            'cash_waterfall':rows,'peak_external_funding_usd':round(peak_gap,2),
            'minimum_cash_before_financing_usd':round(minimum,2),
            'ending_cash_before_financing_usd':round(balance,2),
            'gross_project_margin_pct':round((total-sum(x['costs'] for x in events.values()))/total*100,2),
            'simple_full_draw_interest_upper_bound_usd':round(simple_interest,2),
            'review_required':True,
            'assumptions':{'payment_delay_days':delay,'cost_overrun_pct':overrun,'illustrative_apr_pct':apr,
                           'receipt_day_0_not_delayed':True,'opening_cash_usd':cash,'protected_reserve_usd':reserve},
            'limitations':['Schedule is user-confirmed synthetic inputs, not contract-authenticated or bank-verified.',
                           'This is a cash requirement estimate, not lender eligibility, affordability or an approval.',
                           'Interest uses fully drawn peak funding through the full duration (indicative upper-bound proxy).',
                           'Taxes, retentions, deposits, guarantees, refinancing and existing obligations must be modeled separately.']}
