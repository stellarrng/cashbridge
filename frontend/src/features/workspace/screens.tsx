import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import type { ScreenProps } from "@/shared/lib/screen";

type Screen = LazyExoticComponent<ComponentType<ScreenProps>>;

/** One entry per screen. Each feature is its own lazy chunk, so a role only downloads the screens it opens. */
export const SCREENS: Record<string, Screen> = {
  overview: lazy(() => import("../overview")),
  autopilot: lazy(() => import("../autopilot")),
  core: lazy(() => import("../decision-center")),
  cash: lazy(() => import("../cash-forecast")),
  evidence: lazy(() => import("../receivables")),
  funding: lazy(() => import("../funding")),
  analytics: lazy(() => import("../financial-health")),
  project: lazy(() => import("../bid-simulator")),
  contracts: lazy(() => import("../contracts")),
  green: lazy(() => import("../green-finance")),
  trust: lazy(() => import("../audit-trust")),
  settings: lazy(() => import("../settings")),
  inbox: lazy(() => import("../bank/inbox")),
  case: lazy(() => import("../bank/case")),
};
