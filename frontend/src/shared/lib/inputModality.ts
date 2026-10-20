/**
 * Remember whether the last input was a mouse/touch or the keyboard (html[data-input]). Buttons then show a focus ring
 * for keyboard users only: clicking the theme toggle with a mouse must not leave a ring behind.
 */
export function trackInputModality(): void {
  const root = document.documentElement;
  const KEYS = new Set(["Tab", "Enter", " ", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"]);
  document.addEventListener("pointerdown", () => { root.dataset.input = "mouse"; }, true);
  document.addEventListener("keydown", (e) => { if (KEYS.has(e.key)) root.dataset.input = "keyboard"; }, true);
}
