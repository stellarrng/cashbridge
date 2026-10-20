import { download, get, post, request } from "@/shared/api/client";
import type { CaseMessage, EvidenceRequest, EvidenceView, Notification, PlanningRequest, QualityResult, RequestsView, ScenarioResult } from "./types";

const caseBase = (packId: string) => `/api/workspace/cases/${encodeURIComponent(packId)}`;
const evBase = (packId: string) => caseBase(packId) + "/evidence";

// ---- SME planning changes and appeals (never touch the ledger or a lending decision)
export const fetchRequests = () => get<RequestsView>("/api/workspace/requests");
export const proposeChange = (field: string, proposed_value: string, reason: string) =>
  post<PlanningRequest>("/api/workspace/requests", { field, proposed_value, reason });
export const reviewRequest = (id: string, approve: boolean, note: string) =>
  post<unknown>(`/api/workspace/requests/${encodeURIComponent(id)}/review`, { approve, note });
export const appeal = (evidence_ref: string, reason: string) => post<unknown>("/api/workspace/appeals", { evidence_ref, reason });
export const runScenario = (available_cash_usd: number, minimum_reserve_usd: number) =>
  post<ScenarioResult>("/api/workspace/scenario", { available_cash_usd, minimum_reserve_usd });
export const checkQuality = (body: unknown) => post<QualityResult>("/api/workspace/quality", body);

// ---- the released case, shared by the SME and its lender
export const fetchSnapshotPackId = () => get<{ pack: { pack_id: string | null } }>("/api/snapshot").then((s) => s.pack.pack_id);
export const fetchBankFirstPack = () => get<{ items: Array<{ pack_id: string }> }>("/api/bank/inbox").then((r) => r.items[0]?.pack_id ?? null);
export const fetchMessages = (packId: string) => get<{ items: CaseMessage[] }>(caseBase(packId) + "/messages");
export const postMessage = (packId: string, kind: string, message: string) => post<unknown>(caseBase(packId) + "/messages", { kind, message });
export const fetchNotifications = () => get<{ items: Notification[] }>("/api/workspace/notifications");

// ---- lender evidence requests
export const fetchEvidence = (packId: string) => get<EvidenceView>(evBase(packId));
export const openRequest = (packId: string, item: string, detail: string, due_days: number) => post<EvidenceRequest>(evBase(packId), { item, detail, due_days });
/** The SME uploads the document: the server checks its type, computes the SHA-256 and stores it encrypted. */
export function uploadEvidence(packId: string, rid: string, file: File, ref: string, note: string) {
  const body = new FormData();
  body.append("file", file, file.name);
  body.append("ref", ref);
  body.append("note", note);
  return request<EvidenceRequest>(`${evBase(packId)}/${encodeURIComponent(rid)}/upload`, { method: "POST", body });
}
/** Opening the file through CashBridge is logged and, for the lender, is what allows "Accept". */
export const openEvidenceFile = (packId: string, rid: string, filename: string) => download(`${evBase(packId)}/${encodeURIComponent(rid)}/file`, filename);
export const reviewEvidence = (packId: string, rid: string, body: { accept: boolean; reason: string; version: number; received_sha256?: string }) =>
  post<EvidenceRequest>(`${evBase(packId)}/${encodeURIComponent(rid)}/review`, body);
export const revokeRequest = (packId: string, rid: string, reason: string) => post<EvidenceRequest>(`${evBase(packId)}/${encodeURIComponent(rid)}/revoke`, { reason });
