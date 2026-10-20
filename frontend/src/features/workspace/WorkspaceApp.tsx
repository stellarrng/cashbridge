import { Suspense, useEffect, useRef, useState } from "react";
import { useI18n } from "@/shared/i18n";
import { useAuth, homeRoute } from "../auth";
import { AssistantDrawer } from "../assistant";
import { ErrorBoundary } from "./ErrorBoundary";
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
  }, [target, arg]);

  return (
    <>
      <Topbar onAssistant={() => setAssistantOpen(true)} />
      <div className="shell">
        <Sidebar current={target === "case" ? "inbox" : target} />
        <main className="page" id="page" tabIndex={-1} ref={main}>
          <ErrorBoundary title={t("app.error")} resetKey={target + "/" + (arg ?? "")}>
            <Suspense fallback={<p className="muted">{t("app.loading")}</p>}>
              <Screen arg={arg} />
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
      {user.portal === "sme" && <AssistantDrawer open={assistantOpen} onClose={() => setAssistantOpen(false)} />}
    </>
  );
}
