import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import Page from "../components/layout/Page";
import Panel from "../components/layout/Panel";
import { useToast } from "../components/Toast";
import { formatDate, formatDecimal, formatWhen } from "../format";
import { t } from "../i18n";
import ToolOptions, { RADIUS_MAX, RADIUS_MIN } from "../viewer/ToolOptions";
import Viewer, { type MaskInfo } from "../viewer/Viewer";
import Icon from "../viewer/icons";
import { usePreferences } from "../settings/preferences";
import { useViewerLayout } from "../viewer/layout";
import ViewerBar, { LayoutButton } from "../viewer/ViewerBar";
import ViewerToolRail from "../viewer/ViewerToolRail";
import type { BrushShape, Series, Tool } from "../viewer/types";
import { useMaskEditor } from "../viewer/useMaskEditor";
import { approveCase, approveForm, approveMask, reopenCase, type FieldAnswers, type FormPayload, type QueueEntry, type ReviewCase, unapproveForm, unapproveMask } from "./api";
import { deleteDraft, loadDraft, saveDraft, type Draft } from "./draft";
import ApproveButton from "./ApproveButton";
import BiradsForm, { type FieldState } from "./BiradsForm";
import { applyAnswers, FIELDS, lesionFields, lesionSummary, matchLesion, type FieldKey, type Proposals } from "./fields";
import { fromExtraction } from "./report";
import LesionSwitcher from "./LesionSwitcher";
import MaskStrip from "./MaskStrip";
import ReportOriginal, { scanOf } from "./ReportOriginal";
import ReportPreview from "./ReportPreview";

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
  const [preferred] = usePreferences();
  const [layout, setLayout] = useViewerLayout();
  const [series, setSeries] = useState<Series>(preferred.series);
  const [showMask, setShowMask] = useState(preferred.maskShown);
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

  const report = data.report;
  const extraction = report?.result.status === "ok" ? report.result.data : null;
  const model = useMemo(() => (extraction ? fromExtraction(extraction) : null), [extraction]);
  const lesions = useMemo(() => model?.lesions ?? [], [model]);
  const proposals = useMemo(
    () => Object.fromEntries(lesions.map((l) => [l.id, lesionFields(l, model!.conclusion)])) as Record<number, Proposals>,
    [lesions, model],
  );
  const keysOf = useCallback((id: number) => FIELDS.map((f) => f.key).filter((key) => proposals[id]?.[key]), [proposals]);
  const fresh = useCallback(
    () => Object.fromEntries(lesions.map((l) => [l.id, Object.fromEntries(keysOf(l.id).map((key) => [key, proposals[l.id][key]!.value]))])) as Record<number, Values>,
    [lesions, keysOf, proposals],
  );

  // only the lesion on the image is required
  const match = useMemo(() => matchLesion(lesions, data.segmentation?.side ?? null, data.segmentation?.sizeMm ?? null), [lesions, data.segmentation]);
  const [onImage, setOnImage] = useState<number | null>(match?.id ?? null);
  const [onImageSure, setOnImageSure] = useState(match?.certain ?? false);
  const [current, setCurrent] = useState<number | null>(match?.id ?? null);
  const [values, setValues] = useState<Record<number, Values>>(fresh);
  const [states, setStates] = useState<Record<number, States>>({});
  const [showOriginal, setShowOriginal] = useState(false);
  const originalOpen = useRef(false);
  originalOpen.current = showOriginal;

  const stateOf = (id: number, key: FieldKey, value: string): FieldState => (value === proposals[id]?.[key]?.value ? "confirmed" : "corrected");
  // the case as it was left last time, if it was not approved
  const [restoredAt, setRestoredAt] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const draftLoaded = useRef(false);
  const pendingPatch = useRef<Draft["mask"]>(null);
  // only the radiologist's own changes save a draft, not putting the old one back
  const touched = useRef(false);
  const touch = () => (touched.current = true);

  const change = (key: FieldKey, value: string) => {
    if (current === null) return;
    touch();
    setValues((v) => ({ ...v, [current]: { ...v[current], [key]: value } }));
    setStates((s) => ({ ...s, [current]: { ...s[current], [key]: stateOf(current, key, value) } }));
  };
  const confirm = (key: FieldKey) => {
    if (current === null) return;
    touch();
    setStates((s) => ({ ...s, [current]: { ...s[current], [key]: stateOf(current, key, values[current]?.[key] ?? "") } }));
  };
  // just the lesion on screen
  const confirmAll = () => {
    if (current === null) return;
    touch();
    setStates((s) => ({
      ...s,
      [current]: Object.fromEntries(keysOf(current).map((key) => [key, s[current]?.[key] ?? stateOf(current, key, values[current]?.[key] ?? "")])),
    }));
  };

  const openOf = (id: number) => keysOf(id).filter((key) => !states[id]?.[key]);
  const openFields = onImage === null ? [] : openOf(onImage);
  const currentOpen = current === null ? [] : openOf(current);
  const flagged = currentOpen.filter((key) => proposals[current!]?.[key]?.check).length;
  const complete = lesions.filter((l) => keysOf(l.id).length && !openOf(l.id).length).map((l) => l.id);
  const index = lesions.findIndex((l) => l.id === current);

  // only fully confirmed lesions go out
  const formPayload = useRef<() => FormPayload | undefined>(() => undefined);
  formPayload.current = () => {
    if (!extraction) return undefined;
    const answers = (id: number): FieldAnswers =>
      Object.fromEntries(
        keysOf(id).map((key) => [key, { value: values[id]?.[key] ?? "", state: states[id]?.[key] === "corrected" ? "corrected" : "confirmed" }]),
      );
    return {
      report: applyAnswers(extraction, Object.fromEntries(complete.map((id) => [id, { proposals: proposals[id], values: values[id] ?? {} }]))),
      lesions: Object.fromEntries(complete.map((id) => [id, answers(id)])),
    };
  };
  // edits that all ended up undone or restored leave the model's mask as it was
  const corrected = mask.state === "corrected" && (maskInfo?.edited ?? 1) > 0;
  // approved on its own, the mask is locked; the case still waits for the form
  const [maskApproved, setMaskApproved] = useState(data.maskApproved);
  const locked = maskApproved !== null;
  const lockedRef = useRef(locked);
  lockedRef.current = locked;

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

  const approveMaskNow = useMutation({
    mutationFn: () => approveMask(data.studyId, { mask: corrected ? "corrected" : "confirmed", edits: mask.edits }),
    onSuccess: () => {
      touch();
      setMaskApproved(corrected ? "corrected" : "confirmed");
      setTool((current) => (current === "pan" || current === "window" ? current : "pan"));
      queryClient.invalidateQueries({ queryKey: ["studies"] });
      // when the form is done too, the case is verified and that toast says it
      if (openFields.length) toast(t("review.mask.approvedToast", { n: data.studyNumber }));
    },
  });
  const unapproveMaskNow = useMutation({
    mutationFn: () => unapproveMask(data.studyId),
    onSuccess: () => {
      touch();
      setMaskApproved(null);
      queryClient.invalidateQueries({ queryKey: ["studies"] });
    },
  });

  // confirming another lesion later sends the form again
  const sentFor = useRef<string | null>(null);
  const completeKey = complete.join(",");
  // back to the model's proposals, every lesion
  function unconfirmForm() {
    touch();
    setValues(fresh());
    setStates({});
    sentFor.current = null;
    unapproveForm(data.studyId).then(() => queryClient.invalidateQueries({ queryKey: ["studies"] }));
  }
  useEffect(() => {
    if (!extraction || onImage === null || openFields.length || sentFor.current === completeKey) return;
    sentFor.current = completeKey;
    approveForm(data.studyId, formPayload.current()!).then(() => queryClient.invalidateQueries({ queryKey: ["studies"] }));
  }, [extraction, onImage, openFields.length, completeKey, data.studyId, queryClient]);

  // verified = the mask approved and every field confirmed, in either order; leaving keeps it
  const verified = maskApproved !== null && openFields.length === 0;
  const wasVerified = useRef(verified);
  useEffect(() => {
    if (verified === wasVerified.current) return;
    wasVerified.current = verified;
    if (verified) {
      approveCase(data.studyId, {
        mask: maskApproved ?? "confirmed",
        edits: mask.edits,
        ...formPayload.current(),
        editingSeconds: Math.round((Date.now() - startedAt.current) / 1000),
      }).then(() => queryClient.invalidateQueries({ queryKey: ["studies"] }));
      deleteDraft(data.studyId);
      toast(t("review.verifiedToast", { n: data.studyNumber }), { label: t("review.openOverview"), to: `/badania/${data.studyId}` });
    } else {
      reopenCase(data.studyId).then(() => queryClient.invalidateQueries({ queryKey: ["studies"] }));
    }
  }, [verified, data.studyId, data.studyNumber, maskApproved, mask.edits, queryClient, toast]);

  const nextRef = useRef(() => {});
  nextRef.current = goOn;

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
    if (filling || !maskInfo?.gaps.length) return;
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
      if (originalOpen.current || (event.target as HTMLElement).matches("input, select, textarea")) return;
      const mod = event.metaKey || event.ctrlKey;
      if (mod && event.key === "Enter") return nextRef.current();
      if (mod && event.key.toLowerCase() === "z") {
        event.preventDefault();
        return !lockedRef.current && undoMask();
      }
      if (mod || event.altKey) return;
      const tools: Record<string, Tool> = { b: "brush", t: "threshold", e: "eraser", p: "pan", w: "window" };
      const painting = ["b", "t", "e", "i", "r"].includes(event.key);
      if (painting && lockedRef.current) return;
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

  useEffect(() => {
    let cancelled = false;
    loadDraft(data.studyId).then((draft) => {
      if (cancelled) return;
      draftLoaded.current = true;
      if (!draft) return;
      if (draft.form) {
        const form = draft.form;
        setValues((v) => ({ ...v, ...form.values }));
        setStates(form.states);
        if (form.onImage !== null) {
          setOnImage(form.onImage);
          setCurrent(form.onImage);
        }
      }
      pendingPatch.current = draft.mask;
      setRestoredAt(draft.savedAt);
    });
    return () => {
      cancelled = true;
    };
  }, [data.studyId]);

  // the mask part waits for the images and the model's mask to be on screen
  useEffect(() => {
    const patch = pendingPatch.current;
    if (!maskInfo || !patch) return;
    pendingPatch.current = null;
    if (mask.viewer.current?.applyPatch(patch)) mask.addEdit();
  }, [maskInfo, mask]);

  // saved a moment after every change; nothing left to keep removes the draft
  useEffect(() => {
    if (!draftLoaded.current || !touched.current) return;
    const timer = window.setTimeout(async () => {
      // an approved mask is saved for real, so the draft keeps only the form
      const patch = locked ? null : (mask.viewer.current?.getPatch() ?? null);
      if (!patch && Object.values(states).every((s) => !Object.keys(s ?? {}).length)) {
        await deleteDraft(data.studyId);
        setSavedAt(null);
      } else {
        setSavedAt(await saveDraft(data.studyId, { form: { values, states, onImage }, mask: patch }));
      }
      setRestoredAt(null);
    }, 800);
    return () => window.clearTimeout(timer);
  }, [data.studyId, values, states, onImage, maskInfo, mask.viewer, locked]);

  function discardDraft() {
    deleteDraft(data.studyId);
    setValues(fresh());
    setStates({});
    mask.restoreModel();
    touched.current = false;
    setRestoredAt(null);
    setSavedAt(null);
  }

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
          {restoredAt ? (
            <span className="draft-note">
              {t("review.draft.restored")} <b>{formatWhen(restoredAt)}</b>
              <button type="button" className="link" onClick={discardDraft}>
                {t("review.draft.discard")}
              </button>
            </span>
          ) : (
            savedAt && <span className="muted">{t("review.draft.saved", { when: formatWhen(savedAt) })}</span>
          )}
          <ApproveButton
            waiting={{ mask: maskApproved === null, fields: openFields.length }}
            onShowMask={() => document.querySelector<HTMLButtonElement>(".mask-strip .btn")?.focus()}
            onShowFields={showOpenField}
            next={next}
            upcoming={remaining.slice(0, UPCOMING)}
            total={remaining.length}
            open={picking}
            onOpen={togglePicking}
            onPickNext={(entry) => setPickedId(entry.studyId)}
            onNext={goOn}
          />
        </>
      }
    >
      <div className={fullView ? "review review--full" : "review"}>
        <section className="review__view" aria-label={t("viewer.image")}>
          <ViewerToolRail
            tool={tool === "threshold" && !gridMatch ? "brush" : tool}
            onTool={setTool}
            locked={locked}
            onUndo={() => (touch(), mask.undo())}
            canUndo={mask.edits > 0}
            thresholdOk={gridMatch}
            canFill={!!maskInfo?.gaps.length}
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
              roles={data.segmentation?.series}
              mask={data.mask}
              series={series}
              maskState={locked ? "confirmed" : corrected ? "corrected" : "proposed"}
              showMask={showMask}
              tool={tool === "threshold" && !gridMatch ? "brush" : tool}
              editable={!locked}
              brushShape={brushShape}
              brushRadius={brushRadius}
              onEdit={() => (touch(), mask.addEdit())}
              onSeriesFound={(found) => {
                setAvailable(found);
                // the preferred series may be missing from this study
                if (!found.includes(series)) setSeries("post");
              }}
              onGridMatch={setGridMatch}
              onWindow={setWindowLevel}
              onMaskInfo={setMaskInfo}
              layout={layout}
              onLayout={setLayout}
            />
            <MaskStrip
              corrected={corrected}
              approved={locked}
              pending={approveMaskNow.isPending || unapproveMaskNow.isPending}
              onApprove={() => approveMaskNow.mutate()}
              onUnapprove={() => unapproveMaskNow.mutate()}
              edited={maskInfo?.edited ?? 0}
              gaps={maskInfo?.gaps ?? []}
              version={data.segmentationVersion}
              onGoTo={(index) => mask.viewer.current?.goToSlice(index)}
              onFill={() => fillRef.current()}
              onRestore={() => (touch(), mask.restoreModel())}
              showMask={showMask}
              onToggleMask={() => setShowMask((s) => !s)}
            />
          </div>
        </section>

        {fullView ? (
          <button type="button" className="review__form-tab" title={t("review.showForm")} onClick={() => setFullView(false)}>
            <Icon name="showSide" />
            <span>{t("review.formTab")}</span>
            {extraction && <b>{openFields.length ? t("review.left", { n: openFields.length }) : t("review.formConfirmed")}</b>}
          </button>
        ) : (
          <section className="review__form" aria-label={t("review.form")}>
            <div className="review__form-body">
              <Panel title={t("review.report")}>
                <div className="review__section">
                  {report ? (
                    <>
                      <ReportPreview report={report} onOpen={() => setShowOriginal(true)} />
                      {report.result.status === "error" && (
                        <p className="birads__note">
                          {t("review.original.failed")}
                          {report.result.error && `: ${report.result.error}`}
                        </p>
                      )}
                    </>
                  ) : data.reportPending ? (
                    <div className="empty-box">
                      <b>{t("review.original.pending")}</b>
                      {t("review.original.pendingBody")}
                    </div>
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
                title={
                  data.extractionVersion ? <span title={t("review.extractionVersion", { v: data.extractionVersion })}>{t("review.form")}</span> : t("review.form")
                }
                aux={
                  !extraction
                    ? t("review.formWaitsAux")
                    : current === null
                      ? null
                      : [
                          currentOpen.length ? t("review.left", { n: currentOpen.length }) : t("review.formConfirmed"),
                          flagged ? t("review.flagged", { n: flagged }) : null,
                        ]
                          .filter(Boolean)
                          .join(" · ")
                }
              >
                {extraction && current !== null && lesions.length > 1 && (
                  <LesionSwitcher
                    index={index}
                    total={lesions.length}
                    summary={lesionSummary(lesions[index])}
                    onImage={current === onImage}
                    note={
                      current === onImage
                        ? t(onImageSure ? "review.lesion.onImage" : "review.lesion.onImageGuess")
                        : t(complete.includes(current) ? "review.lesion.confirmed" : "review.lesion.optional")
                    }
                    onPrev={() => setCurrent(lesions[index - 1].id)}
                    onNext={() => setCurrent(lesions[index + 1].id)}
                    onMarkOnImage={
                      current !== onImage && !onImageSure
                        ? () => {
                            touch();
                            setOnImage(current);
                            setOnImageSure(true);
                          }
                        : undefined
                    }
                  />
                )}
                <div className="review__section">
                  {!extraction ? (
                    <div className="empty-box">{t(data.reportPending ? "review.formWaitsRead" : "review.formWaits")}</div>
                  ) : current === null ? (
                    <div className="empty-box">{t("review.original.noLesions")}</div>
                  ) : (
                    <BiradsForm
                      proposals={proposals[current]}
                      values={values[current] ?? {}}
                      states={states[current] ?? {}}
                      onChange={change}
                      onConfirm={confirm}
                      maskSizeMm={current === onImage ? maskInfo?.sizeMm : null}
                    />
                  )}
                </div>
              </Panel>
            </div>
            {extraction && current !== null && (
              <div className="review__foot">
                {currentOpen.length ? (
                  <button type="button" className="btn btn--confirm" onClick={confirmAll}>
                    {t("review.confirmAll")}
                  </button>
                ) : (
                  <button type="button" className="btn" title={t("review.unconfirmFormTitle")} onClick={unconfirmForm}>
                    {t("review.unconfirmForm")}
                  </button>
                )}
              </div>
            )}
          </section>
        )}
      </div>
      {report && (
        <ReportOriginal
          scan={scanOf(report)}
          open={showOriginal}
          onClose={() => setShowOriginal(false)}
          lesion={
            current === null
              ? null
              : {
                  number: index + 1,
                  quotes: lesions[index].observations.map((o) => o.quote),
                }
          }
          onPrev={index > 0 ? () => setCurrent(lesions[index - 1].id) : undefined}
          onNext={index >= 0 && index < lesions.length - 1 ? () => setCurrent(lesions[index + 1].id) : undefined}
        />
      )}
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
