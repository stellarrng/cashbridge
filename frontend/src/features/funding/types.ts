export interface OtpChallenge {
  instructions: string;
  expires_at: string | number;
  action_hash: string;
}

export interface ApproveResult {
  ok: boolean;
  error?: string;
}

export interface TamperResult {
  ok: boolean;
  offending: string[];
}

export interface DoubleFinancingResult {
  blocked: boolean;
  message?: string;
}
