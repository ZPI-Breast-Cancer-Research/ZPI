import Panel from "../components/layout/Panel";
import { t } from "../i18n";
import type { ProcessingItem } from "./api";

export default function ProcessingPanel({ items }: { items: ProcessingItem[] }) {
  return (
    <Panel title={t("dashboard.processing")} aux={items.length}>
      {items.length === 0 ? (
        <p className="dashboard__note">{t("dashboard.inProgress.none")}</p>
      ) : (
        <table className="table">
          <tbody>
            {items.map((item) => (
              <tr key={item.studyNumber}>
                <td className="cell-strong">#{item.studyNumber}</td>
                <td>{item.stage ? t(`dashboard.stage.${item.stage}`) : "—"}</td>
                <td className="cell-right">
                  <span className={item.state === "running" ? "status status--running" : "status"}>
                    {t(`dashboard.state.${item.state}`)}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
