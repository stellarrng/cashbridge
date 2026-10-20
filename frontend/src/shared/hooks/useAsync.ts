import { useCallback, useEffect, useRef, useState } from "react";

export interface AsyncState<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
  /** Fetch again (keeps the current data on screen while loading). */
  reload: () => Promise<T | undefined>;
  setData: (data: T | undefined) => void;
}

/** Load something on mount (and when `deps` change). A late response from a stale request is ignored. */
export function useAsync<T>(load: () => Promise<T>, deps: ReadonlyArray<unknown> = []): AsyncState<T> {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [loading, setLoading] = useState(true);
  const seq = useRef(0);
  const loader = useRef(load);
  loader.current = load;

  const run = useCallback(async (): Promise<T | undefined> => {
    const mine = ++seq.current;
    setLoading(true);
    try {
      const result = await loader.current();
      if (mine === seq.current) {
        setData(result);
        setError(undefined);
      }
      return result;
    } catch (e) {
      if (mine === seq.current) setError(e instanceof Error ? e : new Error(String(e)));
      return undefined;
    } finally {
      if (mine === seq.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    void run();
    return () => {
      seq.current++;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { data, error, loading, reload: run, setData };
}
