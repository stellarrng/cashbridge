import type { Portal, SessionUser } from "@/shared/api/session";

export interface DemoAccount {
  user_id: string;
  name: string;
  role: string;
  initials: string;
  org: string;
  tenant_id?: string;
  portal: Portal;
  role_label?: string;
}

export interface AuthConfig {
  mode: string;
  demo_accounts: DemoAccount[];
  /** Public on purpose in DEMO mode so judges can approve a pack. Absent in PRODUCTION. */
  otp_demo_secret?: string;
}

export interface LoginResponse {
  token: string;
  expires_at: number | string;
  user: SessionUser;
}
