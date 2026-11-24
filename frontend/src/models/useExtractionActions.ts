import { useMutation, useQueryClient } from "@tanstack/react-query";

import { errorText } from "../api";
import { useToast } from "../components/Toast";
import { t } from "../i18n";
import { queryKeys } from "../queryKeys";
import {
  addExample,
  applyExtraction,
  createVersion,
  proposeExtraction,
  rejectExtraction,
  updateDraft,
  withdrawExtraction,
  type DraftChanges,
} from "./extraction";

export function useExtractionActions() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: queryKeys.models });
  const onError = (error: unknown) => toast(t("models.action.failed", { why: errorText(error) }));
  return {
    create: useMutation({
      mutationFn: () => createVersion(),
      onSuccess: (v) => (toast(t("models.ext.created", { v })), refresh()),
      onError,
    }),
    update: useMutation({
      mutationFn: ({ version, changes }: { version: string; changes: DraftChanges }) => updateDraft(version, changes),
      onSuccess: (data) => (toast(t("models.ext.saved", { v: data.version })), refresh()),
      onError,
    }),
    addExample: useMutation({
      mutationFn: ({ version, reportId }: { version: string; reportId: number }) => addExample(version, reportId),
      onSuccess: () => refresh(),
      onError,
    }),
    apply: useMutation({
      mutationFn: ({ version }: { version: string }) => applyExtraction(version),
      onSuccess: (v) => (toast(t("models.ext.applied", { v })), refresh()),
      onError,
    }),
    reject: useMutation({
      mutationFn: ({ version, reason }: { version: string; reason: string }) => rejectExtraction(version, reason),
      onSuccess: (v) => (toast(t("models.reject.done", { v })), refresh()),
      onError,
    }),
    propose: useMutation({
      mutationFn: ({ version, reason }: { version: string; reason: string }) => proposeExtraction(version, reason),
      onSuccess: () => (toast(t("models.proposal.sent")), refresh()),
      onError,
    }),
    withdraw: useMutation({
      mutationFn: ({ version }: { version: string }) => withdrawExtraction(version),
      onSuccess: () => (toast(t("models.proposal.withdrawn")), refresh()),
      onError,
    }),
  };
}
