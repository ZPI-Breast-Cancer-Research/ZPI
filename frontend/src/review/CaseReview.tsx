import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import Page from "../components/layout/Page";
import Panel from "../components/layout/Panel";
import { useToast } from "../components/Toast";
import { formatDate, formatDecimal } from "../format";
import { t } from "../i18n";
import ToolOptions, { RADIUS_MAX, RADIUS_MIN } from "../viewer/ToolOptions";
import Viewer from "../viewer/Viewer";
import ViewerBar from "../viewer/ViewerBar";
import ViewerToolRail from "../viewer/ViewerToolRail";
import type { BrushShape, Series, Tool } from "../viewer/types";
import { useMaskEditor } from "../viewer/useMaskEditor";
import { approveCase, type QueueEntry, type ReviewCase } from "./api";
import ApproveButton from "./ApproveButton";
import BiradsForm, { type FieldState } from "./BiradsForm";
import { FIELDS, type FieldKey } from "./fields";
import MaskStrip from "./MaskStrip";
import ReportText from "./ReportText";

type Values = Partial<Record<FieldKey, string>>;
type States = Partial<Record<FieldKey, FieldState>>;

const FULL_VIEW_KEY = "maria.review.fullView";
const UPCOMING = 4;
const TO_REVIEW = "/badania?filtr=to_review";
const VERIFIED_TODAY = "/badania?filtr=verified&dzis=1";

function readFullView() {
  try {
    return sessionStorage.getItem(FULL_VIEW_KEY) === "1";
  } catch {
    return false;
  }
}

interface Props {
  data: ReviewCase;
  queue: QueueEntry[];
}

