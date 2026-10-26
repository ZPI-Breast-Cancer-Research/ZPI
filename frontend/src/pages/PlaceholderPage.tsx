import Page from "../components/layout/Page";
import Panel from "../components/layout/Panel";
import { t, type MessageKey } from "../i18n";

// TODO: remove once all screens are built
export default function PlaceholderPage({ title }: { title: MessageKey }) {
  return (
    <Page title={t(title)}>
      <Panel title={t(title)}>
        <div className="state">
          <h3>{t("page.placeholder.title")}</h3>
          <p>{t("page.placeholder.body")}</p>
        </div>
      </Panel>
    </Page>
  );
}
