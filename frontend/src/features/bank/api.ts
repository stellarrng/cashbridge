import { download, get, post } from "@/shared/api/client";
import type { BankCase, BankDecision, InboxItem } from "./types";

const base = (packId: string) => `/api/bank/cases/${encodeURIComponent(packId)}`;

export const fetchInbox = () => get<{ items: InboxItem[] }>("/api/bank/inbox");
export const fetchCase = (packId: string) => get<BankCase>(base(packId));
export const verifyCase = (packId: string) => post<unknown>(base(packId) + "/verify");
export const recordDecision = (packId: string, decision: BankDecision, note: string) => post<unknown>(base(packId) + "/decision", { decision, note });
export const downloadCasePdf = (packId: string) => download(base(packId) + "/pdf", `${packId}.pdf`);
