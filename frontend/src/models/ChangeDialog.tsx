import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { errorText } from "../api";
import { t } from "../i18n";
import { fetchGate } from "./api";
import GateList from "./GateList";
import { useModelActions } from "./useModelActions";

interface Props {
  // a researcher proposes, an admin changes the version on their own
  mode: "propose" | "change";
  version: string;
  replaces: string;
  restore: boolean;
  onClose: () => void;
}

export default function ChangeDialog({ mode, version, replaces, restore, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState("");
  const gate = useQuery({ queryKey: ["models", "gate", version], queryFn: () => fetchGate(version) });
  const actions = useModelActions();
  const proposing = mode === "propose";
  const pending = actions.propose.isPending || actions.promote.isPending || actions.rollback.isPending;
  const error = actions.propose.error ?? actions.promote.error ?? actions.rollback.error;

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  const title = proposing
    ? t(restore ? "models.dialog.proposeRestore" : "models.dialog.propose", { v: version, old: replaces })
    : t(restore ? "models.dialog.restore" : "models.dialog.change", { v: version, old: replaces });

  const submit = () => {
    const text = reason.trim();
    if (!text) return;
    const done = { onSuccess: () => dialog.current?.close() };
    if (proposing) actions.propose.mutate({ version, reason: text, restore }, done);
    else if (restore) actions.rollback.mutate({ version, reason: text }, done);
    else actions.promote.mutate({ version, reason: text }, done);
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
          {gate.isPending ? <p className="models__empty">{t("models.loading")}</p> : <GateList gate={gate.data ?? null} />}
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
            {t(proposing ? "models.dialog.send" : restore ? "models.restore" : "models.dialog.changeButton")}
          </button>
        </div>
      </form>
    </dialog>
  );
}
