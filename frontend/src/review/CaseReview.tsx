import { useMutation } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import Page from "../components/layout/Page";
import Panel from "../components/layout/Panel";
import { useToast } from "../components/Toast";
import { formatDate, formatDecimal } from "../format";
import { t } from "../i18n";
import Viewer from "../viewer/Viewer";
import ViewerToolbar from "../viewer/ViewerToolbar";
import type { Series, Tool } from "../viewer/types";
import { useMaskEditor } from "../viewer/useMaskEditor";
import { approveCase, type DoneEntry, type QueueEntry, type ReviewCase } from "./api";
import BiradsForm, { type FieldState } from "./BiradsForm";
import { FIELDS, type FieldKey } from "./fields";
import MaskStrip from "./MaskStrip";
import ReportText from "./ReportText";
import ReviewQueue from "./ReviewQueue";

type Values = Partial<Record<FieldKey, string>>;
type States = Partial<Record<FieldKey, FieldState>>;

interface Props {
  data: ReviewCase;
  queue: QueueEntry[];
  done: DoneEntry[];
}

export default function CaseReview({ data, queue, done }: Props) {
  const navigate = useNavigate();
  const toast = useToast();
  const mask = useMaskEditor();
  const startedAt = useRef(Date.now());
  const [tool, setTool] = useState<Tool>("brush");
  const [series, setSeries] = useState<Series>("post");
  const [showMask, setShowMask] = useState(true);

  const keys = FIELDS.map((f) => f.key).filter((key) => data.proposals[key]);
  const [values, setValues] = useState<Values>(() => Object.fromEntries(keys.map((key) => [key, data.proposals[key]!.value])));
  const [states, setStates] = useState<States>({});

  const stateOf = (key: FieldKey, value: string): FieldState => (value === data.proposals[key]?.value ? "confirmed" : "corrected");
  const change = (key: FieldKey, value: string) => {
    setValues((v) => ({ ...v, [key]: value }));
    setStates((s) => ({ ...s, [key]: stateOf(key, value) }));
  };
  const confirm = (key: FieldKey) => setStates((s) => ({ ...s, [key]: stateOf(key, values[key] ?? "") }));
  const confirmAll = () => setStates(Object.fromEntries(keys.map((key) => [key, states[key] ?? stateOf(key, values[key] ?? "")])));

  const openFields = keys.filter((key) => !states[key]);
  const flagged = openFields.filter((key) => data.proposals[key]?.disagreement).length;
  const ready = mask.state !== "proposed" && openFields.length === 0;

  const next = () => {
    const i = queue.findIndex((q) => q.studyId === data.studyId);
    const following = queue[(i + 1) % queue.length];
    navigate(`/weryfikacja/${following.studyId}`);
  };

  const approve = useMutation({
    mutationFn: () =>
      approveCase(data.studyId, {
        mask: mask.state === "corrected" ? "corrected" : "confirmed",
        strokes: mask.strokes.length,
        fields: Object.fromEntries(keys.map((key) => [key, { value: values[key] ?? "", state: states[key] === "corrected" ? "corrected" : "confirmed" }])),
        editingSeconds: Math.round((Date.now() - startedAt.current) / 1000),
      }),
    onSuccess: () => {
      toast(t("review.approved", { n: data.studyNumber }));
      next();
    },
  });

  const approveRef = useRef(() => {});
  approveRef.current = () => ready && !approve.isPending && approve.mutate();

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement).matches("input, select, textarea")) return;
      const mod = event.metaKey || event.ctrlKey;
      if (mod && event.key === "Enter") return approveRef.current();
      if (mod && event.key.toLowerCase() === "z") {
        event.preventDefault();
        return mask.undo();
      }
      if (mod || event.altKey) return;
      const tools: Record<string, Tool> = { b: "brush", e: "eraser", p: "pan", w: "window" };
      if (tools[event.key]) setTool(tools[event.key]);
      else if (event.key === "m") setShowMask((s) => !s);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mask.undo]);

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
          <span>
            {t("review.uncertainty")} <b>{formatDecimal(data.uncertainty)}</b>
          </span>
          <span>
            {t("review.segmentation")} <b>{t("models.version")} {data.segmentationVersion}</b>
            {data.extractionVersion && (
              <>
                {" "}
                · {t("review.extraction")} <b>{t("models.version")} {data.extractionVersion}</b>
              </>
            )}
          </span>
        </>
      }
      actions={
        <>
          <button type="button" className="btn" onClick={next}>
            {t("review.skip")}
          </button>
          <button type="button" className="btn btn--primary" disabled={!ready || approve.isPending} onClick={() => approve.mutate()}>
            {t("review.approve")} <kbd>Ctrl ↵</kbd>
          </button>
        </>
      }
    >
      <div className="review">
        <ReviewQueue queue={queue} done={done} currentId={data.studyId} />

        <section className="review__view" aria-label={t("viewer.image")}>
          <ViewerToolbar
            tool={tool}
            onTool={setTool}
            onUndo={mask.undo}
            canUndo={mask.strokes.length > 0}
            showMask={showMask}
            onToggleMask={() => setShowMask((s) => !s)}
            series={series}
            onSeries={setSeries}
          />
          <Viewer lesion={data.lesion} series={series} mask={mask.state} strokes={mask.strokes} showMask={showMask} tool={tool} editable onStroke={mask.addStroke} />
          <MaskStrip state={mask.state} measurements={data.measurements} onConfirm={mask.confirm} onRestore={mask.restoreModel} />
        </section>

        <section className="review__form" aria-label={t("review.form")}>
          <div className="review__form-body">
            <Panel title={t("review.report")}>
              <div className="review__section">
                {data.report ? (
                  <ReportText parts={data.report} states={states} />
                ) : (
                  <div className="empty-box">
                    <b>{t("review.noReport")}</b>
                    {t("review.noReportBody")}
                    <br />
                    <Link className="btn" to={`/badania?badanie=${data.studyId}`}>
                      {t("review.attachReport")}
                    </Link>
                  </div>
                )}
              </div>
            </Panel>
            <Panel
              title={t("review.form")}
              aux={
                !data.report
                  ? t("review.formWaitsAux")
                  : openFields.length
                    ? `${t("review.toConfirm", { n: openFields.length })}${flagged ? ` · ${t("review.flagged", { n: flagged })}` : ""}`
                    : t("review.done")
              }
            >
              <div className="review__section">
                {data.report ? (
                  <BiradsForm proposals={data.proposals} values={values} states={states} onChange={change} onConfirm={confirm} />
                ) : (
                  <div className="empty-box">{t("review.formWaits")}</div>
                )}
              </div>
            </Panel>
          </div>
          {data.report && (
            <div className="review__foot">
              <button type="button" className="btn" disabled={openFields.length === 0} onClick={confirmAll}>
                {t("review.confirmAll")}
              </button>
            </div>
          )}
        </section>
      </div>
    </Page>
  );
}
