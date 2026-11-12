import { useState } from "react";

import { useAuth, useCan } from "../auth/AuthProvider";
import Panel from "../components/layout/Panel";
import { EmptyState } from "../components/State";
import { formatDate, formatMetric, formatPercent } from "../format";
import { t } from "../i18n";
import { fieldLabel, FIELDS, type FieldKey } from "../review/fields";
import ChangeDialog from "./ChangeDialog";
import { fetchExtractionGate, type ExtractionOverview, type ExtractionPart, type ExtractionProposal, type ExtractionVersion } from "./extraction";
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

// an older backend sends labels instead of field keys
const label = (field: string) => (FIELDS.some((f) => f.key === field) ? fieldLabel(field as FieldKey) : field);

function periods(v: ExtractionVersion): string {
  if (!v.periods.length) return "—";
  return v.periods.map((p) => (p.to ? `${formatDate(p.from)} – ${formatDate(p.to)}` : `${t("models.since")} ${formatDate(p.from)}`)).join(", ");
}

function ProposalPanel({ data, proposal }: { data: ExtractionOverview; proposal: ExtractionProposal }) {
  const actions = useExtractionActions();
  const mine = useAuth().user?.login === proposal.author.login;
  const [examples, setExamples] = useState(false);
  const target = { part: proposal.part, name: proposal.name };
  const fewShot = data.fewShots.find((v) => v.name === proposal.name);
  const model = proposal.part === "model";

  return (
    <Panel
      title={t(model ? "models.ext.proposal.model" : "models.ext.proposal.fewShot", { v: proposal.name })}
      aux={`${mine ? t("models.proposal.mine") : `${proposal.author.name} (${t(`role.${proposal.author.role}`)})`} · ${formatDate(proposal.at)}`}
    >
      <div className="models__two">
        <div className="models__pad">
          <table className="kv">
            <tbody>
              <tr>
                <th>{t("models.ext.llm")}</th>
                <td className="cell-right">{model ? `${proposal.replaces} → ${proposal.name}` : `${data.inUse?.model ?? "—"} (${t("models.ext.same")})`}</td>
              </tr>
              <tr>
                <th>{t("models.ext.fewShot")}</th>
                <td className="cell-right">
                  {model ? `${data.inUse?.fewShot ?? "—"} (${t("models.ext.same")})` : `${proposal.replaces} → ${proposal.name}`}
                  {!model && fewShot?.examples != null && (
                    <>
                      {" · "}
                      <button type="button" className="link" onClick={() => setExamples(true)}>
                        {t("models.ext.examples", { n: fewShot.examples })}
                      </button>
                    </>
                  )}
                </td>
              </tr>
            </tbody>
          </table>
          <p className="models__label">{t("models.proposal.reason")}</p>
          <blockquote className="models__quote">{proposal.reason}</blockquote>
          <GateList gate={proposal.gate} />
        </div>
        <div className="models__pad">
          {proposal.fields || proposal.f1 ? (
            <table className="kv">
              <thead>
                <tr>
                  <th>{data.testReports !== null ? t("models.ext.accuracyOn", { n: data.testReports }) : t("models.ext.accuracy")}</th>
                  <th className="cell-right">
                    {proposal.replaces} ({t("models.inUse.short")})
                  </th>
                  <th className="cell-right">{proposal.name}</th>
                </tr>
              </thead>
              <tbody>
                {(proposal.fields ?? []).map((f) => (
                  <tr key={f.field}>
                    <th>{label(f.field)}</th>
                    <td className="cell-right">{formatPercent(f.current)}</td>
                    <td className="cell-right cell-strong">{formatPercent(f.next)}</td>
                  </tr>
                ))}
                {proposal.f1 && (
                  <tr>
                    <th>{t("models.ext.f1")}</th>
                    <td className="cell-right">{formatMetric(proposal.f1.current)}</td>
                    <td className="cell-right cell-strong">{formatMetric(proposal.f1.next)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          ) : (
            <p className="models__empty">{t("models.metrics.pending")}</p>
          )}
        </div>
      </div>
      <ProposalActions
        name={proposal.name}
        approveLabel={t(model ? "models.ext.approveModel" : "models.ext.approveFewShot", { v: proposal.name })}
        mine={mine}
        pending={actions.apply.isPending || actions.reject.isPending || actions.withdraw.isPending}
        onApprove={() => actions.apply.mutate(target)}
        onReject={(reason) => actions.reject.mutate({ ...target, reason })}
        onWithdraw={() => actions.withdraw.mutate(target)}
      />
      {examples && <FewShotDialog version={proposal.name} onClose={() => setExamples(false)} />}
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
      title={inUse.fewShot ? t("models.ext.inUse", { model: inUse.model ?? "—", v: inUse.fewShot }) : t("models.inUse.title", { v: inUse.model ?? "—" })}
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
                  <th>{label(f.field)}</th>
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

function ExtractionChange({ part, name, replaces, proposing, onClose }: { part: ExtractionPart; name: string; replaces: string; proposing: boolean; onClose: () => void }) {
  const actions = useExtractionActions();
  const key = part === "model" ? "model" : "fewShot";
  return (
    <ChangeDialog
      title={t(proposing ? `models.ext.dialog.propose.${key}` : `models.ext.dialog.change.${key}`, { v: name, old: replaces })}
      proposing={proposing}
      submitLabel={t(proposing ? "models.dialog.send" : "models.dialog.changeButton")}
      gate={{ key: ["extraction", part, name], load: () => fetchExtractionGate(part, name) }}
      pending={actions.propose.isPending || actions.apply.isPending}
      error={actions.propose.error ?? actions.apply.error}
      onSubmit={(reason, done) => (proposing ? actions.propose : actions.apply).mutate({ part, name, reason }, { onSuccess: done })}
      onClose={onClose}
    />
  );
}

function Registry({ data, part }: { data: ExtractionOverview; part: ExtractionPart }) {
  const can = useCan();
  const manages = can("manageModels");
  const proposes = can("proposeModels");
  const [change, setChange] = useState<string | null>(null);
  const [examples, setExamples] = useState<string | null>(null);
  const fewShot = part === "few_shot";
  const versions = fewShot ? data.fewShots : data.models;
  const current = fewShot ? data.inUse?.fewShot : data.inUse?.model;
  // one proposal at a time
  const open = !data.proposal && !!current && proposes;

  return (
    <Panel title={t(fewShot ? "models.ext.fewShots" : "models.ext.models")}>
      {versions.length === 0 ? (
        <EmptyState title={t("models.versions.empty")} />
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>{t(fewShot ? "models.col.version" : "models.ext.col.model")}</th>
              {fewShot && <th>{t("models.ext.col.examples")}</th>}
              <th>{t("models.col.status")}</th>
              <th>{t("models.col.inUse")}</th>
              <th className="cell-right">F1</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.name}>
                <td className="cell-strong">{v.name}</td>
                {fewShot && (
                  <td>
                    {v.examples === null ? (
                      "—"
                    ) : (
                      <button type="button" className="link" onClick={() => setExamples(v.name)}>
                        {t("models.ext.show", { n: v.examples })}
                      </button>
                    )}
                  </td>
                )}
                <td>
                  <span className={STATUS_CLASS[v.status]}>{t(fewShot ? `models.status.${v.status}` : `models.ext.status.${v.status}`)}</span>
                </td>
                <td>{periods(v)}</td>
                <td className="cell-right">{formatMetric(v.f1)}</td>
                <td className="cell-right">
                  {open && (v.status === "new" || v.status === "retired") && (
                    <button type="button" className={v.status === "new" ? "btn btn--small btn--primary" : "btn btn--small"} onClick={() => setChange(v.name)}>
                      {t(manages ? "models.use" : "models.propose")}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {change && current && <ExtractionChange part={part} name={change} replaces={current} proposing={!manages} onClose={() => setChange(null)} />}
      {examples && <FewShotDialog version={examples} onClose={() => setExamples(null)} />}
    </Panel>
  );
}

export default function ExtractionView({ data }: { data: ExtractionOverview }) {
  return (
    <div className="models">
      {data.proposal && <ProposalPanel data={data} proposal={data.proposal} />}
      {data.inUse ? (
        <InUsePanel data={data} />
      ) : (
        <Panel title={t("models.inUse")}>
          <EmptyState title={t("models.inUse.none")} />
        </Panel>
      )}
      <div className="models__two models__registries">
        <Registry data={data} part="model" />
        <Registry data={data} part="few_shot" />
      </div>
      <p className="note">{t("models.ext.f1Note")}</p>
    </div>
  );
}
