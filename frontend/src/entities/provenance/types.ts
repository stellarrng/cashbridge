/** Field-level provenance of a locked pack figure (GET /api/provenance, GET /api/bank/cases/{id}/provenance). */
export interface RecordSource {
  kind: "record";
  file: string;
  json_path: string;
  file_sha256: string | null;
  value: string | null;
  review_status: string;
  bbox: null;
}

export interface ScanSource {
  kind: "scan";
  doc_id: string;
  doc_type: string;
  field: string;
  value: string | null;
  page: number | null;
  line: number | null;
  char_start: number | null;
  char_end: number | null;
  source_line: string | null;
  excerpt: string | null;
  span_verified: boolean;
  confidence: number;
  review_status: string;
  text_sha256: string | null;
  /** Always null: scans are text layers, so nothing is located by coordinates. */
  bbox: null;
  bbox_note: string;
}

export type ProvenanceSource = RecordSource | ScanSource;

export interface Correction {
  id: string;
  metric_key: string;
  source_ref: string;
  original_value: string | null;
  proposed_value: string;
  reason: string;
  status: "pending" | "approved" | "rejected";
  proposed_by: string;
  decided_by: string | null;
  decision_note: string | null;
  effect: string;
  locked_pack_changed: false;
}

export interface MetricLineage {
  key: string;
  label: string;
  unit: string;
  locked_value: number | string;
  formula: string;
  computation: string;
  recomputed_now: number | string | null;
  reproduces_locked_value: boolean;
  note: string | null;
  inputs: { name: string; value: string }[];
  sources: ProvenanceSource[];
  corrections?: Correction[];
}

export interface Lineage {
  pack_id: string;
  bundle_sha256: string | null;
  metrics: MetricLineage[];
  all_reproduce: boolean;
  coordinates: string;
  corrections_policy: string;
}

/** "SCAN-INV-1030:amount" or "trade_documents.json:$.invoices[9].amount": what a correction points at. */
export const sourceRef = (s: ProvenanceSource): string => (s.kind === "scan" ? `${s.doc_id}:${s.field}` : `${s.file}:${s.json_path}`);
