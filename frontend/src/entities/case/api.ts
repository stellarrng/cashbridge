import { get, post } from "@/shared/api/client";
import type { CaseSnapshot } from "./types";

export const fetchSnapshot = () => get<CaseSnapshot>("/api/snapshot");

/** Wipe this demo session's case and start again from the Monday-morning state. DEMO mode only. */
export const resetDemo = () => post<unknown>("/api/reset_demo");
