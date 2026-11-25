import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { errorText } from "../api";
import Select from "../components/Select";
import { t } from "../i18n";
import { queryKeys } from "../queryKeys";
import { fetchLlmModels, fetchVersion, type VersionConfig } from "./extraction";
import { useExtractionActions } from "./useExtractionActions";

type Example = VersionConfig["fewShotExamples"][number];

const exampleTitle = (example: Example) => example.report.trim().split("\n")[0]?.slice(0, 80) || t("models.draft.untitled");

// A draft of an extraction version: the language model, structured output and the few-shot
// examples; the backend refuses changes once the version is proposed.
function DraftForm({ config, onClose }: { config: VersionConfig; onClose: () => void }) {
  const actions = useExtractionActions();
  const queryClient = useQueryClient();
  const models = useQuery({ queryKey: queryKeys.llmModels, queryFn: fetchLlmModels, retry: false });
  const [llmModel, setLlmModel] = useState(config.llmModel);
  const [structured, setStructured] = useState(config.structuredOutput);
  const [examples, setExamples] = useState<Example[]>(config.fewShotExamples);
  const [reportId, setReportId] = useState("");

  // the server's models, and the one the draft has even when the server no longer offers it
  const choices = models.data ? [...new Set([config.llmModel, ...models.data].filter(Boolean))] : null;
  const changed = llmModel !== config.llmModel || structured !== config.structuredOutput || examples !== config.fewShotExamples;

  const save = () =>
    actions.update.mutate(
      {
        version: config.version,
        changes: {
          ...(llmModel !== config.llmModel && { llm_model: llmModel.trim() }),
          ...(structured !== config.structuredOutput && { structured_output: structured }),
          ...(examples !== config.fewShotExamples && { few_shot_examples: examples }),
        },
      },
      { onSuccess: onClose },
    );

  const add = () => {
    const id = Number(reportId);
    if (!Number.isInteger(id) || id <= 0) return;
    actions.addExample.mutate(
      { version: config.version, reportId: id },
      {
        onSuccess: (data) => {
          // the example joins the list on screen; unsaved removals stay as they are
          const added = data.fewShotExamples.filter((e) => !examples.some((kept) => kept.report === e.report));
          setExamples([...examples, ...added]);
          setReportId("");
          queryClient.setQueryData(queryKeys.extractionVersion(config.version), data);
        },
      },
    );
  };

  return (
    <>
      <div className="model-dialog__body">
        <label className="models__label" htmlFor="draft-llm">
          {t("models.ext.llm")}
        </label>
        {choices ? (
          <Select id="draft-llm" className="field-select--form" value={llmModel} options={choices} placeholder={t("models.draft.pickModel")} onChange={setLlmModel} />
        ) : (
          <input id="draft-llm" className="input" value={llmModel} onChange={(event) => setLlmModel(event.target.value)} />
        )}
        {models.isError && <p className="field__help">{t("models.draft.llmUnavailable", { why: errorText(models.error) })}</p>}

        <label className="models__check">
          <input type="checkbox" checked={structured} onChange={(event) => setStructured(event.target.checked)} />
          {t("models.draft.structured")}
        </label>
        <p className="field__help">{t("models.draft.structuredHelp")}</p>

        <p className="models__label">{t("models.draft.examples", { n: examples.length })}</p>
        {examples.length ? (
          <ul className="draft__examples">
            {examples.map((example, i) => (
              <li key={`${example.report_id ?? "file"}-${i}`}>
                <span>{exampleTitle(example)}</span>
                <button type="button" className="btn btn--small" onClick={() => setExamples(examples.filter((_, k) => k !== i))}>
                  {t("models.draft.remove")}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="models__empty">{t("models.examples.none")}</p>
        )}
        <label className="models__label" htmlFor="draft-report">
          {t("models.draft.addFromReport")}
        </label>
        <div className="reason__row">
          <input id="draft-report" className="input" inputMode="numeric" value={reportId} onChange={(event) => setReportId(event.target.value.replace(/\D/g, ""))} />
          <button type="button" className="btn btn--small" disabled={!reportId || actions.addExample.isPending} onClick={add}>
            {t("models.draft.add")}
          </button>
        </div>
        <p className="field__help">{t("models.draft.addHelp")}</p>

        {actions.update.error != null && (
          <p className="models__error" role="alert">
            {t("models.action.failed", { why: errorText(actions.update.error) })}
          </p>
        )}
      </div>
      <div className="models__actions">
        <button type="button" className="btn" onClick={onClose}>
          {t("models.reject.cancel")}
        </button>
        <button type="button" className="btn btn--primary" disabled={!changed || !llmModel.trim() || actions.update.isPending} onClick={save}>
          {t("models.draft.save")}
        </button>
      </div>
    </>
  );
}

export default function DraftDialog({ version, onClose }: { version: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const config = useQuery({ queryKey: queryKeys.extractionVersion(version), queryFn: () => fetchVersion(version) });

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  const title = t("models.draft.title", { v: version });
  return (
    <dialog ref={dialog} className="model-dialog" aria-label={title} onClose={onClose}>
      <div className="model-dialog__head">{title}</div>
      {config.isPending ? (
        <p className="models__pad models__empty">{t("models.loading")}</p>
      ) : config.isError ? (
        <p className="models__pad models__error">{t("models.action.failed", { why: errorText(config.error) })}</p>
      ) : (
        <DraftForm config={config.data} onClose={() => dialog.current?.close()} />
      )}
    </dialog>
  );
}
