import { useEffect, useState } from "react";

/** How far below the top of the screen the "reading line" sits: just under the sticky header. */
const READING_LINE = 100;

/**
 * The id of the section the reader is in ("" while the hero is showing), for highlighting the matching nav link.
 * An IntersectionObserver wakes us when a section enters or leaves the screen; the choice itself is made from the
 * sections' positions, so two sections that merely touch can never both count as "current".
 */
export function useActiveSection(ids: readonly string[]): string {
  const [active, setActive] = useState("");

  useEffect(() => {
    const els = ids.map((id) => document.getElementById(id)).filter((el): el is HTMLElement => el !== null);
    if (!els.length) return;
    const update = () => {
      let current = "";
      for (const el of els) {
        const r = el.getBoundingClientRect();
        if (r.top <= READING_LINE && r.bottom > READING_LINE) current = el.id;
      }
      setActive(current);
    };
    update();
    window.addEventListener("resize", update);
    if (typeof IntersectionObserver === "undefined") {
      window.addEventListener("scroll", update, { passive: true });
      return () => {
        window.removeEventListener("resize", update);
        window.removeEventListener("scroll", update);
      };
    }
    const io = new IntersectionObserver(update, { threshold: Array.from({ length: 21 }, (_, i) => i / 20) });
    els.forEach((el) => io.observe(el));
    return () => {
      io.disconnect();
      window.removeEventListener("resize", update);
    };
  }, [ids]);

  return active;
}
