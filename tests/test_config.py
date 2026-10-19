"""Settings and tool allowlists (Step 0.2)."""

from decimal import Decimal

from config import settings
from config.settings import Tier, is_demo_mode
from config.tool_allowlist import L3_TOOLS, L4_TOOLS, TOOL_ALLOWLIST, TOOL_TIERS


def test_spec_constants():
    assert (settings.USD_VND, settings.JPY_VND, settings.CNY_VND) == (26_000, 175, 3_650)
    assert settings.INTERMEDIARY_FEE_TOLERANCE_USD == Decimal("50")
    assert settings.THREE_WAY_AMOUNT_TOLERANCE == Decimal("0.01")
    assert settings.FORECAST_WEEKS == 13
    assert settings.MIN_CASH_BUFFER_USD == Decimal("10000")
    assert settings.OTP_VALIDITY_SECONDS == 120
    assert settings.LLM_TIMEOUT_SECONDS == 8
    assert settings.EXTRACTION_CONFIDENCE_THRESHOLD == 0.85
    assert settings.MAX_SUBSET_SIZE == 6
    assert settings.CCC_TARGET_DAYS == {"dio": 35, "dso": 75, "dpo": 28, "ccc": 82}


def test_demo_mode_true_without_key():
    assert is_demo_mode({}) is True
    assert is_demo_mode({"LLM_API_KEY": "   "}) is True
    assert is_demo_mode({"LLM_API_KEY": "sk-test"}) is False


def test_tiers():
    assert [t.value for t in Tier] == [
        "L0_READ", "L1_ANALYZE", "L2_INTERNAL_WRITE", "L3_EXTERNAL", "L4_MONEY_MOVEMENT",
    ]


def test_only_coordinator_can_submit_or_send():
    for agent, tools in TOOL_ALLOWLIST.items():
        if agent == "coordinator":
            assert L3_TOOLS <= tools
        else:
            assert not (L3_TOOLS & tools), agent


def test_no_l4_tool_exists_for_anyone():
    registered_l4 = {name for name, tier in TOOL_TIERS.items() if tier is Tier.L4_MONEY_MOVEMENT}
    assert registered_l4 == set()
    for tools in TOOL_ALLOWLIST.values():
        assert not (L4_TOOLS & tools)


def test_every_allowlisted_tool_is_registered():
    for tools in TOOL_ALLOWLIST.values():
        assert tools <= set(TOOL_TIERS)
