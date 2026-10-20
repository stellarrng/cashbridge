import type { SessionUser } from "@/shared/api/session";

export type NavGroup = readonly [titleKey: string, items: readonly string[]];

const ACCOUNTANT: NavGroup[] = [
  ["grp.decide", ["overview", "autopilot", "evidence", "cash", "funding"]],
  ["grp.analyse", ["analytics", "project", "contracts", "green"]],
  ["grp.control", ["trust", "workspace"]],
  ["grp.system", ["settings"]],
];
const DIRECTOR: NavGroup[] = [
  ["grp.decide", ["core", "funding", "cash"]],
  ["grp.analyse", ["analytics", "project", "green"]],
  ["grp.control", ["trust", "workspace"]],
  ["grp.system", ["settings"]],
];
const SME_ALL: NavGroup[] = [
  ["grp.decide", ["overview", "autopilot", "core", "cash", "evidence", "funding"]],
  ["grp.analyse", ["analytics", "project", "contracts", "green"]],
  ["grp.control", ["trust", "workspace"]],
  ["grp.system", ["settings"]],
];
const BANK: NavGroup[] = [
  ["grp.review", ["inbox", "trust", "workspace"]],
  ["grp.system", ["settings"]],
];

/**
 * A task-focused projection of the permissions the SERVER issued. It is never the authorization boundary:
 * every API call is checked against the session again.
 */
export function navigationFor(user: SessionUser): NavGroup[] {
  if (user.portal === "bank") return BANK;
  const approve = user.permissions.includes("sme:approve");
  const prepare = user.permissions.includes("sme:prepare");
  if (approve && !prepare) return DIRECTOR;
  if (prepare && !approve) return ACCOUNTANT;
  return SME_ALL;
}

/** Screens a person may open (a hidden link is not a permission, this just keeps the URL tidy). */
export function allowedScreens(user: SessionUser): string[] {
  if (user.portal === "bank") return ["inbox", "case", "workspace", "trust", "settings"];
  return navigationFor(user).flatMap((g) => [...g[1]]);
}
