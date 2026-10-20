import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

type Notify = (message: string, bad?: boolean) => void;
const Ctx = createContext<Notify | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<{ message: string; bad: boolean; show: boolean }>({ message: "", bad: false, show: false });
  const timer = useRef<number>();

  const notify = useCallback<Notify>((message, bad = false) => {
    setState({ message, bad, show: true });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState((s) => ({ ...s, show: false })), 4200);
  }, []);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  return (
    <Ctx.Provider value={notify}>
      {children}
      <div className={"toast" + (state.show ? " show" : "") + (state.bad ? " bad" : "")} role="status" aria-live="polite">
        {state.message}
      </div>
    </Ctx.Provider>
  );
}

export function useToast(): Notify {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
