import { useEffect, useRef, type ReactNode } from "react";

interface Props {
  open: boolean;
  /** id of the dialog element (stable hook for tests and links). */
  id?: string;
  /** Wider, scrollable box for long content (provenance). */
  wide?: boolean;
  titleId: string;
  onClose: () => void;
  children: ReactNode;
}

/** Centered dialog: closes on Escape, moves focus inside when it opens. */
export function Modal({ open, id, wide = false, titleId, onClose, children }: Props) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    box.current?.querySelector<HTMLElement>("input, textarea, button")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <div className="modal" id={id} role="dialog" aria-modal="true" aria-labelledby={titleId} hidden={!open}>
      <div className={"modal-box" + (wide ? " wide" : "")} ref={box}>{open ? children : null}</div>
    </div>
  );
}
