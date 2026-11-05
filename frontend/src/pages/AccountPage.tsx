import { useQuery } from "@tanstack/react-query";

import { useAuth } from "../auth/AuthProvider";
import Page from "../components/layout/Page";
import { t } from "../i18n";
import { PasswordSection, ProfileSection, ShortcutsSection, WorkSection } from "../settings/AccountSection";
import { fetchProfile } from "../settings/api";
import Sections from "../settings/Sections";
import "../settings/settings.css";

// everyone's own corner: see the account, change the password and how the viewer opens
export default function AccountPage() {
  const { user } = useAuth();
  const { data: profile } = useQuery({ queryKey: ["profile", user?.login], queryFn: () => fetchProfile(user!), enabled: !!user });

  return (
    <Page title={t("nav.accountSettings")}>
      {profile && (
        <Sections
          label={t("nav.accountSettings")}
          sections={[
            ["dane", "settings.profile", <ProfileSection profile={profile} />],
            ["haslo", "settings.password", <PasswordSection />],
            ["praca", "settings.work", <WorkSection />],
            ["skroty", "settings.shortcuts", <ShortcutsSection />],
          ]}
        />
      )}
    </Page>
  );
}
