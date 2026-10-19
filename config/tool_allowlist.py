"""Tool registry and per-agent allowlists (instructions.md section 3, Rule 2).

Every tool has exactly one tier. Each agent has a fixed list of tools. Only the
coordinator holds ``submit_pack`` and ``send_email`` (both L3). No agent holds
an L4 tool: those names exist only so the gatekeeper can refuse them.
"""

from __future__ import annotations

from typing import Dict, FrozenSet

from config.settings import Tier

TOOL_TIERS: Dict[str, Tier] = {
    # L0: read granted sources
    "read_bank_statements": Tier.L0_READ,
    "read_documents": Tier.L0_READ,
    "read_inbox": Tier.L0_READ,
    "read_payment_history": Tier.L0_READ,
    # L1: analyze and draft
    "reconcile": Tier.L1_ANALYZE,
    "subset_sum": Tier.L1_ANALYZE,
    "three_way_match": Tier.L1_ANALYZE,
    "run_forecast": Tier.L1_ANALYZE,
    "rank_funding_options": Tier.L1_ANALYZE,
    "scan_email": Tier.L1_ANALYZE,
    "query_metric": Tier.L1_ANALYZE,
    "run_scenario": Tier.L1_ANALYZE,
    "explain": Tier.L1_ANALYZE,
    "draft_text": Tier.L1_ANALYZE,
    "parse_reply": Tier.L1_ANALYZE,
    "schedule_reminders": Tier.L1_ANALYZE,
    "score_buyer_risk": Tier.L1_ANALYZE,
    # L2: internal writes
    "ledger_write": Tier.L2_INTERNAL_WRITE,
    "lock_period": Tier.L2_INTERNAL_WRITE,
    # L2 written by a named human at the lender, never by an agent
    "record_credit_decision": Tier.L2_INTERNAL_WRITE,
    # L3: leaves the system, OTP from the Director every time
    "submit_pack": Tier.L3_EXTERNAL,
    "send_email": Tier.L3_EXTERNAL,
}

# Names the gatekeeper recognises as money movement. They appear in no allowlist.
L4_TOOLS: FrozenSet[str] = frozenset({"update_payee", "transfer_funds", "make_payment"})

L3_TOOLS: FrozenSet[str] = frozenset(
    name for name, tier in TOOL_TIERS.items() if tier is Tier.L3_EXTERNAL
)

TOOL_ALLOWLIST: Dict[str, FrozenSet[str]] = {
    "coordinator": frozenset(
        {
            "read_bank_statements",
            "read_documents",
            "read_inbox",
            "read_payment_history",
            "reconcile",
            "run_forecast",
            "rank_funding_options",
            "scan_email",
            "ledger_write",
            "lock_period",
            "submit_pack",
            "send_email",
        }
    ),
    "cfo_assistant": frozenset({"query_metric", "run_scenario", "explain", "draft_text"}),
    "document_agent": frozenset(
        {"read_documents", "three_way_match", "reconcile", "subset_sum", "draft_text"}
    ),
    "collections_agent": frozenset(
        {"read_payment_history", "schedule_reminders", "draft_text", "parse_reply"}
    ),
    "buyer_risk_agent": frozenset({"read_payment_history", "score_buyer_risk"}),
    # The lender's human reviewer (bank portal). Reads the submitted pack, records a decision.
    "bank_reviewer": frozenset({"read_documents", "record_credit_decision"}),
}


def tools_for(agent: str) -> FrozenSet[str]:
    """Return the allowed tools for an agent (empty set for unknown agents)."""
    return TOOL_ALLOWLIST.get(agent, frozenset())
