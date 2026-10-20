import { useEffect, useRef, useState } from "react";

const NUMBER = /(\d+(?:\.\d+)?)/;
const decimals = (token: string) => (token.split(".")[1] ?? "").length;

const prefersReducedMotion = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches || document.documentElement.dataset.motion === "reduce";

/**
 * Counts the numbers inside `text` up from zero the first time it scrolls into view ("25/25" counts both 25s, "0.091"
 * keeps its three decimals). The final text is what a screen reader reads and what shows with reduced motion or
 * without IntersectionObserver, so the figure is never wrong or missing.
 */
export function AnimatedNumber({ text }: { text: string }) {
  const ref = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(text);

  useEffect(() => {
    setShown(text);
    const parts = text.split(NUMBER); // odd indexes are numbers
    const el = ref.current;
    if (!el || parts.length < 3 || typeof IntersectionObserver === "undefined" || prefersReducedMotion()) return;

    let frame = 0;
    const render = (k: number) => parts.map((p, i) => (i % 2 ? (parseFloat(p) * k).toFixed(decimals(p)) : p)).join("");
    const run = () => {
      const start = performance.now();
      const DURATION = 1100;
      const tick = (now: number) => {
        const t = Math.min(1, (now - start) / DURATION);
        setShown(t < 1 ? render(1 - Math.pow(1 - t, 3)) : text); // ease-out, then the exact original text
        if (t < 1) frame = requestAnimationFrame(tick);
      };
      setShown(render(0));
      frame = requestAnimationFrame(tick);
    };
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          io.disconnect();
          run();
        }
      },
      { threshold: 0.5 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [text]);

  return (
    <>
      <span ref={ref} aria-hidden="true">{shown}</span>
      <span className="sr-only">{text}</span>
    </>
  );
}
