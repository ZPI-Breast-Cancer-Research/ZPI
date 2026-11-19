import { useQuery } from "@tanstack/react-query";
import { NavLink, useLocation } from "react-router-dom";

import { errorText } from "../api";
import Page from "../components/layout/Page";
import { ErrorState, LoadingState } from "../components/State";
import { t } from "../i18n";
import ExtractionView from "../models/ExtractionView";
import SegmentationView from "../models/SegmentationView";
import { fetchSegmentation } from "../models/api";
import { fetchExtraction } from "../models/extraction";
import "../models/models.css";

export default function ModelsPage({ module }: { module: "segmentation" | "extraction" }) {
  const { search } = useLocation();

  // both always load, a tab says when a version waits for a decision
  const segmentation = useQuery({ queryKey: ["models", "segmentation", search], queryFn: fetchSegmentation });
  const extraction = useQuery({ queryKey: ["models", "extraction", search], queryFn: fetchExtraction });
  const query = module === "segmentation" ? segmentation : extraction;
  const seg = segmentation.data;
  const ext = extraction.data;

  // a tab speaks only when its model needs attention; the panels below give the details
  const segState = seg?.proposal ? (
    <span className="tabs__state tabs__state--waiting">{t("models.tab.waiting")}</span>
  ) : seg?.training?.run ? (
    <span className="tabs__state tabs__state--running">{t("models.trainingNow")}</span>
  ) : seg?.versions.some((v) => v.status === "new") ? (
    <span className="tabs__state">{t("models.tab.new")}</span>
  ) : null;
  const extState = ext?.proposal ? (
    <span className="tabs__state tabs__state--waiting">{t("models.tab.waiting")}</span>
  ) : [...(ext?.models ?? []), ...(ext?.fewShots ?? [])].some((v) => v.status === "new") ? (
    <span className="tabs__state">{t("models.tab.new")}</span>
  ) : null;

  const tabs = (
    <nav className="tabs" aria-label={t("models.module")}>
      <NavLink to={`/modele${search}`} end>
        {t("models.segmentation")}
        {segState}
      </NavLink>
      <NavLink to={`/modele/ekstrakcja${search}`}>
        {t("models.extraction")}
        {extState}
      </NavLink>
    </nav>
  );

  return (
    <Page title={t("nav.models")} tabs={tabs}>
      {query.isPending ? (
        <LoadingState label={t("models.loading")} />
      ) : query.error ? (
        <ErrorState title={t("models.error")} body={errorText(query.error)} onRetry={() => query.refetch()} retrying={query.isFetching} />
      ) : module === "segmentation" ? (
        seg && <SegmentationView data={seg} />
      ) : extraction.data ? (
        <ExtractionView data={extraction.data} />
      ) : null}
    </Page>
  );
}
