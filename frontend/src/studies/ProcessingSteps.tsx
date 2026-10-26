import { useQuery } from "@tanstack/react-query";

import Panel from "../components/layout/Panel";
import { t } from "../i18n";
import { getProcessingSteps, type StepState, type StudyRow } from "./api";

const STATE_CLASS: Record<StepState, string> = {
  done: "status status--confirmed",
  running: "status status--running",
  waiting: "status",
  waiting_report: "status",
  error: "status status--warning",
};

export default function ProcessingSteps({ study }: { study: StudyRow | null }) {
  const { data } = useQuery({
    queryKey: ["processing-steps", study?.id],
    queryFn: () => getProcessingSteps(study!),
    enabled: study !== null,
  });

  const title = study?.number ? `${t("studies.steps")} #${study.number}` : t("studies.steps");

  return (
    <Panel title={title}>
      {!study ? (
        <p className="note">{t("studies.steps.select")}</p>
      ) : (
        <table className="table steps">
          <tbody>
            {data?.map((step, i) => (
              <tr key={step.key} className={step.state === "waiting" || step.state === "waiting_report" ? "steps__waiting" : undefined}>
                <td className="steps__n">{i + 1}</td>
                <td>{t(`studies.step.${step.key}`)}</td>
                <td className="cell-right">
                  <span className={STATE_CLASS[step.state]}>{t(`studies.stepState.${step.state}`)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}
