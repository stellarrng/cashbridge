import { useEffect, useState } from "react";
import { useSnapshotContext } from "./SnapshotProvider";
import type { CaseSnapshot } from "./types";

/**
 * The case for a screen that needs it. Fetches a fresh snapshot when the screen opens (so figures are never
 * stale after another action) and keeps showing the previous one while it loads.
 */
export function useCase(): { snapshot: CaseSnapshot | null; error: Error | null; refresh: () => Promise<CaseSnapshot | null> } {
  const { snapshot, refresh } = useSnapshotContext();
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let alive = true;
    refresh().catch((e: unknown) => alive && setError(e instanceof Error ? e : new Error(String(e))));
    return () => {
      alive = false;
    };
  }, [refresh]);

  return { snapshot, error, refresh };
}
