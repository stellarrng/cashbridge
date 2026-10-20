/* Small SVG chart kit for CashBridge. Draws only what the backend computed; no financial maths.
 * Rules followed: thin marks with a 2px surface gap, rounded data ends, recessive solid grid,
 * one axis, legends for 2+ series, colour follows the entity, status colours only for status,
 * hover tooltip on every mark ([data-tip], see i18n.js), text in ink tokens, never series colour. */
(function () {
  const esc = (x) => String(x ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const k = (v) => (v === 0 ? "$0" : (v < 0 ? "−" : "") + "$" + (Math.abs(v) >= 1e6 ? (Math.abs(v) / 1e6).toFixed(1) + "M" : Math.round(Math.abs(v) / 1000) + "k"));
  const niceStep = (span) => { const raw = span / 4; const p = Math.pow(10, Math.floor(Math.log10(raw))); return [1, 2, 2.5, 5, 10].map((m) => m * p).find((s) => s >= raw); };

  /* Vertical bars around a zero line. items: [{label, value, cls, tip}] ; overlay: optional numbers for a line */
  function columns(items, opts = {}) {
    const W = opts.width || 720, H = opts.height || 240, L = 54, R = 10, T = 12, B = 26;
    const all = items.map((d) => d.value).concat(opts.overlay || []);
    let max = Math.max(0, ...all), min = Math.min(0, ...all);
    const step = niceStep(max - min || 1);
    max = Math.ceil(max / step) * step; min = Math.floor(min / step) * step;
    const y = (v) => T + ((max - v) * (H - T - B)) / (max - min || 1);
    const bw = (W - L - R) / items.length, gap = Math.max(2, bw * 0.22);
    let g = "";
    for (let v = min; v <= max + 1e-9; v += step) g += `<line class="cg" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="ct" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${k(v)}</text>`;
    items.forEach((d, i) => {
      const x = L + i * bw + gap / 2, w = bw - gap, top = Math.min(y(0), y(d.value)), h = Math.max(1.5, Math.abs(y(d.value) - y(0)));
      const r = Math.min(4, w / 2, h);
      // rounded data end, square at the baseline
      const path = d.value >= 0
        ? `M${x} ${top + h}V${top + r}Q${x} ${top} ${x + r} ${top}H${x + w - r}Q${x + w} ${top} ${x + w} ${top + r}V${top + h}Z`
        : `M${x} ${top}V${top + h - r}Q${x} ${top + h} ${x + r} ${top + h}H${x + w - r}Q${x + w} ${top + h} ${x + w} ${top + h - r}V${top}Z`;
      g += `<path class="${d.cls || "cb-s1"}" d="${path}" data-tip="${esc(d.tip || d.label)}"/>`;
      if (!opts.sparseLabels || i % 2 === 0 || items.length < 9) g += `<text class="ct" x="${x + w / 2}" y="${H - 8}" text-anchor="middle">${esc(d.label)}</text>`;
    });
    if (opts.overlay) {
      g += `<path class="cline" d="${opts.overlay.map((v, i) => (i ? "L" : "M") + (L + i * bw + bw / 2).toFixed(1) + " " + y(v).toFixed(1)).join(" ")}"/>`;
      opts.overlay.forEach((v, i) => { g += `<circle class="cdot" cx="${L + i * bw + bw / 2}" cy="${y(v)}" r="4" data-tip="${esc((opts.overlayTip || (() => ""))(v, i))}"/>`; });
    }
    g += `<line class="cz" x1="${L}" x2="${W - R}" y1="${y(0)}" y2="${y(0)}"/>`;
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.label || "")}">${g}</svg>`;
  }

  /* Donut for part-to-whole (<= 6 parts). parts: [{label, value, color, display}] */
  function donut(parts, opts = {}) {
    const total = parts.reduce((s, p) => s + Math.max(0, p.value), 0) || 1;
    const R = 62, r = 40, C = 80;
    let a0 = -Math.PI / 2, g = "";
    parts.forEach((p) => {
      const frac = Math.max(0, p.value) / total;
      if (frac <= 0) return;
      const a1 = a0 + frac * Math.PI * 2;
      const large = a1 - a0 > Math.PI ? 1 : 0;
      const pt = (rad, ang) => [C + rad * Math.cos(ang), C + rad * Math.sin(ang)];
      const [x0, y0] = pt(R, a0), [x1, y1] = pt(R, a1 - 1e-6), [x2, y2] = pt(r, a1 - 1e-6), [x3, y3] = pt(r, a0);
      const d = frac >= 0.9999
        ? `M${C - R} ${C}a${R} ${R} 0 1 0 ${2 * R} 0a${R} ${R} 0 1 0 ${-2 * R} 0M${C - r} ${C}a${r} ${r} 0 1 1 ${2 * r} 0a${r} ${r} 0 1 1 ${-2 * r} 0Z`
        : `M${x0} ${y0}A${R} ${R} 0 ${large} 1 ${x1} ${y1}L${x2} ${y2}A${r} ${r} 0 ${large} 0 ${x3} ${y3}Z`;
      g += `<path d="${d}" fill="${p.color}" class="dseg" fill-rule="evenodd" data-tip="${esc(p.label)}: ${esc(p.display || p.value)} (${Math.round(frac * 100)}%)"/>`;
      a0 = a1;
    });
    const center = opts.center ? `<text class="dc1" x="${C}" y="${C - 2}" text-anchor="middle">${esc(opts.center)}</text><text class="dc2" x="${C}" y="${C + 16}" text-anchor="middle">${esc(opts.centerSub || "")}</text>` : "";
    const legend = `<ul class="legend-list">${parts.map((p) => `<li><i style="background:${p.color}"></i><span>${esc(p.label)}</span><b>${esc(p.display || p.value)}</b><em>${Math.round((Math.max(0, p.value) / total) * 100)}%</em>${p.flag ? `<span class="pill bad">${esc(p.flag)}</span>` : ""}</li>`).join("")}</ul>`;
    return `<div class="donut"><svg viewBox="0 0 160 160" role="img" aria-label="${esc(opts.label || "")}">${g}${center}</svg>${legend}</div>`;
  }

  /* Horizontal bars with a zero line; items: [{label, value, display, cls, tip, strong}] */
  function hbars(items, opts = {}) {
    const max = Math.max(0, ...items.map((d) => d.value)), min = Math.min(0, ...items.map((d) => d.value));
    const span = max - min || 1;
    const zero = ((0 - min) / span) * 100;
    return `<div class="hbars">${items.map((d) => {
      const w = (Math.abs(d.value) / span) * 100, left = d.value >= 0 ? zero : zero - w;
      return `<div class="hb ${d.strong ? "strong" : ""}" data-tip="${esc(d.tip || d.label + ": " + d.display)}"><span class="hb-l">${esc(d.label)}</span><span class="hb-track"><i class="hb-zero" style="left:${zero}%"></i><i class="hb-bar ${d.cls || "cb-s1"} ${d.value < 0 ? "neg" : ""}" style="left:${left}%;width:${Math.max(0.6, w)}%"></i></span><b class="hb-v">${esc(d.display)}</b></div>`;
    }).join("")}${opts.note ? `<p class="note">${esc(opts.note)}</p>` : ""}</div>`;
  }

  /* 100% stacked bar for a few statuses; parts: [{label, value, cls}] */
  function stack(parts) {
    const total = parts.reduce((s, p) => s + p.value, 0) || 1;
    return `<div class="stack">${parts.filter((p) => p.value > 0).map((p) => `<i class="${p.cls}" style="flex:${p.value}" data-tip="${esc(p.label)}: ${p.value}"></i>`).join("")}</div>
      <ul class="legend-inline">${parts.map((p) => `<li><i class="${p.cls}"></i>${esc(p.label)} <b>${p.value}</b></li>`).join("")}</ul>`;
  }

  /* Line chart over shared categories; series: [{name, values, color, width?, dash?, muted?}]
   * opts: fmt (tooltip value), yfmt (axis), endLabels (direct labels at the right end),
   *       annotate {index, text} (dashed marker), tipExtra(i) (extra tooltip line), dots ("all" | "ends") */
  function lines(labels, series, opts = {}) {
    const W = opts.width || 720, H = opts.height || 230, L = 54, R = opts.endLabels ? 132 : 16, T = opts.annotate ? 26 : 12, B = 26;
    const all = series.flatMap((s) => s.values);
    let max = Math.max(...all), min = Math.min(0, ...all);
    const step = niceStep(max - min || 1);
    max = Math.ceil(max / step) * step;
    const x = (i) => L + (i * (W - L - R)) / (labels.length - 1);
    const y = (v) => T + ((max - v) * (H - T - B)) / (max - min || 1);
    const yl = opts.yfmt || k;
    let g = "";
    for (let v = min; v <= max + 1e-9; v += step) g += `<line class="cg" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text class="ct" x="${L - 6}" y="${y(v) + 4}" text-anchor="end">${yl(v)}</text>`;
    labels.forEach((l, i) => { if (i % 2 === 0) g += `<text class="ct" x="${x(i)}" y="${H - 8}" text-anchor="middle">${esc(l)}</text>`; });
    if (opts.annotate) {
      const ax = x(opts.annotate.index);
      g += `<line x1="${ax}" x2="${ax}" y1="${T - 4}" y2="${H - B}" stroke="var(--ink-3)" stroke-dasharray="3 4" stroke-width="1"/>`;
      g += `<text class="ct" x="${Math.min(ax + 6, W - R - 4)}" y="${T - 10}" text-anchor="${ax + 160 > W - R ? "end" : "start"}">${esc(opts.annotate.text)}</text>`;
    }
    // draw muted series first so the focus series sits on top
    series.map((s, idx) => ({ s, idx })).sort((a, b) => (a.s.muted ? 0 : 1) - (b.s.muted ? 0 : 1)).forEach(({ s }) => {
      g += `<path fill="none" stroke="${s.color}" stroke-width="${s.width || 2}" ${s.dash ? `stroke-dasharray="${s.dash}"` : ""} opacity="${s.muted ? 0.75 : 1}" stroke-linejoin="round" stroke-linecap="round" d="${s.values.map((v, i) => (i ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1)).join(" ")}"/>`;
    });
    const dots = opts.dots || "all";
    labels.forEach((l, i) => {
      const tip = l + "\n" + series.map((s) => `${s.name}: ${opts.fmt ? opts.fmt(s.values[i]) : s.values[i]}`).join("\n") + (opts.tipExtra ? "\n" + opts.tipExtra(i) : "");
      g += `<rect class="hit" x="${x(i) - (W - L - R) / labels.length / 2}" y="${T}" width="${(W - L - R) / labels.length}" height="${H - T - B}" data-tip="${esc(tip)}"/>`;
      series.forEach((s) => {
        if (dots === "all" || i === labels.length - 1) g += `<circle cx="${x(i)}" cy="${y(s.values[i])}" r="${dots === "all" ? 3 : 4}" fill="${s.color}" stroke="var(--surface, #fff)" stroke-width="2" class="lpt"/>`;
      });
    });
    if (opts.endLabels) {
      const last = labels.length - 1;
      const placed = series.map((s) => ({ name: s.name, y: y(s.values[last]), color: s.color })).sort((a, b) => a.y - b.y);
      for (let i = 1; i < placed.length; i++) if (placed[i].y - placed[i - 1].y < 15) placed[i].y = placed[i - 1].y + 15;
      placed.forEach((p) => {
        g += `<line x1="${x(last) + 7}" x2="${x(last) + 17}" y1="${p.y}" y2="${p.y}" stroke="${p.color}" stroke-width="2"/>`;
        g += `<text class="ct cl" x="${x(last) + 21}" y="${p.y + 4}">${esc(p.name)}</text>`;
      });
    }
    const legend = `<ul class="legend-inline">${series.map((s) => `<li><i style="background:${s.color}${s.dash ? ";opacity:.75" : ""}"></i>${esc(s.name)}</li>`).join("")}</ul>`;
    return `${legend}<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.label || "")}">${g}</svg>`;
  }

  window.Charts = { columns, donut, hbars, stack, lines };
})();
