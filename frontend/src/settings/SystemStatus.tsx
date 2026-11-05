import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import Panel from "../components/layout/Panel";
import { t } from "../i18n";
import { fetchSystemStatus, type ComponentStatus } from "./status";

const STATE_CLASS = {
  ok: "status status--confirmed",
  slow: "status status--running",
  down: "status status--warning",
  unknown: "status",
};

const time = (iso: string) => new Date(iso).toLocaleTimeString("pl-PL", { hour: "2-digit", minute: "2-digit" });

function stateText({ state, since }: ComponentStatus) {
  if (state === "down" && since) return t("system.downSince", { n: Math.max(1, Math.round((Date.now() - Date.parse(since)) / 60_000)) });
  return t(`system.${state}`);
}

// read only; checked every minute so a stuck stage shows well within the 5 minutes of Q3
export default function SystemStatus() {
  const { data, refetch, isFetching } = useQuery({ queryKey: ["system-status"], queryFn: fetchSystemStatus, refetchInterval: 60_000 });

  return (
    <Panel
      title={t("system.title")}
      className="settings__section"
      aux={
        <span className="audit__tools">
          {data && t("system.checkedAt", { time: time(data.checkedAt) })}
          <button type="button" className="btn btn--small" disabled={isFetching} onClick={() => refetch()}>
            {t("system.check")}
          </button>
        </span>
      }
    >
      {data && (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>{t("system.col.component")}</th>
                <th>{t("system.col.state")}</th>
                <th>{t("system.col.detail")}</th>
              </tr>
            </thead>
            <tbody>
              {data.components.map((component) => (
                <tr key={component.key}>
                  <td className="cell-strong">{t(`system.component.${component.key}`)}</td>
                  <td>
                    <span className={STATE_CLASS[component.state]}>{stateText(component)}</span>
                  </td>
                  <td>{component.detail ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="settings__body">
            <table className="kv settings__kv">
              <tbody>
                <tr>
                  <th>{t("system.version")}</th>
                  <td>{__APP_VERSION__}</td>
                </tr>
                <tr>
                  <th>{t("system.profile")}</th>
                  <td>{t(`system.profile.${data.profile}`)}</td>
                </tr>
                <tr>
                  <th>{t("system.retraining")}</th>
                  <td>
                    {t(data.retraining ? "settings.on" : "settings.off")} · <Link to="/modele">{t("system.retrainingWhere")}</Link>
                  </td>
                </tr>
                <tr>
                  <th>{t("system.use")}</th>
                  <td>{t("system.researchOnly")}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      )}
    </Panel>
  );
}
