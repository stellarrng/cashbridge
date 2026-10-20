import { useEffect, useRef } from "react";

/**
 * One global tooltip for every element that carries a `data-tip` attribute (chart marks, meters, buttons).
 * Elements under a tooltip are often re-rendered, and a removed node never fires pointerout, so the tip also
 * hides on click, scroll, navigation and Escape and can never stay stuck on screen.
 */
export function TooltipHost() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const tip = ref.current;
    if (!tip) return;
    const closest = (target: EventTarget | null): HTMLElement | null =>
      target instanceof Element ? (target.closest("[data-tip]") as HTMLElement | null) : null;
    const hide = () => tip.classList.remove("on");

    const over = (e: PointerEvent) => {
      const el = closest(e.target);
      if (!el) return;
      tip.textContent = el.getAttribute("data-tip");
      tip.classList.add("on");
    };
    const move = (e: PointerEvent) => {
      if (!tip.classList.contains("on")) return;
      if (!closest(e.target)) return hide();
      const x = Math.min(e.clientX + 14, window.innerWidth - tip.offsetWidth - 8);
      const y = e.clientY + 16 + tip.offsetHeight > window.innerHeight ? e.clientY - tip.offsetHeight - 10 : e.clientY + 16;
      tip.style.left = x + "px";
      tip.style.top = y + "px";
    };
    const out = (e: PointerEvent) => {
      const el = closest(e.target);
      if (el && !el.contains(e.relatedTarget as Node | null)) hide();
    };
    const key = (e: KeyboardEvent) => e.key === "Escape" && hide();

    document.addEventListener("pointerover", over);
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerout", out);
    document.addEventListener("keydown", key);
    document.addEventListener("click", hide, true);
    document.addEventListener("scroll", hide, true);
    window.addEventListener("hashchange", hide, true);
    return () => {
      document.removeEventListener("pointerover", over);
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerout", out);
      document.removeEventListener("keydown", key);
      document.removeEventListener("click", hide, true);
      document.removeEventListener("scroll", hide, true);
      window.removeEventListener("hashchange", hide, true);
    };
  }, []);

  return <div ref={ref} className="tip" role="tooltip" aria-hidden="true" />;
}
