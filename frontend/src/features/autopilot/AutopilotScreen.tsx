import { useEffect, useState, type FormEvent } from "react";
import type { AutopilotRun } from "@/entities/autopilot";
import { useCase } from "@/entities/case";
import { useAct } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import type { ScreenProps } from "@/shared/lib/screen";
import { Button, EngineNote, Empty, Loadable, PageHead } from "@/shared/ui";
import { useAuth } from "../auth";
import { runAutopilot } from "./api";
import { RunView } from "./components/RunView";

export default function AutopilotScreen(_: ScreenProps) {
  const { t } = useI18n();
  const { can } = useAuth();
  const act = useAct();
  const { snapshot, error, refresh } = useCase();
  const preparer = can("sme:prepare");
  const [run, setRun] = useState<AutopilotRun | null>(null);
  const [goal, setGoal] = useState("Close the forecast cash gap safely");
  const [busy, setBusy] = useState(false);

  // Show the latest saved run until a new one is requested.
  useEffect(() => {
    if (snapshot?.autopilot) setRun((current) => current ?? snapshot.autopilot);
  }, [snapshot]);

  async function go(execute: boolean) {
    setBusy(true);
    const out = await act(() => runAutopilot(execute, goal), (r) => t("dec." + r.decision));
    setBusy(false);
    if (out) {
      setRun(out);
      await refresh();
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void go(preparer);
  };

  return (
    <Loadable data={snapshot} error={error}>
      {(s) => (
        <>
          <PageHead
            title={t("nav.autopilot")}
            lede={t(preparer ? "ap.lede.prep" : "ap.lede.dir")}
            actions={
              <>
                <Button id="apRun" variant={preparer ? "bridge" : "ghost"} disabled={busy} onClick={() => void go(preparer)}>
                  {t(preparer ? "ap.run" : "ap.runPlan")}
                </Button>
                {preparer && <Button variant="ghost" disabled={busy} onClick={() => void go(false)}>{t("ap.plan")}</Button>}
              </>
            }
          />
          <EngineNote />
          <form className="panel" onSubmit={submit}>
            <label className="field">
              {t("ap.goal")}
              <input maxLength={300} value={goal} onChange={(e) => setGoal(e.target.value)} />
            </label>
          </form>
          <div>{run ? <RunView run={run} weeks={s.forecast.weeks} /> : <Empty title={t("ap.empty")}>{t("ap.emptyD")}</Empty>}</div>
        </>
      )}
    </Loadable>
  );
}
