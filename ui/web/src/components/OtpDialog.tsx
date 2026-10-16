import { useEffect, useState } from "react";
import { api } from "../api";
import type { OtpChallenge, Snapshot } from "../types";
import { Button } from "./common";

const MESSAGES: Record<string, string> = {
  invalid_code: "That code is not valid. Check the authenticator app and try again.",
  expired: "The 120-second approval window has closed. Request a new approval.",
  replayed: "That code was already used. Wait for the next code and try again.",
  payload_mismatch: "The pack changed after this approval was requested. Request a new approval.",
  DoubleFinancingBlocked: "This invoice is already in the registry and cannot be financed twice.",
};

interface Props {
  onClose: () => void;
  onApproved: (snapshot: Snapshot) => void;
  onFailed: (snapshot: Snapshot) => void;
}

export function OtpDialog({ onClose, onApproved, onFailed }: Props) {
  const [challenge, setChallenge] = useState<OtpChallenge | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [left, setLeft] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const request = () => {
    setError(null);
    setCode("");
    api.requestOtp().then(setChallenge).catch((e) => setError(e.message));
  };
  useEffect(request, []);

  useEffect(() => {
    if (!challenge) return;
    const tick = () => setLeft(Math.max(0, Math.round((new Date(challenge.expires_at).getTime() - Date.now()) / 1000)));
    tick();
    const id = window.setInterval(tick, 500);
    return () => window.clearInterval(id);
  }, [challenge]);

  const submit = async () => {
    if (code.length !== 6 || busy) return;
    setBusy(true);
    try {
      const result = await api.approve(code);
      if (result.ok) onApproved(result.snapshot);
      else {
        setError(MESSAGES[result.error ?? ""] ?? `Refused: ${result.error}`);
        onFailed(result.snapshot);
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const expired = left === 0;
  return (
    <div className="scrim" role="dialog" aria-modal="true">
      <div className="dialog">
        <div className="label">Level 3 action · Director approval</div>
        <h2>Submit the funding pack</h2>
        <p className="muted">
          The code is bound to this exact pack. Approving it cannot authorise a different pack, and editing the pack afterwards
          invalidates it. Each code works once.
        </p>
        {challenge && (
          <div className="hash"><span className="label">Action hash</span><br />{challenge.action_hash}</div>
        )}
        <input
          className="code" inputMode="numeric" maxLength={6} autoFocus placeholder="000000" value={code}
          onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
          onKeyDown={(e) => e.key === "Enter" && submit()}
        />
        <div className="muted num" style={{ fontSize: 12, minHeight: 20 }}>
          {challenge && !expired && left !== null && `Window closes in ${left} s`}
          {expired && "Window closed"}
        </div>
        {error && <div className="notice bad" style={{ marginBottom: 0 }}>{error}</div>}
        <div className="actions">
          <Button primary onClick={submit} disabled={code.length !== 6 || busy || expired}>Approve and submit</Button>
          {expired && <Button onClick={request}>Request again</Button>}
          <Button quiet onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </div>
  );
}
