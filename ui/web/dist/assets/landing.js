/* Landing page: live cash chart, EN/VI copy, and the two-portal sign-in dialog. */
(function () {
  const $ = (id) => document.getElementById(id);
  const { esc, usd } = window.CB;

  // ---------------------------------------------------------------- copy (assets/i18n.js)
  const t = window.I18N.t;
  function applyLang() { window.I18N.apply(); setPortal(portal, false); renderAccounts(); }
  window.I18N.langSwitch($("langSwitch"));
  window.I18N.themeButton($("themeBtn"));
  document.addEventListener("cb:lang", () => { applyLang(); loadOverview(); });

  // ---------------------------------------------------------------- chart
  const SAMPLE = {
    company: "Binh Duong Timberworks Co., Ltd. (SYNTHETIC)",
    weeks: [42000, 14160, 2434.23, 8110.23, 5866.19, 10860.19, -43881.89, -75457.89, -53675.39, -56189.39, -94325.39, -128195.39, -151195.39],
    bridge: { amount_usd: 48000, apr_pct: 17.12, funding_week: 7, trough_week: 13, residual_gap_usd: 152546.62,
      closing_after: [42000, 14160, 2434.23, 8110.23, 5866.19, 10860.19, 4118.11, -27457.89, -55026.62, -57540.62, -95676.62, -129546.62, -152546.62] },
    first_week: 7, shortfall: 43881.89,
  };

  function drawChart(d) {
    const svg = $("cashChart");
    const W = 640, H = 360, L = 58, R = 16, T = 18, B = 34;
    const all = d.weeks.concat(d.bridge ? d.bridge.closing_after : []);
    const max = Math.max(60000, ...all), min = Math.min(0, ...all);
    const x = (i) => L + (i * (W - L - R)) / (d.weeks.length - 1);
    const y = (v) => T + ((max - v) * (H - T - B)) / (max - min);
    const ticks = [];
    const step = 50000;
    for (let v = Math.ceil(min / step) * step; v <= max; v += step) ticks.push(v);
    const path = (vals) => vals.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1)).join(" ");
    const area = "M" + x(0) + " " + y(0) + " " + d.weeks.map((v, i) => "L" + x(i).toFixed(1) + " " + y(Math.min(0, v)).toFixed(1)).join(" ") + " L" + x(d.weeks.length - 1) + " " + y(0) + "Z";
    let out = "";
    ticks.forEach((v) => {
      out += `<line class="${v === 0 ? "zero" : "grid"}" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/>`;
      out += `<text x="${L - 8}" y="${y(v) + 4}" text-anchor="end">${v === 0 ? "$0" : (v < 0 ? "−" : "") + "$" + Math.abs(v / 1000) + "k"}</text>`;
    });
    d.weeks.forEach((_, i) => { if (i % 2 === 0) out += `<text x="${x(i)}" y="${H - 10}" text-anchor="middle">W${i + 1}</text>`; });
    out += `<path class="deficit-area" d="${area}"/>`;
    out += `<path class="base" d="${path(d.weeks)}"/>`;
    if (d.bridge) {
      const fw = d.bridge.funding_week - 1;
      out += `<path class="bridged draw" d="${path(d.bridge.closing_after)}" style="--len:1400"/>`;
      const x1 = x(fw), yb = y(d.weeks[fw]), ya = y(d.bridge.closing_after[fw]);
      out += `<line class="span" x1="${x1}" x2="${x1}" y1="${yb}" y2="${ya}" stroke-dasharray="3 3"/>`;
      out += `<text class="label bridge" x="${x1 + 8}" y="${ya - 8}">${esc(t("lc.advance", { a: usd(d.bridge.amount_usd) }))}</text>`;
      const tw = d.bridge.trough_week - 1;
      out += `<text class="label deficit" x="${x(tw) - 14}" y="${y(d.bridge.closing_after[tw]) + 4}" text-anchor="end">${esc(t("lc.still", { a: usd(d.bridge.residual_gap_usd) }))}</text>`;
    }
    d.weeks.forEach((v, i) => { if (v < 0) out += `<circle class="dot-neg" cx="${x(i)}" cy="${y(v)}" r="3.5"/>`; });
    const fi = d.first_week - 1;
    out += `<text class="label deficit" x="${x(fi) - 8}" y="${y(d.weeks[fi]) + 4}" text-anchor="end">W${d.first_week}: −${usd(d.shortfall)}</text>`;
    svg.innerHTML = out;
    $("chartCompany").textContent = d.company.replace(" Co., Ltd.", "").replace("(SYNTHETIC)", "(synthetic)");
    $("noteGap").textContent = t("lc.week", { w: d.first_week, a: usd(d.shortfall) });
    if (d.bridge) {
      $("noteBridge").textContent = t("lc.apr", { a: usd(d.bridge.amount_usd), p: Number(d.bridge.apr_pct).toFixed(1) });
      $("noteResidual").textContent = t("lc.by", { a: usd(d.bridge.residual_gap_usd), w: d.bridge.trough_week });
    }
  }

  async function loadOverview() {
    drawChart(SAMPLE);
    try {
      const o = await CB.get("/api/public/overview", { anonymous: true });
      if (!o.kpis.first_shortfall_week) return;
      drawChart({ company: o.company, weeks: o.weeks.map((w) => w.closing), bridge: o.bridge,
        first_week: o.kpis.first_shortfall_week, shortfall: o.kpis.shortfall_usd });
    } catch (e) { /* static preview: keep the labelled sample */ }
  }

  async function loadScores() {
    try {
      const s = await CB.get("/api/trust/scorecard", { anonymous: true });
      $("scSec").textContent = `${s.summary.security.passed}/${s.summary.security.total}`;
      $("scAgent").textContent = `${s.summary.agent.passed}/${s.summary.agent.total}`;
      $("scModel").textContent = `${s.summary.model.brier_model.toFixed(3)} vs ${s.summary.model.brier_baseline.toFixed(3)}`;
    } catch (e) { /* keep committed values */ }
  }

  // ---------------------------------------------------------------- sign-in dialog
  let portal = "sme";
  let accounts = [];
  let lastFocus = null;
  const dialog = $("auth");

  function setPortal(next, focus = true) {
    portal = next;
    $("tabSme").setAttribute("aria-selected", String(portal === "sme"));
    $("tabBank").setAttribute("aria-selected", String(portal === "bank"));
    $("authSide").classList.toggle("bank", portal === "bank");
    $("authTitle").innerHTML = t(`auth.${portal}.title`);
    $("authLede").innerHTML = t(`auth.${portal}.lede`);
    $("loginUser").placeholder = portal === "sme" ? "sme.lan" : "bank.lihua";
    $("loginErr").textContent = "";
    renderAccounts();
    if (focus) (portal === "sme" ? $("tabSme") : $("tabBank")).focus();
  }

  function renderAccounts() {
    const list = accounts.filter((a) => a.portal === portal);
    if (!accounts.length) return;
    $("accounts").innerHTML = list.length ? list.map((a) => `
      <button type="button" class="acc" data-user="${esc(a.user_id)}">
        <span class="av" aria-hidden="true">${esc(a.initials)}</span>
        <span><b>${esc(a.name)}</b><span class="meta">${esc(a.org)}</span></span>
        <span class="role">${esc(t("role." + a.role))}</span>
      </button>`).join("") : `<p class="muted">Demo accounts are switched off on this server. Use the passcode form.</p>`;
    $("accounts").querySelectorAll("[data-user]").forEach((b) => b.addEventListener("click", () => demoLogin(b.dataset.user)));
  }

  async function loadAccounts() {
    try {
      const cfg = await CB.get("/api/auth/config", { anonymous: true });
      accounts = cfg.demo_accounts || [];
      if (!accounts.length) $("accounts").innerHTML = `<p class="muted">${t("auth.off")}</p>`;
      renderAccounts();
    } catch (e) {
      $("accounts").innerHTML = `<p class="err">${esc(e.message)}</p>`;
    }
  }

  function openAuth(which) {
    lastFocus = document.activeElement;
    dialog.hidden = false;
    document.body.style.overflow = "hidden";
    setPortal(which || "sme");
    if (!accounts.length) loadAccounts();
  }
  function closeAuth() {
    dialog.hidden = true;
    document.body.style.overflow = "";
    if (lastFocus) lastFocus.focus();
  }

  function enter(session) {
    CB.save({ token: session.token, user: session.user, expires_at: session.expires_at });
    window.location.href = "/app#" + (session.user.portal === "bank" ? "inbox" : "overview");
  }

  async function demoLogin(userId) {
    $("loginErr").textContent = "";
    try { enter(await CB.post("/api/auth/demo-login", { user_id: userId, portal }, { anonymous: true })); }
    catch (e) { $("loginErr").textContent = e.message; }
  }

  $("loginForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = $("loginBtn");
    btn.disabled = true;
    $("loginErr").textContent = "";
    try {
      enter(await CB.post("/api/auth/login", { user_id: $("loginUser").value.trim(), passcode: $("loginPass").value, portal }, { anonymous: true }));
    } catch (e) {
      $("loginErr").textContent = e.message;
    } finally { btn.disabled = false; }
  });

  document.querySelectorAll("[data-open-auth]").forEach((b) => b.addEventListener("click", () => openAuth(b.dataset.openAuth)));
  document.querySelectorAll("[data-portal]").forEach((b) => b.addEventListener("click", () => setPortal(b.dataset.portal)));
  $("authClose").addEventListener("click", closeAuth);
  dialog.addEventListener("click", (e) => { if (e.target === dialog) closeAuth(); });
  document.addEventListener("keydown", (e) => {
    if (dialog.hidden) return;
    if (e.key === "Escape") closeAuth();
    if (e.key === "Tab") {
      const items = [...dialog.querySelectorAll("button, input, [tabindex]:not([tabindex='-1'])")].filter((el) => !el.disabled && el.offsetParent !== null);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });

  const params = new URLSearchParams(location.search);
  const existing = CB.session();
  applyLang();
  loadOverview();
  loadScores();
  if (params.get("signin")) openAuth(params.get("signin") === "bank" ? "bank" : "sme");
  else if (existing && existing.user && params.get("stay") !== "1") {
    // Already signed in in this tab: offer a direct way back instead of a dialog.
    document.querySelectorAll("[data-open-auth]").forEach((b) => {
      if (b.dataset.openAuth === existing.user.portal && b.classList.contains("bridge")) {
        b.textContent = t(existing.user.portal === "bank" ? "auth.back.bank" : "auth.back.sme");
        b.addEventListener("click", (e) => { e.stopImmediatePropagation(); location.href = "/app"; }, { capture: true });
      }
    });
  }
})();
