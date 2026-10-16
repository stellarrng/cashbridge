import { useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { Snapshot } from "./types";
import { Header } from "./components/Header";
import { KpiRibbon } from "./components/KpiRibbon";
import { Chat, PiiInspector, TierMonitor } from "./components/Rail";
import { Notice } from "./components/common";
import { Anticipate } from "./tabs/Anticipate";
import { Approve } from "./tabs/Approve";
import { Compare } from "./tabs/Compare";
import { Evidence } from "./tabs/Evidence";
import { Prove } from "./tabs/Prove";
import { dayMonth, usd } from "./format";

type TabKey = "anticipate" | "prove" | "compare" | "approve" | "evidence";
const TABS: { key: TabKey; title: string }[] = [
  { key: "anticipate", title: "Anticipate" },
  { key: "prove", title: "Prove" },
  { key: "compare", title: "Compare & Choose" },
  { key: "approve", title: "Approve" },
  { key: "evidence", title: "Evidence" },
];

export function App() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [tab, setTab] = useState<TabKey>("anticipate");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    try {
      setSnap(await api.getSnapshot());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const act = async (action: () => Promise<Snapshot>) => {
    setBusy(true);
    try {
      setSnap(await action());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!snap) {
    return (
      <div className="main">
        <span className="wordmark">CashBridge</span>
        <div style={{ marginTop: 24 }}>
          {error ? <Notice tone="bad" title="Cannot reach the backend">{error}. Start it with <span className="num">make run</span>.</Notice> : <span className="muted">Loading…</span>}
        </div>
      </div>
    );
  }

  const short = snap.kpis.first_shortfall_week !== null && snap.kpis.shortfall_usd !== null;
  return (
    <div className="app">
      <Header meta={snap.meta} busy={busy} onReset={() => act(api.resetDemo)} />
      <div className="shell">
        <aside className="rail">
          <TierMonitor rows={snap.tier_monitor} />
          <Chat history={snap.chat.history} onAsk={async (text) => { await api.askCfo(text); await refresh(); }} />
          <PiiInspector data={snap.pii_inspector} />
        </aside>
        <main className="main">
          <div className="hero">
            <div className="micro" style={{ marginBottom: 14 }}>{snap.meta.company} · as of {dayMonth(snap.meta.as_of)} · {snap.meta.fx_note}</div>
            <h1 className="display">{short ? <>Week {snap.kpis.first_shortfall_week} runs <span className="neg">{usd(snap.kpis.shortfall_usd)}</span> short.</> : "No cash shortfall in the next thirteen weeks."}</h1>
            {short && <p>Cash is trapped in receivables and supplier deposits. Below: how it happens, how each invoice is proven, what it costs to bridge, and who has to approve it.</p>}
          </div>
          {error && <Notice tone="bad" title="Request failed">{error}</Notice>}
          <KpiRibbon kpis={snap.kpis} />
          <nav className="tabs">
            {TABS.map((t, i) => (
              <button key={t.key} className={`tab ${tab === t.key ? "active" : ""}`} onClick={() => setTab(t.key)}>
                <span className="idx">0{i + 1}</span>{t.title}
              </button>
            ))}
          </nav>
          {tab === "anticipate" && <Anticipate snap={snap} onAsk={async (text) => { await api.askCfo(text); await refresh(); }} />}
          {tab === "prove" && <Prove snap={snap} />}
          {tab === "compare" && <Compare snap={snap} onChoose={(id) => act(() => api.chooseOption(id))} />}
          {tab === "approve" && <Approve snap={snap} onSnapshot={setSnap} onPrepare={() => act(api.preparePack)} />}
          {tab === "evidence" && <Evidence snap={snap} />}
        </main>
      </div>
    </div>
  );
}
