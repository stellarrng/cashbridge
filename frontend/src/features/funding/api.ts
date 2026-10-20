import { download, post } from "@/shared/api/client";
import type { CaseSnapshot } from "@/entities/case";
import type { ApproveResult, DoubleFinancingResult, OtpChallenge, TamperResult } from "./types";

export const chooseOption = (optionId: string) => post<unknown>("/api/choose_option", { option_id: optionId });
export const preparePack = () => post<CaseSnapshot>("/api/prepare_pack");
export const reopenPack = () => post<unknown>("/api/reopen_pack");
export const rejectPack = (reason: string) => post<unknown>("/api/reject_pack", { reason });
export const requestOtp = () => post<OtpChallenge>("/api/request_otp");
export const approvePack = (code: string) => post<ApproveResult>("/api/approve", { code });
export const downloadPackPdf = (packId: string) => download("/api/pack/pdf", `${packId}.pdf`);
/** Safeguard demos: try to submit a doctored cover letter / re-finance an invoice and watch them be refused. */
export const tamperDraft = () => post<TamperResult>("/api/tamper_draft");
export const retryDoubleFinancing = () => post<DoubleFinancingResult>("/api/retry_double_financing");
