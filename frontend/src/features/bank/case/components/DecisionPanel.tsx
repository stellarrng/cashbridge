import { useState, type FormEvent } from "react";
import { useI18n } from "@/shared/i18n";
import { human } from "@/shared/lib/format";
import { Button, Panel } from "@/shared/ui";
import type { BankDecision, BankReview } from "../../types";

interface Props {
  review: BankReview;
  decided: boolean;
  checklist: string[];
  onDecide: (decision: BankDecision, note: string) => void;
}

/** A named person records the credit decision. The system never makes one. */
export function DecisionPanel({ review, decided, checklist, onDecide }: Props) {
  const { t } = useI18n();
  const [decision, setDecision] = useState<BankDecision>("APPROVE_FUNDING");
  const [note, setNote] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    onDecide(decision, note);
  };

  return (
    <Panel title={t("bk.decision")} sub={t("bk.decisionSub")}>
      {decided ? (
        <p><b>{human(review.decision)}</b> · {review.reviewer}{review.note ? ": " + review.note : ""}</p>
      ) : (
        <form onSubmit={submit}>
          <label className="field">
            Decision
            <select value={decision} onChange={(e) => setDecision(e.target.value as BankDecision)}>
              <option value="APPROVE_FUNDING">Approve funding (mock)</option>
              <option value="REQUEST_INFO">Request more information</option>
              <option value="DECLINE">Decline</option>
            </select>
          </label>
          <label className="field" style={{ marginTop: 10 }}>
            Note
            <textarea rows={3} maxLength={500} value={note} onChange={(e) => setNote(e.target.value)} placeholder="KYC completed offline; notice of assignment sent to the buyer." />
          </label>
          <div className="row" style={{ marginTop: 12 }}>
            <Button variant="bridge" type="submit">{t("bk.record")}</Button>
          </div>
        </form>
      )}
      <h3 className="mini">{t("bk.checklist")}</h3>
      <ul className="list small">{checklist.map((x, i) => <li key={i}>{x}</li>)}</ul>
    </Panel>
  );
}
