import { useEffect, useState, type FormEvent } from "react";
import { useI18n } from "@/shared/i18n";
import { Button, Modal } from "@/shared/ui";

interface Props {
  open: boolean;
  /** "reject": the Director sends the pack back; "withdraw": the Director takes a released pack back from the lender. */
  mode?: "reject" | "withdraw";
  onClose: () => void;
  onSubmit: (reason: string) => void;
}

/** The Director's reason (3 to 300 characters), shown to the preparer or recorded with the consent withdrawal. */
export function RejectDialog({ open, mode = "reject", onClose, onSubmit }: Props) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (open) {
      setReason("");
      setError("");
    }
  }, [open]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (reason.trim().length < 3) return setError(t("fund.rejectReason"));
    onSubmit(reason.trim());
  };
  const send = t(mode === "withdraw" ? "fund.withdraw" : "fund.reject");

  return (
    <Modal id="rejectModal" open={open} titleId="rejectTitle" onClose={onClose}>
      <form onSubmit={submit}>
        <h2 id="rejectTitle">{t(mode === "withdraw" ? "fund.withdrawTitle" : "fund.rejectTitle")}</h2>
        <label className="field">
          <span>{t("fund.rejectReason")}</span>
          <textarea id="rejectReason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} />
        </label>
        <p className="err" id="rejectErr" role="alert">{error}</p>
        <div className="row mt-2">
          <Button variant="danger" type="submit" id="rejectSend">{send}</Button>
          <Button variant="ghost" onClick={onClose}>{t("otp.cancel")}</Button>
        </div>
      </form>
    </Modal>
  );
}
