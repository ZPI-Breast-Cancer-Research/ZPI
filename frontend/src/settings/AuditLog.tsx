import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import Panel from "../components/layout/Panel";
import { formatDate, toIsoDate } from "../format";
import { plural, t } from "../i18n";
import { fetchAudit, GROUP_OF, TARGET_OF, type AuditEntry, type AuditGroup } from "./audit";

const GROUPS: AuditGroup[] = ["review", "models", "accounts", "logins"];
const PAGE = 50;

function target(entry: AuditEntry) {
  const group = GROUP_OF[entry.kind];
  const kind = group ? TARGET_OF[group] : undefined;
  if (!kind || kind === "account") return entry.object;
  const translated = t(`audit.target.${kind}`, { ref: entry.object });
  return entry.object ? (translated ?? entry.object) : (t("audit.target.modelNext") ?? "—");
}

const when = (iso: string) => `${formatDate(iso.slice(0, 10))}, ${iso.slice(11, 16)}`;

// semicolons and a BOM, so it opens straight in a Polish Excel
function exportCsv(rows: AuditEntry[]) {
  const cell = (value: string | undefined | null) => `"${(value ?? "").replace(/"/g, '""')}"`;
  const head = ["audit.col.when", "settings.col.login", "settings.col.name", "audit.col.event", "audit.col.object", "audit.col.detail"] as const;
  const lines = [
    head.map((key) => cell(t(key))).join(";"),
    ...rows.map((row) => [
      when(row.at), 
      row.login, 
      row.name, 
      t(`audit.kind.${row.kind}`) ?? row.kind, 
      target(row), 
      row.detail ?? ""
    ].map(cell).join(";")),
  ];
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob(["" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" }));
  link.download = `dziennik-zdarzen-${toIsoDate(new Date())}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

// who changed what and when (Q5); entries can't be edited or removed from here
export default function AuditLog() {
  const { data = [] } = useQuery({ queryKey: ["audit"], queryFn: fetchAudit });
  const [person, setPerson] = useState("");
  const [group, setGroup] = useState<AuditGroup | "">("");
  const [object, setObject] = useState("");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [shown, setShown] = useState(PAGE);

  const people = useMemo(() => [...new Map(data.map((row) => [row.login, row.name])).entries()].sort((a, b) => a[0].localeCompare(b[0])), [data]);
  const rows = data.filter((row) => {
    const day = row.at.slice(0, 10);
    return (
      (!person || row.login === person) &&
      (!group || GROUP_OF[row.kind] === group) &&
      (!object || target(row).toLowerCase().includes(object.trim().toLowerCase())) &&
      (!from || day >= from) &&
      (!to || day <= to)
    );
  });
  const filtered = person || group || object || from || to;

  const reset = () => {
    setPerson("");
    setGroup("");
    setObject("");
    setFrom("");
    setTo("");
  };

  return (
    <Panel
      title={t("audit.title")}
      className="settings__section"
      aux={
        <span className="audit__tools">
          {plural(rows.length, "audit.count.one", "audit.count.few", "audit.count.many")}
          <button type="button" className="btn btn--small" disabled={!rows.length} onClick={() => exportCsv(rows)}>
            {t("audit.export")}
          </button>
        </span>
      }
    >
      <div className="audit__filters">
        <label className="field">
          <span>{t("audit.filter.person")}</span>
          <select className="select" value={person} onChange={(e) => setPerson(e.target.value)}>
            <option value="">{t("audit.filter.all")}</option>
            {people.map(([login, name]) => (
              <option key={login} value={login}>
                {name === "—" ? login : `${name} (${login})`}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t("audit.filter.group")}</span>
          <select className="select" value={group} onChange={(e) => setGroup(e.target.value as AuditGroup | "")}>
            <option value="">{t("audit.filter.all")}</option>
            {GROUPS.map((name) => (
              <option key={name} value={name}>
                {t(`audit.group.${name}`)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>{t("audit.filter.object")}</span>
          <input className="input" value={object} placeholder="#0012, v4, radiolog2" onChange={(e) => setObject(e.target.value)} />
        </label>
        <label className="field">
          <span>{t("audit.filter.from")}</span>
          <input className="input" type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="field">
          <span>{t("audit.filter.to")}</span>
          <input className="input" type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} />
        </label>
        {filtered && (
          <button type="button" className="link audit__clear" onClick={reset}>
            {t("audit.filter.clear")}
          </button>
        )}
      </div>
      <table className="table">
        <thead>
          <tr>
            <th>{t("audit.col.when")}</th>
            <th>{t("audit.col.who")}</th>
            <th>{t("audit.col.event")}</th>
            <th>{t("audit.col.object")}</th>
            <th>{t("audit.col.detail")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, shown).map((row) => (
            <tr key={row.id}>
              <td className="audit__when">{when(row.at)}</td>
              <td>
                {row.name === "—" ? row.login : row.name}
                {row.name !== "—" && <span className="audit__login"> {row.login}</span>}
              </td>
              <td className={row.kind === "login_failed" ? "audit__alert" : undefined}>
                {t(`audit.kind.${row.kind}`) ?? row.kind}
              </td>
              <td>{target(row)}</td>
              <td>{row.detail ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <p className="note">{t("audit.empty")}</p>}
      {rows.length > shown && (
        <div className="settings__body">
          <button type="button" className="btn" onClick={() => setShown(shown + PAGE)}>
            {t("audit.more")}
          </button>
        </div>
      )}
    </Panel>
  );
}