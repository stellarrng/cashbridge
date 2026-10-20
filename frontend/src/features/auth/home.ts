import type { SessionUser } from "@/shared/api/session";

/** Role-based home screen: the lender reviews cases, the Director decides, the accountant works the queue. */
export function homeRoute(user: Pick<SessionUser, "portal" | "permissions">): string {
  if (user.portal === "bank") return "inbox";
  return user.permissions.includes("sme:approve") ? "core" : "overview";
}
