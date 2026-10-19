import type { Snapshot } from "./types";

export type TabKey = "anticipate" | "prove" | "compare" | "approve" | "evidence" | "green" | "plan" | "analytics" | "contracts" | "bank";

export const TABS: { key: TabKey; title: string; blurb: string }[] = [
  { key: "anticipate", title: "Anticipate", blurb: "See the cash gap coming and what causes it." },
  { key: "prove", title: "Prove", blurb: "Match payments to invoices and check each invoice is safe to finance." },
  { key: "compare", title: "Compare", blurb: "Weigh every way to bridge the gap by what it really costs per year." },
  { key: "approve", title: "Approve", blurb: "Lock the numbers, draft the pack and get the Director's one-time approval." },
  { key: "plan", title: "Capital Planner", blurb: "Test budget allocation, reserve pressure, and illustrative funding gaps." },
  { key: "green", title: "Green Finance", blurb: "Prepare green project evidence for independent SME and bank review." },
  { key: "analytics", title: "Analytics", blurb: "EDA, financial ratios, marketing stress and project feasibility." },
  { key: "contracts", title: "Contracts", blurb: "Extract clauses, review financial risks and draft an unsigned agreement." },
  { key: "bank", title: "Bank Review", blurb: "Read-only SME credit evidence preview for human reviewers." },
  { key: "evidence", title: "Evidence", blurb: "The tamper-evident record of everything the system did." },
];

export interface Step {
  key: TabKey;
  title: string;
  state: "done" | "current" | "todo";
}

export interface Guide {
  steps: Step[];
  next: { label: string; tab: TabKey } | null;
}

/** Where the user is in the four-step loop and what to do next. Reads state only; calculates nothing. */
export function guide(snap: Snapshot, visited: ReadonlySet<TabKey>): Guide {
  const chosen = snap.selected_option_id !== null;
  const status = snap.pack.status;
  // Progress follows the case, not just page views: once an option is chosen the earlier steps are behind you.
  const done: Record<string, boolean> = {
    anticipate: visited.has("anticipate") || chosen,
    prove: visited.has("prove") || chosen,
    compare: chosen || status !== "NOT_STARTED",
    approve: status === "SUBMITTED",
  };
  const order: TabKey[] = ["anticipate", "prove", "compare", "approve"];
  const firstOpen = order.find((k) => !done[k]);
  const steps = order.map<Step>((key) => ({
    key,
    title: TABS.find((t) => t.key === key)!.title,
    state: done[key] ? "done" : key === firstOpen ? "current" : "todo",
  }));

  let next: Guide["next"] = null;
  if (!done.anticipate) next = { label: "Read the cash forecast", tab: "anticipate" };
  else if (!done.prove) next = { label: "See how each invoice is proven", tab: "prove" };
  else if (!chosen) next = { label: "Compare the ways to bridge the gap", tab: "compare" };
  else if (status === "NOT_STARTED") next = { label: "Prepare the funding pack", tab: "approve" };
  else if (status === "AWAITING_APPROVAL") next = { label: "Approve and submit the pack", tab: "approve" };
  else if (status === "SUBMITTED") next = { label: "Review the evidence", tab: "evidence" };
  return { steps, next };
}
