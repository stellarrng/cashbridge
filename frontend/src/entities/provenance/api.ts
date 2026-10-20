import { get, post } from "@/shared/api/client";
import type { Correction, Lineage } from "./types";

/** SME view of the current pack, or the lender's view of a released pack. */
export const lineageUrl = (packId?: string) => (packId ? `/api/bank/cases/${encodeURIComponent(packId)}/provenance` : "/api/provenance");
export const fetchLineage = (url: string) => get<Lineage>(url);
export const proposeCorrection = (body: { metric_key: string; source_ref: string; proposed_value: string; reason: string }) =>
  post<Correction>("/api/provenance/corrections", body);
export const decideCorrection = (id: string, approve: boolean, note: string) =>
  post<Correction>(`/api/provenance/corrections/${encodeURIComponent(id)}/decision`, { approve, note });
