"""CFO assistant: answers questions about cash, funding and scenarios, with sources.

The assistant never calculates. It can only call three fixed tools:

  query_metric(id)       read one metric from an allowlist
  run_scenario(params)   rerun the forecast under typed what-if controls
  explain(source_id)     the formula, source and data version behind a number

Every number in an answer comes from those tool results. The wording is a template, or, when a
model is configured, model-written text that is dropped for the template unless every number in it
is one of the tool results (the number lock). Offline, a rule-based router picks the intent, so the
assistant works with no key and no network. Questions are data: text inside them never triggers
an action.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, ValidationError

from agents.llm_client import LlmClient
from config.settings import SCENARIO_TARIFF_RATE_PCT, Tier
from core.forecasting_engine import compute_ccc
from core.metrics import late_exposure_by_buyer
from schemas.forecast_schemas import ScenarioParams
from security import injection_guard

AGENT = "cfo_assistant"

METRIC_IDS = (
    "cash_today_usd", "ccc_days", "dio_days", "dso_days", "dpo_days", "first_shortfall_week", "shortfall_usd",
    "cheapest_option_name", "cheapest_option_amount_usd", "cheapest_option_apr_pct",
    "runner_up_option_name", "runner_up_option_apr_pct", "blocked_fraud_count",
    "top_late_buyer_name", "top_late_buyer_expected_late_usd", "top_late_buyer_open_usd",
)
INTENTS = ("shortfall", "cheapest_funding", "why_shortfall", "ccc", "dso_whatif", "tariff_whatif", "fx_whatif", "buyer_risk")


@dataclass
class ToolResult:
    """What a tool returned: the values an answer may use and where they came from."""

    values: Dict[str, Any] = field(default_factory=dict)
    sources: List[Tuple[str, str]] = field(default_factory=list)  # (label, source_id)


class IntentChoice(BaseModel):
    """Structured output when a model picks the intent. Numbers are parameters, never results."""

    intent: str
    days: Optional[int] = None
    pct: Optional[float] = None


class Answer(BaseModel):
    text: str


class CfoAssistant:
    """Question answering over the coordinator's current case."""

    def __init__(self, coordinator, llm: Optional[LlmClient] = None) -> None:
        self.coord = coordinator
        self.llm = llm or coordinator.llm

    # ------------------------------------------------------------------ tools
    def _gate(self, tool: str, payload: Dict[str, Any]) -> None:
        self.coord._gate(AGENT, tool, Tier.L1_ANALYZE, payload)

    def query_metric(self, metric_id: str) -> Tuple[Any, str]:
        """Return (value, source_id) for an allowlisted metric. Anything else is refused."""
        if metric_id not in METRIC_IDS:
            raise KeyError(f"metric '{metric_id}' is not on the allowlist")
        self._gate("query_metric", {"metric": metric_id})
        c, forecast = self.coord, self.coord.forecast
        eligible = [o for o in c.options if o.eligible]
        late = late_exposure_by_buyer(c.forecast_inputs.receivables)
        ccc = compute_ccc(c.ledger)
        table: Dict[str, Tuple[Callable[[], Any], str]] = {
            "cash_today_usd": (lambda: c.cash_today, "bank:closing_balance"),
            "ccc_days": (lambda: ccc.ccc, "ledger:ccc"),
            "dio_days": (lambda: ccc.dio, "ledger:ccc"),
            "dso_days": (lambda: ccc.dso, "ledger:ccc"),
            "dpo_days": (lambda: ccc.dpo, "ledger:ccc"),
            "first_shortfall_week": (lambda: forecast.first_shortfall_week, f"forecast:{c.forecast_run_id}"),
            "shortfall_usd": (lambda: forecast.shortfall_usd, f"forecast:{c.forecast_run_id}"),
            "cheapest_option_name": (lambda: eligible[0].name, f"funding:{eligible[0].id}" if eligible else "funding"),
            "cheapest_option_amount_usd": (lambda: eligible[0].amount_usd, f"funding:{eligible[0].id}" if eligible else "funding"),
            "cheapest_option_apr_pct": (lambda: eligible[0].apr_pct, f"funding:{eligible[0].id}" if eligible else "funding"),
            "runner_up_option_name": (lambda: eligible[1].name, f"funding:{eligible[1].id}" if len(eligible) > 1 else "funding"),
            "runner_up_option_apr_pct": (lambda: eligible[1].apr_pct, f"funding:{eligible[1].id}" if len(eligible) > 1 else "funding"),
            "blocked_fraud_count": (lambda: c.blocked_fraud_count, "alerts:bec"),
            "top_late_buyer_name": (lambda: late[0][1], "receivables:late_exposure"),
            "top_late_buyer_open_usd": (lambda: late[0][2], "receivables:late_exposure"),
            "top_late_buyer_expected_late_usd": (lambda: late[0][3], "receivables:late_exposure"),
        }
        getter, source = table[metric_id]
        try:
            return getter(), source
        except IndexError:
            return None, source

    def run_scenario(self, params: ScenarioParams):
        """Rerun the forecast under what-if controls (an engine call)."""
        return self.coord.simulate(params)

    def explain(self, source_id: str) -> str:
        """Plain-text provenance for a source id: what it is, its formula and the data version."""
        self._gate("explain", {"source": source_id})
        version = f"seed data as of {self.coord.as_of.isoformat()}"
        kind = source_id.split(":", 1)[0]
        text = {
            "forecast": f"13-week direct forecast: expected inflow = invoice value x chance of on-time payment, late share four weeks later ({version})",
            "funding": f"APR = total cost / net funds received x 365 / days outstanding ({version})",
            "ledger": f"CCC = days of inventory + days of sales outstanding - days of payables, from the ledger ({version})",
            "scenario": f"Forecast rerun with the what-if controls applied ({version})",
            "receivables": f"Expected late value = invoice value x (1 - chance of on-time payment), per buyer ({version})",
            "bank": f"Closing balance of the operating account ({version})",
            "alerts": f"Inbox messages that were blocked by the fraud checks ({version})",
        }.get(kind, f"Engine output ({version})")
        return text

    # ------------------------------------------------------------------ asking
    def ask(self, question: str) -> Dict[str, Any]:
        """Answer one question. Returns a chat message with citations."""
        flagged = injection_guard.inspect(question).suspicious
        choice = self._route(question)
        try:
            tool = self._execute(choice)
        except (KeyError, ValueError, ValidationError) as error:
            tool = ToolResult(values={"_reply": f"I cannot run that: {error}"})
        template = self._compose(choice, tool)
        locked = {k: v for k, v in tool.values.items() if not str(k).startswith("_")}
        text = template
        if self.llm.current_mode() == "live-llm" and choice.intent in INTENTS:
            prompt = (
                "Answer the finance question in two or three plain sentences using only the facts in this JSON. "
                f"Do not add numbers. Facts: {self._facts_json(tool)}"
            )
            result = self.llm.complete_structured(
                prompt, Answer, Answer(text=template), untrusted=question, locked_metrics=locked
            )
            text = result.value.text
        if flagged:
            text += " Text inside questions is treated as data, not as instructions."
        citations = [{"label": f"{label} ({self.explain(source)})", "source_id": source} for label, source in tool.sources]
        return {"role": "assistant", "text": text, "citations": citations, "mode": self.llm.current_mode()}

    @staticmethod
    def _facts_json(tool: ToolResult) -> str:
        import json

        return json.dumps({k: (float(v) if isinstance(v, Decimal) else v) for k, v in tool.values.items() if not str(k).startswith("_")}, default=str)

    # ---------------------------------------------------------------- routing
    def _route(self, question: str) -> IntentChoice:
        fallback = lambda: self.rule_route(question)  # noqa: E731
        if self.llm.current_mode() != "live-llm":
            return fallback()
        prompt = (
            f"Pick the one intent that best matches the question from {list(INTENTS)}. "
            "For what-if intents also give days (DSO change) or pct (tariff share or FX move) if the question states them. "
            "Reply with intent null-like 'unknown' if none fits."
        )
        result = self.llm.complete_structured(prompt, IntentChoice, fallback, untrusted=question, check_numbers=False)
        chosen = result.value
        return chosen if chosen.intent in INTENTS else fallback()

    @staticmethod
    def rule_route(question: str) -> IntentChoice:
        """Deterministic intent router used offline (and as the live fallback)."""
        q = question.lower()
        number = re.search(r"(\d+(?:\.\d+)?)\s*(days?|d\b|%|percent|per cent)", q)
        value = float(number.group(1)) if number else None
        sign = -1 if re.search(r"\b(sooner|earlier|faster|quicker|shorter|reduce|cut|improve)\b", q) else 1
        if "tariff" in q:
            share = 50.0 if re.search(r"\bhalf\b", q) else value
            return IntentChoice(intent="tariff_whatif", pct=share)
        if re.search(r"\b(fx|exchange rates?|currenc\w*|yen|yuan|jpy|cny|rmb)\b", q):
            down = re.search(r"\b(weak|weaken|fall|falls|drop|drops|down|lose|lower|decline)\w*", q)
            return IntentChoice(intent="fx_whatif", pct=(-(value if value is not None else 5.0) if down or value is None else value))
        days_stated = re.search(r"\d+\s*days?", q)
        paying = re.search(r"\b(pay|pays|paid|payment|collect\w*|dso|delay\w*|late|later|sooner|earlier|slower|faster)\b", q)
        if re.search(r"\b(dso|collect\w*)\b", q) or (days_stated and paying) or (
            re.search(r"\b(if|suppose)\b", q) and re.search(r"\b(pay|pays) (me )?(later|slower|late)\b|\bpaid later\b|\bdelays?\b", q)
        ):
            return IntentChoice(intent="dso_whatif", days=int(sign * (value if value is not None else 15)))
        if re.search(r"\b(buyer|customer|client)s?\b", q) and re.search(r"\b(risk|risky|late|worst|biggest|exposed|concentrat)\w*", q):
            return IntentChoice(intent="buyer_risk")
        if re.search(r"\bwhy\b", q) or re.search(r"\b(cause|causes|driver|drivers|reason|reasons|explain)\b", q):
            return IntentChoice(intent="why_shortfall")
        if re.search(r"\b(ccc|cash conversion|dio|dpo|working capital cycle)\b", q):
            return IntentChoice(intent="ccc")
        if re.search(r"\b(cheap|cheapest|funding|finance|financing|loan|apr|option|options|factoring|borrow|bridge)\w*", q):
            return IntentChoice(intent="cheapest_funding")
        if re.search(r"\b(short|shortfall|gap|run out|negative|cash|runway|when)\b", q):
            return IntentChoice(intent="shortfall")
        return IntentChoice(intent="unknown")

    # --------------------------------------------------------------- execution
    def _execute(self, choice: IntentChoice) -> ToolResult:
        intent = choice.intent
        out = ToolResult()

        def metric(name: str, label: str) -> Any:
            value, source = self.query_metric(name)
            out.values[name] = value
            if (label, source) not in out.sources:
                out.sources.append((label, source))
            return value

        if intent == "shortfall":
            metric("first_shortfall_week", "Forecast")
            metric("shortfall_usd", "Forecast")
            metric("cash_today_usd", "Cash today")
        elif intent == "cheapest_funding":
            for name in ("cheapest_option_name", "cheapest_option_amount_usd", "cheapest_option_apr_pct", "runner_up_option_name", "runner_up_option_apr_pct"):
                metric(name, "Funding calculation")
        elif intent == "why_shortfall":
            metric("first_shortfall_week", "Forecast")
            metric("shortfall_usd", "Forecast")
            drivers = [a for a in self.coord.forecast.attribution if a.source_ref != "ledger:baseline"]
            ordered = sorted(drivers, key=lambda a: a.amount_usd, reverse=True)[:2]
            for index, item in enumerate(ordered, start=1):
                out.values[f"driver_{index}_usd"] = item.amount_usd
                out.values[f"_driver_{index}_ref"] = item.source_ref
            out.sources.append(("Shortfall attribution", f"forecast:{self.coord.forecast_run_id}"))
        elif intent == "ccc":
            for name in ("ccc_days", "dio_days", "dso_days", "dpo_days"):
                metric(name, "Cash conversion cycle")
        elif intent in ("dso_whatif", "tariff_whatif", "fx_whatif"):
            out = self._scenario(choice)
        elif intent == "buyer_risk":
            for name in ("top_late_buyer_name", "top_late_buyer_open_usd", "top_late_buyer_expected_late_usd"):
                metric(name, "Receivables risk")
        else:
            out.values["_reply"] = (
                "I can answer questions about the cash shortfall and its causes, the cheapest funding option, the cash conversion cycle, "
                "what-if scenarios (slower collections, a shared tariff, an FX move) and which buyer is most at risk."
            )
        return out

    def _scenario(self, choice: IntentChoice) -> ToolResult:
        defaults = {"dso_whatif": ("dso_change_days", 15), "tariff_whatif": ("tariff_shared_pct", 50), "fx_whatif": ("fx_change_pct", -5)}
        field_name, default = defaults[choice.intent]
        raw = choice.days if choice.intent == "dso_whatif" and choice.days is not None else (choice.pct if choice.pct is not None else default)
        params = ScenarioParams(**{field_name: raw})
        result = self.run_scenario(params)
        delta = result.delta
        out = ToolResult()
        out.values.update(
            {
                "scenario_value": abs(raw), "week_before": delta.first_shortfall_week_before, "week_after": delta.first_shortfall_week_after,
                "min_closing_before_usd": delta.min_closing_before_usd, "min_closing_after_usd": delta.min_closing_after_usd,
                "_direction": "up" if raw > 0 else "down", "_field": field_name,
            }
        )
        if choice.intent == "tariff_whatif":
            out.values["scenario_tariff_rate_pct"] = SCENARIO_TARIFF_RATE_PCT
        out.sources.append(("Scenario rerun", f"scenario:{field_name}"))
        return out

    # ------------------------------------------------------------------ wording
    def _compose(self, choice: IntentChoice, tool: ToolResult) -> str:
        v = tool.values
        usd = lambda x: f"USD {Decimal(x):,.2f}"  # noqa: E731
        usd0 = lambda x: f"USD {Decimal(x):,.0f}"  # noqa: E731
        if "_reply" in v:
            return v["_reply"]
        intent = choice.intent
        if intent == "shortfall":
            if v["first_shortfall_week"] is None:
                return f"No shortfall is forecast: cash stays above zero in every week. Cash today is {usd0(v['cash_today_usd'])}."
            return (f"Week {v['first_shortfall_week']} is expected to be short by {usd(v['shortfall_usd'])}. "
                    f"Cash today is {usd0(v['cash_today_usd'])}.")
        if intent == "cheapest_funding":
            if v["cheapest_option_name"] is None:
                return "No funding option is eligible right now."
            text = (f"The cheapest way to bridge the gap is {v['cheapest_option_name']}: {usd(v['cheapest_option_amount_usd'])} "
                    f"at about {float(v['cheapest_option_apr_pct']):.1f}% a year.")
            if v.get("runner_up_option_name"):
                text += f" The next cheapest is {v['runner_up_option_name']} at about {float(v['runner_up_option_apr_pct']):.1f}%."
            return text
        if intent == "why_shortfall":
            if v["first_shortfall_week"] is None:
                return "There is no shortfall to explain."
            parts = [self._driver_phrase(v[f"_driver_{i}_ref"], v[f"driver_{i}_usd"], usd0) for i in (1, 2) if f"driver_{i}_usd" in v]
            return (f"Week {v['first_shortfall_week']} is short by {usd(v['shortfall_usd'])}, mainly because of " + " and ".join(parts) + ".")
        if intent == "ccc":
            return (f"The cash conversion cycle is {v['ccc_days']:g} days: {v['dio_days']:g} days of stock plus {v['dso_days']:g} days "
                    f"to collect from buyers, minus {v['dpo_days']:g} days to pay suppliers.")
        if intent in ("dso_whatif", "tariff_whatif", "fx_whatif"):
            return self._scenario_text(intent, v, usd0)
        if intent == "buyer_risk":
            if v["top_late_buyer_name"] is None:
                return "There are no open receivables to assess."
            return (f"{v['top_late_buyer_name']} carries the most late-payment risk: about {usd0(v['top_late_buyer_expected_late_usd'])} "
                    f"of its {usd0(v['top_late_buyer_open_usd'])} in open invoices is expected to arrive late.")
        return "I can answer questions about cash, funding and scenarios."

    @staticmethod
    def _driver_phrase(ref: str, amount: Any, usd0: Callable[[Any], str]) -> str:
        kind, _, ident = ref.partition(":")
        what = {"doc": f"the supplier deposit on {ident}", "inv": f"the likely-late invoice {ident}"}.get(kind, "a scenario change")
        return f"{what} ({usd0(amount)})"

    @staticmethod
    def _scenario_text(intent: str, v: Dict[str, Any], usd0: Callable[[Any], str]) -> str:
        n = f"{v['scenario_value']:g}"
        if intent == "dso_whatif":
            lead = f"If buyers pay {n} days {'later' if v['_direction'] == 'up' else 'sooner'}"
        elif intent == "tariff_whatif":
            lead = f"If you absorb {n}% of a hypothetical {v['scenario_tariff_rate_pct']:g}% tariff on US sales"
        else:
            lead = f"If the yen and yuan {'strengthen' if v['_direction'] == 'up' else 'weaken'} by {n}%"
        before, after = v["week_before"], v["week_after"]
        week = (f"the first shortfall stays in week {after}" if before == after and after is not None
                else f"the first shortfall moves from week {before} to week {after}" if before is not None and after is not None
                else "the shortfall disappears" if after is None else f"a shortfall appears in week {after}")
        return (f"{lead}, {week}, and the lowest cash balance goes from {usd0(v['min_closing_before_usd'])} "
                f"to {usd0(v['min_closing_after_usd'])}.")
