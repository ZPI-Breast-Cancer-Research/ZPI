import { useState } from "react";

import { useCan } from "../auth/AuthProvider";
import { t } from "../i18n";

interface Props {
  // version number or model name
  name: string;
  approveLabel: string;
  mine: boolean;
  pending: boolean;
  onApprove: () => void;
  onReject: (reason: string) => void;
  onWithdraw: () => void;
}

export default function ProposalActions({ name, approveLabel, mine, pending, onApprove, onReject, onWithdraw }: Props) {
  const manages = useCan()("manageModels");
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");

  if (!manages) {
    return (
      <div className="models__actions">
        <span className="models__waiting">{t("models.proposal.waiting")}</span>
        {mine && (
          <button type="button" className="btn" disabled={pending} onClick={onWithdraw}>
            {t("models.proposal.withdraw")}
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="models__actions">
      {rejecting ? (
        <div className="reason">
          <label className="field__help" htmlFor="reject-reason">
            {t("models.reject.reason")}
          </label>
          <textarea id="reject-reason" className="textarea" value={reason} onChange={(event) => setReason(event.target.value)} autoFocus />
          <div className="reason__row">
            <button type="button" className="btn" onClick={() => setRejecting(false)}>
              {t("models.reject.cancel")}
            </button>
            <button type="button" className="btn btn--primary" disabled={!reason.trim() || pending} onClick={() => onReject(reason.trim())}>
              {t("models.reject.confirm", { v: name })}
            </button>
          </div>
        </div>
      ) : (
        <>
          <button type="button" className="btn" onClick={() => setRejecting(true)}>
            {t("models.reject")}
          </button>
          <button type="button" className="btn btn--primary" disabled={pending} onClick={onApprove}>
            {approveLabel}
          </button>
        </>
      )}
    </div>
  );
}
