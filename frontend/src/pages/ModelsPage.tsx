import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { NavLink, useLocation } from "react-router-dom";

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

  const segmentation = useQuery({
    queryKey: ["models", "segmentation", search],
    queryFn: fetchSegmentation,
    enabled: module === "segmentation",
  });
  const extraction = useQuery({ queryKey: ["models", "extraction"], queryFn: fetchExtraction, enabled: module === "extraction" });
  const query = module === "segmentation" ? segmentation : extraction;
  const seg = segmentation.data;

  const switcher = (
    <nav className="segmented" aria-label={t("models.module")}>
      <NavLink to={`/modele${search}`} end>
        {t("models.segmentation")}
      </NavLink>
      <NavLink to="/modele/ekstrakcja">{t("models.extraction")}</NavLink>
    </nav>
  );

  let context = null;
  let buttons = null;
  if (module === "segmentation" && seg) {
    if (seg.candidate) {
      context = (
        <span>
          {t("models.candidate")} <b>{t("models.version")} {seg.candidate.version}</b> <span className="alias">@candidate</span>{" "}
          {t("models.candidateWaits")}
        </span>
      );
      buttons = (
        <>
          <button type="button" className="btn" onClick={() => setRejecting(true)}>
            {t("models.reject")}
          </button>
          <button
            type="button"
            className="btn btn--primary"
            disabled={actions.promote.isPending}
            onClick={() => actions.promote.mutate(seg.candidate!.version)}
          >
            {t("models.promote", { v: seg.candidate.version })}
          </button>
        </>
      );
    } else {
      context = (
        <span>
          {t("models.inProduction")} <b>{t("models.version")} {seg.production.version}</b> <span className="alias">@production</span>
          {seg.training && <span className="status status--running"> · {t("models.trainingNow")}</span>}
        </span>
      );
    }
  } else if (module === "extraction" && extraction.data) {
    context = (
      <span>
        {t("models.inUse")} <b>{t("models.version")} {extraction.data.version}</b>
      </span>
    );
  }

  return (
    <Page
      title={t("nav.models")}
      context={
        <>
          {switcher}
          {context}
        </>
      }
      actions={buttons}
    >
      {query.isPending ? (
        <LoadingState label={t("models.loading")} />
      ) : query.error ? (
        <ErrorState title={t("models.error")} body={query.error.message} onRetry={() => query.refetch()} retrying={query.isFetching} />
      ) : module === "segmentation" && seg ? (
        <SegmentationView data={seg} rejecting={rejecting} onCancelReject={() => setRejecting(false)} />
      ) : extraction.data ? (
        <ExtractionView data={extraction.data} />
      ) : null}
    </Page>
  );
}
