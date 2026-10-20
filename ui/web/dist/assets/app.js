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
  const engineNote = () => (window.I18N.lang() === "en" ? "" : `<p class="note engine-note adv">${esc(t("ui.engineNote"))}</p>`);
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
  // Navigation is a task-focused projection of SERVER-issued permissions.
  // It is never the authorization boundary (every API still checks the session).
  const ACCOUNTANT_NAV = [["grp.decide", ["overview", "autopilot", "evidence", "cash", "funding"]], ["grp.analyse", ["analytics", "project", "contracts", "green"]], ["grp.control", ["trust"]], ["grp.system", ["settings"]]];
  const DIRECTOR_NAV = [["grp.decide", ["core", "funding", "cash"]], ["grp.analyse", ["analytics", "project", "green"]], ["grp.control", ["trust"]], ["grp.system", ["settings"]]];
  const SME_NAV = [["grp.decide", ["overview", "autopilot", "core", "cash", "evidence", "funding"]], ["grp.analyse", ["analytics", "project", "contracts", "green"]], ["grp.control", ["trust"]], ["grp.system", ["settings"]]];
  function navigationForUser() {
    if (!state.user) return [];
    if (state.user.portal === "bank") return BANK_NAV;
    if (can("sme:approve") && !can("sme:prepare")) return DIRECTOR_NAV;
    if (can("sme:prepare") && !can("sme:approve")) return ACCOUNTANT_NAV;
    return SME_NAV;
  }
  const BANK_NAV = [["grp.review", ["inbox", "trust"]], ["grp.system", ["settings"]]];
  function renderNav(current) {
    const groups = navigationForUser();
    const pending = state.snap && state.snap.meta.case_state === "AWAITING_APPROVAL" && can("sme:approve") ? 1 : 0;
    const alerts = state.snap && can("sme:approve") ? (state.snap.meta.director_alerts_open || 0) : 0;
    $("side").innerHTML = groups.map(([title, items]) => `<h4>${esc(t(title))}</h4>` + items.map((id) =>
      `<a href="#${id}" ${current === id ? 'aria-current="page"' : ""}>${esc(t("nav." + id))}${id === "funding" && pending ? `<span class="count" data-tip="${esc(t("next.approve"))}">1</span>` : ""}${id === "core" && alerts ? `<span class="count" data-tip="${esc(t("core.inbox"))}">${alerts}</span>` : ""}</a>`).join("")).join("")
      + `<h4>${esc(t("grp.account"))}</h4><a href="/?stay=1">${esc(t("nav.landing"))}</a>`
      + `<button type="button" class="side-btn" id="sideSwitch">${esc(t("app.switch"))}</button><button type="button" class="side-btn" id="sideLogout">${esc(t("app.logout"))}</button>`
      + `<div class="side-user">${userCard()}</div>`;
    $("sideSwitch").onclick = switchAccount;
    $("sideLogout").onclick = signOut;
  }
  function userCard() {
    const u = state.user;
    const initials = (state.cfg && (state.cfg.demo_accounts || []).find((a) => a.user_id === u.user_id) || {}).initials || u.name.split(" ").map((x) => x[0]).join("").slice(0, 2);
    return `<span class="av" aria-hidden="true">${esc(initials)}</span><span><b>${esc(u.name)}</b><span>${esc(t("role." + u.role))}</span></span>`;
  }

  const routes = {};
  async function route() {
    // Role-based home: the lender reviews cases, the Director decides, the accountant works the queue.
    const home = state.user.portal === "bank" ? "inbox" : can("sme:approve") ? "core" : "overview";
    const hash = (location.hash || "").slice(1) || home;
    const [name, arg] = hash.split("/");
    const allowed = state.user.portal === "bank" ? ["inbox", "case", "trust", "settings"] : navigationForUser().flatMap((group) => group[1]);
    const target = allowed.includes(name) ? name : home;
    state.current = target === name ? hash : target;
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
      location.hash = s.user.portal === "bank" ? "inbox" : s.user.permissions.includes("sme:approve") ? "core" : "overview";
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

    // Work queue for this role: each tile is an action the signed-in person can actually take.
    const director = can("sme:approve");
    const tile = (label, n, href, icon, foot) => `<a class="work-tile ${n ? "due" : ""}" href="${href}"><span class="wt-l">${esc(label)}</span><b>${n}</b><span class="wt-i" aria-hidden="true">${icon}</span>${foot ? `<small>${esc(foot)}</small>` : ""}</a>`;
    const I = { inbox: "▤", bank: "⌂", check: "✓", alert: "!", model: "◇", pack: "▣" };
    const exceptions = s.verification.filter((v) => v.status !== "ELIGIBLE").length + s.scans.filter((x) => x.status !== "READ").length;
    const unmatched = s.reconciliation.rows.filter((r) => r.status === "NEEDS_HUMAN").length;
    const tiles = director ? [
      tile(t("wq.approve"), stateNow === "AWAITING_APPROVAL" ? 1 : 0, "#funding", I.pack, t("wq.approveF")),
      tile(t("wq.alerts"), s.meta.director_alerts_open || 0, "#core/decide", I.alert, t("wq.alertsF")),
      tile(t("wq.model"), s.meta.model_update_pending ? 1 : 0, "#core/evidence", I.model, t("wq.modelF")),
      tile(t("wq.lender"), ["FUNDED", "REJECTED"].includes(stateNow) ? 1 : 0, "#funding", I.bank, t("wq.lenderF")),
    ] : [
      tile(t("wq.exceptions"), exceptions, "#evidence", I.check, t("wq.exceptionsF")),
      tile(t("wq.unmatched"), unmatched, "#evidence", I.bank, t("wq.unmatchedF")),
      tile(t("wq.held"), s.alerts.length, "#evidence", I.inbox, t("wq.heldF")),
      tile(t("wq.prepare"), ["INVOICE_VERIFIED", "OPTIONS_RANKED"].includes(stateNow) || s.pack.status === "REJECTED_BY_DIRECTOR" ? 1 : 0, "#autopilot", I.pack, t("wq.prepareF")),
    ];
    page.innerHTML = roleStrip() + head(t("ov.title"), esc(t("ov.lede"))) + `<div class="work-queue">${tiles.join("")}</div>` +
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
        <h3 class="mini">${esc(t("ap.conditions"))}</h3><ul class="list">${rec.conditions.map((c) => `<li>${esc(c)}</li>`).join("")}</ul>
        ${rec.core_plan ? `<div class="row" style="margin-top:12px"><a class="btn ghost" href="#core">${esc(t("core.open"))}</a></div>` : ""}</section>`;
    }
    html += `<section class="panel"><h2>${esc(t("ap.did"))}</h2><p class="sub">${esc(t("ap.didSub"))}</p><ol class="trace">${r.steps.map((s) => `
      <li class="${esc(s.status)}"><span class="n">${s.n}</span><div><span class="tool">${esc(s.tool)}</span><h3>${esc(s.result)}</h3><p class="why">${esc(s.why)}</p>
      ${s.evidence.length ? `<div class="evs">${s.evidence.map((id) => `<button type="button" class="ev-link" data-ev="${esc(id)}">${esc(id)}</button>`).join("")}</div>` : ""}</div></li>`).join("")}</ol>
      ${r.refused_proposals.length ? `<div class="caution"><b>${esc(t("ap.refused"))}</b><ul class="list">${r.refused_proposals.map((x) => `<li>${esc(x.proposed)}: ${esc(x.reason)}</li>`).join("")}</ul></div>` : ""}
      ${r.goal_injection_detected ? `<p class="note">${esc(t("ap.injected"))}</p>` : ""}
      <h3 class="mini">${esc(t("ap.guardrails"))}</h3><ul class="list small">${r.guardrails.map((g) => `<li>${esc(g)}</li>`).join("")}</ul></section>
      <section class="panel adv"><h2>${esc(t("ap.register"))}</h2><p class="sub">${esc(t("ap.registerSub", { n: r.evidence.length }))}</p>
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


  // ------------------------------------------------------------------ SME: Intelligence Core
  const pp = (x) => (x == null ? "–" : Math.round(x * 100) + "%");
  // Decision trace: five steps rebuilt from the run that produced the plan on screen (not an illustration).
  // Feasibility certificate: which limit stops the goal, shown only when the goal is not reached.
  function feasBlock(plan) {
    const f = plan.feasibility;
    if (!f || f.verdict === "REACHABLE") return "";
    return `<h4 class="mini">${esc(t("tr2.feas", { g: pp(f.goal_probability) }))}</h4>
      <p class="small">${esc(t("tr2.feas.v." + f.verdict, { n: usd(f.cash_needed_week1_usd), c: usd(f.over_borrowing_cap_usd), e: usd(f.eligible_sources_usd) }))}</p>
      <ul class="list small">${f.binding.map((b) => `<li>${esc(b.text)}</li>`).join("")}</ul>
      <div class="scroll"><table class="small"><thead><tr><th>${esc(t("tr2.feas.probe"))}</th><th>${esc(t("tr2.feas.p"))}</th></tr></thead><tbody>
      <tr><td>${esc(t("tr2.feas.now"))}</td><td><b>${pp(f.best_allowed_p_goal)}</b></td></tr>
      ${f.probes.map((p) => `<tr><td>${esc(p.change)}<div class="muted">${esc(p.limit)}</div></td><td>${pp(p.p_goal)}</td></tr>`).join("")}</tbody></table></div>
      <p class="note">${esc(t("tr2.feas.note"))}</p>
      <h4 class="mini">${esc(t("tr2.feas.out"))}</h4><ul class="list small">${f.outside_financing.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>`;
  }
  function decisionTrace(plan, tw, snap, open) {
    const st_ = plan.state, ch = plan.chosen, risk = st_.risk_without_action, base = st_.base_case, cons = st_.considered || {};
    const ver = snap ? snap.verification : [];
    const ok = ver.filter((v) => v.status === "ELIGIBLE").length;
    const excluded = Object.entries(st_.receivables.excluded || {});
    const alts = plan.ranked.filter((r) => r.plan_id !== ch.plan_id).slice(0, 2);
    const caseState = snap ? snap.meta.case_state : "";
    const step = (n, key, status, summary, body) => `<li class="ts ${status}"><details><summary><span class="ts-n">${n}</span><span class="ts-t"><b>${esc(t("tr2." + key))}</b><span>${summary}</span></span><span class="pill ${status === "done" ? "ok" : status === "wait" ? "warn" : "bad"}">${esc(t("tr2.st." + status))}</span></summary><div class="ts-b">${body}</div></details></li>`;
    const events = tw && tw.applied.length ? `<li>${esc(t("tr2.events"))}: ${tw.applied.map((k) => esc(t("core.ev." + k))).join(", ")}</li>` : "";
    return panel(t("tr2.title"), esc(t("tr2.sub")), `<ol class="trace2">
      ${step(1, "risk", base.first_negative_week ? "attention" : "done",
        base.first_negative_week ? esc(t("tr2.risk.s", { w: base.first_negative_week, a: usd(base.shortfall_usd), p: pp(risk.p_no_negative_week) })) : esc(t("tr2.risk.none")),
        `<ul class="list small"><li>${esc(t("tr2.risk.b1", { a: usd(base.min_closing_usd) }))}</li><li>${esc(t("tr2.risk.b2", { p: pp(risk.p_no_negative_week), n: plan.world_model.paths }))}</li>${events}</ul>`)}
      ${step(2, "evidence", excluded.length ? "attention" : "done", esc(t("tr2.ev.s", { ok, n: ver.length || ok, x: excluded.length })),
        `<ul class="list small"><li>${esc(t("tr2.ev.b1", { n: st_.receivables.pledgeable.length }))}</li>${excluded.slice(0, 4).map(([k, v]) => `<li><span class="mono">${esc(k)}</span>: ${esc(v)}</li>`).join("")}<li>${esc(t("tr2.ev.b2", { n: st_.confirmed_orders.count }))}</li></ul><a class="btn ghost small" href="#evidence">${esc(t("tr2.open"))}</a>`)}
      ${step(3, "scenarios", "done", esc(t("tr2.sc.s", { n: cons.plans_scored || plan.ranked.length, r: cons.plans_refused || 0, p: plan.world_model.paths })),
        `<ul class="list small"><li>${esc(t("tr2.sc.b1", { m: cons.plans_meeting_goal || 0, g: pp(plan.goal.min_probability) }))}</li><li>${esc(t("tr2.sc.b2", { w: (cons.draw_weeks || []).join(", ") }))}</li><li>${esc(t("tr2.sc.b3"))} <span class="mono">${esc(plan.world_model.version)}</span></li></ul>`)}
      ${step(4, "rec", plan.status === "GOAL_MET" ? "done" : "attention", esc(ch.description) + ` · ${pp(ch.p_goal)} · ${usd(ch.cost_usd)}`,
        `<ul class="list small">${ch.why.slice(0, 2).map((w) => `<li>${esc(w)}</li>`).join("")}${ch.shortfall_cvar95_usd != null && risk.shortfall_cvar95_usd != null ? `<li>${esc(t("tr2.cvar", { a: usd(ch.shortfall_cvar95_usd), b: usd(risk.shortfall_cvar95_usd) }))}</li>` : ""}</ul>${feasBlock(plan)}<h4 class="mini">${esc(t("tr2.alts"))}</h4><ul class="list small">${alts.map((r) => `<li>${esc(r.description)}: ${esc(r.verdict || "")}</li>`).join("")}</ul><p class="note">${esc(t("core.dc.notCredit"))}</p>`)}
      ${step(5, "approval", open.length ? "wait" : caseState === "AWAITING_APPROVAL" ? "wait" : "done",
        open.length ? esc(t("tr2.ap.inbox", { n: open.length })) : caseState === "AWAITING_APPROVAL" ? esc(t("tr2.ap.pack")) : esc(t("tr2.ap.none")),
        `<ul class="list small"><li>${esc(t("tr2.ap.b1"))}</li><li>${esc(t("tr2.ap.b2"))}</li></ul>${caseState === "AWAITING_APPROVAL" && can("sme:approve") ? `<a class="btn bridge small" href="#funding">${esc(t("btn.openFunding"))}</a>` : ""}`)}
    </ol>`);
  }

  routes.core = async (arg, fresh) => {
    if (["decide", "analysis", "evidence"].includes(arg)) state.coreTab = arg;
    const tab = state.coreTab || "decide";
    const snap = await refresh().catch(() => state.snap);
    let data = fresh || await CB.get("/api/intelligence");
    if (!data.plan && !fresh) data = await CB.post("/api/intelligence/plan", {}).catch(() => data);  // the decision view needs a plan
    const plan = data.plan;
    const L = data.learning;
    const tw = data.twin;
    const goal = plan ? plan.goal : { id: "keep_cash_positive", min_probability: 0.9 };
    const tabs = `<div class="tabs" role="tablist">${["decide", "analysis", "evidence"].map((k) =>
      `<a role="tab" href="#core/${k}" aria-selected="${tab === k}" class="${tab === k ? "on" : ""} ${k === "decide" ? "" : "adv"}">${esc(t("core.tab." + k))}</a>`).join("")}</div>`;
    let html = head(t(tab === "decide" ? "core.dc.title" : "nav.core"), esc(t(tab === "decide" ? "core.dc.lede" : "core.lede")),
      `<button class="btn bridge" id="coreRun">${esc(t("core.run"))}</button>`) + tabs;

    // ---- shared pieces
    const alertCard = (a, open) => `<div class="alert-card ${open ? "open" : ""}"><div class="row-between"><b>${a.priority ? `<span class="pill ${a.priority.level === "HIGH" ? "bad" : a.priority.level === "MEDIUM" ? "warn" : ""}">${esc(a.priority.level)}</span> ` : ""}${esc(a.label)}</b>${statusPill(a.status === "OPEN" ? "AWAITING_APPROVAL" : a.status === "ACCEPTED" ? "APPROVED" : a.status === "HANDLED" ? "ok" : "ALLOWED")}</div>
      <p class="small muted">${esc(a.id)} · ${esc(a.source)} · ${esc(t("lbl.week", { w: a.base_case.first_negative_week_before || "–" }))} → ${esc(t("lbl.week", { w: a.base_case.first_negative_week_after || "–" }))} · ${esc(t("core.inForce"))}: ${pp(a.plan_in_force.p_goal_before)} → ${pp(a.plan_in_force.p_goal_after)}${a.priority && a.priority.deadline && a.status === "OPEN" ? ` · ${esc(t("core.deadline"))} ${esc(a.priority.deadline)}` : ""}</p>
      ${a.reasons.length && open ? `<ul class="list small">${a.reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}
      ${open ? `<p class="small"><b>${esc(a.new_plan.description)}</b> · ${pp(a.new_plan.p_goal)} · ${usd(a.new_plan.cost_usd)}</p>` : ""}
      ${open && can("sme:approve") ? `<div class="row"><button class="btn bridge small" data-alert="${esc(a.id)}" data-accept="1">${esc(t("core.accept"))}</button><button class="btn ghost small" data-alert="${esc(a.id)}" data-accept="0">${esc(t("core.keep"))}</button></div>` : ""}
      ${a.decided_by ? `<p class="small muted">${esc(a.decided_by)}</p>` : ""}</div>`;
    const eventButtons = tw ? `<div class="row">${tw.catalogue.map((e) => `<button class="btn ghost small" data-event="${esc(e.kind)}" ${tw.applied.includes(e.kind) ? "disabled" : ""} data-tip="${esc(e.label)}">${esc(t("core.ev." + e.kind))}</button>`).join("")}
        <button class="btn ghost small" id="evReset">${esc(t("core.evReset"))}</button></div>` : "";

    if (!plan) {
      html += `<div class="empty"><h2>${esc(t("core.empty"))}</h2></div>`;
    } else if (tab === "decide") {
      const ch = plan.chosen, fx = plan.fixed_workflow_plan, risk = plan.state.risk_without_action;
      const open = tw ? tw.inbox.filter((a) => a.status === "OPEN") : [];
      const decided = tw ? tw.inbox.filter((a) => a.status !== "OPEN") : [];
      const headline = open.length ? t("core.dc.need", { n: open.length }) : t("core.dc.none");
      const actions = ch.actions.map((a) => `<li><b>${esc(a.type === "factor" ? "Factoring " + a.ref : a.type === "loan" ? "Bridge loan" : "Deposit " + a.ref)}</b>
        <span>${a.type === "deposit_cut" ? esc(a.new_pct + "%") : usd2(a.advance_usd != null ? a.advance_usd : a.amount_usd)}</span>
        <span class="muted">${esc(t("lbl.week", { w: a.week }))}</span>${a.type === "deposit_cut" ? `<span class="pill warn">supplier</span>` : `<span class="pill">OTP</span>`}</li>`).join("");
      const weeks = risk.p_negative_by_week.map((_, i) => "W" + (i + 1));
      // Focus on the recommended plan; "no action" is a grey dashed reference; the single advance is a muted comparison.
      const simple = prefGet("view") === "simple";
      const noneV = risk.p_negative_by_week.map((x) => x * 100), planV = ch.p_negative_by_week.map((x) => x * 100);
      const series = [{ name: t("core.s.none"), values: noneV, color: "var(--ink-3)", dash: "5 4", muted: true }];
      if (fx && !simple) series.push({ name: t("core.s.fixed"), values: fx.p_negative_by_week.map((x) => x * 100), color: "var(--s2)", muted: true });
      series.push({ name: t("core.s.plan"), values: planV, color: "var(--s1)", width: 3 });
      const ref = fx && !simple ? fx.p_negative_by_week.map((x) => x * 100) : noneV;
      const peak = ref.indexOf(Math.max(...ref));
      const riskOpts = { fmt: (v) => v.toFixed(0) + "%", yfmt: (v) => Math.round(v) + "%", label: t("core.risk"), endLabels: true, dots: "ends",
        annotate: { index: peak, text: t("core.peak", { w: peak + 1, a: Math.round(ref[peak]) + "%", b: Math.round(planV[peak]) + "%" }) },
        tipExtra: (i) => t("core.delta", { d: (planV[i] - noneV[i]).toFixed(0) }) };
      html = roleStrip() + html;
      const sim = `<span class="pill sim">${esc(t("lbl.sim"))}</span> `;
      html += `<div class="decision ${open.length ? "warn" : ""}"><div><h2>${esc(headline)}</h2><p>${esc(t("core.dc.sub"))}</p></div></div>` + engineNote() +
        `<div class="kpis cards">
        ${kpi(t("core.k.none"), pp(risk.p_no_negative_week), "neg", sim + esc(t("core.k.foot")))}
        ${kpi(t("core.k.fixed"), fx ? pp(fx.p_goal) : "–", "warn", sim + (fx ? esc(fx.description) : ""))}
        ${kpi(t("core.k.plan"), pp(ch.p_goal), "hl", sim + esc(t("core.status." + plan.status)))}
        ${kpi(t("core.k.cost"), usd(ch.cost_usd), "", `${ch.packs} ${esc(t("col.packs").toLowerCase())}`)}
      </div>
      ${decisionTrace(plan, tw, snap, open)}
      <div class="dash">
        <div class="span2">${panel(t("core.inbox"), esc(t("core.dc.inboxSub")),
          (open.length ? open.map((a) => alertCard(a, true)).join("") : `<p class="muted">${esc(t("core.dc.empty"))}</p>`) +
          (decided.length ? `<details class="more"><summary>${esc(t("core.dc.decided", { n: decided.length }))}</summary>${decided.map((a) => alertCard(a, false)).join("")}</details>` : "") +
          (tw && tw.digest.length ? `<details class="more"><summary>${esc(t("core.dc.digest", { n: tw.digest.length }))}</summary>${tw.digest.map((a) => alertCard(a, false)).join("")}</details>` : "") +
          `<h3 class="mini">${esc(t("core.dc.simulate"))}</h3>${eventButtons}<p class="small muted" style="margin-top:8px">${tw ? esc(t("core.evCount", { e: tw.counts.events, a: tw.counts.director_alerts })) : ""}</p>`)}</div>
        ${panel(t("core.chosen"), esc(t("core.status." + plan.status)), `<ul class="plan-actions">${actions}</ul><ul class="list small">${ch.why.slice(0, 2).map((w) => `<li>${esc(w)}</li>`).join("")}</ul>
          <div class="row"><a class="btn ghost small" href="#core/analysis">${esc(t("core.dc.compare"))}</a><a class="btn ghost small" href="#core/evidence">${esc(t("core.dc.evidence"))}</a></div><p class="note">${esc(t("core.dc.notCredit"))}</p>`)}
        <div class="span3">${panel(t("core.risk"), esc(t("core.riskSub")), C.lines(weeks, series, riskOpts))}</div>
      </div>`;
    } else if (tab === "analysis") {
      const ch = plan.chosen, risk = plan.state.risk_without_action;
      const weeks = risk.p_negative_by_week.map((_, i) => "W" + (i + 1));
      const goalSel = `<label class="field inline">${esc(t("core.goal"))}<select id="coreGoal">${["keep_cash_positive", "keep_above_buffer"].map((g) =>
        `<option value="${g}" ${goal.id === g ? "selected" : ""}>${esc(t("core.goal." + g))}</option>`).join("")}</select></label>
        <label class="field inline">${esc(t("core.prob"))}<select id="coreProb">${[0.8, 0.85, 0.9, 0.95].map((p) =>
        `<option value="${p}" ${Math.abs(goal.min_probability - p) < 1e-9 ? "selected" : ""}>${pp(p)} ${esc(t("core.ofPaths"))}</option>`).join("")}</select></label>
        <a class="btn ghost small" href="#cash">${esc(t("core.whatif"))}</a>`;
      const band = C.lines(weeks, [
        { name: t("core.s.noneP10"), values: risk.closing_p10_by_week, color: "var(--ink-3)", dash: "5 4", muted: true },
        { name: t("core.s.planP10"), values: ch.closing_p10_by_week, color: "var(--s1)", width: 3 },
        { name: t("core.s.planP50"), values: ch.closing_p50_by_week, color: "var(--s2)", muted: true },
      ], { fmt: (v) => usd(v), label: t("core.band"), endLabels: true, dots: "ends" });
      const cons = plan.state.considered;
      const row = (r) => `<tr class="${r.plan_id === ch.plan_id ? "chosen" : ""}"><td>${esc(r.description)}${r.verdict ? `<div class="muted small">${esc(r.verdict)}</div>` : ""}</td><td>${C.hbars([{ label: "", value: r.p_goal * 100, display: pp(r.p_goal), cls: r.p_goal >= goal.min_probability ? "cb-good" : "cb-muted" }])}</td><td>${usd(r.cost_usd)}</td><td>${r.packs}</td></tr>`;
      const tableHead = `<thead><tr><th>${esc(t("col.plan"))}</th><th>${esc(t("col.pgoal"))}</th><th>${esc(t("col.ecost"))}</th><th>${esc(t("col.packs"))}</th></tr></thead>`;
      html += `<form class="panel goal-bar" id="coreForm">${goalSel}</form>` +
        panel(t("core.ranked"), esc(t("core.rankedSub")) + (cons ? ` · <b>${esc(t("core.considered", { n: cons.plans_scored, r: cons.plans_refused, m: cons.plans_meeting_goal }))}</b>` : ""),
          `<div class="scroll"><table>${tableHead}<tbody>${plan.ranked.slice(0, 3).map(row).join("")}</tbody></table></div>
          ${plan.ranked.length > 3 ? `<details class="more"><summary>${esc(t("core.allPlans", { n: plan.ranked.length }))}</summary><div class="scroll"><table>${tableHead}<tbody>${plan.ranked.slice(3).map(row).join("")}</tbody></table></div></details>` : ""}`) +
        `<div class="dash"><div class="span2">${panel(t("core.band"), esc(t("core.bandSub")), band)}</div>
        ${panel(t("core.chosen"), esc(ch.description), `<ul class="list small">${ch.why.map((w) => `<li>${esc(w)}</li>`).join("")}${ch.incumbent && ch.incumbent.kept && ch.incumbent.instead_of ? `<li>${esc(ch.incumbent.reason)}</li>` : ""}</ul><p class="note">${esc(t("core.packNote"))}</p>`)}
        <div class="span3">${panel(t("core.constraints"), "", `<ul class="list small">
          <li>${esc(plan.state.constraints.allowed_actions.join(", "))}</li>
          <li>max ${plan.state.constraints.max_packs_per_plan} ${esc(t("col.packs").toLowerCase())}</li>
          <li>cap ${usd(plan.state.constraints.over_borrowing_cap_usd)}</li>
          <li>${esc(plan.state.constraints.every_pack_needs)}</li></ul>` +
          (plan.rejected.length ? `<h3 class="mini">${esc(t("core.rejected"))}</h3><ul class="list small">${plan.rejected.slice(0, 5).map((r) => `<li>${esc(r.description)}: ${esc(r.violations.join("; "))}</li>`).join("")}</ul>` : "") +
          (tw ? `<p class="note">${esc(tw.policy)}</p>` : ""))}</div></div>`;
    } else {
      html += panel(t("core.wm"), `${plan.world_model.paths} paths · seed ${plan.world_model.seed}`,
        `<p><b class="mono">${esc(plan.world_model.version)}</b> <span class="pill">${esc(plan.world_model.label)}</span> · ${esc(t("core.memory"))}: ${L.memory_chain_ok ? "hash chain intact" : "BROKEN"}</p>`);
      if (plan.similar_cases.length) html += panel(t("core.memory"), esc(t("core.memorySub")), `<div class="scroll"><table><tbody>${plan.similar_cases.map((m) =>
        `<tr><td class="mono small">${esc(m.run_id)}<div><span class="pill">${esc(m.source)}</span></div></td><td>${esc(m.plan)}<div class="muted small">${esc(m.lesson)}</div></td><td>${pp(m.predicted_p_goal)}</td><td>${m.goal_met ? `<span class="pill ok">${esc(t("core.met"))}</span>` : `<span class="pill bad">${esc(t("core.missed"))}</span><div class="muted small">${esc(m.primary_cause.replaceAll("_", " "))}</div>`}</td></tr>`).join("")}</tbody></table></div>`);
      // learning panel
      const reg = L.registry, pend = reg.pending;
      const shifts = Object.entries(reg.active.buyer_logit_shift || {}).map(([b, v]) => `${b} ${v > 0 ? "+" : ""}${v}`).join(", ") || "none";
      const learnBody = `<div class="grid2"><div><h3 class="mini">${esc(t("core.active"))}</h3><p><b class="mono">${esc(reg.active_version)}</b> <span class="pill">${esc(reg.active.label)}</span></p>
          <p class="small muted">buyer shifts: ${esc(shifts)} · order shipment scale ${esc(reg.active.ship_scale)} · slowdown ${pp(reg.active.slowdown_prob)}</p>
          <p class="small">${esc(t("core.episodes"))}: <b>${L.episodes}</b> (${L.episodes_with_miss} ${esc(t("core.missed"))})</p></div>
        <div><h3 class="mini">${esc(t("core.pending"))}</h3>${pend ? `<p><b class="mono">${esc(pend.version)}</b> · ${esc(pend.proposed_by)}</p>
          <p class="small">${esc(t("core.gate"))}: ${esc(pend.metrics.reason)} (${esc(String(pend.metrics.loglik_current))} → ${esc(String(pend.metrics.loglik_candidate))}, ${esc(String(pend.metrics.held_out_wins))}/${esc(String(pend.metrics.episodes))})</p>
          <p class="small muted">buyer shifts: ${esc(Object.entries(pend.params.buyer_logit_shift).map(([b, v]) => `${b} ${v > 0 ? "+" : ""}${v}`).join(", "))} · ship scale ${esc(pend.params.ship_scale)}</p>
          ${can("sme:approve") ? `<div class="row"><button class="btn bridge" id="coreApprove" ${pend.metrics.accepted ? "" : "disabled"}>${esc(t("core.approve"))}</button><button class="btn ghost" id="coreReject">${esc(t("core.reject"))}</button></div>` : ""}`
          : `<p class="muted">${esc(t("core.noPending"))}</p>`}</div></div>
        <div class="row" style="margin-top:10px">${plan ? `<button class="btn ghost" id="coreSim">${esc(t("core.simulate"))}</button>` : ""}${can("sme:prepare") ? `<button class="btn ghost" id="corePropose">${esc(t("core.propose"))}</button>` : ""}</div>
        <div id="coreOutcome"></div>
        <h3 class="mini">${esc(t("core.history"))}</h3><div class="scroll"><table><tbody>${reg.history.slice().reverse().map((h) => `<tr><td class="mono small">${esc(h.version)}</td><td>${esc(h.label)}</td><td class="small">${esc(h.approved_by || h.rejected_by || "")}</td><td class="small muted">${esc(h.ts || "")}</td></tr>`).join("")}</tbody></table></div>
        ${L.recent.length ? `<h3 class="mini">${esc(t("core.episodes"))}</h3><div class="scroll"><table><tbody>${L.recent.map((e) => `<tr><td class="mono small">${esc(e.run_id)} <span class="pill">${esc(e.source)}</span></td><td class="small">${esc(e.plan)}</td><td>${pp(e.predicted_p_goal)}</td><td>${e.goal_met ? `<span class="pill ok">${esc(t("core.met"))}</span>` : `<span class="pill bad">${esc(t("core.missed"))}</span>`}</td><td class="small muted">${esc(e.cause)}</td></tr>`).join("")}</tbody></table></div>` : ""}`;
      html += panel(t("core.learn"), esc(t("core.learnSub")), learnBody);
      const b = data.benchmark;
      if (b) {
        const names = ["fixed_workflow", "planner_memory", "planner_learning"];
        const bars = C.hbars(names.map((n, i) => ({ label: b.summary[n].label, value: b.summary[n].goal_success_mean * 100, display: (b.summary[n].goal_success_mean * 100).toFixed(1) + "%", cls: i === 2 ? "cb-accent" : "cb-muted", strong: i === 2 })));
        html += panel(t("core.bench"), esc(t("core.benchSub")) + ` · ${esc(b.generated_at)}`, `<h3 class="mini">${esc(t("core.b.success"))}</h3>${bars}
          <div class="scroll"><table><thead><tr><th></th>${names.map((n) => `<th>${esc(b.summary[n].label)}</th>`).join("")}</tr></thead><tbody>
          <tr><td>${esc(t("core.k.cost"))}</td>${names.map((n) => `<td>${usd(b.summary[n].expected_cost_mean_usd)}</td>`).join("")}</tr>
          ${b.summary[names[0]].shortfall_cvar95_mean_usd != null ? `<tr><td>${esc(t("core.b.cvar"))}</td>${names.map((n) => `<td>${usd(b.summary[n].shortfall_cvar95_mean_usd)}</td>`).join("")}</tr>` : ""}
          <tr><td>${esc(t("core.b.overconf"))}</td>${names.map((n) => `<td>${b.summary[n].overconfidence_pp > 0 ? "+" : ""}${b.summary[n].overconfidence_pp} pp</td>`).join("")}</tr>
          <tr><td>${esc(t("core.b.viol"))}</td>${names.map((n) => `<td>${b.summary[n].policy_violations}</td>`).join("")}</tr>
          <tr><td>${esc(t("core.b.same"))}</td>${names.map((n) => `<td>${b.summary[n].same_plan_pct != null ? b.summary[n].same_plan_pct + "%" : "–"}</td>`).join("")}</tr>
          <tr><td>${esc(t("core.b.stable"))}</td>${names.map((n) => `<td>${b.summary[n].stability_pct}%</td>`).join("")}</tr>
          ${b.summary.planner_learning.same_plan_without_incumbent_pct != null ? `<tr><td>${esc(t("abl.noIncumbent"))}</td>${names.map((n) => `<td>${b.summary[n].same_plan_without_incumbent_pct != null ? b.summary[n].same_plan_without_incumbent_pct + "%" : "–"}</td>`).join("")}</tr>
          <tr><td>${esc(t("abl.ownWorld"))}</td>${names.map((n) => `<td>${b.summary[n].overconfidence_own_world_pp != null ? (b.summary[n].overconfidence_own_world_pp > 0 ? "+" : "") + b.summary[n].overconfidence_own_world_pp + " pp" : "–"}</td>`).join("")}</tr>` : ""}</tbody></table></div>
          ${b.ceiling_within_cap ? `<p class="small">${esc(t("abl.ceiling", { m: pp(b.ceiling_within_cap.mean), k: b.ceiling_within_cap.cases_reaching_90pct, n: b.protocol.test_cases }))}</p>` : ""}`);
        if (b.ops) {
          const o = b.ops, cb = o.cashbridge, ev = o.baseline_every_event, th = o.baseline_amount_threshold;
          html += panel(t("ops.title"), esc(t("ops.sub", { r: o.raw_events, c: o.cases })),
            C.hbars([{ label: t("ops.every"), value: ev.director_alerts, display: String(ev.director_alerts), cls: "cb-muted" },
                     { label: t("ops.threshold"), value: th.director_alerts, display: String(th.director_alerts), cls: "cb-muted" },
                     { label: "CashBridge", value: cb.director_alerts, display: String(cb.director_alerts), cls: "cb-accent", strong: true }]) +
            `<div class="scroll"><table><thead><tr><th></th><th>${esc(t("ops.every"))}</th><th>${esc(t("ops.threshold"))}</th><th>CashBridge</th></tr></thead><tbody>
            <tr><td>${esc(t("ops.false"))}</td><td>${ev.false_alerts}</td><td>${th.false_alerts}</td><td>${cb.false_alerts}</td></tr>
            <tr><td>${esc(t("ops.missed"))}</td><td>${ev.missed}</td><td>${th.missed}</td><td>${cb.missed}</td></tr>
            <tr><td>${esc(t("ops.precision"))}</td><td>${ev.precision_pct}%</td><td>${th.precision_pct}%</td><td>${cb.precision_pct}%</td></tr></tbody></table></div>
            <p class="small">${esc(t("ops.auto", { n: o.completed_without_a_person, c: o.cases, v: o.safety_violations }))}</p>
            ${o.ablation ? `<h3 class="mini">${esc(t("abl.title"))}</h3><div class="scroll"><table><thead><tr><th></th><th>${esc(t("ops.notif"))}</th><th>${esc(t("ops.false"))}</th><th>${esc(t("ops.missed"))}</th></tr></thead><tbody>
            <tr><td><b>CashBridge</b></td><td>${cb.director_alerts}</td><td>${cb.false_alerts}</td><td>${cb.missed}</td></tr>
            <tr><td>${esc(t("abl.noPlanCheck"))}</td><td>${o.ablation.without_plan_in_force_check.director_alerts}</td><td>${o.ablation.without_plan_in_force_check.false_alerts}</td><td>${o.ablation.without_plan_in_force_check.missed}</td></tr>
            <tr><td>${esc(t("abl.noGroup"))}</td><td>${o.ablation.without_grouping.director_alerts}</td><td>${o.ablation.without_grouping.false_alerts}</td><td>${o.ablation.without_grouping.missed}</td></tr></tbody></table></div>` : ""}
            <p class="note">${esc(t("ops.note"))}</p>`);
        }
      }
    }
    page.innerHTML = html;
    bindRoleStrip();
    const run = async () => {
      $("coreRun").disabled = true;
      const out = await act(() => CB.post("/api/intelligence/plan", $("coreGoal") ? { goal: $("coreGoal").value, min_probability: Number($("coreProb").value) } : { goal: goal.id, min_probability: goal.min_probability }));
      $("coreRun").disabled = false;
      if (out) routes.core(null, out);
    };
    $("coreRun").onclick = run;
    if ($("coreForm")) $("coreForm").onsubmit = (e) => { e.preventDefault(); run(); };
    if ($("coreSim")) $("coreSim").onclick = async () => {
      const r = await act(() => CB.post("/api/intelligence/simulate-outcome"));
      if (r) {
        const o = r.outcome;
        $("coreOutcome").innerHTML = `<div class="caution"><b>${esc(t("core.outcome"))} ${esc(r.run_id)}: ${o.goal_met ? esc(t("core.met")) : esc(t("core.missed"))}</b>
          <p>${esc(o.attribution.label)}. ${esc(o.attribution.lesson)}</p><p class="small muted">trough ${usd2(o.trough_usd)} (${esc(t("lbl.week", { w: o.trough_week }))}) · ${Object.entries(o.contributions_usd).map(([k_, v]) => `${k_.replaceAll("_", " ")} ${usd(v)}`).join(" · ")}</p></div>`;
      }
    };
    page.querySelectorAll("[data-event]").forEach((btn) => btn.onclick = async () => {
      btn.disabled = true;
      const r = await act(() => CB.post("/api/intelligence/events", { kind: btn.dataset.event }),
        (x) => x.assessment.route === "DIRECTOR_INBOX" ? t("core.inbox") + ": " + x.assessment.id : t("core.digest"));
      if (r) { await refresh(); renderNav("core"); routes.core(); } else btn.disabled = false;
    });
    if ($("evReset")) $("evReset").onclick = async () => { if (await act(() => CB.post("/api/intelligence/events/reset"))) { await refresh(); renderNav("core"); routes.core(); } };
    page.querySelectorAll("[data-alert]").forEach((btn) => btn.onclick = async () => {
      if (await act(() => CB.post(`/api/intelligence/inbox/${encodeURIComponent(btn.dataset.alert)}`, { accept: btn.dataset.accept === "1" }), "OK")) { await refresh(); renderNav("core"); routes.core(); }
    });
    if ($("corePropose")) $("corePropose").onclick = async () => { if (await act(() => CB.post("/api/intelligence/propose-update"), t("core.pending"))) routes.core(); };
    if ($("coreApprove")) $("coreApprove").onclick = async () => { if (await act(() => CB.post("/api/intelligence/decide-update", { approve: true, note: "held-out gate passed" }), "OK")) routes.core(); };
    if ($("coreReject")) $("coreReject").onclick = async () => { if (await act(() => CB.post("/api/intelligence/decide-update", { approve: false, note: "rejected" }), "OK")) routes.core(); };
  };

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
  async function signOut() { try { await CB.post("/api/auth/logout"); } catch (e) { /* ignore */ } CB.clear(); location.href = "/?signedout=1"; }

  function paintChrome() {
    const u = state.user;
    window.I18N.apply();
    $("portalTag").textContent = t(u.portal === "bank" ? "app.bank" : "app.sme");
    document.title = t(u.portal === "bank" ? "app.bank" : "app.sme") + " | CashBridge";
  }

  // ------------------------------------------------------------------ settings
  // Personal display preferences live on this device only. Organisation policy is read from the server and
  // shown read-only: no permission, limit or approval rule is ever stored or decided in the browser.
  const PREFS = { view: ["advanced", "simple"], text: ["normal", "large"], motion: ["normal", "reduce"], contrast: ["normal", "high"] };
  const prefGet = (k) => { try { const v = localStorage.getItem("cb." + k); return PREFS[k].includes(v) ? v : PREFS[k][0]; } catch (e) { return PREFS[k][0]; } };
  const prefSet = (k, v) => { try { localStorage.setItem("cb." + k, v); } catch (e) { /* private mode: keep for this page only */ } };
  function applyPrefs() { Object.keys(PREFS).forEach((k) => { document.documentElement.dataset[k] = prefGet(k); }); }
  applyPrefs();

  // Settings is a page in the side bar (System › Settings), like the reference app: display changes apply at once
  // and are kept on this device; session actions sit with the account; organisation policy is read-only.
  const fmtExpiry = (v) => {
    const d = typeof v === "number" || /^\d+$/.test(String(v)) ? new Date(Number(v) * 1000) : new Date(v);
    if (isNaN(d)) return String(v);
    const loc = { en: "en-GB", vi: "vi-VN", zh: "zh-CN" }[window.I18N.lang()] || "en-GB";
    return d.toLocaleString(loc, { dateStyle: "medium", timeStyle: "short" });
  };
  routes.settings = async () => {
    const u = state.user;
    const [pol, health] = await Promise.all([CB.get("/api/settings/policy").catch(() => null), CB.get("/api/health", { anonymous: true }).catch(() => null)]);
    const sess = CB.session() || {};
    const theme = document.documentElement.dataset.theme || "system";
    const seg = (key, opts, cur, label) => `<div class="seg" role="group" aria-label="${esc(label)}">${opts.map(([v, l]) => `<button type="button" data-set="${key}" data-v="${v}" class="${v === cur ? "on" : ""}" aria-pressed="${v === cur}">${esc(l)}</button>`).join("")}</div>`;
    const row = (title, hint, control) => `<div class="set-row"><div><b>${esc(title)}</b>${hint ? `<span>${esc(hint)}</span>` : ""}</div>${control}</div>`;
    const sw = (key, on, title, hint) => row(title, hint, `<label class="switch"><input type="checkbox" data-sw="${key}" ${on ? "checked" : ""} aria-label="${esc(title)}"><span></span></label>`);
    const profile = panel(t("set.profile"), esc(t("set.profileSub")), `<div class="side-user big">${userCard()}</div>
      ${row(t("set.orgName"), "", `<span>${esc(u.org || "–")}</span>`)}
      ${row(t("set.uid"), "", `<span class="mono">${esc(u.user_id)}</span>`)}
      ${pol ? row(t("set.tenant"), "", `<span class="mono">${esc(pol.you.tenant)}</span>`) : ""}
      <p class="note">${esc(t("set.roleNote"))}</p>${u.portal === "sme" ? roleStrip() : ""}`);
    const display = panel(t("set.display"), esc(t("set.personalSub")), `
      ${row(t("set.lang"), "", seg("lang", [["en", "English"], ["vi", "Tiếng Việt"], ["zh", "中文"]], window.I18N.lang(), t("set.lang")))}
      ${row(t("set.theme"), "", seg("theme", [["system", t("set.system")], ["light", t("set.light")], ["dark", t("set.dark")]], theme, t("set.theme")))}
      ${row(t("set.view"), t("set.viewHint"), seg("view", [["advanced", t("set.advanced")], ["simple", t("set.simple")]], prefGet("view"), t("set.view")))}
      ${row(t("set.text"), "", seg("text", [["normal", t("set.normal")], ["large", t("set.large")]], prefGet("text"), t("set.text")))}
      ${sw("motion", prefGet("motion") === "reduce", t("set.motion"), t("set.motionHint"))}
      ${sw("contrast", prefGet("contrast") === "high", t("set.contrast"), t("set.contrastHint"))}`);
    const session = panel(t("set.sessionData"), esc(t("set.sessionSub")), `
      ${row(t("set.server"), "", `<span class="pill ${health ? "ok" : "bad"}">${esc(t(health ? "set.online" : "set.offline"))}</span>`)}
      ${pol ? row(t("set.mode"), "", `<span class="mono">${esc(pol.mode)}</span>`) : ""}
      ${sess.expires_at ? row(t("set.expires"), "", `<span>${esc(fmtExpiry(sess.expires_at))}</span>`) : ""}
      <div class="row" style="margin-top:12px"><button class="btn ghost small" type="button" id="setSwitch">${esc(t("app.switch"))}</button><button class="btn ghost small" type="button" id="setLogout">${esc(t("app.logout"))}</button>${can("demo:reset") ? `<button class="btn danger small" type="button" id="setReset">${esc(t("tr.reset"))}</button>` : ""}</div>`);
    const org = panel(t("set.org"), esc(t("set.orgSub")), pol ? `<div class="scroll"><table class="small"><tbody>
        <tr><td>${esc(t("set.you"))}</td><td>${esc(t("role." + pol.you.role))}<div class="muted mono">${esc(pol.you.permissions.join(", "))}</div></td></tr>
        <tr><td>${esc(t("set.buffer"))}</td><td>${usd(pol.cash.buffer_usd)} · ${esc(t("set.conc"))} ${pol.cash.concentration_alert_pct}%</td></tr>
        <tr><td>${esc(t("set.approvals"))}</td><td>OTP ${pol.approvals.otp_validity_seconds}s · ${esc(t("set.session"))} ${pol.approvals.session_hours}h<div class="muted">${esc(pol.approvals.segregation_of_duties)}. ${esc(pol.approvals.lender_decision)}.</div></td></tr>
        <tr><td>${esc(t("set.planner"))}</td><td>${Object.values(pol.planner.goals).map((g) => `${esc(g.label)} (${Math.round(g.min_probability * 100)}%)`).join("; ")} · max ${pol.planner.max_packs_per_plan} · ×${pol.planner.over_borrowing_factor}</td></tr>
        <tr><td>${esc(t("set.alerts"))}</td><td>${esc(pol.alerts)}</td></tr></tbody></table></div><p class="note">${esc(pol.change_process)}</p>` : `<p class="muted">–</p>`);
    page.innerHTML = head(t("set.title"), esc(t("set.lede"))) + `<div class="grid2 settings-grid">${display}${profile}${session}${org}</div>`;
    bindRoleStrip();
    page.querySelectorAll("[data-set]").forEach((b) => b.onclick = () => {
      const k = b.dataset.set, v = b.dataset.v;
      if (k === "lang") { const l = document.querySelector(`#langSwitch [data-l="${v}"]`); if (l) l.click(); return; }
      if (k === "theme") {
        if (v === "system") { delete document.documentElement.dataset.theme; try { localStorage.removeItem("cb.theme"); } catch (e) { /* ignore */ } }
        else { document.documentElement.dataset.theme = v; try { localStorage.setItem("cb.theme", v); } catch (e) { /* ignore */ } }
        document.dispatchEvent(new CustomEvent("cb:theme"));
      } else { prefSet(k, v); applyPrefs(); routes.settings(); }
      toast(t("set.saved"));
    });
    page.querySelectorAll("[data-sw]").forEach((i) => i.onchange = () => {
      const k = i.dataset.sw;
      prefSet(k, i.checked ? (k === "motion" ? "reduce" : "high") : "normal"); applyPrefs(); toast(t("set.saved"));
    });
    $("setSwitch").onclick = switchAccount;
    $("setLogout").onclick = signOut;
    if ($("setReset")) $("setReset").onclick = async () => { if (confirm(t("tr.reset") + "?") && await act(() => CB.post("/api/reset_demo"), "OK")) { state.summary = null; await refresh().catch(() => null); route(); } };
  };

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
