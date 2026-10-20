import { useEffect, type ReactNode } from "react";
import { isUnauthorized } from "../api/client";
import { clearSession, signInUrl } from "../api/session";
import { useI18n } from "../i18n";
import { LoadingSkeleton } from "./LoadingSkeleton";
import { PageHead } from "./primitives";

interface Props<T> {
  data: T | null | undefined;
  error?: Error | null;
  children: (data: T) => ReactNode;
}

/**
 * Loading and error states for a screen. Shows the loading line until there is data, the error message when the
 * first load failed, and sends an expired session back to sign-in.
 */
export function Loadable<T>({ data, error, children }: Props<T>) {
  const { t } = useI18n();
  const expired = isUnauthorized(error);

  useEffect(() => {
    if (expired) {
      clearSession();
      window.location.href = signInUrl();
    }
  }, [expired]);

  if (data != null) return <>{children(data)}</>;
  if (error && !expired) {
    return (
      <>
        <PageHead title={t("app.error")} />
        <div className="empty"><p>{error.message}</p></div>
      </>
    );
  }
  return <LoadingSkeleton />;
}
