import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { SnapshotProvider } from "@/entities/case";
import { AuthProvider, useAuth } from "@/features/auth";
import { WorkspaceApp } from "@/features/workspace";
import { I18nProvider } from "@/shared/i18n";
import { PreferencesProvider, applyStoredPreferences } from "@/shared/preferences";
import { ToastProvider, TooltipHost } from "@/shared/ui";
import "@/shared/styles/base.css";
import "@/shared/styles/app.css";
import "@/shared/styles/premium-ui.css";

applyStoredPreferences();

/** Only the SME portal has a case to load; the lender sees released packs through its own endpoints. */
function Workspace() {
  const { user } = useAuth();
  return (
    <SnapshotProvider enabled={user.portal === "sme"}>
      <WorkspaceApp />
    </SnapshotProvider>
  );
}

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <I18nProvider>
      <PreferencesProvider>
        <ToastProvider>
          <AuthProvider>
            <Workspace />
          </AuthProvider>
          <TooltipHost />
        </ToastProvider>
      </PreferencesProvider>
    </I18nProvider>
  </StrictMode>,
);
