import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { errorText } from "../api";
import { useCan } from "../auth/AuthProvider";
import Page from "../components/layout/Page";
import Panel from "../components/layout/Panel";
import { ErrorState, LoadingState } from "../components/State";
import { formatDate, formatDecimal, formatMetric, formatOneDecimal } from "../format";
import { t } from "../i18n";
import { fetchOverview, type Overview } from "../lesion-overview/api";
import "../lesion-overview/lesion-overview.css";
import "../review/review.css";
import { fieldLabel, FIELDS, lesionSummary, optionLabel } from "../review/fields";
import { fromExtraction } from "../review/report";
import ReportOriginal, { scanOf } from "../review/ReportOriginal";
import LesionSwitcher from "../review/LesionSwitcher";
import ReportPreview from "../review/ReportPreview";
import { MaskToggle } from "../review/MaskStrip";
import Icon from "../viewer/icons";
import type { Series, Tool } from "../viewer/types";
import { usePreferences } from "../settings/preferences";
import { useViewerLayout } from "../viewer/layout";
import Viewer from "../viewer/Viewer";
import ViewerBar, { LayoutButton } from "../viewer/ViewerBar";

function agreement({ mask, verification }: Overview): string {
  if (!mask.corrected) return t("overview.agreement.same");
  const a = verification.agreement;
  if (!a || a.dice === null) return "—";
  const volume = a.volumeMl === null ? "—" : `${a.volumeMl > 0 ? "+" : ""}${formatOneDecimal(a.volumeMl)} ml`;
  return t("overview.agreement.value", { dice: formatMetric(a.dice), volume });
}

