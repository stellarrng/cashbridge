/* CashBridge workspace: SME portal (accountant / director) and Bank portal (credit reviewer).
 * The page renders backend results only; it never calculates a financial figure, and it never
 * decides permissions: buttons are hidden for convenience, the server refuses regardless.
 * Interface text comes from assets/i18n.js (EN / VI / 中文); engine output stays in English. */
(function () {
  const { esc, usd } = window.CB;
  const { t } = window.I18N;
  const C = window.Charts;
  const $ = (id) => document.getElementById(id);
  const page = $("page");
  const usd2 = (x) => usd(x, 2);
  const pct = (x, d = 1) => (x == null ? "n/a" : Number(x).toFixed(d) + "%");
  const human = (s) => String(s || "").replaceAll("_", " ").toLowerCase();
  const state = { user: null, snap: null, summary: null, scorecard: null, evFilter: "ALL", cfg: null, current: "",
    contract: "SUPPLY AGREEMENT (SYNTHETIC SAMPLE)\nCustomer: Northern Retail LLC\nTotal consideration: USD 200,000\nPayment 30% advance\nPayment 40% upon delivery\nPayment 30% after acceptance\nTermination: Either party may terminate after written notice.\nChanges to bank account require callback verification.",
    invoice: "Invoice INV-1188, USD 260,000" };

  // ------------------------------------------------------------------ helpers
  let toastTimer;
  function toast(message, bad = false) {
    const el = $("toast");
    el.textContent = message;
    el.className = "toast show" + (bad ? " bad" : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.className = "toast"; }, 4200);
  }
  async function act(fn, okMessage) {
    try {
      const out = await fn();
      if (okMessage) toast(typeof okMessage === "function" ? okMessage(out) : okMessage);
      return out;
    } catch (e) {
      if (e.status === 401) { CB.clear(); location.href = "/?signin=" + (state.user ? state.user.portal : "sme"); return null; }
      toast(e.message, true);
      return null;
    }
  }
  const can = (perm) => state.user && state.user.permissions.includes(perm);
  const engineNote = () => (window.I18N.lang() === "en" ? "" : `<p class="note engine-note">${esc(t("ui.engineNote"))}</p>`);
  const head = (title, lede, actions = "") => `<div class="head"><div><h1>${esc(title)}</h1>${lede ? `<p>${lede}</p>` : ""}</div>${actions ? `<div class="row">${actions}</div>` : ""}</div>`;
  const kpi = (label, value, cls = "", foot = "") => `<div class="kpi ${cls.includes("hl") ? "hl" : ""}"><span>${esc(label)}</span><b class="${cls.replace("hl", "")}">${esc(value)}</b>${foot ? `<small>${foot}</small>` : ""}</div>`;
  const statusPill = (s) => {
    const map = { ok: "ok", ELIGIBLE: "ok", BOOKED: "ok", READ: "ok", VERIFIED: "ok", SUBMITTED: "ok", FUNDED: "ok", FUNDED_MOCK: "ok", ALLOWED: "ok", APPROVED: "ok",
      at_risk: "warn", FLAGGED: "warn", NEEDS_HUMAN: "warn", AWAITING_APPROVAL: "warn", IN_REVIEW: "warn", INFO_REQUESTED: "warn",
      shortfall: "bad", BLOCKED: "bad", REJECTED: "bad", DECLINED: "bad", REJECTED_BY_DIRECTOR: "bad" };
    const label = window.I18N.has("st." + s) ? t("st." + s) : human(s);
    return `<span class="pill ${map[s] || ""}">${esc(label)}</span>`;
  };
  const st = (s) => `<span class="st ${esc(s)}">${esc(t("ev." + s))}</span>`;
  const metricText = (m) => m.unit === "USD" ? usd2(m.value) : m.unit === "%" ? pct(m.value) : m.unit === "week" ? t("lbl.week", { w: m.value }) : m.value + " " + m.unit;
  const panel = (title, sub, body, cls = "") => `<section class="panel ${cls}"><h2>${esc(title)}</h2>${sub ? `<p class="sub">${sub}</p>` : ""}${body}</section>`;
  const SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];

  function weeklyColumns(weeks, after) {
    return C.columns(weeks.map((w) => ({
      label: "W" + w.week, value: w.closing,
      cls: w.status === "shortfall" ? "cb-neg" : w.status === "at_risk" ? "cb-risk" : "cb-good",
      tip: `${t("lbl.week", { w: w.week })}: ${usd2(w.closing)}\n${t("lbl.in")} ${usd(w.inflows)} · ${t("lbl.out")} ${usd(w.outflows)}`,
    })), { overlay: after, overlayTip: (v, i) => `${t("lbl.withAdvance")} ${t("lbl.week", { w: i + 1 })}: ${usd2(v)}`, label: t("ov.weekly") })
      + `<ul class="legend-inline"><li><i class="cb-good"></i>${esc(t("ov.lg.ok"))}</li><li><i class="cb-risk"></i>${esc(t("ov.lg.risk"))}</li><li><i class="cb-neg"></i>${esc(t("ov.lg.neg"))}</li>${after ? `<li><i class="line"></i>${esc(t("lbl.withAdvance"))}</li>` : ""}</ul>`;
  }

  async function refresh() { state.snap = await CB.get("/api/snapshot"); renderCaseTag(); return state.snap; }
  function renderCaseTag() {
    const s = state.snap;
    if (s) $("caseTag").textContent = `${s.meta.case_id} · ${human(s.meta.case_state)}`;
  }

  // ------------------------------------------------------------------ navigation
  const SME_NAV = [["grp.decide", ["overview", "autopilot", "cash", "evidence", "funding"]], ["grp.analyse", ["analytics", "project", "contracts", "green"]], ["grp.control", ["trust"]]];
  const BANK_NAV = [["grp.review", ["inbox", "trust"]]];
  function renderNav(current) {
    const groups = state.user.portal === "bank" ? BANK_NAV : SME_NAV;
    const pending = state.snap && state.snap.meta.case_state === "AWAITING_APPROVAL" && can("sme:approve") ? 1 : 0;
    $("side").innerHTML = groups.map(([title, items]) => `<h4>${esc(t(title))}</h4>` + items.map((id) =>
      `<a href="#${id}" ${current === id ? 'aria-current="page"' : ""}>${esc(t("nav." + id))}${id === "funding" && pending ? `<span class="count" data-tip="${esc(t("next.approve"))}">1</span>` : ""}</a>`).join("")).join("");
  }

  const routes = {};
  async function route() {
    const hash = (location.hash || "").slice(1) || (state.user.portal === "bank" ? "inbox" : "overview");
    const [name, arg] = hash.split("/");
    const allowed = state.user.portal === "bank" ? ["inbox", "case", "trust"] : ["overview", "autopilot", "cash", "evidence", "funding", "analytics", "project", "contracts", "green", "trust"];
    const target = allowed.includes(name) ? name : allowed[0];
    state.current = hash;
    renderNav(target === "case" ? "inbox" : target);
    page.innerHTML = `<p class="muted">${esc(t("app.loading"))}</p>`;
    try { await routes[target](arg); } catch (e) {
      if (e.status === 401) { CB.clear(); location.href = "/?signin=" + state.user.portal; return; }
      page.innerHTML = head(t("app.error")) + `<div class="empty"><p>${esc(e.message)}</p></div>`;
    }
    page.focus({ preventScroll: true });
  }

  // role strip with one-click persona switch (demo mode only)
  function roleStrip() {
    const u = state.user;
    const people = (state.cfg && state.cfg.demo_accounts || []).filter((a) => a.portal === u.portal || true);
    const switcher = people.length ? `<span class="rs-switch"><span class="muted small">${esc(t("app.viewAs"))}</span>${people.map((a) =>
      `<button type="button" class="btn small ${a.user_id === u.user_id ? "bridge" : "ghost"}" data-as="${esc(a.user_id)}" data-tip="${esc(t("role." + a.role))} · ${esc(a.org)}">${esc(a.name)}</button>`).join("")}</span>` : "";
    return `<div class="role-strip"><span class="pill">${esc(t("role." + u.role))}</span><span class="rs-note">${esc(t("role.note." + u.role))}</span>${switcher}</div>`;
  }
  function bindRoleStrip() {
    page.querySelectorAll("[data-as]").forEach((b) => b.onclick = async () => {
      if (b.dataset.as === state.user.user_id) return;
      try { await CB.post("/api/auth/logout"); } catch (e) { /* ignore */ }
      const s = await act(() => CB.post("/api/auth/demo-login", { user_id: b.dataset.as }, { anonymous: true }));
      if (!s) return;
      CB.save({ token: s.token, user: s.user, expires_at: s.expires_at });
      window.removeEventListener("hashchange", route);
      location.hash = s.user.portal === "bank" ? "inbox" : (state.current.split("/")[0] || "overview");
      location.reload();
    });
  }

  // ------------------------------------------------------------------ SME: overview dashboard
  routes.overview = async () => {
    const s = await refresh();
    const k = s.kpis;
    const best = s.funding_options.filter((o) => o.eligible && o.apr_pct != null).sort((a, b) => a.apr_pct - b.apr_pct)[0];
    const people = s.verification.filter((v) => v.status !== "ELIGIBLE").length + s.reconciliation.rows.filter((r) => r.status === "NEEDS_HUMAN").length + s.alerts.length + s.scans.filter((x) => x.status !== "READ").length;
    const stateNow = s.meta.case_state;
    const nextKey = stateNow === "AWAITING_APPROVAL" ? (can("sme:approve") ? "next.approve" : "next.wait")
      : stateNow === "SUBMITTED" ? "next.lender" : ["FUNDED", "REJECTED"].includes(stateNow) ? "next.done"
      : s.pack.status === "REJECTED_BY_DIRECTOR" ? "next.rework" : can("sme:prepare") ? "next.run" : "next.prepare";
    const nextBtn = ["next.approve", "next.wait", "next.lender", "next.done", "next.rework"].includes(nextKey) ? `<a class="btn bridge" href="#funding">${esc(t("btn.openFunding"))}</a>` : `<a class="btn bridge" href="#autopilot">${esc(t("btn.openAutopilot"))}</a>`;

    // buyers donut: colour follows the buyer (fixed order by buyer id), not by rank
    const buyerOrder = ["B-US-01", "B-JP-01", "B-US-02", "B-CN-01"];
    const buyers = s.buyer_risk.slice().sort((a, b) => buyerOrder.indexOf(a.buyer_id) - buyerOrder.indexOf(b.buyer_id));
    const shortName = (n) => n.replace(" (SYNTHETIC)", "").split(" ").slice(0, 2).join(" ");
    const donutBuyers = C.donut(buyers.map((b, i) => ({ label: shortName(b.buyer), value: b.share_of_receivables_pct,
      color: SERIES[i % 4], display: pct(b.share_of_receivables_pct), flag: b.concentration_alert ? ">40%" : "" })),
      { center: pct(buyers[0] ? buyers[0].share_of_receivables_pct : 0, 0), centerSub: buyers[0] ? buyers[0].buyer.split(" ")[0] : "", label: t("ov.buyers") });

    const opts = s.funding_options.filter((o) => o.apr_pct != null);
    const optionBars = C.hbars(opts.map((o) => ({ label: t("opt." + o.type), value: o.apr_pct, display: pct(o.apr_pct, 1),
      cls: o.id === (best && best.id) ? "cb-accent" : "cb-muted", strong: o.id === (best && best.id),
      tip: `${o.name}\n${t("col.apr")}: ${pct(o.apr_pct, 2)}\n${t("col.amount")}: ${usd2(o.amount_usd)}\n${t("col.total")}: ${o.cost_breakdown.total_usd != null ? usd2(o.cost_breakdown.total_usd) : "–"}` })));

    const drivers = s.forecast.attribution.slice().sort((a, b) => b.amount_usd - a.amount_usd).slice(0, 6);
    const driverBars = C.hbars(drivers.map((a) => ({ label: a.driver.replace(" (SYNTHETIC)", "").replace(/ is likely late: (\d+)% chance of on-time payment/, " late ($1% on time)"),
      value: a.amount_usd, display: usd(a.amount_usd), cls: a.amount_usd >= 0 ? "cb-neg" : "cb-good", tip: `${a.driver}\n${usd2(a.amount_usd)}\n${a.source_ref}` })));

    const vcount = (st_) => s.verification.filter((v) => v.status === st_).length;
    const checks = C.donut([
      { label: t("st.ELIGIBLE"), value: vcount("ELIGIBLE"), color: "var(--good)", display: vcount("ELIGIBLE") },
      { label: t("st.FLAGGED"), value: vcount("FLAGGED"), color: "var(--risk)", display: vcount("FLAGGED") },
      { label: t("st.BLOCKED"), value: vcount("BLOCKED"), color: "var(--deficit)", display: vcount("BLOCKED") },
    ], { center: `${vcount("ELIGIBLE")}/${s.verification.length}`, centerSub: t("st.ELIGIBLE"), label: t("ov.checks") });

    const activity = s.evidence.audit_tail.slice(-6).reverse().map((a) => `<li><span class="mono small">#${a.seq}</span><span>${esc(a.agent)} · ${esc(a.tool)}</span>${statusPill(a.decision)}</li>`).join("");

    page.innerHTML = roleStrip() + head(t("ov.title"), esc(t("ov.lede"))) +
      `<div class="kpis cards">
        ${kpi(t("ov.cash"), usd(k.cash_today_usd), "hl", esc(t("ov.cashFoot")))}
        ${kpi(t("ov.gap"), k.first_shortfall_week ? t("lbl.week", { w: k.first_shortfall_week }) : "–", "neg", k.shortfall_usd ? `${esc(t("ov.gapFoot"))} <b class="neg">${usd(k.shortfall_usd)}</b>` : "")}
        ${kpi(t("ov.best"), best ? pct(best.apr_pct, 1) : "–", "", best ? `${esc(best.name.split(" (")[0])}, ${esc(t("ov.bestFoot"))} ${usd(best.cost_breakdown.total_usd)}` : "")}
        ${kpi(t("ov.todo"), String(people), people ? "warn" : "pos", esc(t("ov.todoFoot")))}
      </div>
      <div class="dash">
        <div class="span2">${panel(t("ov.weekly"), esc(t("ov.weeklySub")), weeklyColumns(s.forecast.weeks))}</div>
        ${panel(t("ov.buyers"), esc(t("ov.buyersSub")), donutBuyers)}
        ${panel(t("ov.options"), esc(t("ov.optionsSub")), optionBars)}
        <div class="span2">${panel(t("ov.drivers", { w: k.first_shortfall_week || "–" }), esc(t("ov.driversSub")), driverBars)}</div>
        ${panel(t("ov.checks"), "", checks)}
        <div class="span2">${panel(t("ov.next"), "", `<p class="next">${esc(t(nextKey))}</p><div class="row" style="margin-top:12px">${nextBtn}</div><h3 class="mini">${esc(t("ov.activity"))}</h3><ul class="activity">${activity}</ul>`)}</div>
      </div>`;
    bindRoleStrip();
  };

  // ------------------------------------------------------------------ SME: Autopilot
  routes.autopilot = async () => {
    await refresh();
    const run = state.snap.autopilot;
    const preparer = can("sme:prepare");
    page.innerHTML = head(t("nav.autopilot"), esc(t(preparer ? "ap.lede.prep" : "ap.lede.dir")),
      `<button class="btn ${preparer ? "bridge" : "ghost"}" id="apRun">${esc(t(preparer ? "ap.run" : "ap.runPlan"))}</button>` +
      (preparer ? `<button class="btn ghost" id="apPlan">${esc(t("ap.plan"))}</button>` : "")) + engineNote() +
      `<form class="panel" id="apGoal"><label class="field">${esc(t("ap.goal"))}<input id="apGoalText" maxlength="300" value="Close the forecast cash gap safely"></label></form>` +
      `<div id="apOut">${run ? renderRun(run) : `<div class="empty"><h2>${esc(t("ap.empty"))}</h2><p>${esc(t("ap.emptyD"))}</p></div>`}</div>`;
    const go = async (execute) => {
      const btn = execute ? $("apRun") : ($("apPlan") || $("apRun"));
      btn.disabled = true;
      const out = await act(() => CB.post("/api/autopilot/run", { execute, goal: $("apGoalText").value }), (r) => t("dec." + r.decision));
      btn.disabled = false;
      if (out) { $("apOut").innerHTML = renderRun(out); bindRun(); await refresh(); renderNav("autopilot"); }
    };
    $("apRun").onclick = () => go(preparer);
    if ($("apPlan")) $("apPlan").onclick = () => go(false);
    $("apGoal").onsubmit = (e) => { e.preventDefault(); go(preparer); };
    bindRun();
  };

  function renderRun(r) {
    const d = r.decision;
    const btn = { AWAITING_DIRECTOR_APPROVAL: can("sme:approve") ? `<a class="btn" href="#funding">${esc(t("btn.review"))}</a>` : "",
      HUMAN_REVIEW_REQUIRED: `<a class="btn" href="#evidence">${esc(t("btn.exceptions"))}</a>`,
      SUBMITTED_TO_LENDER: `<a class="btn" href="#funding">${esc(t("btn.lenderStatus"))}</a>`, DECLINED_BY_LENDER: `<a class="btn" href="#funding">${esc(t("btn.lenderStatus"))}</a>` }[d] || "";
    const warn = ["HUMAN_REVIEW_REQUIRED", "DECLINED_BY_LENDER"].includes(d);
    const rec = r.recommendation;
    const counts = r.evidence_counts || {};
    const order = ["VERIFIED", "CALCULATED", "MODEL_ESTIMATE", "ASSUMPTION", "NEEDS_HUMAN", "NOT_VERIFIABLE_HERE"];
    let html = `<div class="decision ${warn ? "warn" : ""}"><div><h2>${esc(t("dec." + d))}</h2><p>${esc(r.human_handoff.action)}. ${esc(r.human_handoff.why)}.</p></div>${btn}</div>`;
    if (rec) {
      html += `<section class="panel"><h2>${esc(t("ap.rec"))}</h2><p class="sub">Run ${esc(r.run_id)} · ${esc(r.mode)} · ${esc(r.planner)}</p>
        <div class="rec-head"><b>${esc(rec.option_name)}</b><span>${usd2(rec.amount_usd)} · ${pct(rec.apr_pct, 2)}</span><span class="muted">${esc(t("col.total"))} ${usd2(rec.total_cost_usd)}</span></div>
        <ul class="list">${rec.why.map((w) => `<li>${esc(w)}</li>`).join("")}</ul>
        <div class="caution"><b>${esc(t("ap.notFix"))}</b><ul class="list">${rec.what_would_change.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>
        ${rec.coverage ? `<h3 class="mini">${esc(t("ap.withWithout"))}</h3>${weeklyColumns(state.snap.forecast.weeks, rec.coverage.weeks.map((w) => w.closing_after))}<p class="note">${esc(rec.coverage.assumptions.filter(Boolean).join(" "))}</p>` : ""}
        <h3 class="mini">${esc(t("ap.conditions"))}</h3><ul class="list">${rec.conditions.map((c) => `<li>${esc(c)}</li>`).join("")}</ul></section>`;
    }
    html += `<section class="panel"><h2>${esc(t("ap.did"))}</h2><p class="sub">${esc(t("ap.didSub"))}</p><ol class="trace">${r.steps.map((s) => `
      <li class="${esc(s.status)}"><span class="n">${s.n}</span><div><span class="tool">${esc(s.tool)}</span><h3>${esc(s.result)}</h3><p class="why">${esc(s.why)}</p>
      ${s.evidence.length ? `<div class="evs">${s.evidence.map((id) => `<button type="button" class="ev-link" data-ev="${esc(id)}">${esc(id)}</button>`).join("")}</div>` : ""}</div></li>`).join("")}</ol>
      ${r.refused_proposals.length ? `<div class="caution"><b>${esc(t("ap.refused"))}</b><ul class="list">${r.refused_proposals.map((x) => `<li>${esc(x.proposed)}: ${esc(x.reason)}</li>`).join("")}</ul></div>` : ""}
      ${r.goal_injection_detected ? `<p class="note">${esc(t("ap.injected"))}</p>` : ""}
      <h3 class="mini">${esc(t("ap.guardrails"))}</h3><ul class="list small">${r.guardrails.map((g) => `<li>${esc(g)}</li>`).join("")}</ul></section>
      <section class="panel"><h2>${esc(t("ap.register"))}</h2><p class="sub">${esc(t("ap.registerSub", { n: r.evidence.length }))}</p>
      ${C.stack(order.map((s_) => ({ label: t("ev." + s_), value: counts[s_] || 0, cls: "evc-" + s_ })))}
      <div class="filters" id="evFilters">${["ALL"].concat(order).map((key) =>
        `<button type="button" data-f="${key}" aria-pressed="${state.evFilter === key}">${esc(key === "ALL" ? t("ap.all") : t("ev." + key))} ${key === "ALL" ? r.evidence.length : counts[key] || 0}</button>`).join("")}</div>
      <div class="scroll"><table id="evTable"><thead><tr><th>ID</th><th>${esc(t("ap.claim"))}</th><th>${esc(t("ap.value"))}</th><th>${esc(t("ap.status"))}</th></tr></thead><tbody>${r.evidence.map((e) => `
        <tr data-id="${esc(e.id)}" data-status="${esc(e.status)}"><td>${esc(e.id)}</td><td>${esc(e.claim)}${e.note ? `<div class="muted small">${esc(e.note)}</div>` : ""}<div class="muted small mono">${esc(e.source)}</div></td><td>${typeof e.value === "number" ? esc(Math.abs(e.value) >= 1000 ? usd2(e.value) : e.value) : `<span class="${String(e.value).length > 40 ? "mono" : ""}">${esc(e.value)}</span>`}</td><td>${st(e.status)}</td></tr>`).join("")}</tbody></table></div></section>`;
    return html;
  }
  function bindRun() {
    const filters = $("evFilters");
    if (!filters) return;
    const apply = () => {
      filters.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.f === state.evFilter)));
      document.querySelectorAll("#evTable tbody tr").forEach((tr) => { tr.hidden = state.evFilter !== "ALL" && tr.dataset.status !== state.evFilter; });
    };
    filters.onclick = (e) => { const b = e.target.closest("button"); if (b) { state.evFilter = b.dataset.f; apply(); } };
    document.querySelectorAll(".ev-link").forEach((b) => b.onclick = () => {
      state.evFilter = "ALL"; apply();
      const row = document.querySelector(`#evTable tr[data-id="${b.dataset.ev}"]`);
      if (row) { row.scrollIntoView({ block: "center", behavior: "smooth" }); row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash"); }
    });
    apply();
  }

  // ------------------------------------------------------------------ SME: cash forecast
  routes.cash = async () => {
    const s = await refresh();
    const k = s.kpis;
    const sliderLabel = { dso_change_days: "cash.sl.dso", deposit_pct: "cash.sl.dep", tariff_shared_pct: "cash.sl.tar", fx_change_pct: "cash.sl.fx" };
    page.innerHTML = head(t("cash.title"), esc(t("cash.lede"))) +
      `<div class="kpis cards">${kpi(t("ov.cash"), usd(k.cash_today_usd), "hl")}${kpi(t("cash.firstNeg"), k.first_shortfall_week ? t("lbl.week", { w: k.first_shortfall_week }) : "–", "neg")}${kpi(t("cash.short"), k.shortfall_usd ? "−" + usd(k.shortfall_usd) : "–", "neg")}${kpi(t("cash.ccc"), k.ccc.ccc + " d")}${kpi(t("cash.blocked"), k.blocked_fraud_count)}</div>
      ${panel(t("ov.weekly"), esc(t("ov.weeklySub")), `<div id="chartBox">${weeklyColumns(s.forecast.weeks)}</div><div id="delta"></div>`)}
      <div class="grid2">${panel(t("cash.try"), esc(t("cash.trySub")), `<div id="sliders">${Object.entries(s.scenario_controls).map(([key, c]) => `
        <label class="slider">${esc(t(sliderLabel[key] || key))} <output id="o_${key}">${c.default}</output>
        <input type="range" name="${key}" min="${c.min}" max="${c.max}" step="${c.step}" value="${c.default}"></label>`).join("")}</div>
        <div class="row" style="margin-top:12px"><button class="btn ghost small" id="simReset">${esc(t("cash.reset"))}</button></div>`)}
      ${panel(t("ov.drivers", { w: k.first_shortfall_week || "–" }), esc(t("ov.driversSub")), `<table><tbody>${s.forecast.attribution.map((a) => `<tr><td>${esc(a.driver)}<div class="muted small mono">${esc(a.source_ref)}</div></td><td class="num">${usd2(a.amount_usd)}</td></tr>`).join("")}</tbody></table>`)}</div>
      ${panel(t("cash.risk"), `${esc(s.risk_model.method)}, ${s.risk_model.training_rows}. ${esc(s.risk_model.on_time_definition)}.`, `<div class="scroll"><table><thead><tr><th>${esc(t("cash.col.buyer"))}</th><th class="num">${esc(t("cash.col.share"))}</th><th class="num">${esc(t("cash.col.late"))}</th><th>${esc(t("cash.col.p"))}</th><th></th></tr></thead><tbody>${s.buyer_risk.map((b) => `<tr><td>${esc(b.buyer)}${b.has_history ? "" : `<div class="muted small">${esc(t("cash.noHist"))}</div>`}</td><td class="num">${pct(b.share_of_receivables_pct)}</td><td class="num">${b.avg_days_late}</td><td><span class="meter" data-tip="${Math.round(b.p_on_time * 100)}%"><i style="width:${Math.round(b.p_on_time * 100)}%"></i></span> ${Math.round(b.p_on_time * 100)}%</td><td>${b.concentration_alert ? `<span class="pill bad">${esc(t("cash.conc"))}</span>` : ""}</td></tr>`).join("")}</tbody></table></div>`)}`;
    let timer;
    const run = () => {
      clearTimeout(timer);
      timer = setTimeout(async () => {
        const params = {};
        $("sliders").querySelectorAll("input").forEach((i) => { params[i.name] = Number(i.value); $("o_" + i.name).textContent = i.value; });
        const r = await act(() => CB.post("/api/simulate", { params }));
        if (!r) return;
        $("chartBox").innerHTML = weeklyColumns(r.forecast.weeks);
        const dd = r.delta;
        $("delta").innerHTML = `<div class="delta"><span>${esc(t("cash.firstNeg"))}: <b>${dd.first_shortfall_week_before ?? "–"}</b> → <b>${dd.first_shortfall_week_after ?? "–"}</b></span><span>${esc(t("cash.lowest"))}: <b>${usd(dd.min_closing_before_usd)}</b> → <b>${usd(dd.min_closing_after_usd)}</b></span></div>`;
      }, 180);
    };
    $("sliders").addEventListener("input", run);
    $("simReset").onclick = () => { $("sliders").querySelectorAll("input").forEach((i) => { i.value = s.scenario_controls[i.name].default; }); run(); };
  };

  // ------------------------------------------------------------------ SME: receivables & checks
  routes.evidence = async () => {
    const s = await refresh();
    const w = s.reconciliation.featured_wire;
    const recon = s.reconciliation.rows;
    const rc = (x) => recon.filter((r) => r.status === x).length;
    page.innerHTML = head(t("evd.title"), esc(t("evd.lede"))) + engineNote() +
      `<div class="grid3">${panel(t("evd.recon"), "", C.donut([{ label: human("BOOKED"), value: rc("BOOKED"), color: "var(--good)" }, { label: human("NEEDS_HUMAN"), value: rc("NEEDS_HUMAN"), color: "var(--risk)" }], { center: `${rc("BOOKED")}/${recon.length}`, centerSub: human("BOOKED") }))}
        ${panel(t("ov.checks"), "", C.donut([{ label: t("st.ELIGIBLE"), value: s.verification.filter((v) => v.status === "ELIGIBLE").length, color: "var(--good)" }, { label: t("st.FLAGGED"), value: s.verification.filter((v) => v.status === "FLAGGED").length, color: "var(--risk)" }, { label: t("st.BLOCKED"), value: s.verification.filter((v) => v.status === "BLOCKED").length, color: "var(--deficit)" }], { center: String(s.verification.length), centerSub: "invoices" }))}
        ${w ? panel(t("evd.wire"), "", `<p>${esc(w.txn_id)}: <b>${usd2(w.received)}</b></p>${C.hbars(w.invoices.map((i) => ({ label: i.id, value: i.amount, display: usd(i.amount), cls: "cb-accent" })).concat([{ label: "gap", value: w.gap, display: usd2(w.gap), cls: "cb-muted" }]))}<p class="note">${esc(w.explanation)}</p>`) : ""}</div>` +
      panel(t("evd.recon"), "", `<div class="scroll"><table><thead><tr><th>Txn</th><th class="num">${esc(t("col.amount"))}</th><th>Invoices</th><th>${esc(t("col.status"))}</th><th></th></tr></thead><tbody>${recon.map((r) => `<tr><td>${esc(r.txn_id)}<div class="muted small">${esc(r.reference)}</div></td><td class="num">${esc(r.currency)} ${Number(r.amount).toLocaleString()}</td><td>${esc(r.matched_invoices.join(", ") || "–")}</td><td>${statusPill(r.status)}</td><td class="small">${esc(r.reason || r.gap_reason || "")}</td></tr>`).join("")}</tbody></table></div>`) +
      panel(t("evd.match"), "", `<div class="scroll"><table><thead><tr><th>Invoice</th><th>${esc(t("cash.col.buyer"))}</th><th class="num">${esc(t("col.amount"))}</th><th>Due</th><th>3-way</th><th>Registry</th><th></th></tr></thead><tbody>${s.verification.map((v) => `<tr><td>${esc(v.invoice_id)}</td><td>${esc(v.buyer)}</td><td class="num">${esc(v.currency)} ${Number(v.amount).toLocaleString()}</td><td>${esc(v.due_date)}</td><td>${statusPill(v.status)}</td><td class="small">${esc(human(v.registry_status))}</td><td class="small">${esc(v.differences.join("; "))}</td></tr>`).join("")}</tbody></table></div>`) +
      `<div class="grid2">${panel(t("evd.scans"), esc(t("evd.scansSub")), `<table><tbody>${s.scans.map((d) => `<tr><td>${esc(d.doc_id)}<div class="muted small">${esc(human(d.doc_type))}</div></td><td>${statusPill(d.status)}</td><td><span class="meter ${d.min_confidence < 0.85 ? "low" : ""}" data-tip="${Number(d.min_confidence).toFixed(2)}"><i style="width:${Math.round(d.min_confidence * 100)}%"></i></span></td><td class="small">${esc(d.reason || (d.matches_record ? "matches the record" : d.differences.join("; ")))}</td></tr>`).join("")}</tbody></table>`)}
      ${panel(t("evd.held"), esc(t("evd.heldSub")), s.alerts.map((a) => `<div class="flag ${a.severity === "critical" || a.severity === "high" ? "high" : ""}"><b>${esc(a.type)}: ${esc(a.subject)}</b><div class="small mono">${esc(a.sender)}</div><ul class="list small">${(a.reasons || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul><p class="small">${esc(a.action_hint || "")}</p></div>`).join("") || `<p class="muted">–</p>`)}</div>`;
  };

  // ------------------------------------------------------------------ SME: funding & approval
  routes.funding = async () => {
    const s = await refresh();
    const p = s.pack;
    const cs = s.meta.case_state;
    const preparer = can("sme:prepare"), approver = can("sme:approve");
    const lr = s.lender_review;
    let actions = "";
    if (preparer && cs === "INVOICE_VERIFIED") actions = `<button class="btn bridge" id="prep" ${s.selected_option_id ? "" : "disabled"}>${esc(t("fund.prepare"))}</button>`;
    if (preparer && cs === "NEEDS_HUMAN" && p.status === "REJECTED_BY_DIRECTOR") actions = `<button class="btn bridge" id="reopen">${esc(t("fund.rework"))}</button>`;
    if (approver && cs === "AWAITING_APPROVAL") actions = `<button class="btn bridge" id="approveBtn">${esc(t("fund.approve"))}</button><button class="btn danger" id="rejectBtn">${esc(t("fund.reject"))}</button>`;
    const opts = s.funding_options;
    page.innerHTML = head(t("fund.title"), esc(t(preparer ? "fund.lede.prep" : "fund.lede.dir")), actions) + engineNote() +
      (s.meta.last_error ? `<div class="decision warn"><div><h2>${esc(t("fund.notDone"))}</h2><p>${esc(s.meta.last_error)}</p></div></div>` : "") +
      `<div class="grid2">${panel(t("ov.options"), esc(t("ov.optionsSub")), C.hbars(opts.filter((o) => o.apr_pct != null).map((o) => ({ label: t("opt." + o.type), value: o.apr_pct, display: pct(o.apr_pct, 2), cls: o.id === s.selected_option_id ? "cb-accent" : "cb-muted", strong: o.id === s.selected_option_id }))))}
        ${panel(t("col.total"), "", C.hbars(opts.filter((o) => o.cost_breakdown && o.cost_breakdown.total_usd != null).map((o) => ({ label: t("opt." + o.type), value: o.cost_breakdown.total_usd, display: usd2(o.cost_breakdown.total_usd), cls: o.id === s.selected_option_id ? "cb-accent" : "cb-muted" }))))}</div>` +
      panel(t("fund.ways"), "", `<div class="scroll"><table><thead><tr><th>${esc(t("col.option"))}</th><th class="num">${esc(t("col.amount"))}</th><th class="num">${esc(t("col.apr"))}</th><th class="num">${esc(t("col.total"))}</th><th>${esc(t("col.status"))}</th><th></th></tr></thead><tbody>${opts.map((o) => `<tr class="${o.id === s.selected_option_id ? "sel" : ""}"><td>${esc(o.name)}<div class="muted small">${esc(o.why_not_cheaper || "")}</div></td><td class="num">${o.amount_usd == null ? "–" : usd2(o.amount_usd)}</td><td class="num">${o.apr_pct == null ? "–" : pct(o.apr_pct, 2)}</td><td class="num">${o.cost_breakdown && o.cost_breakdown.total_usd != null ? usd2(o.cost_breakdown.total_usd) : "–"}</td><td>${o.eligible ? statusPill("ELIGIBLE") : `<span class="small muted">${esc(o.ineligible_reason || "")}</span>`}</td><td>${preparer && o.eligible && cs === "INVOICE_VERIFIED" ? `<button class="btn small ${o.id === s.selected_option_id ? "bridge" : "ghost"}" data-opt="${esc(o.id)}">${esc(t(o.id === s.selected_option_id ? "fund.chosen" : "fund.choose"))}</button>` : ""}</td></tr>`).join("")}</tbody></table></div>`) +
      (p.pack_id ? `<div class="grid2">${panel(`Pack ${p.pack_id}`, `${statusPill(p.status)} ${esc(p.prepared_by || "")}${p.approved_by ? " → " + esc(p.approved_by) : ""}`,
          `<table><tbody>${p.locked_metrics.map((m) => `<tr><td>${esc(m.label)}</td><td class="num">${esc(metricText(m))}</td></tr>`).join("")}</tbody></table>
          <p class="hashline" style="margin-top:10px">action <span class="mono">${esc(p.action_hash)}</span></p>
          <div class="row" style="margin-top:10px"><button class="btn ghost small" id="pdf">${esc(t("fund.pdf"))}</button>${preparer ? `<button class="btn ghost small" id="tamper">${esc(t("fund.tamper"))}</button>` : ""}${cs === "SUBMITTED" && preparer ? `<button class="btn ghost small" id="dupe">${esc(t("fund.dupe"))}</button>` : ""}</div>`)}
        ${panel(t("fund.letter"), esc(t("fund.letterSub")), `<div class="letter">${esc(p.letter_text || "")}</div>`)}</div>` :
        `<div class="empty"><h2>${esc(t("fund.noPack"))}</h2><p>${esc(t(preparer ? "next.run" : "next.prepare"))}</p></div>`) +
      (["SUBMITTED", "FUNDED", "REJECTED"].includes(cs) ? panel(t("fund.lender"), `${statusPill(lr.status)} ${lr.reviewer ? esc(lr.reviewer) : ""}`, `${lr.note ? `<p>${esc(lr.note)}</p>` : ""}<ul class="list small">${lr.history.map((h) => `<li>${esc(human(h.event))}${h.by ? " · " + esc(h.by) : ""}${h.note ? ": " + esc(h.note) : ""}</li>`).join("")}</ul>`) : "");
    page.querySelectorAll("[data-opt]").forEach((b) => b.onclick = async () => { if (await act(() => CB.post("/api/choose_option", { option_id: b.dataset.opt }))) routes.funding(); });
    if ($("prep")) $("prep").onclick = async () => { const r = await act(() => CB.post("/api/prepare_pack")); if (r) { if (r.meta.last_error) toast(r.meta.last_error, true); routes.funding(); } };
    if ($("reopen")) $("reopen").onclick = async () => { if (await act(() => CB.post("/api/reopen_pack"))) routes.funding(); };
    if ($("approveBtn")) $("approveBtn").onclick = openOtp;
    if ($("rejectBtn")) $("rejectBtn").onclick = async () => {
      const reason = prompt(t("fund.reject") + ": ?");
      if (reason && reason.trim().length >= 3 && await act(() => CB.post("/api/reject_pack", { reason }))) routes.funding();
    };
    if ($("pdf")) $("pdf").onclick = () => act(() => CB.download("/api/pack/pdf", `${p.pack_id}.pdf`));
    if ($("tamper")) $("tamper").onclick = () => act(() => CB.post("/api/tamper_draft"), (r) => r.ok ? "Unexpected: accepted" : `Rejected: ${r.offending.join(", ")} is not a locked figure`);
    if ($("dupe")) $("dupe").onclick = () => act(() => CB.post("/api/retry_double_financing"), (r) => r.blocked ? "Blocked: this invoice is already in the registry" : r.message);
  };

  async function openOtp() {
    const ch = await act(() => CB.post("/api/request_otp"));
    if (!ch) return;
    $("otpInfo").textContent = `${ch.instructions} (${new Date(ch.expires_at).toLocaleTimeString()})`;
    $("otpHash").textContent = ch.action_hash;
    $("otpHelp").innerHTML = state.cfg && state.cfg.otp_demo_secret ? `Demo: <span class="mono">${esc(state.cfg.otp_demo_secret)}</span> (Base32, 30 s)` : "";
    $("otpErr").textContent = "";
    $("otpCode").value = "";
    $("otpModal").hidden = false;
    $("otpCode").focus();
  }
  $("otpCancel").onclick = () => { $("otpModal").hidden = true; };
  $("otpApprove").onclick = async () => {
    const code = $("otpCode").value.trim();
    if (!/^\d{6}$/.test(code)) { $("otpErr").textContent = "6 digits"; return; }
    try {
      const r = await CB.post("/api/approve", { code });
      if (!r.ok) {
        $("otpErr").textContent = { invalid_code: "That code is not valid for this pack. Check your device's clock and try again.", replayed: "That code was already used. Wait for the next one.", expired: "The approval window closed. Cancel and open it again.", segregation_of_duties: "You prepared this pack, so you cannot approve it.", DoubleFinancingBlocked: "This invoice is already financed." }[r.error] || r.error;
        return;
      }
      $("otpModal").hidden = true;
      toast(t("dec.SUBMITTED_TO_LENDER"));
      await routes.funding();
      renderNav("funding");
    } catch (e) { $("otpErr").textContent = e.message; }
  };
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") { $("otpModal").hidden = true; $("drawer").hidden = true; } });

  // ------------------------------------------------------------------ SME: analysis tools
  const field = (key, value, label) => `<label class="field">${esc(label || key.replaceAll("_", " "))}<input name="${esc(key)}" type="number" step="any" value="${esc(value)}" required></label>`;
  const formData = (form) => Object.fromEntries([...new FormData(form).entries()].map(([k, v]) => [k, Number(v)]));
  const flags = (list) => (list || []).map((f) => `<div class="flag ${f.severity === "high" ? "high" : ""}"><b>${esc(f.code)}</b> <span class="muted small">${esc(f.severity)}</span><p class="small">${esc(f.description)}</p>${f.evidence ? `<p class="small muted">${esc(f.evidence)}</p>` : ""}</div>`).join("") || `<p class="muted">No rule-based flags. Authenticity and legal completeness are still unverified.</p>`;

  routes.analytics = async () => {
    const d = state.summary || (state.summary = await CB.get("/api/analytics/summary"));
    const labels = { dso_days_estimate: "DSO", dio_days_estimate: "DIO", dpo_days: "DPO", cash_conversion_cycle_days: "CCC", net_working_capital_usd: "Net working capital", receivables_to_revenue_pct: "Receivables / revenue", inventory_to_cogs_pct: "Inventory / COGS", operating_margin_pct: "Operating margin", current_ratio: "Current ratio", quick_ratio: "Quick ratio", cash_ratio: "Cash ratio", gross_margin_pct: "Gross margin", ebitda_margin_pct: "EBITDA margin", interest_coverage: "Interest coverage", dscr_proxy: "DSCR (proxy)", debt_to_equity: "Debt / equity", cash_runway_months_gross_expenses: "Cash runway (months)" };
    const fmt = (k, v) => v == null ? "n/a" : k.endsWith("_usd") ? usd(v) : k.endsWith("_pct") ? pct(v) : Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 });
    const m = d.eda.monthly;
    const last = m[m.length - 1];
    const other = Math.max(0, last.expenses - last.marketing - last.payroll - (last.supplier || 0));
    const mix = C.donut([{ label: "Supplier", value: last.supplier || 0, color: SERIES[0], display: usd(last.supplier || 0) }, { label: "Payroll", value: last.payroll, color: SERIES[1], display: usd(last.payroll) },
      { label: "Marketing", value: last.marketing, color: SERIES[2], display: usd(last.marketing) }, { label: "Other", value: other, color: SERIES[3], display: usd(other) }], { center: usd(last.expenses), centerSub: last.month });
    const r = d.ratios;
    page.innerHTML = head(t("fin.title"), esc(t("fin.lede"))) +
      `<div class="kpis cards">${kpi("Current ratio", fmt("current_ratio", r.current_ratio), "hl")}${kpi("Quick ratio", fmt("quick_ratio", r.quick_ratio))}${kpi("Operating margin", fmt("operating_margin_pct", r.operating_margin_pct))}${kpi("DSCR (proxy)", fmt("dscr_proxy", r.dscr_proxy))}${kpi("Cash runway (months)", fmt("x", r.cash_runway_months_gross_expenses), r.cash_runway_months_gross_expenses < 1 ? "neg" : "")}</div>
      <div class="dash"><div class="span2">${panel(t("fin.trend"), "", C.lines(m.map((x) => x.month.slice(2)), [{ name: "Revenue", values: m.map((x) => x.revenue), color: SERIES[0] }, { name: "Expenses", values: m.map((x) => x.expenses), color: SERIES[1] }], { fmt: (v) => usd(v) }) + `<p class="note">Expense outliers above 2σ: ${esc(d.eda.expense_outliers.map((x) => x.month).join(", ") || "none")}.</p>`)}</div>
      ${panel(t("fin.mix"), "", mix)}
      <div class="span3">${panel(t("fin.ratios"), esc(d.definitions.dscr_proxy || ""), `<dl class="ratio-grid">${Object.entries(r).map(([k, v]) => `<div><dt>${esc(labels[k] || k)}</dt><dd class="${v == null ? "muted" : ""}">${esc(fmt(k, v))}</dd></div>`).join("")}</dl>`)}</div></div>
      ${panel(t("fin.scn"), "", `<form id="scn"><div class="inputs">${field("marketing_increase_pct", 25, "Marketing +%")}${field("receipts_delayed_pct", 10, "Receipts delayed %")}${field("new_loan_usd", 0, "New loan USD")}${field("loan_apr_pct", 15, "Loan APR %")}${field("horizon_months", 3, "Months")}${field("minimum_reserve_usd", 20000, "Min reserve USD")}</div><button class="btn bridge">${esc(t("fin.calc"))}</button></form><div id="scnOut"></div>`)}`;
    $("scn").onsubmit = async (e) => {
      e.preventDefault();
      const x = await act(() => CB.post("/api/analytics/scenario", { data: formData(e.target) }));
      if (x) $("scnOut").innerHTML = `<div class="kpis cards" style="margin-top:14px">${kpi("Baseline closing cash", usd(x.baseline_ending_cash_usd))}${kpi("Scenario closing cash", usd(x.scenario_ending_cash_usd))}${kpi("Lowest cash", usd(x.minimum_cash_usd), x.reserve_breach ? "neg" : "")}${kpi("Reserve", x.reserve_breach ? "breached" : "held", x.reserve_breach ? "neg" : "pos")}</div>` +
        (x.schedule ? C.columns(x.schedule.map((row) => ({ label: "M" + row.month, value: row.closing_cash_usd, cls: row.closing_cash_usd < 0 ? "cb-neg" : "cb-accent", tip: usd(row.closing_cash_usd) })), { height: 200 }) : "") + (x.limitations || []).map((l) => `<p class="note">${esc(l)}</p>`).join("");
    };
  };

  routes.project = async () => {
    const d = { contract_value_usd: 200000, upfront_cost_usd: 110000, remaining_cost_usd: 55000, available_cash_usd: 60000, minimum_reserve_usd: 15000, advance_payment_pct: 20, stress_cost_overrun_pct: 15, loan_apr_pct: 15, financing_days: 90, workforce_required_hours: 400, workforce_available_hours: 300, outsourced_hourly_cost_usd: 25 };
    page.innerHTML = head(t("prj.title"), esc(t("prj.lede"))) + panel("", "", `<form id="prj"><div class="inputs">${Object.entries(d).map(([k, v]) => field(k, v)).join("")}</div><button class="btn bridge">${esc(t("prj.assess"))}</button></form><div id="prjOut"></div>`);
    $("prj").onsubmit = async (e) => {
      e.preventDefault();
      const x = await act(() => CB.post("/api/projects/assess", { data: formData(e.target) }));
      if (x) $("prjOut").innerHTML = `<div class="kpis cards" style="margin-top:14px">${kpi("Upfront funding gap", usd(x.initial_funding_gap_usd), x.initial_funding_gap_usd > 0 ? "neg" : "pos")}${kpi("Gap under stress", usd(x.stress_gap_if_advance_delayed_and_cost_overruns_usd), "neg")}${kpi("Indicative margin", pct(x.estimated_margin_pct))}${kpi("Team hours short", x.workforce_readiness.uncovered_team_hours)}${kpi("Outsourcing cost", usd(x.workforce_readiness.indicative_outsourcing_cost_usd))}</div>` +
        C.hbars([{ label: "Upfront gap", value: x.initial_funding_gap_usd, display: usd(x.initial_funding_gap_usd), cls: "cb-risk" }, { label: "Stress gap", value: x.stress_gap_if_advance_delayed_and_cost_overruns_usd, display: usd(x.stress_gap_if_advance_delayed_and_cost_overruns_usd), cls: "cb-neg" }]) +
        (x.limitations || []).map((l) => `<p class="note">${esc(l)}</p>`).join("");
    };
  };

  routes.contracts = async () => {
    page.innerHTML = head(t("ctr.title"), esc(t("ctr.lede"))) + engineNote() +
      panel("1", "PDF / PNG / JPG / TXT ≤ 5 MB", `<label class="field">File<input id="up" type="file" accept=".txt,.pdf,.png,.jpg,.jpeg"></label>
        <label class="field" style="margin-top:10px">Contract<textarea id="ct" rows="9"></textarea></label>
        <label class="field" style="margin-top:10px">Invoice<textarea id="it" rows="2"></textarea></label>
        <div class="row" style="margin-top:12px"><button class="btn bridge" id="rev">Review contract</button><button class="btn ghost" id="cmp">Compare with invoice</button></div><div id="ctOut"></div>`) +
      panel("2", "Unsigned draft", `<form id="drf"><div class="inputs"><label class="field">Type<select name="contract_type"><option>supply</option><option>services</option><option>construction</option></select></label><label class="field">Supplier<input name="supplier" value="Binh Duong Timberworks (synthetic)"></label><label class="field">Customer<input name="customer" value="Northern Retail (synthetic)"></label><label class="field">Amount (USD)<input name="amount" type="number" value="200000"></label><label class="field">Scope<input name="scope" value="Supply verified goods under purchase order"></label><label class="field">Governing law<input name="governing_law" value="To be confirmed by counsel"></label></div>
        <div class="row"><button class="btn bridge">Generate draft</button><button class="btn ghost" type="button" id="docx">.docx</button></div></form>
        <label class="field" style="margin-top:12px">Draft<textarea id="drOut" rows="14" readonly></textarea></label><p class="note">Not legally reviewed or signed. Have qualified counsel review before use.</p>`);
    $("ct").value = state.contract; $("it").value = state.invoice;
    $("ct").oninput = (e) => { state.contract = e.target.value; };
    $("it").oninput = (e) => { state.invoice = e.target.value; };
    $("up").onchange = async (e) => {
      const f = e.target.files[0]; if (!f) return;
      const form = new FormData(); form.append("file", f);
      const d = await act(() => CB.request("/api/contracts/extract-upload", { method: "POST", body: form }), (r) => `Read locally (${r.method}). Check every amount and party.`);
      if (d) { $("ct").value = d.text; state.contract = d.text; }
    };
    $("rev").onclick = async () => {
      const d = await act(() => CB.post("/api/contracts/analyze", { text: state.contract }));
      if (d) $("ctOut").innerHTML = `<div class="kpis cards" style="margin-top:14px">${kpi("Review flags", d.risk_signal_count, d.risk_signal_count ? "warn" : "pos")}${kpi("Payment terms sum", d.extracted.payment_percentage_sum == null ? "–" : d.extracted.payment_percentage_sum + "%")}${kpi("Amounts found", d.extracted.amounts_usd.map((a) => usd(a)).join(", ") || "–")}</div>${flags(d.flags)}${(d.limitations || []).map((l) => `<p class="note">${esc(l)}</p>`).join("")}`;
    };
    $("cmp").onclick = async () => {
      const d = await act(() => CB.post("/api/contracts/reconcile", { data: { contract_text: state.contract, invoice_text: state.invoice } }));
      if (d) $("ctOut").innerHTML = `<div class="kpis cards" style="margin-top:14px">${kpi("Contract", d.contract_amounts_usd.map((a) => usd(a)).join(", "))}${kpi("Invoice", d.invoice_amounts_usd.map((a) => usd(a)).join(", "))}${kpi("Mismatch", d.amount_mismatch ? "yes" : "no", d.amount_mismatch ? "neg" : "pos")}</div>${flags(d.flags)}<p class="note">${esc(d.limitations)}</p>`;
    };
    const draftData = () => { const p = Object.fromEntries(new FormData($("drf")).entries()); p.amount = Number(p.amount); return p; };
    $("drf").onsubmit = async (e) => { e.preventDefault(); const r = await act(() => CB.post("/api/contracts/draft", { data: draftData() })); if (r) $("drOut").value = r.draft; };
    $("docx").onclick = () => act(() => CB.download("/api/contracts/draft-docx", "CashBridge_UNSIGNED_DRAFT.docx", { method: "POST", body: { data: draftData() } }));
  };

  routes.green = async () => {
    const d = await CB.get("/api/green-finance");
    page.innerHTML = head(t("grn.title"), esc(t("grn.lede"))) + engineNote() +
      d.projects.map((p) => {
        const ok = p.evidence.filter((x) => x.status !== "missing").length;
        return `<section class="panel"><h2>${esc(p.name)}</h2><p class="sub">${esc(p.activity_name)}</p><div class="grid2"><div><div class="kpis cards">${kpi("Project cost", usd(p.project_cost_usd))}${kpi("Loan requested", usd(p.requested_loan_usd))}${kpi("tCO2e / yr (illustrative)", p.illustrative_annual_impact_tco2e == null ? "–" : p.illustrative_annual_impact_tco2e)}</div>
          <table><tbody>${p.evidence.map((x) => `<tr><td>${esc(x.label)}</td><td>${x.status === "missing" ? `<span class="pill bad">missing</span>` : `<span class="pill warn">${esc(human(x.status))}</span>`}</td></tr>`).join("")}</tbody></table></div>
          ${C.donut([{ label: "provided", value: ok, color: "var(--good)" }, { label: "missing", value: p.evidence.length - ok, color: "var(--deficit)" }], { center: p.documentation_completeness_pct + "%", centerSub: "evidence" })}</div>
          <div class="row" style="margin-top:12px"><button class="btn ghost small" data-eco="${esc(p.project_id)}">Payback @ $0.12/kWh</button><button class="btn small ${p.review_status === "PENDING_HUMAN_REVIEW" ? "ghost" : "bridge"}" data-rev="${esc(p.project_id)}" ${p.review_status === "PENDING_HUMAN_REVIEW" ? "disabled" : ""}>${p.review_status === "PENDING_HUMAN_REVIEW" ? "Review requested" : "Request internal review"}</button></div><div id="eco-${esc(p.project_id)}"></div></section>`;
      }).join("");
    page.querySelectorAll("[data-eco]").forEach((b) => b.onclick = async () => {
      const x = await act(() => CB.post("/api/green-finance/economics", { project_id: b.dataset.eco, electricity_price_usd_per_kwh: 0.12, annual_opex_usd: 1500 }));
      if (x) $("eco-" + b.dataset.eco).innerHTML = `<div class="kpis cards" style="margin-top:12px">${kpi("Net savings / yr", usd(x.estimated_net_savings_usd_per_year))}${kpi("Simple payback", x.simple_payback_years == null ? "–" : x.simple_payback_years + " y")}</div><p class="note">${esc(x.limitation)}</p>`;
    });
    page.querySelectorAll("[data-rev]").forEach((b) => b.onclick = async () => { if (await act(() => CB.post("/api/green-finance/request-review", { project_id: b.dataset.rev }))) routes.green(); });
  };

  // ------------------------------------------------------------------ shared: audit & trust
  routes.trust = async () => {
    const sc = state.scorecard || (state.scorecard = await CB.get("/api/trust/scorecard", { anonymous: true }).catch(() => null));
    const sme = state.user.portal === "sme";
    const s = sme ? await refresh() : null;
    const ev = s && s.evidence;
    const decisions = {};
    if (ev) ev.audit_tail.forEach((a) => { decisions[a.decision] = (decisions[a.decision] || 0) + 1; });
    page.innerHTML = head(t("tr.title"), esc(t("tr.lede")),
      sme ? `<button class="btn ghost" id="verify">${esc(t("tr.verify"))}</button><button class="btn ghost" id="tamperLog">${esc(t("tr.tamper"))}</button>${can("demo:reset") ? `<button class="btn danger" id="reset">${esc(t("tr.reset"))}</button>` : ""}` : "") +
      (sc ? `<div class="kpis cards">${kpi("Security cases", `${sc.summary.security.passed}/${sc.summary.security.total}`, "hl")}${kpi("Agent scenarios", `${sc.summary.agent.passed}/${sc.summary.agent.total}`, "pos")}${kpi("Brier: model", sc.summary.model.brier_model)}${kpi("Brier: baseline", sc.summary.model.brier_baseline)}</div>
        <div class="grid2">${panel("Security & compliance", `make trust · ${esc(sc.generated_at)}`, `<table><tbody>${sc.security.map((c) => `<tr><td class="mono">${esc(c.id)}</td><td>${esc(c.title)}</td><td>${c.passed ? `<span class="pill ok">pass</span>` : `<span class="pill bad">fail</span>`}</td></tr>`).join("")}</tbody></table>`)}
        ${panel("Agent scenarios", esc(sc.model.caveat), `<table><tbody>${sc.agent.map((c) => `<tr><td class="mono">${esc(c.id)}</td><td>${esc(c.title)}<div class="muted small">${esc(c.got || "")}</div></td><td>${c.passed ? `<span class="pill ok">pass</span>` : `<span class="pill bad">fail</span>`}</td></tr>`).join("")}</tbody></table>`)}</div>` : "") +
      (ev ? `<div class="grid2">${panel("Audit log", `${ev.chain_ok ? "hash chain intact" : "broken at " + ev.broken_seq} · ${ev.lines_checked}`, C.stack(Object.entries(decisions).map(([k_, v]) => ({ label: human(k_), value: v, cls: k_ === "ALLOWED" || k_ === "APPROVED" ? "cb-good" : k_ === "AWAITING_APPROVAL" ? "cb-risk" : "cb-neg" }))) + `<div class="scroll"><table><tbody>${ev.audit_tail.slice().reverse().map((a) => `<tr><td>${a.seq}</td><td>${esc(a.agent)}</td><td class="small">${esc(a.tool)}</td><td class="small">${esc(a.tier)}</td><td>${statusPill(a.decision)}</td></tr>`).join("")}</tbody></table></div>`)}
        ${panel("Invoice registry", "this installation only", ev.registry_blocks.length ? `<table><tbody>${ev.registry_blocks.map((b) => `<tr><td>#${b.block_index}</td><td class="mono">${esc(String(b.block_hash).slice(0, 24))}…</td><td>${esc(b.lender_ref || "")}</td></tr>`).join("")}</tbody></table>` : `<p class="muted">–</p>`) .replace("</section>", `<h2 style="margin-top:18px">Privacy</h2><p class="sub">${esc(s.pii_inspector.note)}</p><p class="small mono">${esc(s.pii_inspector.before)}</p><p class="small mono" style="margin-top:6px">${esc(s.pii_inspector.after)}</p></section>`)}</div>` : "");
    if ($("verify")) $("verify").onclick = () => act(() => CB.post("/api/verify_chain"), (r) => r.ok ? `OK: ${r.lines_checked}` : `Broken at ${r.broken_seq}`);
    if ($("tamperLog")) $("tamperLog").onclick = () => act(() => CB.post("/api/tamper_demo"), (r) => r.ok ? "Unexpected: not detected" : `Edit detected at line ${r.broken_seq} (temporary copy)`);
    if ($("reset")) $("reset").onclick = async () => { if (confirm(t("tr.reset") + "?") && await act(() => CB.post("/api/reset_demo"), "OK")) { state.summary = null; route(); } };
  };

  // ------------------------------------------------------------------ Bank portal
  routes.inbox = async () => {
    const d = await CB.get("/api/bank/inbox");
    const items = d.items;
    const decided = items.filter((i) => ["FUNDED_MOCK", "DECLINED"].includes(i.review.status)).length;
    page.innerHTML = roleStrip() + head(t("bk.inbox"), esc(t("bk.notice"))) +
      `<div class="kpis cards">${kpi(t("bk.received"), items.length, "hl")}${kpi(t("bk.awaiting"), items.length - decided, items.length - decided ? "warn" : "")}${kpi(t("bk.decided"), decided)}</div>` +
      (items.length ? items.map((i) => `
      <a class="inbox-item" href="#case/${esc(i.pack_id)}"><div><b>${esc(i.company)}</b><div>${esc(i.product)}: ${usd2(i.amount_usd)} · ${pct(i.apr_pct, 2)} · ${esc(i.invoice_no)}</div><div class="muted small">${esc(i.pack_id)} · ${esc(i.prepared_by)} → ${esc(i.submitted_by)} · ${esc(i.lender_ref)}</div></div>${statusPill(i.review.status)}</a>`).join("") :
      `<div class="empty"><h2>${esc(t("bk.empty"))}</h2><p>${esc(t("bk.emptyD"))}</p></div>`);
    bindRoleStrip();
  };

  routes.case = async (packId) => {
    const c = await CB.get("/api/bank/cases/" + encodeURIComponent(packId));
    const product = c.product || {};
    const inv = c.invoice;
    const ap = c.autopilot;
    const review = c.review;
    const decided = ["FUNDED_MOCK", "DECLINED"].includes(review.status);
    const v = review.verification;
    const vc = v ? { ok: v.checks.filter((x) => x.ok === true).length, no: v.checks.filter((x) => x.ok === false).length, na: v.checks.filter((x) => x.ok === null).length } : null;
    const evCounts = ap ? ap.evidence_counts : null;
    const order = ["VERIFIED", "CALCULATED", "MODEL_ESTIMATE", "ASSUMPTION", "NEEDS_HUMAN", "NOT_VERIFIABLE_HERE"];
    page.innerHTML = head(c.company, `${esc(c.pack_id)} · ${esc(product.name || "")} · ${esc(c.prepared_by)} → ${esc(c.approved_by)} · ${esc(c.lender_ref)}`,
      `<button class="btn ghost" id="bpdf">${esc(t("fund.pdf"))}</button>`) + engineNote() +
      `<div class="kpis cards">${kpi(t("bk.requested"), usd2(product.amount_usd), "hl")}${kpi(t("col.apr"), pct(product.apr_pct, 2))}${kpi(t("bk.pledged"), inv.invoice_no)}${kpi(t("bk.invValue"), usd(inv.amount_usd))}${kpi(t("bk.ontime"), c.buyer_risk ? Math.round(c.buyer_risk.p_on_time * 100) + "%" : "–")}${kpi(t("bk.reviewStatus"), window.I18N.has("st." + review.status) ? t("st." + review.status) : human(review.status), decided ? "pos" : "warn")}</div>
      <div class="grid2">${panel(t("bk.verify"), esc(t("bk.verifySub")), `${vc ? C.donut([{ label: t("chk.ok"), value: vc.ok, color: "var(--good)" }, { label: t("chk.no"), value: vc.no, color: "var(--deficit)" }, { label: t("chk.na"), value: vc.na, color: "var(--risk)" }], { center: `${vc.ok}/${v.checks.length}`, centerSub: t("chk.ok") }) : ""}<div id="checks">${v ? renderChecks(v) : `<p class="muted">${esc(t("bk.notVerified"))}</p>`}</div>
        <div class="row" style="margin-top:12px"><button class="btn ${v ? "ghost" : "bridge"}" id="bverify">${esc(t(v ? "bk.verifyAgain" : "bk.runVerify"))}</button></div>`)}
      ${panel(t("bk.decision"), esc(t("bk.decisionSub")), (decided ? `<p><b>${esc(human(review.decision))}</b> · ${esc(review.reviewer)}${review.note ? ": " + esc(review.note) : ""}</p>` : `
        <form id="bdec"><label class="field">Decision<select name="decision"><option value="APPROVE_FUNDING">Approve funding (mock)</option><option value="REQUEST_INFO">Request more information</option><option value="DECLINE">Decline</option></select></label>
        <label class="field" style="margin-top:10px">Note<textarea name="note" rows="3" maxlength="500" placeholder="KYC completed offline; notice of assignment sent to the buyer."></textarea></label>
        <div class="row" style="margin-top:12px"><button class="btn bridge">${esc(t("bk.record"))}</button></div></form>`) + `<h3 class="mini">${esc(t("bk.checklist"))}</h3><ul class="list small">${c.review_checklist.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`)}</div>
      <div class="grid2">${panel(t("bk.metrics"), "", `<table><tbody>${c.locked_metrics.map((m) => `<tr><td>${esc(m.label)}</td><td class="num">${esc(metricText(m))}</td></tr>`).join("")}</tbody></table><p class="hashline" style="margin-top:10px">bundle <span class="mono">${esc(c.bundle_sha256)}</span></p>`)}
      ${panel(t("fund.letter"), "", `<div class="letter">${esc(c.letter_text)}</div>`)}</div>
      ${panel(t("bk.invoice"), `${esc(inv.buyer)} · ${esc(inv.issue_date)} → ${esc(inv.due_date)} · 3-way ${inv.three_way ? statusPill(inv.three_way.status) : ""}`, `<table><tbody>${inv.scans.map((sd) => `<tr><td>${esc(sd.doc_id)}</td><td>${statusPill(sd.status)}</td><td><span class="meter" data-tip="${Number(sd.min_confidence).toFixed(2)}"><i style="width:${Math.round(sd.min_confidence * 100)}%"></i></span></td><td class="small">${sd.matches_record ? "matches the record" : esc(sd.differences.join("; "))}</td></tr>`).join("")}</tbody></table><h3 class="mini">${esc(t("bk.forecast"))}</h3>${weeklyColumns(c.forecast.weeks)}`)}` +
      (ap ? panel(t("bk.agent"), `Run ${esc(ap.run_id)}`, (evCounts ? C.stack(order.map((s_) => ({ label: t("ev." + s_), value: evCounts[s_] || 0, cls: "evc-" + s_ }))) : "") + `<table><tbody>${ap.evidence.slice().sort((a, b) => (["NOT_VERIFIABLE_HERE", "NEEDS_HUMAN", "ASSUMPTION"].includes(b.status) ? 1 : 0) - (["NOT_VERIFIABLE_HERE", "NEEDS_HUMAN", "ASSUMPTION"].includes(a.status) ? 1 : 0)).map((e) => `<tr><td>${esc(e.claim)}<div class="muted small">${esc(e.note || "")}</div></td><td>${st(e.status)}</td></tr>`).join("")}</tbody></table>
        ${ap.recommendation ? `<div class="caution"><b>${esc(t("ap.notFix"))}</b><ul class="list">${ap.recommendation.what_would_change.map((w) => `<li>${esc(w)}</li>`).join("")}</ul></div>` : ""}`) : "") +
      panel(t("bk.notShared"), "", `<ul class="list">${c.not_shared.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`, "flat");
    $("bpdf").onclick = () => act(() => CB.download(`/api/bank/cases/${encodeURIComponent(c.pack_id)}/pdf`, `${c.pack_id}.pdf`));
    $("bverify").onclick = async () => { const r = await act(() => CB.post(`/api/bank/cases/${encodeURIComponent(c.pack_id)}/verify`)); if (r) routes.case(packId); };
    if ($("bdec")) $("bdec").onsubmit = async (e) => {
      e.preventDefault();
      const f = Object.fromEntries(new FormData(e.target).entries());
      if (await act(() => CB.post(`/api/bank/cases/${encodeURIComponent(c.pack_id)}/decision`, f), t("bk.record"))) routes.case(packId);
    };
  };
  function renderChecks(v) {
    return `<ul class="checks">${v.checks.map((c) => `<li><span class="mark ${c.ok === true ? "ok" : c.ok === false ? "no" : "na"}">${c.ok === true ? "✓" : c.ok === false ? "✗" : "?"}</span><div><b>${esc(c.check)}</b><div class="detail">${esc(c.detail || "")}</div></div></li>`).join("")}</ul>`;
  }

  // ------------------------------------------------------------------ assistant drawer (SME)
  function renderChat() {
    const history = (state.snap && state.snap.chat.history) || [];
    $("chat").innerHTML = history.map((m) => `<div class="bubble ${m.role === "user" ? "user" : ""}">${esc(m.text)}${m.citations && m.citations.length ? `<small>${m.citations.map((c) => esc(c.label || c.source_id)).join(", ")}</small>` : ""}</div>`).join("");
    $("chat").scrollTop = $("chat").scrollHeight;
  }
  $("assistantBtn").onclick = async () => { $("drawer").hidden = false; await refresh(); renderChat(); $("chatInput").focus(); };
  $("drawerClose").onclick = () => { $("drawer").hidden = true; };
  const SUGGEST = ["When do we run short?", "What is the cheapest funding?", "Which buyer is most at risk?", "What if buyers pay 15 days late?"];
  $("suggest").innerHTML = SUGGEST.map((q) => `<button type="button">${esc(q)}</button>`).join("");
  $("suggest").onclick = (e) => { const b = e.target.closest("button"); if (b) { $("chatInput").value = b.textContent; $("chatForm").requestSubmit(); } };
  $("chatForm").onsubmit = async (e) => {
    e.preventDefault();
    const text = $("chatInput").value.trim();
    if (!text) return;
    $("chatInput").value = "";
    if (await act(() => CB.post("/api/ask_cfo", { text }))) { await refresh(); renderChat(); }
  };

  // ------------------------------------------------------------------ session
  async function switchAccount() {
    try { await CB.post("/api/auth/logout"); } catch (e) { /* already gone */ }
    CB.clear();
    location.href = "/?signin=" + (state.user ? state.user.portal : "sme");
  }
  $("switchBtn").onclick = switchAccount;
  $("logoutBtn").onclick = async () => { try { await CB.post("/api/auth/logout"); } catch (e) { /* ignore */ } CB.clear(); location.href = "/"; };

  function paintChrome() {
    const u = state.user;
    window.I18N.apply();
    $("portalTag").textContent = t(u.portal === "bank" ? "app.bank" : "app.sme");
    const initials = (state.cfg && (state.cfg.demo_accounts || []).find((a) => a.user_id === u.user_id) || {}).initials || u.name.split(" ").map((x) => x[0]).join("").slice(0, 2);
    $("me").innerHTML = `<span class="av" aria-hidden="true">${esc(initials)}</span><span><b>${esc(u.name)}</b><span>${esc(t("role." + u.role))}</span></span>`;
    document.title = t(u.portal === "bank" ? "app.bank" : "app.sme") + " | CashBridge";
  }

  async function start() {
    window.I18N.langSwitch($("langSwitch"));
    window.I18N.themeButton($("themeBtn"));
    const session = CB.session();
    if (!session || !session.token) { location.href = "/?signin=sme"; return; }
    try { state.user = await CB.get("/api/auth/me"); } catch (e) { CB.clear(); location.href = "/?signin=" + ((session.user && session.user.portal) || "sme"); return; }
    state.cfg = await CB.get("/api/auth/config", { anonymous: true }).catch(() => null);
    const u = state.user;
    $("portalTag").classList.toggle("bank", u.portal === "bank");
    paintChrome();
    if (u.portal === "sme") { $("assistantBtn").hidden = false; await refresh().catch(() => null); }
    else $("caseTag").textContent = u.org;
    document.addEventListener("cb:lang", () => { paintChrome(); route(); });
    document.addEventListener("cb:theme", () => route());
    window.addEventListener("hashchange", route);
    route();
  }
  start();
})();
