/* Where the CashBridge API lives. Empty string = same origin (FastAPI or Vercel full-stack deploy).
 * For a static-only frontend on Vercel with the API on Render/Railway, set the API origin here, e.g.
 *   window.CASHBRIDGE_API = "https://cashbridge-api.onrender.com";
 * and add the frontend origin to CASHBRIDGE_ALLOWED_ORIGINS on the API. */
window.CASHBRIDGE_API = window.CASHBRIDGE_API || "";