export default function CaseReview({ data, queue }: Props) {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const toast = useToast();
  const mask = useMaskEditor();
  const undoMask = mask.undo;
  const startedAt = useRef(Date.now());
  const [tool, setTool] = useState<Tool>("brush");
  const [series, setSeries] = useState<Series>("post");
  const [showMask, setShowMask] = useState(true);
  const [available, setAvailable] = useState<Series[]>(["post"]);
  const [brushShape, setBrushShape] = useState<BrushShape>("circle");
  const [brushRadius, setBrushRadius] = useState(5);
  const [gridMatch, setGridMatch] = useState(true);
  const [windowLevel, setWindowLevel] = useState<{ width: number; center: number } | null>(null);
  const [fullView, setFullView] = useState(readFullView);
  const [picking, setPicking] = useState(false);
  const [pickedId, setPickedId] = useState<string | null>(null);
  const resizeBrush = (radius: number) => setBrushRadius(Math.max(RADIUS_MIN, Math.min(RADIUS_MAX, radius)));

  // back to the list the case was opened from, or the cases waiting for verification
  const backTo = (location.state as { from?: string } | null)?.from ?? TO_REVIEW;

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

  // the queue is ordered least certain first; the next case is the first other one unless picked
  const remaining = queue.filter((q) => q.studyId !== data.studyId);
  const next = remaining.find((q) => q.studyId === pickedId) ?? remaining[0] ?? null;

  useEffect(() => {
    try {
      sessionStorage.setItem(FULL_VIEW_KEY, fullView ? "1" : "0");
    } catch {
      // the mode just won't be remembered
    }
  }, [fullView]);

  const goOn = () => navigate(next ? `/weryfikacja/${next.studyId}` : VERIFIED_TODAY, { state: { from: backTo } });

  const approve = useMutation({
    mutationFn: () =>
      approveCase(data.studyId, {
        mask: mask.state === "corrected" ? "corrected" : "confirmed",
        edits: mask.edits,
        fields: Object.fromEntries(keys.map((key) => [key, { value: values[key] ?? "", state: states[key] === "corrected" ? "corrected" : "confirmed" }])),
        editingSeconds: Math.round((Date.now() - startedAt.current) / 1000),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      queryClient.invalidateQueries({ queryKey: ["studies"] });
      toast(t(mask.state === "corrected" ? "review.approvedCorrected" : "review.approvedConfirmed", { n: data.studyNumber }), {
        label: t("review.openOverview"),
        to: `/badania/${data.studyId}`,
      });
      goOn();
    },
  });

  const approveRef = useRef(() => {});
  approveRef.current = () => ready && !approve.isPending && approve.mutate();

  const showMaskDecision = () => {
    setFullView(false);
    const button = document.querySelector<HTMLButtonElement>(".mask-strip .btn");
    button?.focus();
  };
  const showOpenField = () => {
    setFullView(false);
    // the form comes back on the next render
    requestAnimationFrame(() => {
      const field = document.getElementById(`field-${openFields[0]}`);
      field?.scrollIntoView({ block: "center" });
      field?.focus();
    });
  };

  const togglePicking = useCallback((open: boolean) => setPicking(open), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.target as HTMLElement).matches("input, select, textarea")) return;
      const mod = event.metaKey || event.ctrlKey;
      if (mod && event.key === "Enter") return approveRef.current();
      if (mod && event.key.toLowerCase() === "z") {
        event.preventDefault();
        return undoMask();
      }
      if (mod || event.altKey) return;
      const tools: Record<string, Tool> = { b: "brush", t: "threshold", e: "eraser", p: "pan", w: "window" };
      if (tools[event.key]) setTool(tools[event.key]);
      else if (event.key === "m") setShowMask((s) => !s);
      else if (event.key === "s") setBrushShape((s) => (s === "circle" ? "sphere" : "circle"));
      else if (event.key === "[" || event.key === "]") setBrushRadius((r) => Math.max(RADIUS_MIN, Math.min(RADIUS_MAX, r + (event.key === "]" ? 1 : -1))));
      else if (event.key === "f") setFullView(true);
      else if (event.key === "n") setPicking((open) => !open);
      else if (event.key === "Escape") {
        setPicking(false);
        setFullView(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undoMask]);

  return (
    <Page
      title={data.patientId}
      back={{ to: backTo, label: t("nav.studies") }}
      context={
        <>
          <span>
            {t("review.age")} {data.age ?? "—"}
          </span>
          <span>
            <b>#{data.studyNumber}</b> · {data.description} · {formatDate(data.studyDate)}
          </span>
          <span>
            {t("review.uncertainty")} <b>{formatDecimal(data.uncertainty)}</b>
          </span>
        </>
      }
      actions={
        <>
          {next ? (
            <button type="button" className="link" onClick={goOn}>
              {t("review.skip")}
            </button>
          ) : (
            <span className="muted">{t("review.lastInQueue")}</span>
          )}
          <ApproveButton
            missing={{ mask: mask.state === "proposed", fields: openFields.length }}
            onMissingMask={showMaskDecision}
            onMissingFields={showOpenField}
            next={next}
            upcoming={remaining.slice(0, UPCOMING)}
            total={remaining.length}
            open={picking}
            onOpen={togglePicking}
            onPickNext={(entry) => setPickedId(entry.studyId)}
            onApprove={() => approve.mutate()}
            pending={approve.isPending}
          />
        </>
      }
    >
      <div className={fullView ? "review review--full" : "review"}>
        <section className="review__view" aria-label={t("viewer.image")}>
          <ViewerToolRail
            tool={tool === "threshold" && !gridMatch ? "brush" : tool}
            onTool={setTool}
            onUndo={mask.undo}
            canUndo={mask.edits > 0}
            thresholdOk={gridMatch}
          />
          <div className="review__viewer">
            <ViewerBar series={series} onSeries={setSeries} available={available}>
              <ToolOptions
                tool={tool}
                shape={brushShape}
                onShape={setBrushShape}
                radius={brushRadius}
                onRadius={resizeBrush}
                window={windowLevel}
                onResetWindow={() => mask.viewer.current?.resetWindow()}
              />
            </ViewerBar>
            <Viewer
              ref={mask.viewer}
              studyUid={data.studyUid}
              mask={data.mask}
              series={series}
              maskState={mask.state}
              showMask={showMask}
              tool={tool === "threshold" && !gridMatch ? "brush" : tool}
              editable
              brushShape={brushShape}
              brushRadius={brushRadius}
              onEdit={mask.addEdit}
              onSeriesFound={setAvailable}
              onGridMatch={setGridMatch}
              onWindow={setWindowLevel}
              headerExtra={
                <button
                  type="button"
                  className="viewer__head-btn"
                  title={t(fullView ? "review.showFormTitle" : "review.fullViewTitle")}
                  onClick={() => setFullView((on) => !on)}
                >
                  {t(fullView ? "review.showForm" : "review.fullView")} <kbd>{fullView ? "Esc" : "F"}</kbd>
                </button>
              }
            />
            <MaskStrip
              state={mask.state}
              measurements={data.measurements}
              version={data.segmentationVersion}
              onConfirm={mask.confirm}
              onRestore={mask.restoreModel}
              showMask={showMask}
              onToggleMask={() => setShowMask((s) => !s)}
            />
          </div>
        </section>

        {!fullView && (
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
                    : [
                        data.extractionVersion && `${t("models.version")} ${data.extractionVersion}`,
                        openFields.length ? t("review.left", { n: openFields.length }) : t("review.done"),
                        flagged ? t("review.flagged", { n: flagged }) : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")
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
        )}
      </div>
    </Page>
  );
}
