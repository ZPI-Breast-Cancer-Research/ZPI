import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import Page from "../components/layout/Page";
import { ErrorState, LoadingState } from "../components/State";
import AttentionPanel from "../dashboard/AttentionPanel";
import ProcessingPanel from "../dashboard/ProcessingPanel";
import QueuePanel from "../dashboard/QueuePanel";
import VerifiedChart from "../dashboard/VerifiedChart";
import { fetchDashboard } from "../dashboard/api";
import "../dashboard/dashboard.css";
import { t } from "../i18n";

export default function DashboardPage() {
  const { data, error, isPending, refetch } = useQuery({ queryKey: ["dashboard"], queryFn: fetchDashboard });

  const counts = data && (
    <>
      <span>
        {t("dashboard.toReview")} <b>{data.toReview}</b>
      </span>
      <span>
        {t("dashboard.processing")} <b>{data.processing}</b>
      </span>
      <span>
        {t("dashboard.verifiedToday")} <b>{data.verifiedToday}</b>
      </span>
    </>
  );

  return (
    <Page
      title={t("nav.dashboard")}
      context={counts}
      actions={
        <Link className="btn btn--primary" to="/weryfikacja">
          {t("dashboard.start")}
        </Link>
      }
    >
      {isPending ? (
        <LoadingState label={t("dashboard.loading")} />
      ) : error ? (
        <ErrorState title={t("dashboard.error")} body={error.message} onRetry={() => refetch()} />
      ) : (
        <div className="dashboard">
          <QueuePanel items={data.queue} />
          <div className="dashboard__side">
            <AttentionPanel items={data.attention} />
            <ProcessingPanel items={data.inProgress} />
            <VerifiedChart days={data.verifiedLastWeek} />
          </div>
        </div>
      )}
    </Page>
  );
}
