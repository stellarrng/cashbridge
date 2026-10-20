import { get, post } from "@/shared/api/client";
import type { Portal, SessionUser } from "@/shared/api/session";
import type { AuthConfig, LoginResponse } from "./types";

export const fetchMe = () => get<SessionUser>("/api/auth/me");
export const fetchAuthConfig = () => get<AuthConfig>("/api/auth/config", { anonymous: true });
export const demoLogin = (userId: string, portal?: Portal) => post<LoginResponse>("/api/auth/demo-login", { user_id: userId, portal }, { anonymous: true });
export const passcodeLogin = (userId: string, passcode: string, portal: Portal) =>
  post<LoginResponse>("/api/auth/login", { user_id: userId, passcode, portal }, { anonymous: true });
export const logout = () => post<unknown>("/api/auth/logout");
