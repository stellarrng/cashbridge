import type { ApproveResult, ChatMessage, OtpChallenge, ScenarioParams, SimulateResult, Snapshot } from "./types";

// One function per method in the UI contract (docs/UI_CONTRACT.md, C.1). No logic lives here.
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(path, {
    method: body === undefined && path === "/api/snapshot" ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: path === "/api/snapshot" ? undefined : JSON.stringify(body ?? {}),
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = await response.json();
      detail = typeof payload.detail === "string" ? payload.detail : JSON.stringify(payload.detail);
    } catch {
      /* keep the status text */
    }
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export const api = {
  getSnapshot: () => request<Snapshot>("/api/snapshot"),
  simulate: (params: ScenarioParams) => request<SimulateResult>("/api/simulate", { params }),
  askCfo: (text: string) => request<ChatMessage>("/api/ask_cfo", { text }),
  chooseOption: (option_id: string) => request<Snapshot>("/api/choose_option", { option_id }),
  preparePack: () => request<Snapshot>("/api/prepare_pack"),
  requestOtp: () => request<OtpChallenge>("/api/request_otp"),
  approve: (code: string) => request<ApproveResult>("/api/approve", { code }),
  retryDoubleFinancing: () => request<{ blocked: boolean; error: string | null; message: string }>("/api/retry_double_financing"),
  tamperDraft: () => request<{ ok: boolean; offending: string[]; message: string }>("/api/tamper_draft"),
  verifyChain: () => request<{ ok: boolean; broken_seq: number | null; lines_checked: number }>("/api/verify_chain"),
  tamperDemo: () => request<{ ok: boolean; broken_seq: number | null; lines_checked: number; note: string }>("/api/tamper_demo"),
  resetDemo: () => request<Snapshot>("/api/reset_demo"),
};
