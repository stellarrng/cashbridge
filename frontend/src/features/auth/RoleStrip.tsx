import { useAct } from "@/shared/hooks";
import { useI18n } from "@/shared/i18n";
import { Button } from "@/shared/ui";
import { useAuth } from "./AuthProvider";

/** Role banner with one-click persona switching (DEMO mode lists the demo accounts). */
export function RoleStrip() {
  const { t } = useI18n();
  const { user, config, viewAs } = useAuth();
  const act = useAct();
  const people = config?.demo_accounts ?? [];
  return (
    <div className="role-strip">
      <span className="pill">{t("role." + user.role)}</span>
      <span className="rs-note">{t("role.note." + user.role)}</span>
      {people.length > 0 && (
        <span className="rs-switch">
          <span className="muted small">{t("app.viewAs")}</span>
          {people.map((a) => (
            <Button key={a.user_id} small variant={a.user_id === user.user_id ? "bridge" : "ghost"} data-tip={`${t("role." + a.role)} · ${a.org}`} onClick={() => void act(() => viewAs(a.user_id))}>
              {a.name}
            </Button>
          ))}
        </span>
      )}
    </div>
  );
}
