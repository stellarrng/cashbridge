import { post } from "@/shared/api/client";
import type { AutopilotRun } from "@/entities/autopilot";

/** execute=false only plans; execute=true (accountant) also drafts the funding pack up to the Director's hand-off. */
export const runAutopilot = (execute: boolean, goal: string) => post<AutopilotRun>("/api/autopilot/run", { execute, goal });
