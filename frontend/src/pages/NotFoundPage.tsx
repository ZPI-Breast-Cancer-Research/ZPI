import { Link } from "react-router-dom";

import Page from "../components/layout/Page";
import { EmptyState } from "../components/State";
import { t } from "../i18n";

export default function NotFoundPage() {
  return (
    <Page title={t("notFound.title")}>
      <EmptyState
        title={t("notFound.title")}
        body={t("notFound.body")}
        action={
          <Link className="btn" to="/pulpit">
            {t("notFound.back")}
          </Link>
        }
      />
    </Page>
  );
}
