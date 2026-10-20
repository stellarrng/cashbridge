/** Labelled number input used by the what-if forms. Read the values with `new FormData(form)`. */
export function NumberField({ name, value, label }: { name: string; value: number; label?: string }) {
  return (
    <label className="field">
      {label ?? name.replaceAll("_", " ")}
      <input name={name} type="number" step="any" defaultValue={value} required />
    </label>
  );
}

/** Read a form's numeric fields into a plain object. */
export function readNumbers(form: HTMLFormElement): Record<string, number> {
  return Object.fromEntries([...new FormData(form).entries()].map(([k, v]) => [k, Number(v)]));
}
