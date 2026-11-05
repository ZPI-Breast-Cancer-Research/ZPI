import { useQuery } from "@tanstack/react-query";

import Page from "../components/layout/Page";
import Panel from "../components/layout/Panel";
import { formatDate } from "../format";
import { t } from "../i18n";
import { fetchUsers } from "../settings/api";
import Sections from "../settings/Sections";
import "../settings/settings.css";

function UsersSection() {
  const { data } = useQuery({ queryKey: ["users"], queryFn: fetchUsers });
  return (
    <Panel
      title={t("settings.users")}
      className="settings__section"
      aux={
        <button type="button" className="btn btn--primary btn--small">
          {t("settings.addUser")}
        </button>
      }
    >
      <table className="table">
        <thead>
          <tr>
            <th>{t("settings.col.name")}</th>
            <th>{t("settings.col.login")}</th>
            <th>{t("settings.col.role")}</th>
            <th>{t("settings.col.state")}</th>
            <th>{t("settings.col.lastLogin")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {data?.map((user) => (
            <tr key={user.id}>
              <td className="cell-strong">{user.name}</td>
              <td>{user.login}</td>
              <td>{t(`role.${user.role}`)}</td>
              <td>
                <span className={user.state === "active" ? "status status--confirmed" : user.state === "invited" ? "status status--running" : "status"}>
                  {t(`userState.${user.state}`)}
                </span>
              </td>
              <td>{user.lastLogin ? formatDate(user.lastLogin) : "—"}</td>
              <td className="cell-right">
                <button type="button" className="link">
                  {t(user.state === "invited" ? "settings.resend" : "settings.edit")}
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

// the admin's side of the system; each person's own settings live under /konto
export default function SettingsPage() {
  return (
    <Page title={t("nav.settings")}>
      <Sections label={t("nav.settings")} sections={[["uzytkownicy", "settings.users", <UsersSection />]]} />
    </Page>
  );
}
