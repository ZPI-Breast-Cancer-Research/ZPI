import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import Panel from "../components/layout/Panel";
import { useToast } from "../components/Toast";
import WarningIcon from "../components/WarningIcon";
import { formatDate, formatDuration, formatMetric, formatPercent } from "../format";
import { t } from "../i18n";
import { promote, reject, rollback, startTraining, type ModelVersion, type SegmentationOverview } from "./api";
import TrendChart from "./TrendChart";

const STATUS_CLASS: Record<ModelVersion["status"], string> = {
  candidate: "status",
  production: "status status--confirmed",
  archived: "status",
  rejected: "status status--warning",
  training: "status status--running",
};

function period(v: ModelVersion): string {
  if (!v.from) return "—";
  return `${formatDate(v.from)} – ${v.to ? formatDate(v.to) : t("models.now")}`;
}

export function useModelActions() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["models"] });
  return {
    promote: useMutation({ mutationFn: promote, onSuccess: (v) => (toast(t("models.promote.done", { v })), refresh()) }),
    reject: useMutation({
      mutationFn: ({ version, reason }: { version: string; reason: string }) => reject(version, reason),
      onSuccess: (v) => (toast(t("models.reject.done", { v })), refresh()),
    }),
    rollback: useMutation({ mutationFn: rollback, onSuccess: (v) => (toast(t("models.restore.done", { v })), refresh()) }),
    train: useMutation({ mutationFn: startTraining, onSuccess: () => (toast(t("models.next.started")), refresh()) }),
  };
}

