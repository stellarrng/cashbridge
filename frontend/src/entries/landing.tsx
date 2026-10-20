import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { LandingPage } from "@/features/landing";
import { I18nProvider } from "@/shared/i18n";
import { PreferencesProvider, applyStoredPreferences } from "@/shared/preferences";
import { TooltipHost } from "@/shared/ui";
import "@/shared/styles/base.css";
import "@/shared/styles/landing.css";
import "@/shared/styles/premium-ui.css";

applyStoredPreferences();

createRoot(document.getElementById("root") as HTMLElement).render(
  <StrictMode>
    <I18nProvider>
      <PreferencesProvider>
        <LandingPage />
        <TooltipHost />
      </PreferencesProvider>
    </I18nProvider>
  </StrictMode>,
);
