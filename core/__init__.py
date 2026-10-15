"""CashBridge core module exports."""

from core.forecasting_engine import calculate_ccc, run_13_week_forecast, simulate_forecast
from core.matching_engine import (
    run_3way_match,
    run_subset_sum_reconciliation,
    compute_bundle_hash,
)
from core.funding_evaluator import (
    evaluate_liquidity_options,
    summarise_comparison,
    annualized_simple_cost,
    effective_apr,
    check_facility_compatibility,
    build_factoring_facility,
    build_early_discount_facility,
    build_bridge_facility,
)
from core.cryptographic_registry import (
    register_invoice,
    is_invoice_registered,
    find_by_bundle_hash,
    check_registration,
    get_registry,
    get_chain_head,
    verify_chain_integrity,
    DoubleFinancingError,
    RegistryConflictError,
)
from core.pdf_compiler import generate_funding_pack_pdf

__all__ = [
    "calculate_ccc",
    "run_13_week_forecast",
    "simulate_forecast",
    "run_3way_match",
    "run_subset_sum_reconciliation",
    "compute_bundle_hash",
    "evaluate_liquidity_options",
    "summarise_comparison",
    "annualized_simple_cost",
    "effective_apr",
    "check_facility_compatibility",
    "build_factoring_facility",
    "build_early_discount_facility",
    "build_bridge_facility",
    "register_invoice",
    "is_invoice_registered",
    "find_by_bundle_hash",
    "check_registration",
    "get_registry",
    "get_chain_head",
    "verify_chain_integrity",
    "DoubleFinancingError",
    "RegistryConflictError",
    "generate_funding_pack_pdf",
]
