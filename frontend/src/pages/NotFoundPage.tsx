import { Link } from "react-router-dom";

import Page from "../components/layout/Page";
import { t } from "../i18n";

export default function NotFoundPage() {
  return (
    <Page title={t("notFound.title")}>
      <div className="state">
        <h3>{t("notFound.title")}</h3>
        <p>{t("notFound.body")}</p>
        <Link className="btn" to="/pulpit">
          {t("notFound.back")}
        </Link>
      </div>
    </Page>
  );
}
