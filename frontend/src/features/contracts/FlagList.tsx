import type { Flag } from "./api";

export function FlagList({ flags }: { flags: Flag[] }) {
  if (!flags.length) return <p className="muted">No rule-based flags. Authenticity and legal completeness are still unverified.</p>;
  return (
    <>
      {flags.map((f, i) => (
        <div key={i} className={"flag" + (f.severity === "high" ? " high" : "")}>
          <b>{f.code}</b> <span className="muted small">{f.severity}</span>
          <p className="small">{f.description}</p>
          {f.evidence && <p className="small muted">{f.evidence}</p>}
        </div>
      ))}
    </>
  );
}
