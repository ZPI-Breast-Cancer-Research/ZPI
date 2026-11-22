import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { errorText } from "../api";
import { useToast } from "../components/Toast";
import { useAuth, useCan } from "../auth/AuthProvider";
import { formatDate } from "../format";
import { t } from "../i18n";
import { queryKeys } from "../queryKeys";
import { attachReport, deleteReport, processReport, type StudyRow, type UnassignedReport } from "./api";
import ReportCard from "./ReportCard";

interface Props {
  reports: UnassignedReport[];
  studies: StudyRow[];
  // the study picked in the list, offered first
  selected: StudyRow | null;
}

// a report picks its study right under its card
export default function UnassignedReports({ reports, studies, selected }: Props) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [openId, setOpenId] = useState<string | null>(null);
  const can = useCan();
  const canDelete = can("addStudies");
  // the backend lets the roles that add studies or propose models order the processing
  const canProcess = can("addStudies") || can("proposeModels");
  const { user } = useAuth();
  // the first run is for anyone here; again: a researcher or an admin, a radiologist after a failure
  const processLabel = (report: UnassignedReport) => {
    if (!canProcess) return null;
    if (report.reading === "uploaded") return t("studies.unassigned.process");
    const again = report.reading === "failed" || (report.reading === "read" && (user?.role === "researcher" || user?.role === "admin"));
    return again ? t("studies.unassigned.processAgain") : null;
  };

  const waiting = studies.filter((s) => s.report === "missing");
  const candidates = selected?.report === "missing" ? [selected, ...waiting.filter((s) => s.id !== selected.id)] : waiting;

  const assign = useMutation({
    mutationFn: ({ study, report }: { study: StudyRow; report: UnassignedReport }) => attachReport(study.id, report.id),
    onSuccess: () => {
      toast(t("studies.attach.done"));
      setOpenId(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.studies });
      queryClient.invalidateQueries({ queryKey: queryKeys.unassignedReports });
    },
    onError: (error) => toast(t("studies.attach.failed", { why: errorText(error) })),
  });

  const remove = useMutation({
    mutationFn: (report: UnassignedReport) => deleteReport(report.id),
    onSuccess: (_, report) => {
      toast(t("studies.unassigned.delete.done", { name: report.fileName }));
      setOpenId(null);
      queryClient.invalidateQueries({ queryKey: queryKeys.unassignedReports });
    },
    onError: (error: Error) => toast(error.message || t("api.unknown")),
  });
  const process = useMutation({
    mutationFn: (report: UnassignedReport) => processReport(report.id),
    onSuccess: () => {
      toast(t("studies.unassigned.process.done"));
      queryClient.invalidateQueries({ queryKey: queryKeys.unassignedReports });
    },
    onError: (error: Error) => toast(error.message || t("api.unknown")),
  });
  const askDelete = (report: UnassignedReport) => {
    if (window.confirm(t("studies.unassigned.delete.confirm", { name: report.fileName }))) remove.mutate(report);
  };

  if (!reports.length) return <p className="note">{t("studies.unassigned.none")}</p>;

  return (
    <div>
      {reports.map((report) => (
        <ReportCard key={report.id} item={report} preview selected={openId === report.id} onSelect={() => setOpenId(openId === report.id ? null : report.id)}>
          <div className="assign">
            <p className="assign__title">{t("studies.assign.to")}</p>
            {candidates.length ? (
              candidates.map((study, i) => (
                <div key={study.id} className="assign__row">
                  <span>
                    {study.number && <b>#{study.number} · </b>}
                    {study.patientId} · {study.studyDate ? formatDate(study.studyDate) : "—"}
                  </span>
                  <button
                    type="button"
                    className={i === 0 && study.id === selected?.id ? "btn btn--small btn--primary" : "btn btn--small"}
                    disabled={assign.isPending}
                    onClick={() => assign.mutate({ study, report })}
                  >
                    {t("studies.unassigned.assign")}
                  </button>
                </div>
              ))
            ) : (
              <p className="note">{t("studies.assign.noStudies")}</p>
            )}
            {processLabel(report) && (
              <button type="button" className="btn btn--small" disabled={process.isPending} onClick={() => process.mutate(report)}>
                {processLabel(report)}
              </button>
            )}
            {canDelete && (
              <button type="button" className="btn btn--small" disabled={remove.isPending} onClick={() => askDelete(report)}>
                {t("studies.unassigned.delete")}
              </button>
            )}
          </div>
        </ReportCard>
      ))}
    </div>
  );
}
