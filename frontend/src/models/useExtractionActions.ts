import { useMutation, useQueryClient } from "@tanstack/react-query";

import { errorText } from "../api";
import { useToast } from "../components/Toast";
import { t } from "../i18n";
import { applyExtraction, proposeExtraction, rejectExtraction, withdrawExtraction, type ExtractionPart } from "./extraction";

type Target = { part: ExtractionPart; name: string };

export function useExtractionActions() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["models"] });
  const onError = (error: unknown) => toast(t("models.action.failed", { why: errorText(error) }));
  return {
    apply: useMutation({
      mutationFn: ({ part, name, reason }: Target & { reason?: string | null }) => applyExtraction(part, name, reason ?? null),
      onSuccess: (v) => (toast(t("models.ext.applied", { v })), refresh()),
      onError,
    }),
    reject: useMutation({
      mutationFn: ({ part, name, reason }: Target & { reason: string }) => rejectExtraction(part, name, reason),
      onSuccess: (v) => (toast(t("models.reject.done", { v })), refresh()),
      onError,
    }),
    propose: useMutation({
      mutationFn: ({ part, name, reason }: Target & { reason: string }) => proposeExtraction(part, name, reason),
      onSuccess: () => (toast(t("models.proposal.sent")), refresh()),
      onError,
    }),
    withdraw: useMutation({
      mutationFn: ({ part, name }: Target) => withdrawExtraction(part, name),
      onSuccess: () => (toast(t("models.proposal.withdrawn")), refresh()),
      onError,
    }),
  };
}
