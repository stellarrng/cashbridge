import { useEffect, useRef, type ReactNode } from "react";

interface Props {
  open: boolean;
  titleId: string;
  onClose: () => void;
  children: ReactNode;
}

/** Centered dialog: closes on Escape, moves focus inside when it opens. */
export function Modal({ open, titleId, onClose, children }: Props) {
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    box.current?.querySelector<HTMLElement>("input, textarea, button")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-labelledby={titleId} hidden={!open}>
      <div className="modal-box" ref={box}>{open ? children : null}</div>
    </div>
  );
}
