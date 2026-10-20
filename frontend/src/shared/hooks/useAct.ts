import { useCallback } from "react";
import { isUnauthorized } from "../api/client";
import { clearSession, signInUrl } from "../api/session";
import { useToast } from "../ui/Toast";

/**
 * Run an API call from an event handler: toast the failure (or a success message), and send the person back
 * to sign-in when the session has expired. Resolves to the result, or `null` when the call failed.
 */
export function useAct() {
  const toast = useToast();
  return useCallback(
    async <T>(fn: () => Promise<T>, ok?: string | ((result: T) => string)): Promise<T | null> => {
      try {
        const out = await fn();
        if (ok) toast(typeof ok === "function" ? ok(out) : ok);
        return out;
      } catch (e) {
        if (isUnauthorized(e)) {
          clearSession();
          window.location.href = signInUrl();
          return null;
        }
        toast(e instanceof Error ? e.message : String(e), true);
        return null;
      }
    },
    [toast],
  );
}
