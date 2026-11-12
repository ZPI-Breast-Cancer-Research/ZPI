import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { errorText } from "../api";
import { t } from "../i18n";
import type { GateCheck } from "./api";
import GateList from "./GateList";

interface Props {
  title: string;
  // a researcher's proposal, or an admin's own change
  proposing: boolean;
  submitLabel: string;
  gate: { key: unknown[]; load: () => Promise<GateCheck[] | null> };
  pending: boolean;
  error: unknown;
  onSubmit: (reason: string, done: () => void) => void;
  onClose: () => void;
}

export default function ChangeDialog({ title, proposing, submitLabel, gate, pending, error, onSubmit, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState("");
  const checks = useQuery({ queryKey: ["models", "gate", ...gate.key], queryFn: gate.load });

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  const submit = () => {
    const text = reason.trim();
    if (text) onSubmit(text, () => dialog.current?.close());
  };

  return (
    <dialog ref={dialog} className="model-dialog" aria-label={title} onClose={onClose}>
      <form
        method="dialog"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <div className="model-dialog__head">{title}</div>
        <div className="model-dialog__body">
          {checks.isPending ? <p className="models__empty">{t("models.loading")}</p> : <GateList gate={checks.data ?? null} />}
          <label className="models__label" htmlFor="change-reason">
            {t(proposing ? "models.dialog.reason" : "models.dialog.adminReason")}
          </label>
          {proposing ? (
            <textarea id="change-reason" className="textarea" value={reason} onChange={(event) => setReason(event.target.value)} autoFocus />
          ) : (
            <input id="change-reason" className="input" value={reason} onChange={(event) => setReason(event.target.value)} autoFocus />
          )}
          <p className="field__help">{t(proposing ? "models.dialog.reasonHelp" : "models.dialog.adminReasonHelp")}</p>
          {error != null && (
            <p className="models__error" role="alert">
              {t("models.action.failed", { why: errorText(error) })}
            </p>
          )}
        </div>
        <div className="models__actions">
          <button type="button" className="btn" onClick={() => dialog.current?.close()}>
            {t("models.reject.cancel")}
          </button>
          <button type="submit" className="btn btn--primary" disabled={!reason.trim() || pending}>
            {submitLabel}
          </button>
        </div>
      </form>
    </dialog>
  );
}
