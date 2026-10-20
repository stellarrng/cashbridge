import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/inter/latin-700.css";
import "@fontsource/inter/vietnamese-400.css";
import "@fontsource/inter/vietnamese-500.css";
import "@fontsource/inter/vietnamese-600.css";
import "@fontsource/inter/vietnamese-700.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { SnapshotProvider } from "@/entities/case";
import { AuthProvider, useAuth } from "@/features/auth";
import { WorkspaceApp } from "@/features/workspace";
import { I18nProvider } from "@/shared/i18n";
import { trackInputModality } from "@/shared/lib/inputModality";
import { PreferencesProvider, applyStoredPreferences } from "@/shared/preferences";
import { ToastProvider, TooltipHost } from "@/shared/ui";
import "@/shared/styles/base.css";
import "@/shared/styles/app.css";

document.documentElement.classList.add("js");
applyStoredPreferences();
trackInputModality();

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
