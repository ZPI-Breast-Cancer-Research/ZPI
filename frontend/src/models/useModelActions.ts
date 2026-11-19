import { useMutation, useQueryClient } from "@tanstack/react-query";

import { errorText } from "../api";
import { useToast } from "../components/Toast";
import { t } from "../i18n";
import { promote, propose, reject, rollback, startTraining, stopTraining, withdraw } from "./api";

type Change = { version: string; reason?: string | null };

export function useModelActions() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["models"] });
  const onError = (error: unknown) => toast(t("models.action.failed", { why: errorText(error) }));
  return {
    promote: useMutation({
      mutationFn: ({ version, reason }: Change) => promote(version, reason ?? null),
      onSuccess: (v) => (toast(t("models.promote.done", { v })), refresh()),
      onError,
    }),
    reject: useMutation({
      mutationFn: ({ version, reason }: { version: string; reason: string }) => reject(version, reason),
      onSuccess: (v) => (toast(t("models.reject.done", { v })), refresh()),
      onError,
    }),
    rollback: useMutation({
      mutationFn: ({ version, reason }: Change) => rollback(version, reason ?? null),
      onSuccess: (v) => (toast(t("models.restore.done", { v })), refresh()),
      onError,
    }),
    propose: useMutation({
      mutationFn: ({ version, reason, restore }: { version: string; reason: string; restore: boolean }) => propose(version, reason, restore),
      onSuccess: () => (toast(t("models.proposal.sent")), refresh()),
      onError,
    }),
    withdraw: useMutation({ mutationFn: withdraw, onSuccess: () => (toast(t("models.proposal.withdrawn")), refresh()), onError }),
    train: useMutation({ mutationFn: startTraining, onSuccess: () => (toast(t("models.next.started")), refresh()), onError }),
    stop: useMutation({ mutationFn: stopTraining, onSuccess: () => (toast(t("models.training.stopped")), refresh()), onError }),
  };
}
