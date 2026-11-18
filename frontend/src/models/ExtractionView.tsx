import { useState } from "react";

import { useAuth, useCan } from "../auth/AuthProvider";
import Panel from "../components/layout/Panel";
import { EmptyState } from "../components/State";
import { formatDate, formatMetric, formatPercent } from "../format";
import { t } from "../i18n";
import { anyFieldLabel } from "../review/fields";
import ChangeDialog from "./ChangeDialog";
import DraftDialog from "./DraftDialog";
import type { ExtractionOverview, ExtractionProposal, ExtractionVersion } from "./extraction";
import FewShotDialog from "./FewShotDialog";
import GateList from "./GateList";
import ProposalActions from "./ProposalActions";
import { useExtractionActions } from "./useExtractionActions";

const STATUS_CLASS: Record<ExtractionVersion["status"], string> = {
  training: "status status--running",
  new: "status",
  proposed: "status status--corrected",
  in_use: "status status--confirmed",
  retired: "status",
  rejected: "status status--warning",
};

function periods(v: ExtractionVersion): string {
  if (!v.periods.length) return "—";
  return v.periods.map((p) => (p.to ? `${formatDate(p.from)} – ${formatDate(p.to)}` : `${t("models.since")} ${formatDate(p.from)}`)).join(", ");
}

const yesNo = (value: boolean) => t(value ? "models.ext.yes" : "models.ext.no");

// "old → new", or the value and "bez zmian" when the proposal keeps it
function change(current: string | undefined, next: string): string {
  if (current === undefined) return next || "—";
  return current === next ? `${next || "—"} (${t("models.ext.same")})` : `${current || "—"} → ${next || "—"}`;
}

function ProposalPanel({ proposal }: { proposal: ExtractionProposal }) {
  const actions = useExtractionActions();
  const mine = useAuth().user?.login === proposal.author.login;
  const [examples, setExamples] = useState(false);
  const { version: next, replaces } = proposal;
  const target = { version: next.version };

  return (
    <Panel
      title={
        next.restore && replaces
          ? t("models.proposal.restoreTitle", { v: next.version, old: replaces.version })
          : t("models.ext.proposal", { v: next.version })
      }
      aux={[mine ? t("models.proposal.mine") : proposal.author.name, proposal.at && formatDate(proposal.at)].filter(Boolean).join(" · ")}
    >
      <div className="models__two">
        <div className="models__pad">
          <table className="kv">
            <tbody>
              <tr>
                <th>{t("models.ext.llm")}</th>
                <td className="cell-right">{change(replaces?.llmModel, next.llmModel)}</td>
              </tr>
              <tr>
                <th>{t("models.ext.structured")}</th>
                <td className="cell-right">{change(replaces ? yesNo(replaces.structuredOutput) : undefined, yesNo(next.structuredOutput))}</td>
              </tr>
              <tr>
                <th>{t("models.ext.fewShot")}</th>
                <td className="cell-right">
                  {replaces ? `${replaces.examples} → ${next.examples}` : next.examples}
                  {" · "}
                  <button type="button" className="link" onClick={() => setExamples(true)}>
                    {t("models.ext.examples")}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <p className="models__label">{t("models.proposal.reason")}</p>
          <blockquote className="models__quote">{proposal.reason}</blockquote>
          <GateList gate={null} />
        </div>
        <div className="models__pad">
          {next.f1 !== null || replaces?.f1 != null ? (
            <table className="kv">
              <thead>
                <tr>
                  <th />
                  <th className="cell-right">
                    {replaces?.version ?? "—"} ({t("models.inUse.short")})
                  </th>
                  <th className="cell-right">{next.version}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th>{t("models.ext.f1")}</th>
                  <td className="cell-right">{formatMetric(replaces?.f1 ?? null)}</td>
                  <td className="cell-right cell-strong">{formatMetric(next.f1)}</td>
                </tr>
              </tbody>
            </table>
          ) : (
            <p className="models__empty">{t("models.metrics.pending")}</p>
          )}
        </div>
      </div>
      <ProposalActions
        name={next.version}
        approveLabel={t("models.ext.approve", { v: next.version })}
        mine={mine}
        pending={actions.apply.isPending || actions.reject.isPending || actions.withdraw.isPending}
        onApprove={() => actions.apply.mutate(target)}
        onReject={(reason) => actions.reject.mutate({ ...target, reason })}
        onWithdraw={() => actions.withdraw.mutate(target)}
      />
      {examples && <FewShotDialog version={next.version} onClose={() => setExamples(false)} />}
    </Panel>
  );
}

