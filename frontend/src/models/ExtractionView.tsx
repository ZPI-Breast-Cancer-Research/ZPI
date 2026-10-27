import Panel from "../components/layout/Panel";
import WarningIcon from "../components/WarningIcon";
import { formatDate, formatMetric, formatPercent } from "../format";
import { t } from "../i18n";
import type { ExtractionOverview } from "./api";

export default function ExtractionView({ data }: { data: ExtractionOverview }) {
  const worst = Math.max(...data.fields.map((f) => f.correctedShare));

  return (
    <div className="models">
      <Panel
        title={
          <>
            {t("models.inUse")} · {t("models.version")} {data.version}
          </>
        }
        aux={`${t("models.ext.info")} · ${t("models.since")} ${formatDate(data.since)}`}
      >
        <div className="models__two">
          <div>
            <div className="models__pad">
              <table className="kv">
                <thead>
                  <tr>
                    <th>{t("models.ext.field")}</th>
                    <th className="cell-right">{t("models.ext.f1")}</th>
                    <th className="cell-right">{t("models.ext.corrected")}</th>
                  </tr>
                </thead>
                <tbody>
                  {data.fields.map((f) => (
                    <tr key={f.field}>
                      <th>
                        {f.correctedShare === worst && <WarningIcon />}
                        {f.field}
                      </th>
                      <td className="cell-right">{formatMetric(f.f1)}</td>
                      <td className="cell-right">{formatPercent(f.correctedShare)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="note">{t("models.ext.mostCorrected")}</p>
          </div>
          <div className="models__pad">
            <table className="kv">
              <tbody>
                <tr>
                  <th>{t("models.ext.llm")}</th>
                  <td className="cell-right">
                    {t("models.version")} {data.version}
                  </td>
                </tr>
                <tr>
                  <th>{t("models.ext.prompt")}</th>
                  <td className="cell-right">
                    {t("models.version")} {data.version}
                  </td>
                </tr>
                <tr>
                  <th>{t("models.ext.pool")}</th>
                  <td className="cell-right">{t("models.ext.poolValue", { n: data.examplePool })}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </Panel>
      <Panel title={t("models.next")}>
        <p className="models__pad models__sub">{t("models.ext.next")}</p>
      </Panel>
    </div>
  );
}
