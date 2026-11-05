import Page from "../components/layout/Page";
import { t } from "../i18n";
import AuditLog from "../settings/AuditLog";
import Sections from "../settings/Sections";
import SystemStatus from "../settings/SystemStatus";
import UsersSection from "../settings/UsersSection";
import "../settings/settings.css";

// the admin's side of the system; each person's own settings live under /konto
export default function SettingsPage() {
  return (
    <Page title={t("nav.settings")}>
      <Sections
        label={t("nav.settings")}
        sections={[
          ["uzytkownicy", "settings.users", <UsersSection />],
          ["dziennik", "audit.title", <AuditLog />],
          ["stan", "system.title", <SystemStatus />],
        ]}
      />
    </Page>
  );
}
