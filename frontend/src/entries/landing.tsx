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
import { LandingPage } from "@/features/landing";
import { I18nProvider } from "@/shared/i18n";
import { trackInputModality } from "@/shared/lib/inputModality";
import { PreferencesProvider, applyStoredPreferences } from "@/shared/preferences";
import { TooltipHost } from "@/shared/ui";
import "@/shared/styles/base.css";
import "@/shared/styles/landing.css";

document.documentElement.classList.add("js");
applyStoredPreferences();
trackInputModality();

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