export default function LesionOverviewPage() {
  const { studyId = "" } = useParams();
  const { search, state } = useLocation();
  // back to the list the overview was opened from
  const backTo = (state as { from?: string } | null)?.from ?? "/badania?filtr=verified";
  const [showModel, setShowModel] = useState(false);
  const [preferred] = usePreferences();
  const [showMask, setShowMask] = useState(preferred.maskShown);
  const [tool, setTool] = useState<Tool>("pan");
  const [series, setSeries] = useState<Series>(preferred.series);
  const [available, setAvailable] = useState<Series[]>(["post"]);
  const [layout, setLayout] = useViewerLayout();
  const [showOriginal, setShowOriginal] = useState(false);
  const [lesionAt, setLesionAt] = useState(0);
  const reviews = useCan()("review");
  const { data, error, refetch } = useQuery({ queryKey: ["overview", studyId, search], queryFn: () => fetchOverview(studyId) });

  if (error) {
    return (
      <Page title={t("overview.title")}>
        <ErrorState title={t("review.error")} body={errorText(error)} onRetry={() => refetch()} />
      </Page>
    );
  }
  if (!data) {
    return (
      <Page title={t("overview.title")}>
        <LoadingState label={t("overview.loading")} />
      </Page>
    );
  }

  const saving = data.status === "saving";
  const value = (text: string) => (saving ? <span className="muted">{t("overview.recalc")}</span> : text);
  const measure = data.measurements;
  const severalParts = !!measure && measure.totalMl > measure.largest.volumeMl;
  const volume = (ml: number | undefined) => value(ml === undefined ? "—" : `${formatDecimal(ml)} cm³`);
  const measuredFrom = measure ? t(measure.source === "model" ? "overview.fromModel" : "overview.fromApproved") : undefined;
  const report = data.report;
  const extracted = report?.source.result.data;
  const lesions = extracted ? fromExtraction(extracted).lesions : [];
  const lesionIndex = Math.min(lesionAt, Math.max(0, lesions.length - 1));
  const lesion = lesions[lesionIndex] ?? null;
  const answers = report && lesion ? (report.lesions[lesion.id] ?? {}) : {};
  const rows = FIELDS.filter((f) => answers[f.key]);

  return (
    <Page
      title={data.patientId}
      back={{ to: backTo, label: t("nav.studies") }}
      context={
        <>
          <span>
            {t("review.age")} {data.age ?? "—"}
          </span>
          <span>
            {t("review.study")} <b>#{data.studyNumber}</b>
          </span>
          <span>
            {data.description} · {formatDate(data.studyDate)}
          </span>
          <span className={saving ? "status status--running" : "status status--confirmed"}>
            {t(saving ? "overview.status.saving" : "overview.status.verified")}
          </span>
        </>
      }
      actions={
        reviews && (
          <Link className="btn" to={`/weryfikacja/${data.studyId}`}>
            {t("overview.openReview")}
          </Link>
        )
      }
    >
      <div className="overview">
        <section className="overview__view" aria-label={t("viewer.image")}>
          {/* read only: no rail, just looking around */}
          <ViewerBar series={series} onSeries={setSeries} available={available} corner={<LayoutButton layout={layout} onLayout={setLayout} />}>
            <div className="segmented" role="group" aria-label={t("viewer.tools")}>
              {(["pan", "window"] as Tool[]).map((name) => (
                <button
                  key={name}
                  type="button"
                  className="viewer-bar__icon"
                  aria-pressed={tool === name}
                  aria-label={t(name === "pan" ? "viewer.pan" : "viewer.window")}
                  title={name === "pan" ? t("viewer.panTitle") : `${t("viewer.window")} (W)`}
                  onClick={() => setTool(name)}
                >
                  <Icon name={name} />
                </button>
              ))}
            </div>
          </ViewerBar>
          <Viewer
            studyUid={data.studyUid}
            mask={data.masks.approved}
            modelMask={data.masks.model}
            series={series}
            maskState="confirmed"
            showMask={showMask}
            tool={tool}
            modelOutline={showModel}
            onSeriesFound={(found) => {
              setAvailable(found);
              // the preferred series may be missing from this study
              if (!found.includes(series)) setSeries("post");
            }}
            layout={layout}
            onLayout={setLayout}
          />
          <div className="mask-strip">
            <MaskToggle shown={showMask} onToggle={() => setShowMask((s) => !s)} />
            <span className="mask-strip__state">{t("overview.approvedMask")}</span>
            <span className={data.mask.corrected ? "status status--corrected" : "status"}>
              {t(data.mask.corrected ? "overview.correctedBy" : "overview.confirmedBy")}
            </span>
            <span>{t("overview.maskVersion", { v: data.mask.version, date: formatDate(data.mask.date), who: data.mask.by })}</span>
            <span className="mask-strip__end">
              <label className="overview__toggle">
                <input type="checkbox" checked={showModel} onChange={(event) => setShowModel(event.target.checked)} />
                {t("overview.showModel")} <span className="overview__key" aria-hidden="true" />
              </label>
            </span>
          </div>
        </section>

        <section className="overview__info">
          <Panel title={t("overview.measurements")} aux={saving ? t("overview.recalculating") : measuredFrom}>
            <div className="overview__pad">
              <table className="kv">
                <tbody>
                  <tr>
                    <th>{t("overview.largestSize")}</th>
                    <td className="cell-right">{value(measure ? `${Math.round(measure.largest.sizeMm)} mm` : "—")}</td>
                  </tr>
                  <tr>
                    <th>{t(severalParts ? "overview.volumeLargest" : "overview.volume")}</th>
                    <td className="cell-right">{volume(measure?.largest.volumeMl)}</td>
                  </tr>
                  {severalParts && (
                    <tr>
                      <th>{t("overview.volumeTotal")}</th>
                      <td className="cell-right">{volume(measure?.totalMl)}</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title={t("overview.reportData")} aux={data.verification.extractionVersion ? `${t("review.extraction")} ${t("models.version")} ${data.verification.extractionVersion}` : undefined}>
            <div className="overview__pad">
              {report ? (
                <>
                  <div style={{ margin: "8px 0 10px" }}>
                    <ReportPreview report={report.source} onOpen={() => setShowOriginal(true)} />
                  </div>
                  {lesion && lesions.length > 1 && (
                    <LesionSwitcher
                      index={lesionIndex}
                      total={lesions.length}
                      summary={lesionSummary(lesion)}
                      note={null}
                      onPrev={() => setLesionAt(lesionIndex - 1)}
                      onNext={() => setLesionAt(lesionIndex + 1)}
                    />
                  )}
                  <table className="kv">
                    <thead>
                      <tr>
                        <th>{t("review.col.field")}</th>
                        <th>{t("review.col.value")}</th>
                        <th className="cell-right">{t("review.col.status")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((field) => {
                        const answer = answers[field.key]!;
                        const corrected = answer.state === "corrected";
                        return (
                          <tr key={field.key}>
                            <th>{fieldLabel(field.key)}</th>
                            <td>{answer.value ? `${optionLabel(field.key, answer.value)}${field.unit ? ` ${field.unit}` : ""}` : "—"}</td>
                            <td className="cell-right">
                              <span className={corrected ? "status status--corrected" : "status status--confirmed"}>
                                {t(corrected ? "review.field.corrected" : "review.field.confirmed")}
                              </span>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  <ReportOriginal
                    scan={scanOf(report.source)}
                    open={showOriginal}
                    onClose={() => setShowOriginal(false)}
                    lesion={lesion ? { number: lesionIndex + 1, quotes: lesion.observations.map((o) => o.quote) } : null}
                  />
                </>
              ) : (
                <div className="empty-box" style={{ marginTop: 8 }}>
                  <b>{t(data.reportPending ? "review.original.pending" : "review.noReport")}</b>
                  {t("overview.noReportBody")}
                  <br />
                  <Link className="btn btn--small" to={`/badania?badanie=${data.studyId}`}>
                    {t("review.attachReport")}
                  </Link>
                </div>
              )}
            </div>
          </Panel>

          <Panel title={t("overview.comparison")}>
            <div className="overview__pad">
              {report ? (
                <table className="kv">
                  <thead>
                    <tr>
                      <th>{t("overview.feature")}</th>
                      <th>{t("overview.fromMask")}</th>
                      <th>{t("overview.fromReport")}</th>
                      <th className="cell-right">{t("overview.result")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.comparison.map((row) => (
                      <tr key={row.feature}>
                        <th>{t(`overview.${row.feature}`)}</th>
                        <td>{saving ? "…" : (row.fromMask ?? "—")}</td>
                        <td>{row.fromReport ?? "—"}</td>
                        <td className="cell-right">
                          {saving || row.match === null ? (
                            "—"
                          ) : (
                            <span className={row.match ? "status status--confirmed" : "status status--warning"}>
                              {t(row.match ? "overview.match" : "overview.mismatch")}
                            </span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <p className="muted" style={{ padding: "10px 0" }}>
                  {t("overview.needsReport")}
                </p>
              )}
            </div>
          </Panel>

          <Panel title={t("overview.verification")}>
            <div className="overview__pad">
              <table className="kv">
                <tbody>
                  <tr>
                    <th>{t("overview.verifiedBy")}</th>
                    <td className="cell-right">{data.verification.by}</td>
                  </tr>
                  <tr>
                    <th>{t("overview.date")}</th>
                    <td className="cell-right">{formatDate(data.verification.date)}</td>
                  </tr>
                  <tr>
                    <th>{t("overview.agreement")}</th>
                    <td className="cell-right">{agreement(data)}</td>
                  </tr>
                  <tr>
                    <th>{t("review.segmentation")}</th>
                    <td className="cell-right">
                      {t("models.version")} {data.verification.segmentationVersion}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Panel>
        </section>
      </div>
    </Page>
  );
}
