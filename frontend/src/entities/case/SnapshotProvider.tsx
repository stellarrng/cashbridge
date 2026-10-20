import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { fetchSnapshot } from "./api";
import type { CaseSnapshot } from "./types";

interface SnapshotContext {
  /** The latest snapshot (null until the first load, or for the bank portal, which has no SME case). */
  snapshot: CaseSnapshot | null;
  /** Fetch a fresh copy. Resolves to it, or to the previous one when the request fails. */
  refresh: () => Promise<CaseSnapshot | null>;
}

const Ctx = createContext<SnapshotContext | null>(null);

/** Holds the current case so the sidebar, top bar and screens all read the same data. SME portal only. */
export function SnapshotProvider({ children, enabled }: { children: ReactNode; enabled: boolean }) {
  const [snapshot, setSnapshot] = useState<CaseSnapshot | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await fetchSnapshot();
      setSnapshot(next);
      return next;
    } catch (e) {
      if (!enabled) return null;
      throw e;
    }
  }, [enabled]);

  useEffect(() => {
    if (enabled) refresh().catch(() => undefined);
  }, [enabled, refresh]);

  const value = useMemo(() => ({ snapshot, refresh }), [snapshot, refresh]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useSnapshotContext(): SnapshotContext {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useSnapshotContext must be used inside <SnapshotProvider>");
  return ctx;
}
