import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import Panel from "../components/layout/Panel";
import { useToast } from "../components/Toast";
import { t } from "../i18n";
import { attachReport, type StudyRow, type UnassignedReport } from "./api";
import DropZone from "./DropZone";
import { FileTag } from "./ImportReview";
import ReportCard from "./ReportCard";

interface Props {
  study: StudyRow;
  unassigned: UnassignedReport[];
  onClose: () => void;
}

export default function AttachReport({ study, unassigned, onClose }: Props) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [existing, setExisting] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  useEffect(() => {
    setPreview(null);
    if (file && file.name.toLowerCase().endsWith(".txt")) {
      file.text().then((text) => setPreview(text.slice(0, 600)));
    }
  }, [file]);

  const submit = useMutation({
    mutationFn: () => attachReport(study.id, file ?? existing!),
    onSuccess: () => {
      toast(t("studies.attach.done"));
      queryClient.invalidateQueries({ queryKey: ["studies"] });
      // an existing report leaves the unassigned list; a new file may fail its extraction there
      queryClient.invalidateQueries({ queryKey: ["unassigned-reports"] });
      queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      onClose();
    },
  });

  const chosen = file !== null || existing !== null;
  const isScan = file !== null && !file.name.toLowerCase().endsWith(".txt");

  return (
    <Panel
      title={
        study.number
          ? t("studies.attach.titleFor", { n: study.number, patient: study.patientId })
          : t("studies.attach.titleForNoNumber", { patient: study.patientId })
      }
      className="attach"
    >
      <div className="pad">
        <DropZone
          title={t("studies.attach.drop")}
          body={t("studies.attach.dropBody")}
          accept=".txt,.jpg,.jpeg,.png"
          multiple={false}
          filesLabel={t("studies.attach.pick")}
          onFiles={([picked]) => {
            setFile(picked);
            setExisting(null);
          }}
        >
          {file && (
            <div className="drop__picked">
              <FileTag file={file} />
            </div>
          )}
        </DropZone>

        {unassigned.length > 0 && (
          <>
            <div className="or">{t("studies.attach.or")}</div>
            <div className="attach__reports">
              {unassigned.map((report) => (
                <ReportCard
                  key={report.id}
                  item={report}
                  selected={existing === report.id && file === null}
                  onSelect={() => {
                    setExisting(report.id);
                    setFile(null);
                  }}
                />
              ))}
            </div>
          </>
        )}

        {preview !== null && <pre className="report-preview">{preview}</pre>}
        {isScan && <p className="field__help">{t("studies.attach.scan")}</p>}
        <p className="field__help">{t("studies.attach.hint")}</p>
      </div>
      <div className="panel__foot">
        <button type="button" className="btn" onClick={onClose}>
          {t("studies.attach.cancel")}
        </button>
        <button type="button" className="btn btn--primary" disabled={!chosen || submit.isPending} onClick={() => submit.mutate()}>
          {study.number ? t("studies.attach.submitTo", { n: study.number }) : t("studies.attach.submit")}
        </button>
      </div>
    </Panel>
  );
}
