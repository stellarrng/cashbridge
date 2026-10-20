/** The signed session lives in sessionStorage (cleared when the tab closes), never in persistent storage. */

export type Portal = "sme" | "bank";

export interface SessionUser {
  user_id: string;
  name: string;
  role: string;
  org: string;
  tenant_id?: string;
  portal: Portal;
  role_label?: string;
  permissions: string[];
  expires_at?: number | string;
}

export interface Session {
  token: string;
  user: SessionUser;
  expires_at: number | string;
}

const KEY = "cb.session";
let memory: Session | null = null;
/** Remembered so a 401 (which clears the session) can still send the person back to the right sign-in tab. */
let lastPortal: Portal = "sme";

function read(): Session | null {
  try {
    return JSON.parse(sessionStorage.getItem(KEY) || "null") as Session | null;
  } catch {
    return null;
  }
}

memory = read();
if (memory) lastPortal = memory.user.portal;

export const getSession = (): Session | null => memory ?? read();

export function saveSession(session: Session): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify(session));
  } catch {
    /* private mode: memory only */
  }
  memory = session;
  lastPortal = session.user.portal;
}

/** Landing-page URL that opens the sign-in dialog on the given portal. */
export const signInUrl = (portal: Portal = lastPortal): string => "/?signin=" + portal;

export function clearSession(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
  memory = null;
}
