import { useEffect, useState } from "react";
import { useCase } from "@/entities/case";
import { useAct, useAsync } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import type { ScreenProps } from "@/shared/lib/screen";
import { Button, Empty, Loadable, PageHead } from "@/shared/ui";
import { RoleStrip } from "../auth";
import { applyEvent, decideAlert, fetchIntelligence, resetEvents, runPlan } from "./api";
import { AnalysisTab } from "./tabs/AnalysisTab";
import { DecideTab } from "./tabs/DecideTab";
import { EvidenceTab } from "./tabs/EvidenceTab";
import type { IntelligenceData } from "./types";

const TABS = ["decide", "analysis", "evidence"] as const;
type Tab = (typeof TABS)[number];

// Remembered between visits, like the original app: coming back opens the tab you left.
let lastTab: Tab = "decide";

/** Load the current plan; if none exists yet, ask the planner for one so the decision view is never empty. */
async function loadData(): Promise<IntelligenceData> {
  const data = await fetchIntelligence();
  if (data.plan) return data;
  return runPlan().catch(() => data);
}

export default function DecisionCenterScreen({ arg }: ScreenProps) {
  const { t } = useI18n();
  const act = useAct();
  const { snapshot, refresh } = useCase();
  const intel = useAsync(loadData, []);
  const tab: Tab = (TABS as readonly string[]).includes(arg ?? "") ? (arg as Tab) : lastTab;
  lastTab = tab;

  const plan = intel.data?.plan ?? null;
  const [goalId, setGoalId] = useState("keep_cash_positive");
  const [probability, setProbability] = useState(0.9);
  useEffect(() => {
    if (plan) {
      setGoalId(plan.goal.id);
      setProbability(plan.goal.min_probability);
    }
  }, [plan]);

  // After an action: refresh the nav counts (snapshot) and the plan data.
  const changed = async () => {
    await refresh().catch(() => undefined);
    await intel.reload();
  };

  async function run() {
    // Only the analysis tab exposes the goal controls; elsewhere the planner is re-run with the current goal.
    const out = await act(() => runPlan(goalId, probability));
    if (out) intel.setData(out);
  }

  const onDecide = async (id: string, accept: boolean) => {
    if (await act(() => decideAlert(id, accept), "OK")) await changed();
  };
  const onApplyEvent = async (kind: string) => {
    const r = await act(() => applyEvent(kind), (x) => (x.assessment.route === "DIRECTOR_INBOX" ? t("core.inbox") + ": " + x.assessment.id : t("core.digest")));
    if (r) await changed();
  };
  const onResetEvents = async () => {
    if (await act(resetEvents)) await changed();
  };

  return (
    <Loadable data={intel.data} error={intel.error}>
      {(data) => (
        <>
          <PageHead
            title={t(tab === "decide" ? "core.dc.title" : "nav.core")}
            lede={t(tab === "decide" ? "core.dc.lede" : "core.lede")}
            actions={<Button variant="bridge" onClick={() => void run()}>{t("core.run")}</Button>}
          />
          {tab === "decide" && <RoleStrip />}
          <div className="tabs" role="tablist">
            {TABS.map((k) => (
              <a key={k} role="tab" href={"#core/" + k} aria-selected={tab === k} className={(tab === k ? "on" : "") + (k === "decide" ? "" : " adv")}>
                {t("core.tab." + k)}
              </a>
            ))}
          </div>
          {!data.plan ? (
            <Empty title={t("core.empty")} />
          ) : tab === "decide" ? (
            <DecideTab plan={data.plan} twin={data.twin} snapshot={snapshot} onDecide={onDecide} onApplyEvent={onApplyEvent} onResetEvents={onResetEvents} />
          ) : tab === "analysis" ? (
            <AnalysisTab
              plan={data.plan}
              twin={data.twin}
              goalId={goalId}
              probability={probability}
              onGoalChange={(g, p) => {
                setGoalId(g);
                setProbability(p);
              }}
              onRun={() => void run()}
            />
          ) : (
            <EvidenceTab data={data} plan={data.plan} onChanged={() => void changed()} />
          )}
        </>
      )}
    </Loadable>
  );
}
