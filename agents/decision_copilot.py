"""Policy-driven specialist-agent workflow (NO LLM tool planning).

The conversational text is *never* interpreted as an executable tool instruction.
A trusted backend dispatches a fixed, allowlisted, read-only workflow using an
explicit workflow ID and validated input presence. All financial calculations are
performed by deterministic engines, and the buyer-payment forecast uses a local
scikit-learn model in the existing Coordinator. External effects remain separate
from this service and require the existing OTP/human review workflow.

No private contract, invoice, prompt, account data or LLM token is sent to any
model provider by this class. This class is stateless across users/requests.
"""
from __future__ import annotations

from typing import Any, Literal

from contracts.intelligence import analyze, reconcile
from core.financial_intelligence import financial_summary, budget_stress, project_feasibility
from core.project_cashflow import project_cash_waterfall
from security.injection_guard import inspect

Tool = Literal['financial_eda','contract_review','invoice_reconcile',
               'budget_scenario','bid_risk','cash_waterfall','funding_compare']
ORDER: tuple[Tool, ...] = ('contract_review','invoice_reconcile','financial_eda',
                          'budget_scenario','bid_risk','cash_waterfall','funding_compare')
WORKFLOWS = {'auto', 'financial_health', 'contract_check', 'project_finance', 'contract_to_funding'}
INPUT_KEYS = {'workflow', 'contract_text', 'invoice_text', 'budget', 'project', 'cash_waterfall'}


def choose_tools(question: str, inputs: dict[str, Any]) -> list[Tool]:
    """Legacy entry point; `question` is deliberately ignored for authorization.

    A workflow can *only* be selected by an explicit, schema-like workflow ID
    or by the presence of typed data fields. Phrases in documents cannot add
    a tool and natural-language prompt injection cannot change the plan.
    """
    workflow = inputs.get('workflow', 'auto')
    if not isinstance(workflow, str) or workflow not in WORKFLOWS:
        raise ValueError('Unknown workflow; choose an allowlisted workflow ID')
    if not isinstance(inputs.get('contract_text', ''), str) or not isinstance(inputs.get('invoice_text', ''), str):
        raise ValueError('Contract and invoice text must be strings')
    for key in ('project', 'budget', 'cash_waterfall'):
        if key in inputs and not isinstance(inputs[key], dict):
            raise ValueError(f'{key} must be a structured object')
    has_contract = bool(inputs.get('contract_text'))
    has_invoice = bool(inputs.get('invoice_text'))
    has_project = bool(inputs.get('project'))
    has_budget = bool(inputs.get('budget'))
    has_schedule = bool(inputs.get('cash_waterfall'))

    selected: set[Tool] = set()
    if workflow == 'auto':
        if has_contract: selected.add('contract_review')
        if has_contract and has_invoice: selected.add('invoice_reconcile')
        if has_budget: selected.add('budget_scenario')
        if has_project: selected.add('bid_risk')
        if has_schedule: selected.add('cash_waterfall')
        selected.add('financial_eda')
        if has_project or has_schedule: selected.add('funding_compare')
    elif workflow == 'financial_health':
        selected.add('financial_eda')
        if has_budget: selected.add('budget_scenario')
    elif workflow == 'contract_check':
        if not has_contract: raise ValueError('contract_check requires contract_text')
        selected.add('contract_review')
        if has_invoice: selected.add('invoice_reconcile')
    elif workflow == 'project_finance':
        if not (has_project or has_schedule):
            raise ValueError('project_finance requires project or cash_waterfall')
        selected.update(['financial_eda', 'funding_compare'])
        if has_project: selected.add('bid_risk')
        if has_schedule: selected.add('cash_waterfall')
        if has_budget: selected.add('budget_scenario')
    elif workflow == 'contract_to_funding':
        if not has_contract or not (has_project or has_schedule):
            raise ValueError('contract_to_funding needs contract_text plus structured project or cash_waterfall')
        selected.update(['contract_review','financial_eda','funding_compare'])
        if has_invoice: selected.add('invoice_reconcile')
        if has_project: selected.add('bid_risk')
        if has_schedule: selected.add('cash_waterfall')
        if has_budget: selected.add('budget_scenario')
    return [tool for tool in ORDER if tool in selected]


def _summaries(results: dict[str, Any]) -> list[str]:
    statements: list[str] = []
    r = results.get('contract_review')
    if r:
        statements.append(f"Contract: {r['risk_signal_count']} review flag(s). Uploaded text is not proof of authenticity.")
    r = results.get('invoice_reconcile')
    if r:
        statements.append('Contract/invoice amounts differ and require investigation.' if r['amount_mismatch']
                          else 'No amount mismatch found by text matching; authenticity is unverified.')
    r = results.get('financial_eda')
    if r:
        statements.append(f"Synthetic current ratio: {r['ratios']['current_ratio']}; DSCR proxy: {r['ratios']['dscr_proxy']} (not bank CFADS).")
    r = results.get('budget_scenario')
    if r:
        statements.append(f"Budget ending cash: USD {r['scenario_ending_cash_usd']:,.2f}; reserve breach: {r['reserve_breach']}.")
    r = results.get('bid_risk')
    if r:
        statements.append(f"Project funding gap: USD {r['initial_funding_gap_usd']:,.2f}; delayed-advance/cost-stress gap: USD {r['stress_gap_if_advance_delayed_and_cost_overruns_usd']:,.2f}.")
    r = results.get('cash_waterfall')
    if r:
        statements.append(f"Milestone-based reserve-adjusted peak funding need: USD {r['peak_external_funding_usd']:,.2f}.")
    r = results.get('funding_compare')
    if r:
        options = r['eligible_options']
        statements.append((f"Illustrative APR catalog (separate synthetic invoice): {options[0]['name']}, {options[0]['apr_pct']}%. NOT project-specific loan eligibility; human underwriting required."
                           if options else 'No provisionally eligible funding option in the demo catalog.'))
    return statements


