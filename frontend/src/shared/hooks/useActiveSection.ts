import { useCallback, useEffect, useRef, useState } from "react";

/** Reading line: just under the sticky header. */
const LINE = 100;

/**
 * Which section the reader is in, for highlighting the matching nav link: `[activeId, pin]`.
 *
 * - Scrolling: the current section is the last one whose top has passed the reading line ("" while the hero shows).
 *   At the very bottom of the page it is the last section, so Install lights up even if it cannot reach the header.
 * - Clicking a nav link: call `pin(id)`. The clicked link stays highlighted while the page glides there, and until the
 *   reader scrolls, types or touches. A tall window cannot scroll far enough to bring the last sections up to the
 *   header, so position alone can never tell which link was clicked.
 *
 * An IntersectionObserver wakes the check when a section enters or leaves the screen; scroll events cover the rest.
 */
export function useActiveSection(ids: readonly string[]): [string, (id: string) => void] {
  const [active, setActive] = useState("");
  const pinned = useRef<string | null>(null);

  const pin = useCallback((id: string) => {
    pinned.current = id;
    setActive(id);
  }, []);

  useEffect(() => {
    const els = ids.map((id) => document.getElementById(id)).filter((el): el is HTMLElement => el !== null);
    if (!els.length) return;

    const update = () => {
      if (pinned.current) return;
      const atBottom = window.scrollY >= document.documentElement.scrollHeight - window.innerHeight - 2 && window.scrollY > 0;
      let current = "";
      for (const el of els) if (el.getBoundingClientRect().top <= LINE) current = el.id;
      setActive(atBottom ? els[els.length - 1].id : current);
    };
    // The reader takes over: stop honouring the click and follow the scroll again.
    const release = () => {
      if (pinned.current) {
        pinned.current = null;
        update();
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (["ArrowUp", "ArrowDown", "PageUp", "PageDown", "Home", "End", " "].includes(e.key)) release();
    };

    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    window.addEventListener("wheel", release, { passive: true });
    window.addEventListener("touchmove", release, { passive: true });
    window.addEventListener("keydown", onKey);
    const io = typeof IntersectionObserver === "undefined" ? null : new IntersectionObserver(update, { threshold: Array.from({ length: 21 }, (_, i) => i / 20) });
    els.forEach((el) => io?.observe(el));
    return () => {
      io?.disconnect();
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
      window.removeEventListener("wheel", release);
      window.removeEventListener("touchmove", release);
      window.removeEventListener("keydown", onKey);
    };
  }, [ids]);

  return [active, pin];
}
