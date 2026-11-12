import { useState } from "react";
import { Link } from "react-router-dom";

import { useAuth, useCan } from "../auth/AuthProvider";
import Panel from "../components/layout/Panel";
import Select from "../components/Select";
import { EmptyState } from "../components/State";
import { formatDate, formatMetric, formatOneDecimal, formatPercent } from "../format";
import { t, type MessageKey } from "../i18n";
import type { ModelVersion, Proposal, SegmentationOverview, ValidationMetrics } from "./api";
import { fetchGate } from "./api";
import ChangeDialog from "./ChangeDialog";
import GateList from "./GateList";
import ProposalActions from "./ProposalActions";
import { useModelActions } from "./useModelActions";

const STATUS_CLASS: Record<ModelVersion["status"], string> = {
  training: "status status--running",
  new: "status",
  proposed: "status status--corrected",
  in_use: "status status--confirmed",
  retired: "status",
  rejected: "status status--warning",
};

const REJECTED_REASONS: Record<string, MessageKey> = {
  incomplete: "models.rejected.incomplete",
  ambiguous: "models.rejected.ambiguous",
  bad_geometry: "models.rejected.bad_geometry",
};

function periods(v: ModelVersion): string {
  if (!v.periods.length) return "—";
  return v.periods.map((p) => (p.to ? `${formatDate(p.from)} – ${formatDate(p.to)}` : `${t("models.since")} ${formatDate(p.from)}`)).join(", ");
}

function mm(value: number | null): string {
  return value === null ? "—" : `${formatOneDecimal(value)} mm`;
}

// the last time a version was in use, short enough for a select
function lastUsed(v: ModelVersion): string {
  const last = v.periods[v.periods.length - 1];
  return last?.to ? t("models.compare.until", { v: v.version, date: formatDate(last.to) }) : v.version;
}

function pair(a: number | null, b: number | null): string {
  if (a === null && b === null) return "—";
  return `${formatMetric(a)} / ${formatMetric(b)}`;
}

function signedMl(value: number | null): string {
  if (value === null) return "—";
  return `${value > 0 ? "+" : ""}${formatOneDecimal(value)} ml`;
}

