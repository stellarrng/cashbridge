import type { AutopilotRun } from "@/entities/autopilot";
import type { ForecastWeek } from "@/entities/forecast";
import type { LockedMetric, PackVerification } from "@/entities/funding";
import type { ScannedDocument } from "@/entities/case";

export interface InboxItem {
  pack_id: string;
  company: string;
  product: string;
  amount_usd: number;
  apr_pct: number;
  invoice_no: string;
  prepared_by: string;
  submitted_by: string;
  lender_ref: string;
  review: { status: string };
}

export interface BankReview {
  status: string;
  decision: string | null;
  reviewer: string | null;
  note: string | null;
  verification: PackVerification | null;
}

export interface BankCase {
  pack_id: string;
  company: string;
  prepared_by: string;
  approved_by: string;
  lender_ref: string;
  product: { name?: string; amount_usd: number; apr_pct: number };
  invoice: {
    invoice_no: string;
    amount_usd: number;
    buyer: string;
    issue_date: string;
    due_date: string;
    three_way?: { status: string } | null;
    scans: ScannedDocument[];
  };
  buyer_risk: { p_on_time: number } | null;
  /** v9 behavioural model, shown as a labelled second opinion; not a credit decision. */
  buyer_behaviour_cross_check?: { p_on_time: number } | null;
  autopilot: Pick<AutopilotRun, "run_id" | "evidence" | "evidence_counts" | "recommendation"> | null;
  review: BankReview;
  review_checklist: string[];
  locked_metrics: LockedMetric[];
  bundle_sha256: string;
  letter_text: string;
  forecast: { weeks: ForecastWeek[] };
  not_shared: string[];
}

export type BankDecision = "APPROVE_FUNDING" | "REQUEST_INFO" | "DECLINE";
