export interface StackPart {
  label: string;
  value: number;
  cls: string;
}

/** 100% stacked bar for a handful of statuses, with an inline legend. */
export function StackBar({ parts }: { parts: StackPart[] }) {
  return (
    <>
      <div className="stack">
        {parts.filter((p) => p.value > 0).map((p, i) => (
          <i key={i} className={p.cls} style={{ flex: p.value }} data-tip={`${p.label}: ${p.value}`} />
        ))}
      </div>
      <ul className="legend-inline">
        {parts.map((p, i) => (
          <li key={i}>
            <i className={p.cls} />
            {p.label} <b>{p.value}</b>
          </li>
        ))}
      </ul>
    </>
  );
}
