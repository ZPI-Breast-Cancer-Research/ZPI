import { Link } from "react-router-dom";

import WarningIcon from "../components/WarningIcon";
import Panel from "../components/layout/Panel";
import { t } from "../i18n";
import type { AttentionItem } from "./api";

function row(item: AttentionItem) {
  switch (item.kind) {
    case "processing_error":
      return {
        subject: (
          <>
            <WarningIcon />#{item.subject}
          </>
        ),
        what: t("dashboard.attention.processing_error"),
        action: t("dashboard.attention.details"),
      };
    case "model_candidate":
      return {
        subject: t("dashboard.attention.segmentation"),
        what: t("dashboard.attention.model_candidate"),
        action: t("dashboard.attention.open"),
      };
    case "missing_report":
      return {
        subject: t("dashboard.attention.noReport"),
        what: `${item.count ?? 0} ${t("dashboard.attention.missing_report")}`,
        action: t("dashboard.attention.show"),
      };
  }
}

export default function AttentionPanel({ items }: { items: AttentionItem[] }) {
  return (
    <Panel title={t("dashboard.attention")} aux={items.length}>
      {items.length === 0 ? (
        <p className="dashboard__note">{t("dashboard.attention.none")}</p>
      ) : (
        <table className="table">
          <tbody>
            {items.map((item, i) => {
              const { subject, what, action } = row(item);
              return (
                <tr key={i}>
                  <td className="cell-strong">{subject}</td>
                  <td>{what}</td>
                  <td className="cell-right">
                    <Link className="link" to={item.href}>
                      {action}
                    </Link>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
