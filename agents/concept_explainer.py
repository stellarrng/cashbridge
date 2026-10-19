"""Optional HUMAN-FACING LLM: public finance concepts only, no private case inputs.

This module deliberately has no references to Coordinator, bank connectors,
contracts, documents, accounts, loans or tool execution. It accepts ONLY a
fixed enum. If the user chooses to enable it, only predefined public topic
labels are transmitted to the external provider, never user text or data.
"""
from __future__ import annotations

import os
from typing import Any

from pydantic import BaseModel, Field
from agents.llm_client import LlmClient

TOPICS = {
    'cash_conversion_cycle': 'Cash conversion cycle and its DIO, DSO, DPO components',
    'cash_reserve': 'Why a small business protects a minimum operating cash reserve',
    'financing_apr': 'Annual percentage rate and why a lower fee does not always mean a cheaper short-term loan',
    'contract_milestones': 'Payment milestones and cash-flow gaps in a supply contract',
    'financial_fraud_signals': 'Why invoice mismatches and suspicious contract clauses are review signals rather than fraud proof',
    'green_investment': 'Difference between an energy-saving investment payback estimate and certified green loan eligibility',
}
FALLBACKS = {
    'cash_conversion_cycle': 'CCC measures how long cash is tied up in inventory and unpaid customer invoices, offset by supplier credit. Lower CCC typically releases working capital.',
    'cash_reserve': 'A cash reserve protects payroll, supplier payments and unexpected costs. Compare financing choices after setting a realistic buffer.',
    'financing_apr': 'APR annualizes the all-in financing cost. For short-term borrowing compare fees, repayment timing, net proceeds and eligibility, not headline interest alone.',
    'contract_milestones': 'Milestone payments determine when project cash comes in. Map each receipt and expense to its date, then stress test customer delays and cost overruns.',
    'financial_fraud_signals': 'A mismatch is a reason to review originals, counterparties and transaction records. It is not sufficient evidence to conclude fraud.',
    'green_investment': 'Savings and payback are estimates under assumptions. Taxonomy eligibility, environmental claims and loan approval require separate review.',
}


class PublicExplanation(BaseModel):
    text: str = Field(min_length=20, max_length=550)


class ConceptExplainer:
    def __init__(self, llm: LlmClient | None = None, enabled: bool | None = None):
        self.llm = llm or LlmClient()
        self.enabled = (os.getenv('CASHBRIDGE_CONCEPT_LLM_ENABLED', '').lower() == 'true') if enabled is None else enabled

    def explain(self, topic: str) -> dict[str, Any]:
        if topic not in TOPICS:
            raise ValueError('Choose a recognized public finance topic')
        fallback = PublicExplanation(text=FALLBACKS[topic])
        if not self.enabled:
            return {'topic': topic, 'text': fallback.text, 'mode': 'local-concept-template',
                    'provider_received_private_data': False}
        # The request only contains developer-owned text from TOPICS; no raw
        # question or firm data is ever placed in the model context.
        result = self.llm.complete_structured(
            f'Explain this public finance concept for a beginner: {TOPICS[topic]}. '
            'Do not mention any particular company, person, lender, account, loan amount or case. '
            'Respond with 2 concise sentences and do not include numerals.',
            PublicExplanation, fallback, locked_metrics={})
        return {'topic': topic, 'text': result.value.text,
                'mode': 'public-concept-llm' if result.mode == 'live-llm' else 'local-concept-template',
                'provider_received_private_data': False,
                'fallback_reason': result.reason}
