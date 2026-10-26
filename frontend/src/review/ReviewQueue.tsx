import { useNavigate } from "react-router-dom";

import Panel from "../components/layout/Panel";
import { formatDayMonth, formatDecimal } from "../format";
import { t } from "../i18n";
import type { DoneEntry, QueueEntry } from "./api";

interface Props {
  queue: QueueEntry[];
  done: DoneEntry[];
  currentId: string | undefined;
}

export default function ReviewQueue({ queue, done, currentId }: Props) {
  const navigate = useNavigate();
  const open = (id: string) => navigate(`/weryfikacja/${id}`);

  return (
    <aside className="review__queue">
      <Panel title={t("review.queue")} aux={queue.length}>
        <table className="table review__queue-table">
          <thead>
            <tr>
              <th>{t("review.col.number")}</th>
              <th>{t("review.col.date")}</th>
              <th className="cell-right">{t("review.col.uncertainty")}</th>
            </tr>
          </thead>
          <tbody>
            {queue.map((entry) => (
              <tr
                key={entry.studyId}
                className="is-clickable"
                tabIndex={0}
                aria-current={entry.studyId === currentId ? "true" : undefined}
                onClick={() => open(entry.studyId)}
                onKeyDown={(event) => event.key === "Enter" && open(entry.studyId)}
              >
                <td className="cell-strong">#{entry.studyNumber}</td>
                <td>{formatDayMonth(entry.studyDate)}</td>
                <td className="cell-right">{formatDecimal(entry.uncertainty)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
      <Panel title={t("review.doneToday")} aux={done.length}>
        <table className="table">
          <tbody>
            {done.map((entry) => (
              <tr key={entry.studyId}>
                <td>#{entry.studyNumber}</td>
                <td className="cell-right">
                  <span className={entry.corrected ? "status status--corrected" : "status"}>
                    {t(entry.corrected ? "review.field.corrected" : "review.field.confirmed")}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>
    </aside>
  );
}
