import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import Page from "../components/layout/Page";
import Panel from "../components/layout/Panel";
import { useToast } from "../components/Toast";
import { formatDate, formatDecimal } from "../format";
import { t } from "../i18n";
import ToolOptions, { RADIUS_MAX, RADIUS_MIN } from "../viewer/ToolOptions";
import Viewer, { type MaskInfo } from "../viewer/Viewer";
import Icon from "../viewer/icons";
import { useViewerLayout } from "../viewer/layout";
import ViewerBar, { LayoutButton } from "../viewer/ViewerBar";
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
  // looking comes first, so a case opens with the hand
  const [tool, setTool] = useState<Tool>("pan");
  const [layout, setLayout] = useViewerLayout();
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
  const [maskInfo, setMaskInfo] = useState<MaskInfo | null>(null);
  const [filling, setFilling] = useState(false);
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
  const ready = openFields.length === 0;
  // edits that all ended up undone or restored leave the model's mask as it was
  const corrected = mask.state === "corrected" && (maskInfo?.edited ?? 1) > 0;

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
        mask: corrected ? "corrected" : "confirmed",
        edits: mask.edits,
        fields: Object.fromEntries(keys.map((key) => [key, { value: values[key] ?? "", state: states[key] === "corrected" ? "corrected" : "confirmed" }])),
        editingSeconds: Math.round((Date.now() - startedAt.current) / 1000),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["review-queue"] });
      queryClient.invalidateQueries({ queryKey: ["studies"] });
      toast(t(corrected ? "review.approvedCorrected" : "review.approvedConfirmed", { n: data.studyNumber }), {
        label: t("review.openOverview"),
        to: `/badania/${data.studyId}`,
      });
      goOn();
    },
  });

  const approveRef = useRef(() => {});
  approveRef.current = () => ready && !approve.isPending && approve.mutate();

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

  const fillRef = useRef(() => {});
  fillRef.current = async () => {
    if (filling || (maskInfo?.slices ?? 0) < 2) return;
    setFilling(true);
    const done = await mask.viewer.current?.interpolate();
    setFilling(false);
    if (done === false) toast(t("viewer.fillFailed"));
  };

  const restoreSliceRef = useRef(() => {});
  restoreSliceRef.current = () => {
    if (mask.viewer.current?.restoreSlice()) toast(t("viewer.sliceRestored"));
  };

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
      else if (event.key === "i") fillRef.current();
      else if (event.key === "r") restoreSliceRef.current();
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
      back={{ to: backTo, label: t("review.backToQueue") }}
      context={
        <>
          <div className="banner__group">
            <Value label={t("review.patient")} strong>
              {data.patientId}
            </Value>
            <Value label={t("review.ageLabel")}>{data.age ?? "—"}</Value>
          </div>
          <div className="banner__group">
            <Value label={t("review.case")} strong>
              #{data.studyNumber}
            </Value>
            <Value label={t("review.study")}>{data.description}</Value>
            <Value label={t("review.date")}>{formatDate(data.studyDate)}</Value>
            <Value label={t("review.uncertainty")} strong>
              {formatDecimal(data.uncertainty)}
            </Value>
          </div>
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
            missingFields={openFields.length}
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
            canFill={(maskInfo?.slices ?? 0) >= 2}
            filling={filling}
            onFill={() => fillRef.current()}
            canRestoreSlice={!!maskInfo?.currentEdited}
            onRestoreSlice={() => restoreSliceRef.current()}
          />
          <div className="review__viewer">
            <ViewerBar
              series={series}
              onSeries={setSeries}
              available={available}
              corner={
                <>
                  <LayoutButton layout={layout} onLayout={setLayout} />
                  {!fullView && (
                    <button type="button" title={t("review.hideForm")} aria-label={t("review.hideForm")} onClick={() => setFullView(true)}>
                      <Icon name="hideSide" />
                    </button>
                  )}
                </>
              }
            >
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
              maskState={corrected ? "corrected" : "proposed"}
              showMask={showMask}
              tool={tool === "threshold" && !gridMatch ? "brush" : tool}
              editable
              brushShape={brushShape}
              brushRadius={brushRadius}
              onEdit={mask.addEdit}
              onSeriesFound={setAvailable}
              onGridMatch={setGridMatch}
              onWindow={setWindowLevel}
              onMaskInfo={setMaskInfo}
              layout={layout}
              onLayout={setLayout}
            />
            <MaskStrip
              corrected={corrected}
              edited={maskInfo?.edited ?? 0}
              gaps={maskInfo?.gaps ?? []}
              version={data.segmentationVersion}
              onGoTo={(index) => mask.viewer.current?.goToSlice(index)}
              onFill={() => fillRef.current()}
              onRestore={mask.restoreModel}
              showMask={showMask}
              onToggleMask={() => setShowMask((s) => !s)}
            />
          </div>
        </section>

        {fullView ? (
          <button type="button" className="review__form-tab" title={t("review.showForm")} onClick={() => setFullView(false)}>
            <Icon name="showSide" />
            <span>{t("review.formTab")}</span>
            {data.report && <b>{openFields.length ? t("review.left", { n: openFields.length }) : t("review.done")}</b>}
          </button>
        ) : (
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

// a label above its value, as in the case banner
function Value({ label, strong, children }: { label: string; strong?: boolean; children: ReactNode }) {
  return (
    <div className="banner__value">
      <small>{label}</small>
      {strong ? <b>{children}</b> : <span>{children}</span>}
    </div>
  );
}
