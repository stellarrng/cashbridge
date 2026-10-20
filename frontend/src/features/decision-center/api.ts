import { get, post } from "@/shared/api/client";
import type { EventResult, IntelligenceData, SimulatedOutcome } from "./types";

export const fetchIntelligence = () => get<IntelligenceData>("/api/intelligence");
export const runPlan = (goal?: string, minProbability?: number) =>
  post<IntelligenceData>("/api/intelligence/plan", goal === undefined ? {} : { goal, min_probability: minProbability });
export const simulateOutcome = () => post<SimulatedOutcome>("/api/intelligence/simulate-outcome");
export const applyEvent = (kind: string) => post<EventResult>("/api/intelligence/events", { kind });
export const resetEvents = () => post<unknown>("/api/intelligence/events/reset");
export const decideAlert = (id: string, accept: boolean) => post<unknown>(`/api/intelligence/inbox/${encodeURIComponent(id)}`, { accept });
export const proposeUpdate = () => post<unknown>("/api/intelligence/propose-update");
export const decideUpdate = (approve: boolean, note: string) => post<unknown>("/api/intelligence/decide-update", { approve, note });
