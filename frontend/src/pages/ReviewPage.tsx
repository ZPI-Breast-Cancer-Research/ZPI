import { useQuery } from "@tanstack/react-query";
import { Link, Navigate, useParams } from "react-router-dom";

import Page from "../components/layout/Page";
import { EmptyState, ErrorState, LoadingState } from "../components/State";
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
        <EmptyState
          title={t("review.queueEmpty")}
          body={t("review.queueEmptyBody")}
          action={
            <Link className="btn" to="/badania">
              {t("review.goToStudies")}
            </Link>
          }
        />
      </Page>
    );
  }

  if (current.error || queue.error) {
    return (
      <Page title={t("nav.review")}>
        <ErrorState title={t("review.error")} body={(current.error ?? queue.error)?.message} onRetry={() => (current.refetch(), queue.refetch())} />
      </Page>
    );
  }

  if (!current.data || !queue.data) {
    return (
      <Page title={t("nav.review")}>
        <LoadingState label={t("review.loading")} />
      </Page>
    );
  }

  return <CaseReview key={current.data.studyId} data={current.data} queue={queue.data.queue} done={queue.data.done} />;
}
