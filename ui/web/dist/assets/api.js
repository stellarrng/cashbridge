/* Shared API client. The session token lives in sessionStorage (cleared when the tab closes) and is
 * sent as a Bearer header. The browser never decides permissions: every call is checked on the server. */
(function () {
  const KEY = "cb.session";
  const base = () => (window.CASHBRIDGE_API || "").replace(/\/$/, "");

  function read() {
    try { return JSON.parse(sessionStorage.getItem(KEY) || "null"); } catch (e) { return null; }
  }
  function save(session) {
    try { sessionStorage.setItem(KEY, JSON.stringify(session)); } catch (e) { /* private mode: memory only */ }
    memory = session;
  }
  function clear() {
    try { sessionStorage.removeItem(KEY); } catch (e) { /* ignore */ }
    memory = null;
  }
  let memory = read();

  class ApiError extends Error {
    constructor(status, message) { super(message); this.status = status; }
  }

  async function request(path, options = {}) {
    const headers = Object.assign({}, options.headers || {});
    const session = memory || read();
    if (session && session.token && !options.anonymous) headers.Authorization = "Bearer " + session.token;
    let body = options.body;
    if (body !== undefined && !(body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(base() + path, { method: options.method || (body === undefined ? "GET" : "POST"), headers, body });
    } catch (e) {
      throw new ApiError(0, "The CashBridge server is not reachable. Start it with `make run`, or check the API address in assets/config.js.");
    }
    if (options.raw) {
      if (!response.ok) throw new ApiError(response.status, await errorText(response));
      return response;
    }
    const text = await response.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) { data = { detail: text }; }
    if (!response.ok) {
      const detail = data && data.detail;
      const message = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map(d => d.msg).join("; ") : (data && data.error) || response.statusText;
      if (response.status === 401 && session && !options.anonymous) clear();
      throw new ApiError(response.status, message || "Request failed");
    }
    return data;
  }

  async function errorText(response) {
    try { const d = await response.json(); return typeof d.detail === "string" ? d.detail : response.statusText; } catch (e) { return response.statusText; }
  }

  async function download(path, filename, options = {}) {
    const response = await request(path, Object.assign({}, options, { raw: true }));
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = filename; document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  window.CB = {
    session: () => memory || read(),
    save, clear, request, download, ApiError,
    get: (p, o) => request(p, o),
    post: (p, b, o) => request(p, Object.assign({}, o, { method: "POST", body: b === undefined ? {} : b })),
    esc: (x) => String(x ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])),
    usd: (x, digits = 0) => x == null || Number.isNaN(Number(x)) ? "n/a" : (Number(x) < 0 ? "−" : "") + "$" + Math.abs(Number(x)).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits }),
  };
})();
