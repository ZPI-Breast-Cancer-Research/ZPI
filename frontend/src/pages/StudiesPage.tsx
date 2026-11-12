import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";

import { ApiError, errorText } from "../api";
import { useCan } from "../auth/AuthProvider";
import Page from "../components/layout/Page";
import { EmptyState, ErrorState, LoadingState } from "../components/State";
import Panel from "../components/layout/Panel";
import { useToast } from "../components/Toast";
import { t, type MessageKey } from "../i18n";
import AttachReport from "../studies/AttachReport";
import DropZone from "../studies/DropZone";
import { ImportTable, UnpairedReports } from "../studies/ImportReview";
import ProcessingSteps from "../studies/ProcessingSteps";
import UnassignedReports from "../studies/UnassignedReports";
import StudiesTable, { matches, parseFilter, parsePart } from "../studies/StudiesTable";
import { listStudies, listUnassignedReports, sendStudy, type StudyRow } from "../studies/api";
import { groupFiles, type GroupedFiles } from "../studies/files";
import "../studies/studies.css";
import JSZip from "jszip";

function errorTitle(error: Error): string {
  const kind = error instanceof ApiError ? error.kind : "unknown";
  if (kind === "orthanc_unavailable") return t("studies.error.orthancUnavailable");
  if (kind === "orthanc_unauthorized") return t("studies.error.orthancUnauthorized");
  return t("studies.error.title");
}

export default function StudiesPage() {
  const toast = useToast();
  const adds = useCan()("addStudies");
  const [params, setParams] = useSearchParams();
  const [imported, setImported] = useState<GroupedFiles | null>(null);
  const [attachFor, setAttachFor] = useState<StudyRow | null>(null);
  const notice = (useLocation().state as { notice?: MessageKey } | null)?.notice;

  // e.g. the review queue ran out on the way here
  useEffect(() => {
    if (notice) toast(t(notice));
  }, [notice, toast]);

  const studies = useQuery({ queryKey: ["studies"], queryFn: listStudies, retry: false });
  const unassigned = useQuery({ queryKey: ["unassigned-reports"], queryFn: listUnassignedReports });

  const selectedId = params.get("badanie");
  const selected = studies.data?.find((row) => row.id === selectedId) ?? null;
  const filter = parseFilter(params.get("filtr"));
  const updateParams = (changes: Record<string, string>) => setParams({ ...Object.fromEntries(params), ...changes });
  const select = (row: StudyRow) => {
    updateParams({ badanie: row.id });
    // attaching a report belongs to the row it was opened for
    if (attachFor && attachFor.id !== row.id) setAttachFor(null);
  };
  const attach = (row: StudyRow) => {
    updateParams({ badanie: row.id });
    setAttachFor(row);
  };

const send = useMutation({
  mutationFn: async () => {
    if (!imported || (imported.studies.length === 0 && imported.unpairedReports.length === 0)) {
      throw new Error(t("api.sendFailed"));
    }

    const studyItem = imported.studies[0];
    const dicomFiles: File[] = studyItem?.dicomFiles || [];

    let archiveFile: File | undefined = undefined;

    if (dicomFiles.length > 0) {
      const isSingleZip = dicomFiles.length === 1 && dicomFiles[0].name.toLowerCase().endsWith(".zip");

      if (isSingleZip) {
        archiveFile = dicomFiles[0]; 
      } else {
        const zip = new JSZip();
        for (const file of dicomFiles) {
          const path = file.webkitRelativePath || file.name;
          zip.file(path, file);
        }
        const zipBlob = await zip.generateAsync({ type: "blob" });
        archiveFile = new File([zipBlob], `${studyItem?.folder && studyItem.folder !== "—" ? studyItem.folder : "study"}_archive.zip`, { type: "application/zip" });
      }
    }

    const reportFile: File | undefined = studyItem?.report || imported.unpairedReports[0];

    return await sendStudy(archiveFile, reportFile);
  },
  onSuccess: () => {
    toast(t("studies.import.sent"));
    setImported(null);
    studies.refetch();
    unassigned.refetch();
  },
  onError: (error: Error) => {
    toast(error.message || t("api.sendFailed"));
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
              disabled={(imported.studies.length === 0 && imported.unpairedReports.length === 0)|| send.isPending}
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
        {t("studies.processing")} <b>{rows.filter((r) => matches(r, "processing")).length}</b>
      </span>
      <span>
        {t("studies.toReview")} <b>{rows.filter((r) => matches(r, "to_review")).length}</b>
      </span>
      <span>
        {t("studies.noReport")} <b>{rows.filter((r) => matches(r, "no_report")).length}</b>
      </span>
    </>
  );

  return (
    <Page title={t("nav.studies")} context={studies.data && counts}>
      <div className="studies">
        <Panel title={t("studies.list")}>
          {studies.isPending ? (
            <LoadingState label={t("studies.loading")} />
          ) : studies.error ? (
            <ErrorState title={errorTitle(studies.error)} body={errorText(studies.error)} onRetry={() => studies.refetch()} retrying={studies.isFetching} />
          ) : rows.length === 0 ? (
            <EmptyState title={t("studies.empty.title")} body={t("studies.empty.body")} />
          ) : (
            <StudiesTable
              rows={rows}
              selectedId={selectedId}
              onSelect={select}
              onAttach={attach}
              filter={filter}
              onFilter={(next) => updateParams({ filtr: next })}
              today={params.get("dzis") !== "0"}
              onToday={(today) => updateParams({ dzis: today ? "1" : "0" })}
              part={parsePart(params.get("czeka"))}
              onPart={(part) => {
                const next = new URLSearchParams(params);
                if (part === "all") next.delete("czeka");
                else next.set("czeka", part === "mask" ? "maska" : "opis");
                setParams(next);
              }}
            />
          )}
        </Panel>

        <div className="studies__side">
          {attachFor ? (
            <AttachReport study={attachFor} unassigned={unassigned.data ?? []} onClose={() => setAttachFor(null)} />
          ) : (
            <>
              {/* adding studies and pairing reports is the radiologist's job */}
              {adds && (
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
                    <UnassignedReports reports={unassigned.data ?? []} studies={studies.data ?? []} selected={selected} />
                  </Panel>
                </>
              )}
              <ProcessingSteps study={selected} />
            </>
          )}
        </div>
      </div>
    </Page>
  );
}
