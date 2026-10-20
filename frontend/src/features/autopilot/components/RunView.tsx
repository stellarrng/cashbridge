import { useCallback, useState } from "react";
import type { AutopilotRun } from "@/entities/autopilot";
import type { ForecastWeek } from "@/entities/forecast";
import { DecisionBanner } from "./DecisionBanner";
import { EvidenceRegister, evidenceRowId } from "./EvidenceRegister";
import { RecommendationPanel } from "./RecommendationPanel";
import { TracePanel } from "./TracePanel";

export function RunView({ run, weeks }: { run: AutopilotRun; weeks: ForecastWeek[] }) {
  const [filter, setFilter] = useState("ALL");

  // The trace links to an evidence row: reveal every row, then scroll to it and flash it.
  const jumpTo = useCallback((id: string) => {
    setFilter("ALL");
    window.setTimeout(() => {
      const row = document.getElementById(evidenceRowId(id));
      if (!row) return;
      row.scrollIntoView({ block: "center", behavior: "smooth" });
      row.classList.remove("flash");
      void row.offsetWidth; // restart the CSS animation
      row.classList.add("flash");
    }, 0);
  }, []);

  return (
    <>
      <DecisionBanner run={run} />
      {run.recommendation && <RecommendationPanel run={run} rec={run.recommendation} weeks={weeks} />}
      <TracePanel run={run} onJump={jumpTo} />
      <EvidenceRegister run={run} filter={filter} onFilter={setFilter} />
    </>
  );
}
