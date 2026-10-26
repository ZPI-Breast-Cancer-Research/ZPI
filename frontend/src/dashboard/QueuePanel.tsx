import { Link, useNavigate } from "react-router-dom";

import Panel from "../components/layout/Panel";
import { formatDate, formatDecimal } from "../format";
import { t } from "../i18n";
import type { QueueItem } from "./api";

export default function QueuePanel({ items }: { items: QueueItem[] }) {
  const navigate = useNavigate();
  const open = (item: QueueItem) => navigate(`/weryfikacja/${item.studyId}`);

  return (
    <Panel title={t("dashboard.queue")} aux={t("dashboard.queue.hint")}>
      {items.length === 0 ? (
        <div className="state">
          <h3>{t("dashboard.queue.empty.title")}</h3>
          <p>{t("dashboard.queue.empty.body")}</p>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t("dashboard.col.number")}</th>
              <th>{t("dashboard.col.patient")}</th>
              <th>{t("dashboard.col.date")}</th>
              <th className="cell-right">{t("dashboard.col.uncertainty")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr
                key={item.studyId}
                className="is-clickable"
                tabIndex={0}
                onClick={() => open(item)}
                onKeyDown={(event) => event.key === "Enter" && open(item)}
              >
                <td className="cell-strong">#{item.studyNumber}</td>
                <td>{item.patientId}</td>
                <td>{formatDate(item.studyDate)}</td>
                <td className="cell-right">{formatDecimal(item.uncertainty)}</td>
                <td className="cell-right">
                  <Link className="link" to={`/weryfikacja/${item.studyId}`} onClick={(event) => event.stopPropagation()}>
                    {t("dashboard.review")}
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