class DecisionCopilot:
    """Read-only, stateless specialist workflow; accepts unused legacy `llm` argument."""

    def __init__(self, llm: Any = None):
        # Intentionally discard the client; there is no provider call from any workflow.
        pass

    def reset(self) -> None:
        pass

    def run(self, question: str, inputs: dict[str, Any], *, funding_options: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        if not isinstance(question, str) or not question.strip() or len(question) > 1200:
            raise ValueError('question must contain 1–1200 characters')
        if not isinstance(inputs, dict) or set(inputs) - INPUT_KEYS or len(str(inputs)) > 80000:
            raise ValueError('inputs must be bounded and contain only recognized fields')
        selected = choose_tools(question, inputs)
        # Do not run financing from contradictory document and structured values.
        # If OCR found no unique total, the numerical scenario remains explicitly
        # user-provided and needs human verification (no inferred amount).
        cash_schedule = inputs.get('cash_waterfall')
        project = inputs.get('project')
        if project and cash_schedule:
            from contracts.intelligence import _money
            a = _money(project.get('contract_value_usd'), 'project.contract_value_usd')
            b = _money(cash_schedule.get('contract_value_usd'), 'cash_waterfall.contract_value_usd')
            if abs(a-b) > .01:
                raise ValueError('Contract totals differ between project and milestone schedule; verify before financing')
        if 'contract_review' in selected and (project or cash_schedule):
            extracted = analyze(inputs['contract_text'])['extracted']['amounts_usd']
            if len(extracted) == 1:
                from contracts.intelligence import _money
                expected = _money((project or cash_schedule).get('contract_value_usd'), 'contract_value_usd')
                if abs(expected-extracted[0]) > .01:
                    raise ValueError('Document amount conflicts with scenario amount; human reconciliation required')
        results: dict[str, Any] = {}
        trace: list[dict[str, Any]] = []
        sources: list[dict[str, Any]] = []

        def record(tool: Tool, result: dict[str, Any], source: str, caveat: str) -> None:
            results[tool] = result
            trace.append({'step': len(trace) + 1, 'tool': tool, 'state': 'completed', 'source_id': source, 'caveat': caveat})
            sources.append({'source_id': source, 'tool': tool, 'verified': 'synthetic_demo_only'})

        for tool in selected:
            if tool == 'contract_review':
                record(tool, analyze(inputs['contract_text']), 'uploaded:contract_text',
                       'Offline rules flag signals, not proven legal fraud')
            elif tool == 'invoice_reconcile':
                record(tool, reconcile({'contract_text': inputs['contract_text'],
                                        'invoice_text': inputs['invoice_text']}),
                       'uploaded:contract_text+invoice_text', 'Text matching cannot authenticate a document')
            elif tool == 'financial_eda':
                r = financial_summary()
                record(tool, r, r['source_id'], 'Synthetic ledger; no ratio is imputed if data is missing')
            elif tool == 'budget_scenario':
                r = budget_stress(inputs['budget'])
                record(tool, r, r['source_id'], 'No modeled marketing ROI')
            elif tool == 'bid_risk':
                record(tool, project_feasibility(inputs['project']), 'input:project_scenario',
                       'Simplified scenario, not a lending or bid decision')
            elif tool == 'cash_waterfall':
                r = project_cash_waterfall(inputs['cash_waterfall'])
                record(tool, r, r['source_id'], 'User-entered milestones must be verified against originals')
            elif tool == 'funding_compare':
                options = funding_options or []
                eligible = sorted([{'id': x['id'], 'name': x['name'], 'apr_pct': x['apr_pct'],
                                    'amount_usd': x['amount_usd']} for x in options
                                   if x.get('eligible') and x.get('apr_pct') is not None],
                                  key=lambda x: x['apr_pct'])
                record(tool, {'eligible_options': eligible, 'comparison_only': True, 'matched_to_project': False, 'project_credit_eligibility': 'NOT_ASSESSED', 'credit_decision': 'NOT_PERFORMED'},
                       'sandbox:lender_catalog+funding_evaluator', 'Synthetic options belong to existing demo invoice and are NOT matched to this project')
        flags = results.get('contract_review', {}).get('flags', [])
        high_risk = any(f.get('severity') == 'high' for f in flags)
        suspicious_question = inspect(question).suspicious
        return {
            'mode': 'policy-workflow-no-llm',
            'orchestration': 'explicit_policy_and_structured_inputs_only',
            'llm_tools_enabled': False,
            'prompt_injection_ignored': suspicious_question,
            'synthetic': True, 'plan': trace, 'results': results,
            'answer': ' '.join(_summaries(results)), 'citations': sources,
            'decision': 'HUMAN_REVIEW_REQUIRED' if high_risk or any(t in results for t in ('bid_risk','cash_waterfall','funding_compare')) else 'INFORMATIONAL_ONLY',
            'human_actions': ['Verify original contracts and parties',
                              'Confirm all milestones and funding assumptions',
                              'Approve external financing only after Director OTP and bank underwriting'],
        }
