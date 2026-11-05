import { Link, useNavigate } from "react-router-dom";

import Panel from "../components/layout/Panel";
import { EmptyState } from "../components/State";
import { formatDate, formatDecimal } from "../format";
import { t } from "../i18n";
import type { QueueItem } from "./api";

// only a radiologist opens cases; the others see the queue as it stands
export default function QueuePanel({ items, canOpen }: { items: QueueItem[]; canOpen: boolean }) {
  const navigate = useNavigate();
  const open = (item: QueueItem) => canOpen && navigate(`/weryfikacja/${item.studyId}`);

  return (
    <Panel title={t("dashboard.queue")} aux={t("dashboard.queue.hint")}>
      {items.length === 0 ? (
        <EmptyState
          title={t("dashboard.queue.empty.title")}
          body={t("dashboard.queue.empty.body")}
          action={
            <Link className="btn" to="/badania">
              {t("review.goToStudies")}
            </Link>
          }
        />
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
                className={canOpen ? "is-clickable" : undefined}
                tabIndex={canOpen ? 0 : undefined}
                onClick={() => open(item)}
                onKeyDown={(event) => event.key === "Enter" && open(item)}
              >
                <td className="cell-strong">#{item.studyNumber}</td>
                <td>{item.patientId}</td>
                <td>{formatDate(item.studyDate)}</td>
                <td className="cell-right">{formatDecimal(item.uncertainty)}</td>
                <td className="cell-right">
                  {canOpen && (
                    <Link className="link" to={`/weryfikacja/${item.studyId}`} onClick={(event) => event.stopPropagation()}>
                      {t("dashboard.review")}
                    </Link>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
