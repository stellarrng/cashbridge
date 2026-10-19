import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { Snapshot } from "./types";
import { Header } from "./components/Header";
import { KpiRibbon } from "./components/KpiRibbon";
import { Activity, Assistant, Privacy } from "./components/Rail";
import { NextStep, Notice, PageHead, PageNav, Summary } from "./components/common";
import { TABS, guide as buildGuide, type TabKey } from "./journey";
import { Anticipate } from "./tabs/Anticipate";
import { Approve } from "./tabs/Approve";
import { Compare } from "./tabs/Compare";
import { Evidence } from "./tabs/Evidence";
import { Prove } from "./tabs/Prove";
import { dayMonth, usd } from "./format";

const SECTIONS: Record<TabKey, { id: string; label: string }[]> = {
  anticipate: [
    { id: "forecast", label: "Cash forecast" }, { id: "causes", label: "What causes it" }, { id: "whatif", label: "Try a scenario" },
    { id: "collections", label: "Collections" }, { id: "buyerrisk", label: "Buyer risk" },
  ],
  prove: [
    { id: "money", label: "Money received" }, { id: "wire", label: "How the wire matched" },
    { id: "emails", label: "Suspicious emails" }, { id: "scans", label: "Scanned documents" }, { id: "invoices", label: "Invoice checks" },
  ],
  compare: [],
  approve: [
    { id: "metrics", label: "Locked numbers" }, { id: "letter", label: "Cover letter" },
    { id: "approval", label: "Approval" }, { id: "safeguards", label: "Try to break it" },
  ],
  evidence: [{ id: "audit", label: "Audit log" }, { id: "registry", label: "Invoice registry" }, { id: "eval", label: "Evaluation" }],
};

const fromHash = (): TabKey => {
  const key = window.location.hash.replace("#/", "") as TabKey;
  return TABS.some((t) => t.key === key) ? key : "anticipate";
};

export function App() {
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [tab, setTab] = useState<TabKey>(fromHash);
  const [visited, setVisited] = useState<Set<TabKey>>(new Set([fromHash()]));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [railOpen, setRailOpen] = useState(false);

  const go = useCallback((next: TabKey) => {
    window.location.hash = `#/${next}`;
    window.scrollTo({ top: 0 });
  }, []);

  useEffect(() => {
    const onHash = () => {
      const next = fromHash();
      setTab(next);
      setVisited((v) => new Set(v).add(next));
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (e.key === "Escape") setRailOpen(false);
      if (target.closest("input, textarea") || e.metaKey || e.ctrlKey || e.altKey) return;
      const index = Number(e.key) - 1;
      if (index >= 0 && index < TABS.length) go(TABS[index].key);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go]);

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

  const guide = useMemo(() => (snap ? buildGuide(snap, visited) : null), [snap, visited]);

  if (!snap || !guide) {
    return (
      <div className="main">
        <span className="wordmark">CashBridge</span>
        <div style={{ marginTop: 24 }}>
          {error ? <Notice tone="bad" title="Cannot reach the backend">{error}. Start it with <span className="mono">make run</span>.</Notice> : <span className="muted">Loading…</span>}
        </div>
      </div>
    );
  }

  const ask = async (text: string) => { await api.askCfo(text); await refresh(); setRailOpen(true); };
  const short = snap.kpis.first_shortfall_week !== null && snap.kpis.shortfall_usd !== null;
  const info = TABS.find((t) => t.key === tab)!;
  const sections = tab === "approve" && snap.pack.status === "NOT_STARTED" ? [] : SECTIONS[tab];

  return (
    <div className="app">
      <Header
        meta={snap.meta} guide={guide} tab={tab} go={go} busy={busy}
        onReset={() => act(api.resetDemo)} railOpen={railOpen} toggleRail={() => setRailOpen(!railOpen)}
      />
      {railOpen && <button className="drawer-scrim" aria-label="Close panel" onClick={() => setRailOpen(false)} />}
      {railOpen && (
        <aside className="drawer" aria-label="Assistant and activity">
          <Assistant history={snap.chat.history} onAsk={ask} />
          <Activity rows={snap.tier_monitor} total={snap.evidence.lines_checked} onMore={() => { setRailOpen(false); go("evidence"); }} />
          <Privacy data={snap.pii_inspector} />
        </aside>
      )}
      <div className="shell">
        <main className="main">
          {tab === "anticipate" ? (
            <div className="hero">
              <div className="label kicker">{snap.meta.company} · as of {dayMonth(snap.meta.as_of)} · {snap.meta.fx_note}</div>
              <h1>{short ? <>Week {snap.kpis.first_shortfall_week} runs <span className="neg">{usd(snap.kpis.shortfall_usd)}</span> short.</> : "No cash shortfall in the next thirteen weeks."}</h1>
              {short && <p>Profit on paper, but cash is tied up in unpaid invoices and supplier deposits. This page shows when the gap opens and why.</p>}
              <KpiRibbon kpis={snap.kpis} />
            </div>
          ) : (
            <>
              <PageHead title={info.title}>{info.blurb}</PageHead>
              <Summary kpis={snap.kpis} />
            </>
          )}
          {error && <Notice tone="bad" title="Request failed">{error}</Notice>}
          {sections.length > 0 && <PageNav items={sections} />}

          {tab === "anticipate" && <Anticipate snap={snap} onAsk={ask} />}
          {tab === "prove" && <Prove snap={snap} />}
          {tab === "compare" && <Compare snap={snap} onChoose={(id) => act(() => api.chooseOption(id))} />}
          {tab === "approve" && <Approve snap={snap} onSnapshot={setSnap} onPrepare={() => act(api.preparePack)} />}
          {tab === "evidence" && <Evidence snap={snap} />}

          <NextStep guide={guide} current={tab} go={go} />
        </main>
      </div>
    </div>
  );
}
