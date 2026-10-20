import { Suspense, useEffect, useRef, useState } from "react";
import { useI18n } from "@/shared/i18n";
import { useAuth, homeRoute } from "../auth";
import { AssistantDrawer } from "../assistant";
import { ErrorBoundary } from "./ErrorBoundary";
import { LoadingSkeleton } from "@/shared/ui";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { allowedScreens } from "./nav";
import { SCREENS } from "./screens";
import { useHashRoute } from "./useHashRoute";

/** The signed-in shell: top bar, role-aware sidebar, the current screen, and the CFO assistant drawer. */
export function WorkspaceApp() {
  const { t } = useI18n();
  const { user } = useAuth();
  const route = useHashRoute();
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const main = useRef<HTMLElement>(null);

  const home = homeRoute(user);
  const target = allowedScreens(user).includes(route.name) ? route.name : home;
  const arg = target === route.name ? route.arg : undefined;
  const Screen = SCREENS[target];

  // A bare or forbidden hash falls back to the role's home screen.
  useEffect(() => {
    if (route.name !== target) window.location.replace("#" + home);
  }, [route.name, target, home]);

  useEffect(() => {
    main.current?.focus({ preventScroll: true });
    setMenuOpen(false);
  }, [target, arg]);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMenuOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <>
      <Topbar onAssistant={() => setAssistantOpen(true)} onMenu={() => setMenuOpen((o) => !o)} menuOpen={menuOpen} />
      <div className="shell">
        <Sidebar current={target === "case" ? "inbox" : target} open={menuOpen} onNavigate={() => setMenuOpen(false)} />
        {menuOpen && <div className="side-scrim" onClick={() => setMenuOpen(false)} />}
        <main className="page" id="page" tabIndex={-1} ref={main}>
          <ErrorBoundary title={t("app.error")} resetKey={target + "/" + (arg ?? "")}>
            <Suspense fallback={<LoadingSkeleton />}>
              <div className="screen" key={target + "/" + (arg ?? "")}><Screen arg={arg} /></div>
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
      {user.portal === "sme" && <AssistantDrawer open={assistantOpen} onClose={() => setAssistantOpen(false)} />}
    </>
  );
}
