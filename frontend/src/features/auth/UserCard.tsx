import type { SessionUser } from "@/shared/api/session";
import { useI18n } from "@/shared/i18n";
import { useAuth } from "./AuthProvider";

export function UserCard({ user }: { user: SessionUser }) {
  const { t } = useI18n();
  const { config } = useAuth();
  const initials =
    config?.demo_accounts.find((a) => a.user_id === user.user_id)?.initials ??
    user.name.split(" ").map((x) => x[0]).join("").slice(0, 2);
  return (
    <>
      <span className="av" aria-hidden="true">{initials}</span>
      <span>
        <b>{user.name}</b>
        <span>{t("role." + user.role)}</span>
      </span>
    </>
  );
}
