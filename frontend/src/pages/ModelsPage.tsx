import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

import { errorText } from "../api";
import { useCan } from "../auth/AuthProvider";
import Page from "../components/layout/Page";
import { ErrorState, LoadingState } from "../components/State";
import { t } from "../i18n";
import ExtractionView from "../models/ExtractionView";
import SegmentationView, { useModelActions } from "../models/SegmentationView";
import { fetchExtraction, fetchSegmentation } from "../models/api";
import "../models/models.css";

export default function ModelsPage({ module }: { module: "segmentation" | "extraction" }) {
  const { search } = useLocation();
  const [rejecting, setRejecting] = useState(false);
  const actions = useModelActions();
  const manages = useCan()("manageModels");

  // segmentation always loads, its tab says when a version waits for a decision
  const segmentation = useQuery({ queryKey: ["models", "segmentation", search], queryFn: fetchSegmentation });
  const extraction = useQuery({ queryKey: ["models", "extraction"], queryFn: fetchExtraction, enabled: module === "extraction" });
  const query = module === "segmentation" ? segmentation : extraction;
  const seg = segmentation.data;

  // a tab speaks only when its model needs attention; the panels below give the details
  const segState = seg?.candidate ? (
    <span className="tabs__state tabs__state--waiting">{t("models.tab.waiting")}</span>
  ) : seg?.training ? (
    <span className="tabs__state tabs__state--running">{t("models.trainingNow")}</span>
  ) : null;

  const tabs = (
    <nav className="tabs" aria-label={t("models.module")}>
      <NavLink to={`/modele${search}`} end>
        {t("models.segmentation")}
        {segState}
      </NavLink>
      <NavLink to={`/modele/ekstrakcja${search}`}>{t("models.extraction")}</NavLink>
    </nav>
  );

  const buttons =
    module === "segmentation" &&
    seg?.candidate &&
    manages && (
      <>
        <button type="button" className="btn" onClick={() => setRejecting(true)}>
          {t("models.reject")}
        </button>
        <button type="button" className="btn btn--primary" disabled={actions.promote.isPending} onClick={() => actions.promote.mutate(seg.candidate!.version)}>
          {t("models.promote", { v: seg.candidate.version })}
        </button>
      </>
    );

  return (
    <Page title={t("nav.models")} actions={buttons} tabs={tabs}>
      {query.isPending ? (
        <LoadingState label={t("models.loading")} />
      ) : query.error ? (
        <ErrorState title={t("models.error")} body={errorText(query.error)} onRetry={() => query.refetch()} retrying={query.isFetching} />
      ) : module === "segmentation" && seg ? (
        <SegmentationView data={seg} rejecting={rejecting} onCancelReject={() => setRejecting(false)} />
      ) : extraction.data ? (
        <ExtractionView data={extraction.data} />
      ) : null}
    </Page>
  );
}
