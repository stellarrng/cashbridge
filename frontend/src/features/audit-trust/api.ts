import { get, post } from "@/shared/api/client";

export interface Scorecard {
  generated_at: string;
  summary: {
    security: { passed: number; total: number };
    agent: { passed: number; total: number };
    model: { brier_model: number; brier_baseline: number };
  };
  security: Array<{ id: string; title: string; passed: boolean }>;
  agent: Array<{ id: string; title: string; passed: boolean; got?: string }>;
  model: { caveat: string };
}

export interface ChainCheck {
  ok: boolean;
  lines_checked: number;
  broken_seq: number | null;
}

/** Public: the scorecard is the same for the SME and the lender, and is shown before sign-in on the landing page. */
export const fetchScorecard = () => get<Scorecard>("/api/trust/scorecard", { anonymous: true });
export const verifyChain = () => post<ChainCheck>("/api/verify_chain");
export const tamperDemo = () => post<ChainCheck>("/api/tamper_demo");

export interface ChainAnchor { index: number; root: string; entries: number; last_entry_hash: string; anchored_at: number; publisher: string; reproduced?: boolean }
export interface ChainStatus {
  available: boolean;
  reason?: string;
  network?: string;
  block?: number;
  contracts?: Record<string, { compiler: string; source_sha256: string; address: string }>;
  members?: string[];
  registrations?: number;
  duplicates_refused?: number;
  anchors?: number;
  on_chain_data?: string;
  invoice?: { invoice_no: string; commitment: string; active: boolean; holder: string | null } | null;
  audit?: { anchors: ChainAnchor[]; all_reproduced: boolean; log_entries: number };
}
export interface ChainProof { entry: number; line_sha256: string; anchor_index: number; root: string; path: [string, string][]; verified: boolean;
  event: { seq: number; agent: string; tool: string; decision: string; reason: string } }

/** On-chain consortium (in-process EVM): cross-lender invoice register and audit-log anchors. */
export const fetchChain = () => get<ChainStatus>("/api/chain/status");
export const anchorNow = () => post<{ index: number; root: string; entries: number; block: number }>("/api/chain/anchor");
export const chainProof = (entry: number) => get<ChainProof>(`/api/chain/proof/${entry}`);
export const duplicateDrill = () => post<{ refused: boolean; holder: string; block: number }>("/api/chain/drill");