function MetricsTable({ current, next }: { current: ModelVersion | undefined; next: ModelVersion | undefined }) {
  const metrics: ValidationMetrics | null = next?.metrics ?? current?.metrics ?? null;
  const rows: { label: MessageKey; value: (m: ValidationMetrics) => string }[] = [
    { label: "models.metric.diceIou", value: (m) => pair(m.dice, m.iou) },
    { label: "models.metric.hd95", value: (m) => mm(m.hd95) },
    { label: "models.metric.diceSmall", value: (m) => formatMetric(m.diceSmall) },
    { label: "models.metric.volumeError", value: (m) => (m.volumeErrorPct === null ? "—" : `${m.volumeErrorPct}%`) },
  ];
  if (!metrics) return <p className="models__empty">{t("models.metrics.pending")}</p>;
  return (
    <table className="kv">
      <thead>
        <tr>
          <th>
            {[metrics.set && t(`models.set.${metrics.set}`), metrics.cases !== null && t("models.cases.count", { n: metrics.cases })].filter(Boolean).join(" · ")}
          </th>
          {current && (
            <th className="cell-right">
              {current.version} ({t("models.inUse.short")})
            </th>
          )}
          {next && <th className="cell-right">{next.version}</th>}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.label}>
            <th>{t(row.label)}</th>
            {current && <td className="cell-right">{current.metrics ? row.value(current.metrics) : "—"}</td>}
            {next && <td className="cell-right cell-strong">{next.metrics ? row.value(next.metrics) : "—"}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function trainingLine(training: Proposal["training"]): string | null {
  if (!training?.base) return null;
  return training.corrections !== null
    ? t("models.proposal.trainedOn", { base: training.base, n: training.corrections })
    : t("models.proposal.trainedFrom", { base: training.base });
}

function ProposalPanel({ proposal, versions }: { proposal: Proposal; versions: ModelVersion[] }) {
  const actions = useModelActions();
  const mine = useAuth().user?.login === proposal.author.login;
  const trained = trainingLine(proposal.training);

  return (
    <Panel
      title={t(proposal.restore ? "models.proposal.restoreTitle" : "models.proposal.title", { v: proposal.version, old: proposal.replaces })}
      aux={`${mine ? t("models.proposal.mine") : `${proposal.author.name} (${t(`role.${proposal.author.role}`)})`} · ${formatDate(proposal.at)}`}
    >
      <div className="models__two">
        <div className="models__pad">
          <GateList gate={proposal.gate} />
          {trained && (
            <>
              <p className="models__label">{t("models.proposal.training")}</p>
              <p>{trained}</p>
            </>
          )}
          <p className="models__label">{t("models.proposal.reason")}</p>
          <blockquote className="models__quote">{proposal.reason}</blockquote>
        </div>
        <div className="models__pad">
          <MetricsTable current={versions.find((v) => v.version === proposal.replaces)} next={versions.find((v) => v.version === proposal.version)} />
        </div>
      </div>
      <ProposalActions
        name={proposal.version}
        approveLabel={t(proposal.restore ? "models.restoreTo" : "models.promote", { v: proposal.version })}
        mine={mine}
        pending={actions.promote.isPending || actions.rollback.isPending || actions.reject.isPending || actions.withdraw.isPending}
        onApprove={() => (proposal.restore ? actions.rollback : actions.promote).mutate({ version: proposal.version })}
        onReject={(reason) => actions.reject.mutate({ version: proposal.version, reason })}
        onWithdraw={() => actions.withdraw.mutate(proposal.version)}
      />
    </Panel>
  );
}

function InUsePanel({ data }: { data: SegmentationOverview }) {
  const inUse = data.inUse!;
  const current = data.versions.find((v) => v.version === inUse.version);
  // only versions that were in use have anything to compare in the hospital
  const others = data.versions.filter((v) => v.version !== inUse.version && v.agreement);
  const [compared, setCompared] = useState(data.compareWith && others.some((v) => v.version === data.compareWith) ? data.compareWith : null);
  const other = others.find((v) => v.version === compared);
  const rejected = inUse.rejected.reduce((sum, r) => sum + r.count, 0);
  const summary = [
    inUse.studies !== null && t("models.inUse.studies", { n: inUse.studies }),
    rejected > 0 &&
      t("models.inUse.rejected", {
        n: rejected,
        why: inUse.rejected.map((r) => (REJECTED_REASONS[r.reason] ? t(REJECTED_REASONS[r.reason]) : r.reason)).join(", "),
      }),
  ]
    .filter(Boolean)
    .join(" ");

  const rows: { label: MessageKey; value: (v: ModelVersion) => string }[] = [
    { label: "models.agreement.approved", value: (v) => (v.agreement?.approved == null ? "—" : String(v.agreement.approved)) },
    { label: "models.agreement.unchanged", value: (v) => formatPercent(v.agreement?.unchanged) },
    { label: "models.agreement.dice", value: (v) => pair(v.agreement?.dice ?? null, v.agreement?.iou ?? null) },
    { label: "models.agreement.volume", value: (v) => signedMl(v.agreement?.volumeMl ?? null) },
  ];

  return (
    <Panel
      title={t("models.inUse.title", { v: inUse.version })}
      aux={[inUse.since && `${t("models.since")} ${formatDate(inUse.since)}`, inUse.approvedBy && `${t("models.approvedBy")} ${inUse.approvedBy.name}`]
        .filter(Boolean)
        .join(" · ")}
    >
      <div className="models__two">
        <div className="models__pad">
          <table className="kv">
            <thead>
              <tr>
                <th>{t("models.agreement")}</th>
                <th className="cell-right">
                  {inUse.version} ({t("models.inUse.short")})
                </th>
                {others.length > 0 && (
                  <th className="cell-right">
                    <span className="models__compare-head">
                      <label htmlFor="compare-version">{t("models.compare")}</label>
                      <Select
                        id="compare-version"
                        className="models__compare"
                        placeholder={t("models.compare.pick")}
                        value={compared ?? ""}
                        options={others.map((v) => v.version)}
                        label={(version) => lastUsed(others.find((v) => v.version === version)!)}
                        onChange={setCompared}
                      />
                    </span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.label}>
                  <th>{t(row.label)}</th>
                  <td className="cell-right cell-strong">{current ? row.value(current) : "—"}</td>
                  {others.length > 0 && <td className="cell-right">{other ? row.value(other) : ""}</td>}
                </tr>
              ))}
            </tbody>
          </table>
          {current?.agreement?.dice == null && <p className="note">{t("models.agreement.pending")}</p>}
        </div>
        <div className="models__pad">
          {inUse.weakest?.length ? (
            <table className="kv">
              <thead>
                <tr>
                  <th>{t("models.weakest", { v: inUse.version })}</th>
                  <th className="cell-right">{t("models.weakest.dice")}</th>
                </tr>
              </thead>
              <tbody>
                {inUse.weakest.map((c) => (
                  <tr key={c.studyId}>
                    <th>
                      <Link className="link" to={`/badania/${c.studyId}`}>
                        {t("models.weakest.study", { n: c.studyNumber })}
                      </Link>
                    </th>
                    <td className="cell-right">{formatMetric(c.dice)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="models__empty">{t("models.weakest.none")}</p>
          )}
          {summary && <p className="note">{summary}</p>}
        </div>
      </div>
    </Panel>
  );
}

function TrainingPanel({ training }: { training: NonNullable<SegmentationOverview["training"]> }) {
  const actions = useModelActions();
  const starts = useCan()("proposeModels");
  const run = training.run;

  if (run) {
    const pct = run.epoch !== null && run.epochs ? (run.epoch / run.epochs) * 100 : 0;
    return (
      <Panel title={t("models.training.title", { v: run.version })}>
        <div className="models__pad">
          <div className="line">
            <span>
              {t("models.training.epoch")}{" "}
              <b>
                {run.epoch ?? "—"} / {run.epochs ?? "—"}
              </b>
            </span>
            <div className="progress progress--running">
              <i style={{ width: `${pct}%` }} />
            </div>
            {run.etaHours !== null && <span>{t("models.training.eta", { h: run.etaHours })}</span>}
            {starts && run.canStop && (
              <button type="button" className="btn btn--small line__end" disabled={actions.stop.isPending} onClick={() => actions.stop.mutate()}>
                {t("models.training.stop")}
              </button>
            )}
          </div>
        </div>
      </Panel>
    );
  }

  const when =
    training.window && training.threshold !== null
      ? t("models.next.when", { date: formatDate(training.window.slice(0, 10)), time: training.window.slice(11, 16), n: training.threshold })
      : undefined;
  return (
    <Panel title={t("models.next")} aux={when}>
      <div className="models__pad">
        <div className="line">
          <span>
            {t("models.next.corrections")}{" "}
            <b>
              {training.corrections ?? "—"}
              {training.threshold !== null && ` / ${training.threshold}`}
            </b>
          </span>
          {training.corrections !== null && training.threshold ? (
            <div className="progress">
              <i style={{ width: `${Math.min(1, training.corrections / training.threshold) * 100}%` }} />
            </div>
          ) : null}
          {starts && training.canStart && (
            <button type="button" className="btn btn--small line__end" disabled={actions.train.isPending} onClick={() => actions.train.mutate()}>
              {t("models.next.start")}
            </button>
          )}
        </div>
      </div>
    </Panel>
  );
}

function SegmentationChange({ version, replaces, restore, proposing, onClose }: { version: string; replaces: string; restore: boolean; proposing: boolean; onClose: () => void }) {
  const actions = useModelActions();
  const title = proposing
    ? t(restore ? "models.dialog.proposeRestore" : "models.dialog.propose", { v: version, old: replaces })
    : t(restore ? "models.dialog.restore" : "models.dialog.change", { v: version, old: replaces });
  return (
    <ChangeDialog
      title={title}
      proposing={proposing}
      submitLabel={t(proposing ? "models.dialog.send" : restore ? "models.restore" : "models.dialog.changeButton")}
      gate={{ key: ["segmentation", version], load: () => fetchGate(version) }}
      pending={actions.propose.isPending || actions.promote.isPending || actions.rollback.isPending}
      error={actions.propose.error ?? actions.promote.error ?? actions.rollback.error}
      onSubmit={(reason, done) => {
        const options = { onSuccess: done };
        if (proposing) actions.propose.mutate({ version, reason, restore }, options);
        else (restore ? actions.rollback : actions.promote).mutate({ version, reason }, options);
      }}
      onClose={onClose}
    />
  );
}

function VersionsPanel({ data }: { data: SegmentationOverview }) {
  const can = useCan();
  const manages = can("manageModels");
  const proposes = can("proposeModels");
  const versions = data.versions;
  const set = versions.find((v) => v.metrics)?.metrics?.set;
  const [change, setChange] = useState<{ version: string; restore: boolean } | null>(null);
  // one proposal at a time
  const open = !data.proposal && !!data.inUse && proposes;

  const action = (v: ModelVersion) => {
    if (!open || (v.status !== "new" && v.status !== "retired")) return null;
    const restore = v.status === "retired";
    return (
      <button type="button" className={restore ? "btn btn--small" : "btn btn--small btn--primary"} onClick={() => setChange({ version: v.version, restore })}>
        {t(manages ? "models.use" : "models.propose")}
      </button>
    );
  };

  return (
    <Panel title={t("models.versions")} aux={t("models.versions.note")}>
      {versions.length === 0 ? (
        <EmptyState title={t("models.versions.empty")} body={t("models.versions.emptyBody")} />
      ) : (
        <>
          <table className="table">
            <thead>
              <tr>
                <th>{t("models.col.version")}</th>
                <th>{t("models.col.status")}</th>
                <th>{t("models.col.inUse")}</th>
                <th className="cell-right">Dice / IoU</th>
                <th className="cell-right">HD95</th>
                <th className="cell-right">{t("models.col.unchanged")}</th>
                <th>{t("models.col.decision")}</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {versions.map((v) => (
                <tr key={v.version}>
                  <td className="cell-strong">{v.version}</td>
                  <td>
                    <span className={STATUS_CLASS[v.status]}>{t(`models.status.${v.status}`)}</span>
                  </td>
                  <td>{periods(v)}</td>
                  <td className="cell-right">{v.metrics ? pair(v.metrics.dice, v.metrics.iou) : "—"}</td>
                  <td className="cell-right">{mm(v.metrics?.hd95 ?? null)}</td>
                  <td className="cell-right">{formatPercent(v.agreement?.unchanged)}</td>
                  <td>
                    {v.proposedBy || v.decidedBy ? `${v.proposedBy?.name ?? "—"} → ${v.decidedBy?.name ?? "—"}` : "—"}
                    {v.reason && (
                      <span className="models__why" title={v.reason}>
                        {v.reason}
                      </span>
                    )}
                  </td>
                  <td className="cell-right">{action(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {set && <p className="note">{t("models.versions.set", { set: t(`models.set.${set}`) })}</p>}
        </>
      )}
      {change && data.inUse && <SegmentationChange {...change} replaces={data.inUse.version} proposing={!manages} onClose={() => setChange(null)} />}
    </Panel>
  );
}

export default function SegmentationView({ data }: { data: SegmentationOverview }) {
  return (
    <div className="models">
      {data.proposal && <ProposalPanel proposal={data.proposal} versions={data.versions} />}
      {data.inUse ? (
        // remounts when another version goes into use
        <InUsePanel key={data.inUse.version} data={data} />
      ) : (
        <Panel title={t("models.inUse")}>
          <EmptyState title={t("models.inUse.none")} body={t("models.inUse.noneBody")} />
        </Panel>
      )}
      {data.training && <TrainingPanel training={data.training} />}
      <VersionsPanel data={data} />
    </div>
  );
}
