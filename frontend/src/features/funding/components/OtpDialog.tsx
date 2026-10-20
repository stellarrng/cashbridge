import { useEffect, useState, type FormEvent } from "react";
import { ApiError } from "@/shared/api/client";
import { useI18n } from "@/shared/i18n";
import { Button, Modal } from "@/shared/ui";
import { useAuth } from "../../auth";
import { approvePack } from "../api";
import type { OtpChallenge } from "../types";

const ERRORS: Record<string, string> = {
  invalid_code: "That code is not valid for this pack. Check your device's clock and try again.",
  replayed: "That code was already used. Wait for the next one.",
  expired: "The approval window closed. Cancel and open it again.",
  segregation_of_duties: "You prepared this pack, so you cannot approve it.",
  DoubleFinancingBlocked: "This invoice is already financed.",
};

interface Props {
  challenge: OtpChallenge | null;
  onClose: () => void;
  onApproved: () => void;
}

/** The Director's one-time-code approval. The code is bound to this exact pack and works once. */
export function OtpDialog({ challenge, onClose, onApproved }: Props) {
  const { t } = useI18n();
  const { config } = useAuth();
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (challenge) {
      setCode("");
      setError("");
    }
  }, [challenge]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const digits = code.trim();
    if (!/^\d{6}$/.test(digits)) return setError("6 digits");
    setBusy(true);
    try {
      const r = await approvePack(digits);
      if (!r.ok) setError(ERRORS[r.error ?? ""] ?? r.error ?? "");
      else onApproved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={challenge !== null} titleId="otpTitle" onClose={onClose}>
      {challenge && (
        <form onSubmit={submit}>
          <h2 id="otpTitle">{t("otp.title")}</h2>
          <p className="muted">{challenge.instructions} ({new Date(challenge.expires_at).toLocaleTimeString()})</p>
          <p className="hashline"><span>{t("otp.bound")}</span> <span className="mono">{challenge.action_hash}</span></p>
          <label className="field">
            <span>{t("otp.code")}</span>
            <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" maxLength={6} pattern="[0-9]{6}" />
          </label>
          <p className="muted small">{config?.otp_demo_secret ? <>Demo: <span className="mono">{config.otp_demo_secret}</span> (Base32, 30 s)</> : null}</p>
          <p className="err" role="alert">{error}</p>
          <div className="row">
            <Button variant="bridge" type="submit" disabled={busy}>{t("otp.approve")}</Button>
            <Button variant="ghost" onClick={onClose}>{t("otp.cancel")}</Button>
          </div>
        </form>
      )}
    </Modal>
  );
}
