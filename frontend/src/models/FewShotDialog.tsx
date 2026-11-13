import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { t } from "../i18n";
import { lesionGroup, observationGroups, rowLines, visibleRows } from "../review/rows";
import ReportText from "../review/ReportText";
import { fetchFewShot, type FewShotExample } from "./extraction";
import "../review/review.css";

function Answer({ example, json }: { example: FewShotExample; json: boolean }) {
  if (json) return <pre className="examples__json">{JSON.stringify(example.output, null, 2)}</pre>;
  const report = example.output;
  return (
    <>
      {report.zmiany.map((lesion, i) => (
        <div key={lesion.id}>
          <p className="models__label">{t("models.examples.lesion", { n: i + 1 })}</p>
          <table className="kv">
            <tbody>
              {[lesionGroup(i), ...observationGroups(report, i)].flatMap((group, k) => [
                ...(k > 0
                  ? [
                      <tr key={group.key} className="kv__group">
                        <th colSpan={2}>{group.title}</th>
                      </tr>,
                    ]
                  : []),
                // as the model should answer: only what the report says
                ...visibleRows(group, report, report, [])
                  .filter((row) => rowLines(row, report).some((line) => line.text))
                  .map((row) => (
                    <tr key={row.key}>
                      <th>{row.label}</th>
                      <td className="cell-right">
                        {rowLines(row, report, lesion.strona)
                          .map((line) => [line.text, line.extra].filter(Boolean).join(" · "))
                          .join("; ")}
                      </td>
                    </tr>
                  )),
              ])}
            </tbody>
          </table>
        </div>
      ))}
    </>
  );
}

export default function FewShotDialog({ version, onClose }: { version: string; onClose: () => void }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const examples = useQuery({ queryKey: ["models", "few-shot", version], queryFn: () => fetchFewShot(version) });
  const [picked, setPicked] = useState(0);
  const [json, setJson] = useState(false);
  const example = examples.data?.[picked];

  useEffect(() => {
    dialog.current?.showModal();
  }, []);

  const title = t("models.examples.title", { v: version });
  return (
    <dialog ref={dialog} className="examples" aria-label={title} onClose={onClose} onClick={(event) => event.target === dialog.current && dialog.current.close()}>
      <div className="examples__head">
        {title}
        <button type="button" className="btn btn--small" onClick={() => dialog.current?.close()}>
          ✕ {t("review.original.close")}
        </button>
      </div>
      {examples.isPending ? (
        <p className="models__pad models__empty">{t("models.loading")}</p>
      ) : !examples.data?.length ? (
        <p className="models__pad models__empty">{t("models.examples.none")}</p>
      ) : (
        <div className="examples__cols">
          <ul className="examples__list">
            {examples.data.map((e, i) => (
              <li key={e.id}>
                <button type="button" aria-pressed={i === picked} onClick={() => setPicked(i)}>
                  {e.title}
                  {e.isNew && <span className="status status--corrected">{t("models.examples.new")}</span>}
                </button>
              </li>
            ))}
          </ul>
          {example && (
            <>
              <div className="examples__text">
                <p className="models__label">{t("models.examples.report")}</p>
                <ReportText text={example.report} quotes={example.output.zmiany.flatMap((l) => l.obserwacje.map((o) => o.cytat))} />
              </div>
              <div className="examples__answer">
                <div className="examples__tabs" role="tablist">
                  <button type="button" role="tab" aria-selected={!json} onClick={() => setJson(false)}>
                    {t("models.examples.fields")}
                  </button>
                  <button type="button" role="tab" aria-selected={json} onClick={() => setJson(true)}>
                    JSON
                  </button>
                </div>
                <Answer example={example} json={json} />
              </div>
            </>
          )}
        </div>
      )}
    </dialog>
  );
}
