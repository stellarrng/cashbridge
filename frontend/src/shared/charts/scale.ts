/** Round a value span to a readable axis step (1, 2, 2.5, 5 x 10^n). */
export function niceStep(span: number): number {
  const raw = span / 4;
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  return [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw) ?? raw;
}

/** Axis tick values from min to max inclusive. */
export function ticks(min: number, max: number, step: number): number[] {
  const out: number[] = [];
  for (let v = min; v <= max + 1e-9; v += step) out.push(v);
  return out;
}
