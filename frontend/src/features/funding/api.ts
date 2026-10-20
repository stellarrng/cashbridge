import { download, get, post } from "@/shared/api/client";
import type { CaseSnapshot } from "@/entities/case";
import type { ApproveResult, DoubleFinancingResult, FundingScheduleView, LenderQuotes, OtpChallenge, TamperResult } from "./types";

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
/** Consent withdrawal: the Director takes a released pack back before the lender decides (evidence files are deleted). */
export const withdrawRelease = (reason: string) => post<unknown>("/api/withdraw_release", { reason });
/** One timeline per lender product: quote, drawdown, settlement, and what each payment scenario costs. */
export const fetchSchedules = () => get<Record<string, FundingScheduleView>>("/api/funding/schedules");
/** Quotes through the configured lender adapter; a simulated quote is labelled and is never a lender offer. */
export const fetchQuotes = () => get<LenderQuotes>("/api/lender/quotes");
