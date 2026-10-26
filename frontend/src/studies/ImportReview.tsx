import Panel from "../components/layout/Panel";
import { EmptyState } from "../components/State";
import WarningIcon from "../components/WarningIcon";
import { t } from "../i18n";
import type { DetectedStudy } from "./files";

export function FileTag({ file }: { file: { name: string } }) {
  const ext = file.name.split(".").pop()?.toUpperCase() ?? "";
  return (
    <span className="file-tag">
      <span className="file-tag__ext">{ext.slice(0, 4)}</span>
      {file.name}
    </span>
  );
}

export function ImportTable({ studies }: { studies: DetectedStudy[] }) {
  return (
    <Panel title={t("studies.import.table")} aux={t("studies.import.tableHint")}>
      {studies.length === 0 ? (
        <EmptyState title={t("studies.import.nothing")} />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t("studies.import.col.folder")}</th>
              <th className="cell-right">{t("studies.import.col.files")}</th>
              <th>{t("studies.import.col.report")}</th>
              <th>{t("studies.import.col.status")}</th>
            </tr>
          </thead>
          <tbody>
            {studies.map((study) => (
              <tr key={study.folder}>
                <td className="cell-strong">{study.folder}</td>
                <td className="cell-right">{study.dicomFiles.length}</td>
                <td>{study.report ? <FileTag file={study.report} /> : <span className="muted">{t("studies.import.noReport")}</span>}</td>
                <td>
                  <span className="status status--confirmed">{t("studies.import.ready")}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="note">{t("studies.import.note")}</p>
    </Panel>
  );
}

interface UnpairedProps {
  reports: File[];
  studies: DetectedStudy[];
  onAssign: (report: File, folder: string) => void;
}

export function UnpairedReports({ reports, studies, onAssign }: UnpairedProps) {
  const free = studies.filter((study) => !study.report);
  return (
    <Panel title={t("studies.import.unpaired")} aux={reports.length}>
      <div className="pad">
        {reports.map((report) => (
          <div key={report.name} className="pick">
            <WarningIcon />
            <FileTag file={report} />
            {free.length > 0 && (
              <select
                className="select pick__select"
                aria-label={t("studies.import.assignTo")}
                defaultValue=""
                onChange={(event) => event.target.value && onAssign(report, event.target.value)}
              >
                <option value="" disabled>
                  {t("studies.import.assignTo")}
                </option>
                {free.map((study) => (
                  <option key={study.folder} value={study.folder}>
                    {study.folder}
                  </option>
                ))}
              </select>
            )}
          </div>
        ))}
        <p className="field__help">{t("studies.import.unpairedNote")}</p>
      </div>
    </Panel>
  );
}