function InUsePanel({ data }: { data: ExtractionOverview }) {
  const inUse = data.inUse!;
  const rows: [string, number | null][] = [
    [t("models.ext.verified"), inUse.verified],
    [t("models.ext.failed"), inUse.failed],
    [t("models.ext.corrected"), inUse.corrected],
  ];
  return (
    <Panel
      title={inUse.model ? t("models.ext.inUse", { v: inUse.version, model: inUse.model }) : t("models.inUse.title", { v: inUse.version })}
      aux={[inUse.since && `${t("models.since")} ${formatDate(inUse.since)}`, inUse.approvedBy && `${t("models.approvedBy")} ${inUse.approvedBy.name}`]
        .filter(Boolean)
        .join(" · ")}
    >
      <div className="models__two">
        <div className="models__pad">
          <table className="kv">
            <thead>
              <tr>
                <th>{t("models.ext.field")}</th>
                <th className="cell-right">{data.testReports !== null ? t("models.ext.accuracyOn", { n: data.testReports }) : t("models.ext.accuracy")}</th>
                <th className="cell-right">{t("models.ext.correctedShare")}</th>
              </tr>
            </thead>
            <tbody>
              {data.fields.map((f) => (
                <tr key={f.field}>
                  <th>{anyFieldLabel(f.field)}</th>
                  <td className="cell-right">{formatPercent(f.accuracy)}</td>
                  <td className="cell-right">{formatPercent(f.corrected)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="models__pad">
          <table className="kv">
            <tbody>
              {rows.map(([name, value]) => (
                <tr key={name}>
                  <th>{name}</th>
                  <td className="cell-right">{value ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Panel>
  );
}

function ProposeDialog({ version, replaces, onClose }: { version: ExtractionVersion; replaces: string | null; onClose: () => void }) {
  const actions = useExtractionActions();
  const restore = version.status === "retired";
  return (
    <ChangeDialog
      title={
        replaces
          ? t(restore ? "models.dialog.proposeRestore" : "models.dialog.propose", { v: version.version, old: replaces })
          : t("models.ext.dialog.propose", { v: version.version })
      }
      proposing
      submitLabel={t("models.dialog.send")}
      pending={actions.propose.isPending}
      error={actions.propose.error}
      onSubmit={(reason, done) => actions.propose.mutate({ version: version.version, reason }, { onSuccess: done })}
      onClose={onClose}
    />
  );
}

function Registry({ data }: { data: ExtractionOverview }) {
  const proposes = useCan()("proposeModels");
  const actions = useExtractionActions();
  const [proposing, setProposing] = useState<ExtractionVersion | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [examples, setExamples] = useState<string | null>(null);
  // one proposal at a time
  const open = !data.proposal && proposes;

  return (
    <Panel
      title={t("models.ext.versions")}
      aux={
        proposes ? (
          <button type="button" className="btn btn--small" disabled={actions.create.isPending} onClick={() => actions.create.mutate()}>
            {t("models.ext.new")}
          </button>
        ) : undefined
      }
    >
      {data.versions.length === 0 ? (
        <EmptyState title={t("models.versions.empty")} />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t("models.col.version")}</th>
              <th>{t("models.ext.col.model")}</th>
              <th>{t("models.ext.col.examples")}</th>
              <th>{t("models.col.status")}</th>
              <th>{t("models.col.inUse")}</th>
              <th className="cell-right">F1</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {data.versions.map((v) => (
              <tr key={v.version}>
                <td className="cell-strong">{v.version}</td>
                <td>{v.llmModel || "—"}</td>
                <td>
                  <button type="button" className="link" onClick={() => setExamples(v.version)}>
                    {t("models.ext.show", { n: v.examples })}
                  </button>
                </td>
                <td>
                  <span className={STATUS_CLASS[v.status]}>{t(`models.status.${v.status}`)}</span>
                </td>
                <td>{periods(v)}</td>
                <td className="cell-right">{formatMetric(v.f1)}</td>
                <td className="cell-right">
                  {proposes && v.editable && (
                    <button type="button" className="btn btn--small" onClick={() => setEditing(v.version)}>
                      {t("models.ext.edit")}
                    </button>
                  )}
                  {open && (v.status === "new" || v.status === "retired") && (
                    <button
                      type="button"
                      className={v.status === "new" ? "btn btn--small btn--primary" : "btn btn--small"}
                      disabled={!v.llmModel}
                      title={v.llmModel ? undefined : t("models.ext.needsModel")}
                      onClick={() => setProposing(v)}
                    >
                      {t(v.status === "retired" ? "models.ext.restore" : "models.propose")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data.versions.length > 0 && <p className="note">{t("models.ext.f1Note")}</p>}
      {proposing && <ProposeDialog version={proposing} replaces={data.inUse?.version ?? null} onClose={() => setProposing(null)} />}
      {editing && <DraftDialog version={editing} onClose={() => setEditing(null)} />}
      {examples && <FewShotDialog version={examples} onClose={() => setExamples(null)} />}
    </Panel>
  );
}

export default function ExtractionView({ data }: { data: ExtractionOverview }) {
  return (
    <div className="models">
      {data.proposal && <ProposalPanel proposal={data.proposal} />}
      {data.inUse ? (
        <InUsePanel data={data} />
      ) : (
        <Panel title={t("models.inUse")}>
          <EmptyState title={t("models.inUse.none")} />
        </Panel>
      )}
      <Registry data={data} />
    </div>
  );
}
