import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError } from "../api";
import Page from "../components/layout/Page";
import Panel from "../components/layout/Panel";
import { useToast } from "../components/Toast";
import { t } from "../i18n";
import AttachReport from "../studies/AttachReport";
import DropZone from "../studies/DropZone";
import { FileTag, ImportTable, UnpairedReports } from "../studies/ImportReview";
import ProcessingSteps from "../studies/ProcessingSteps";
import StudiesTable, { parseFilter } from "../studies/StudiesTable";
import { listStudies, listUnassignedReports, sendStudies, type StudyRow } from "../studies/api";
import { groupFiles, type GroupedFiles } from "../studies/files";
import "../studies/studies.css";

function errorTitle(error: Error): string {
  const kind = error instanceof ApiError ? error.kind : "unknown";
  if (kind === "orthanc_unavailable") return t("studies.error.orthancUnavailable");
  if (kind === "orthanc_unauthorized") return t("studies.error.orthancUnauthorized");
  return t("studies.error.title");
}

export default function StudiesPage() {
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [imported, setImported] = useState<GroupedFiles | null>(null);
  const [attachFor, setAttachFor] = useState<StudyRow | null>(null);

  const studies = useQuery({ queryKey: ["studies"], queryFn: listStudies, retry: false });
  const unassigned = useQuery({ queryKey: ["unassigned-reports"], queryFn: listUnassignedReports });

  const selectedId = params.get("badanie");
  const selected = studies.data?.find((row) => row.id === selectedId) ?? null;
  const filter = parseFilter(params.get("filtr"));
  const updateParams = (changes: Record<string, string>) => setParams({ ...Object.fromEntries(params), ...changes });
  const select = (row: StudyRow) => updateParams({ badanie: row.id });

  const send = useMutation({
    mutationFn: () => sendStudies(imported?.studies.length ?? 0),
    onSuccess: () => {
      toast(t("studies.import.sent"));
      setImported(null);
    },
  });

  const assign = (report: File, folder: string) =>
    setImported((current) =>
      current && {
        studies: current.studies.map((study) => (study.folder === folder ? { ...study, report } : study)),
        unpairedReports: current.unpairedReports.filter((file) => file !== report),
      },
    );

  if (imported) {
    return (
      <Page
        title={t("studies.import.title")}
        context={
          <>
            <span>
              {t("studies.import.detected")} <b>{imported.studies.length}</b>
            </span>
            <span>
              {t("studies.import.unpaired")} <b>{imported.unpairedReports.length}</b>
            </span>
          </>
        }
        actions={
          <>
            <button type="button" className="btn" onClick={() => setImported(null)}>
              {t("studies.import.cancel")}
            </button>
            <button
              type="button"
              className="btn btn--primary"
              disabled={imported.studies.length === 0 || send.isPending}
              onClick={() => send.mutate()}
            >
              {t("studies.import.send")} ({imported.studies.length})
            </button>
          </>
        }
      >
        <div className="studies">
          <ImportTable studies={imported.studies} />
          <div className="studies__side">
            {imported.unpairedReports.length > 0 && (
              <UnpairedReports reports={imported.unpairedReports} studies={imported.studies} onAssign={assign} />
            )}
          </div>
        </div>
      </Page>
    );
  }

  const rows = studies.data ?? [];
  const counts = (
    <>
      <span>
        {t("studies.all")} <b>{rows.length}</b>
      </span>
      <span>
        {t("studies.processing")} <b>{rows.filter((r) => r.image === "processing" || r.image === "queued").length}</b>
      </span>
      <span>
        {t("studies.toReview")} <b>{rows.filter((r) => r.image === "to_review").length}</b>
      </span>
      <span>
        {t("studies.noReport")} <b>{rows.filter((r) => r.report === "missing").length}</b>
      </span>
    </>
  );

  return (
    <Page title={t("nav.studies")} context={studies.data && counts}>
      <div className="studies">
        <Panel title={t("studies.list")}>
          {studies.isPending ? (
            <p className="state">{t("studies.loading")}</p>
          ) : studies.error ? (
            <div className="state state--error" role="alert">
              <h3>{errorTitle(studies.error)}</h3>
              <p>{studies.error.message}</p>
              <button className="btn" onClick={() => studies.refetch()} disabled={studies.isFetching}>
                {studies.isFetching ? t("studies.retrying") : t("studies.retry")}
              </button>
            </div>
          ) : rows.length === 0 ? (
            <div className="state">
              <h3>{t("studies.empty.title")}</h3>
              <p>{t("studies.empty.body")}</p>
            </div>
          ) : (
            <StudiesTable
              rows={rows}
              selectedId={selectedId}
              onSelect={select}
              onAttach={setAttachFor}
              filter={filter}
              onFilter={(next) => updateParams({ filtr: next })}
            />
          )}
        </Panel>

        <div className="studies__side">
          {attachFor ? (
            <AttachReport study={attachFor} unassigned={unassigned.data ?? []} onClose={() => setAttachFor(null)} />
          ) : (
            <>
              <Panel title={t("studies.add")}>
                <div className="pad">
                  <DropZone
                    title={t("studies.drop.title")}
                    body={t("studies.drop.body")}
                    folderLabel={t("studies.drop.folder")}
                    filesLabel={t("studies.drop.files")}
                    onFiles={(files) => setImported(groupFiles(files))}
                  />
                  <p className="field__help">{t("studies.drop.hint")}</p>
                </div>
              </Panel>
              <Panel title={t("studies.unassigned")} aux={unassigned.data?.length ?? ""}>
                {unassigned.data && unassigned.data.length > 0 ? (
                  <table className="table">
                    <tbody>
                      {unassigned.data.map((report) => (
                        <tr key={report.id}>
                          <td>
                            <FileTag file={{ name: report.fileName }} />
                          </td>
                          <td className="cell-right">
                            {selected?.report === "missing" ? (
                              <button type="button" className="link" onClick={() => setAttachFor(selected)}>
                                {t("studies.unassigned.assign")}
                              </button>
                            ) : (
                              <button type="button" className="link" onClick={() => updateParams({ filtr: "no_report" })}>
                                {t("studies.unassigned.assign")}
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <p className="note">{t("studies.unassigned.none")}</p>
                )}
              </Panel>
              <ProcessingSteps study={selected} />
            </>
          )}
        </div>
      </div>
    </Page>
  );
}
