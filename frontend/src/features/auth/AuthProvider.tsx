import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { clearSession, getSession, saveSession, signInUrl, type SessionUser } from "@/shared/api/session";
import { useI18n } from "@/shared/i18n";
import { demoLogin, fetchAuthConfig, fetchMe, logout } from "./api";
import { homeRoute } from "./home";
import type { AuthConfig } from "./types";

interface Auth {
  user: SessionUser;
  config: AuthConfig | null;
  /** UI convenience only. The server checks every request regardless. */
  can: (permission: string) => boolean;
  signOut: () => Promise<void>;
  /** End this session and return to the sign-in dialog. */
  switchAccount: () => Promise<void>;
  /** One-click persona switch (DEMO mode). */
  viewAs: (userId: string) => Promise<void>;
}

const Ctx = createContext<Auth | null>(null);

async function endServerSession() {
  try {
    await logout();
  } catch {
    /* already gone */
  }
}

/** Resolves the signed-in user for the workspace, or sends the browser to the sign-in dialog. */
export function AuthProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [config, setConfig] = useState<AuthConfig | null>(null);

  useEffect(() => {
    let alive = true;
    const session = getSession();
    if (!session?.token) {
      window.location.href = signInUrl("sme");
      return;
    }
    fetchMe()
      .then((me) => alive && setUser(me))
      .catch(() => {
        clearSession();
        window.location.href = signInUrl(session.user?.portal ?? "sme");
      });
    fetchAuthConfig().then((c) => alive && setConfig(c)).catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  const signOut = useCallback(async () => {
    await endServerSession();
    clearSession();
    window.location.href = "/?signedout=1";
  }, []);

  const switchAccount = useCallback(async () => {
    const portal = user?.portal ?? "sme";
    await endServerSession();
    clearSession();
    window.location.href = signInUrl(portal);
  }, [user]);

  const viewAs = useCallback(
    async (userId: string) => {
      if (userId === user?.user_id) return;
      await endServerSession();
      const next = await demoLogin(userId);
      saveSession({ token: next.token, user: next.user, expires_at: next.expires_at });
      window.location.hash = homeRoute(next.user);
      window.location.reload();
    },
    [user],
  );

  const value = useMemo<Auth | null>(
    () => (user ? { user, config, can: (p) => user.permissions.includes(p), signOut, switchAccount, viewAs } : null),
    [user, config, signOut, switchAccount, viewAs],
  );

  if (!value) return <p className="muted" style={{ padding: 24 }}>{t("app.loading")}</p>;
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): Auth {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}
