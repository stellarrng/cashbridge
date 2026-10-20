import { useEffect, useState, type FormEvent } from "react";
import { useI18n } from "@/shared/i18n";
import { Button, Modal } from "@/shared/ui";

/** The Director's reason for sending a pack back to the accountant (at least 3 characters). */
export function RejectDialog({ open, onClose, onSubmit }: { open: boolean; onClose: () => void; onSubmit: (reason: string) => void }) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  useEffect(() => {
    if (open) setReason("");
  }, [open]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (reason.trim().length >= 3) onSubmit(reason.trim());
  };

  return (
    <Modal open={open} titleId="rejectTitle" onClose={onClose}>
      <form onSubmit={submit}>
        <h2 id="rejectTitle">{t("fund.reject")}</h2>
        <label className="field">
          <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} required minLength={3} />
        </label>
        <div className="row mt-2">
          <Button variant="danger" type="submit" disabled={reason.trim().length < 3}>{t("fund.reject")}</Button>
          <Button variant="ghost" onClick={onClose}>{t("otp.cancel")}</Button>
        </div>
      </form>
    </Modal>
  );
}
