/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Origin of the CashBridge API when the UI is hosted apart from it (e.g. https://api.example.com). Empty = same origin. */
  readonly VITE_API_BASE?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
