/** Placeholder shown while a screen or its data loads: calmer than a bare "Loading…" line and keeps the layout steady. */
export function LoadingSkeleton() {
  return (
    <div role="status" aria-busy="true" aria-live="polite">
      <div className="skeleton sk-title" />
      <div className="kpis">
        {[0, 1, 2, 3].map((i) => <div key={i} className="skeleton sk-kpi" />)}
      </div>
      <div className="skeleton sk-block" />
    </div>
  );
}
