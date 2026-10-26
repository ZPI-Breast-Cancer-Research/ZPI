import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import Page from "../components/layout/Page";
import Panel from "../components/layout/Panel";
import { formatDate, formatDuration, formatMetric } from "../format";
import { t } from "../i18n";
import { fetchOverview } from "../lesion-overview/api";
import "../lesion-overview/lesion-overview.css";
import "../review/review.css";
import { FIELDS } from "../review/fields";
import Viewer from "../viewer/Viewer";

export default function LesionOverviewPage() {
  const { studyId = "" } = useParams();
  const { search } = useLocation();
  const [showModel, setShowModel] = useState(false);
  const { data, error, refetch } = useQuery({ queryKey: ["overview", studyId, search], queryFn: () => fetchOverview(studyId) });

  if (error) {
    return (
      <Page title={t("overview.title")}>
        <div className="state state--error" role="alert">
          <h3>{t("review.error")}</h3>
          <button className="btn" onClick={() => refetch()}>
            {t("studies.retry")}
          </button>
        </div>
      </Page>
    );
  }
  if (!data) {
    return (
      <Page title={t("overview.title")}>
        <p className="state">{t("overview.loading")}</p>
      </Page>
    );
  }

  const saving = data.status === "saving";
  const value = (text: string) => (saving ? <span className="muted">{t("overview.recalc")}</span> : text);
  const label = (key: string) => FIELDS.find((f) => f.key === key)?.label ?? key;
  const dims = data.measurements.dimensions;

  return (
    <Page
      title={data.patientId}
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
        <>
          <Link className="btn" to="/badania">
            {t("overview.back")}
          </Link>
          <Link className="btn" to={`/weryfikacja/${data.studyId}`}>
            {t("overview.openReview")}
          </Link>
        </>
      }
    >
      <div className="overview">
        <section className="overview__view" aria-label={t("viewer.image")}>
          <Viewer lesion={data.lesion} series="post" mask="confirmed" strokes={[]} showMask modelOutline={showModel} />
          <div className="mask-strip">
            <span className="mask-strip__label">{t("overview.approvedMask")}</span>
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
          <Panel title={t("overview.measurements")} aux={saving ? t("overview.recalculating") : t("overview.fromApproved")}>
            <div className="overview__pad">
              <table className="kv">
                <tbody>
                  <tr>
                    <th>{t("overview.volume")}</th>
                    <td className="cell-right">{value(`${formatMetric(data.measurements.volume)} cm³`)}</td>
                  </tr>
                  <tr>
                    <th>{t("overview.dimensions")}</th>
                    <td className="cell-right">{value(dims ? dims.map((d) => formatMetric(d)).join(" × ") + " mm" : "— × — × — mm")}</td>
                  </tr>
                  <tr>
                    <th>{t("overview.intensity")}</th>
                    <td className="cell-right">{value(formatMetric(data.measurements.intensity))}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title={t("overview.reportData")} aux={data.verification.extractionVersion ? `${t("review.extraction")} ${t("models.version")} ${data.verification.extractionVersion}` : undefined}>
            <div className="overview__pad">
              {data.report ? (
                <table className="kv">
                  <thead>
                    <tr>
                      <th>{t("review.col.field")}</th>
                      <th>{t("review.col.value")}</th>
                      <th className="cell-right">{t("review.col.status")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.report.map((row) => (
                      <tr key={row.field}>
                        <th>{label(row.field)}</th>
                        <td>{row.value}</td>
                        <td className="cell-right">
                          <span className={row.corrected ? "status status--corrected" : "status status--confirmed"}>
                            {t(row.corrected ? "review.field.corrected" : "review.field.confirmed")}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="empty-box" style={{ marginTop: 8 }}>
                  <b>{t("review.noReport")}</b>
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
              {data.report ? (
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
                    <th>{t("overview.editTime")}</th>
                    <td className="cell-right">{formatDuration(data.verification.editingSeconds)}</td>
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
