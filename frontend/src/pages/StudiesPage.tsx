import StudyList from "../components/StudyList";
import Page from "../components/layout/Page";
import Panel from "../components/layout/Panel";
import { t } from "../i18n";

export default function StudiesPage() {
  return (
    <Page title={t("nav.studies")}>
      <Panel title={t("studies.list")}>
        <StudyList />
      </Panel>
    </Page>
  );
}
