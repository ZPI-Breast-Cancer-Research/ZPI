import { useQuery } from "@tanstack/react-query";
import { Navigate, useParams } from "react-router-dom";

import Page from "../components/layout/Page";
import { t } from "../i18n";
import { fetchCase, fetchQueue } from "../review/api";
import CaseReview from "../review/CaseReview";
import "../review/review.css";

export default function ReviewPage() {
  const { studyId } = useParams();
  const queue = useQuery({ queryKey: ["review-queue"], queryFn: fetchQueue });
  const current = useQuery({ queryKey: ["review-case", studyId], queryFn: () => fetchCase(studyId!), enabled: !!studyId });

  if (!studyId && queue.data) {
    const first = queue.data.queue[0];
    if (first) return <Navigate to={`/weryfikacja/${first.studyId}`} replace />;
    return (
      <Page title={t("nav.review")}>
        <div className="state">
          <h3>{t("review.queueEmpty")}</h3>
          <p>{t("review.queueEmptyBody")}</p>
        </div>
      </Page>
    );
  }

  if (current.error || queue.error) {
    return (
      <Page title={t("nav.review")}>
        <div className="state state--error" role="alert">
          <h3>{t("review.error")}</h3>
          <button className="btn" onClick={() => (current.refetch(), queue.refetch())}>
            {t("studies.retry")}
          </button>
        </div>
      </Page>
    );
  }

  if (!current.data || !queue.data) {
    return (
      <Page title={t("nav.review")}>
        <p className="state">{t("review.loading")}</p>
      </Page>
    );
  }

  return <CaseReview key={current.data.studyId} data={current.data} queue={queue.data.queue} done={queue.data.done} />;
}