export default function SegmentationView({ data, rejecting, onCancelReject }: { data: SegmentationOverview; rejecting: boolean; onCancelReject: () => void }) {
  const actions = useModelActions();
  const [reason, setReason] = useState("");

  const restore = (version: string) => {
    if (window.confirm(t("models.restore.confirm", { v: version }))) actions.rollback.mutate(version);
  };

  return (
    <div className="models">
      {data.candidate && (
        <>
          {rejecting && (
            <div className="reason">
              <label className="field__help" htmlFor="reject-reason">
                {t("models.reject.reason")}
              </label>
              <textarea id="reject-reason" className="textarea" value={reason} onChange={(event) => setReason(event.target.value)} autoFocus />
              <div className="reason__row">
                <button type="button" className="btn" onClick={onCancelReject}>
                  {t("models.reject.cancel")}
                </button>
                <button
                  type="button"
                  className="btn btn--primary"
                  disabled={!reason.trim() || actions.reject.isPending}
                  onClick={() =>
                    actions.reject.mutate({ version: data.candidate!.version, reason: reason.trim() }, { onSuccess: onCancelReject })
                  }
                >
                  {t("models.reject.confirm", { v: data.candidate.version })}
                </button>
              </div>
            </div>
          )}
          <Panel
            title={
              <>
                {t("models.decision")} · {t("models.version")} {data.candidate.version} <span className="alias">@candidate</span>{" "}
                {t("models.decision.vs")} {data.production.version}
              </>
            }
            aux={t("models.decision.human")}
          >
            <div className="models__two">
              <div className="models__pad">
                <ul className="gate">
                  {data.candidate.gate.map((g) => (
                    <li key={g.rule}>
                      {t(`models.gate.${g.rule}`)}
                      <span className={g.passed ? "status status--confirmed" : "status status--warning"}>
                        {t(g.passed ? "models.gate.passed" : "models.gate.failed")}
                      </span>
                    </li>
                  ))}
                </ul>
                <table className="kv" style={{ marginTop: 8 }}>
                  <tbody>
                    <tr>
                      <th>{t("models.trainingData")}</th>
                      <td className="cell-right">{t("models.trainingData.value", { n: data.candidate.trainingData })}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <div className="models__pad">
                <table className="kv">
                  <thead>
                    <tr>
                      <th>{t("models.cases")}</th>
                      <th className="cell-right">Dice {data.production.version}</th>
                      <th className="cell-right">Dice {data.candidate.version}</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {data.candidate.cases.map((c) => (
                      <tr key={c.studyId}>
                        <th>
                          #{c.studyNumber} <span className="muted">· {t(`models.case.${c.label}`)}</span>
                        </th>
                        <td className="cell-right">{formatMetric(c.current)}</td>
                        <td className="cell-right">{formatMetric(c.candidate)}</td>
                        <td className="cell-right">
                          <Link className="link" to={`/badania/${c.studyId}`}>
                            {t("models.case.open")}
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="field__help">{t("models.cases.note")}</p>
              </div>
            </div>
          </Panel>
        </>
      )}

      <Panel
        title={
          <>
            {t("models.inProduction")} · {t("models.version")} {data.production.version} <span className="alias">@production</span>
          </>
        }
        aux={`${t("models.since")} ${formatDate(data.production.since)} · ${t("models.approvedBy")} ${data.production.approvedBy}`}
      >
        <div className="models__two">
          <div>
            <div className="models__pad" style={{ paddingBottom: 0 }}>
              {t("models.weekly")}
            </div>
            <TrendChart points={data.weeklyCorrected} />
            <p className="note">{t("models.weekly.note")}</p>
          </div>
          <div className="models__pad">
            <table className="kv">
              <thead>
                <tr>
                  <th />
                  <th className="cell-right">
                    {t("models.version")} {data.production.version} ({t("models.current")})
                  </th>
                  {data.previous && (
                    <th className="cell-right">
                      {t("models.version")} {data.previous} ({t("models.previous")})
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th>{t("models.correctedShare")}</th>
                  <td className="cell-right">{formatPercent(data.correctedShare.current)}</td>
                  {data.previous && <td className="cell-right">{data.correctedShare.previous !== null ? formatPercent(data.correctedShare.previous) : "—"}</td>}
                </tr>
                <tr>
                  <th>{t("models.editTime")}</th>
                  <td className="cell-right">{formatDuration(data.editTime.current)}</td>
                  {data.previous && <td className="cell-right">{data.editTime.previous !== null ? formatDuration(data.editTime.previous) : "—"}</td>}
                </tr>
              </tbody>
            </table>
            {data.previous && (
              <div style={{ marginTop: 12, textAlign: "right" }}>
                <button type="button" className="btn btn--small" onClick={() => restore(data.previous!)}>
                  {t("models.restoreVersion")} {data.previous}
                </button>
              </div>
            )}
          </div>
        </div>
      </Panel>

      {data.training ? (
        <Panel title={t("models.training")} aux={t("models.training.queue")}>
          <div className="models__pad">
            <div className="line">
              <span>
                {t("models.version")} {data.training.version} · {t("models.training.epoch")}{" "}
                <b>
                  {data.training.epoch} / {data.training.epochs}
                </b>
              </span>
              <div className="progress progress--running">
                <i style={{ width: `${(data.training.epoch / data.training.epochs) * 100}%` }} />
              </div>
              <span>{t("models.training.eta", { h: data.training.etaHours })}</span>
              <button type="button" className="btn btn--small line__end">
                {t("models.training.stop")}
              </button>
            </div>
            <p className="models__sub">{t("models.training.priority")}</p>
          </div>
        </Panel>
      ) : (
        data.next && (
          <Panel title={t("models.next")}>
            <div className="models__pad">
              <div className="line">
                <span>
                  {t("models.next.corrections")}{" "}
                  <b>
                    {data.next.corrections} / {data.next.threshold}
                  </b>
                </span>
                <div className="progress">
                  <i style={{ width: `${Math.min(1, data.next.corrections / data.next.threshold) * 100}%` }} />
                </div>
                <span>
                  {t("models.next.window")} · {formatDate(data.next.window.slice(0, 10))} {data.next.window.slice(11, 16)}
                </span>
                <button type="button" className="btn btn--small line__end" disabled={actions.train.isPending} onClick={() => actions.train.mutate()}>
                  {t("models.next.start")}
                </button>
              </div>
              {data.lastRun && (
                <p className="models__sub">
                  {data.lastRun.outcome === "rejected_gate" && <WarningIcon />}
                  {t(`models.lastRun.${data.lastRun.outcome}`, { date: formatDate(data.lastRun.date), v: data.lastRun.version })}
                </p>
              )}
            </div>
          </Panel>
        )
      )}

      <Panel title={t("models.versions")} aux={t("models.versions.note")}>
        <table className="table">
          <thead>
            <tr>
              <th>{t("models.col.version")}</th>
              <th>{t("models.col.status")}</th>
              <th>{t("models.col.inProduction")}</th>
              <th className="cell-right">Dice</th>
              <th className="cell-right">HD95</th>
              <th className="cell-right">Dice MAMA-MIA</th>
              <th>{t("models.col.decision")}</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.versions.map((v) => (
              <tr key={v.version} aria-current={v.status === "candidate" ? "true" : undefined}>
                <td className="cell-strong">
                  {t("models.version")} {v.version}
                </td>
                <td>
                  <span className={STATUS_CLASS[v.status]}>{t(`models.status.${v.status}`)}</span>
                </td>
                <td>{period(v)}</td>
                <td className="cell-right">{formatMetric(v.dice)}</td>
                <td className="cell-right">{formatMetric(v.hd95, " mm")}</td>
                <td className="cell-right">{formatMetric(v.diceMamaMia)}</td>
                <td>
                  {t(`models.decision.${v.decision}`)}
                  {v.decidedBy && ` · ${v.decidedBy}`}
                </td>
                <td className="cell-right">
                  {v.canRestore && (
                    <button type="button" className="link" onClick={() => restore(v.version)}>
                      {t("models.restore")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note">{t("models.versions.testNote")}</p>
      </Panel>
    </div>
  );
}
