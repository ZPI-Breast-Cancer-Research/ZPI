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
import { approveCase, approveForm, approveMask, reopenCase, type FormPayload, type QueueEntry, type ReviewCase, unapproveForm, unapproveMask } from "./api";
import { deleteDraft, loadDraft, saveDraft, type Draft } from "./draft";
import ApproveButton from "./ApproveButton";
import { fromExtraction } from "./report";
import LesionSwitcher from "./LesionSwitcher";
import MaskStrip from "./MaskStrip";
import ReportOriginal, { scanOf } from "./ReportOriginal";
import ReportPreview from "./ReportPreview";
import ReportRows, { rowId } from "./ReportRows";
import { applyAnswers, caseGroups, fieldChecks, getAt, lesionGroup, lesionSummary, NO_ANSWERS, observationGroups, pathKey, waiting, type Answers, type Group, type Path, type Row } from "./rows";

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
  // each lesion: its own fields, then one group for each observation
  const groups = useMemo<Group[][]>(() => (extraction ? extraction.zmiany.map((_, i) => [lesionGroup(i), ...observationGroups(extraction, i)]) : []), [extraction]);
  // breasts, lymph nodes and the conclusion
  const studyGroups = useMemo<Group[]>(() => (extraction ? caseGroups(extraction) : []), [extraction]);
  // folded by hand, or open while something there waits
  const [studyOpen, setStudyOpen] = useState<boolean | null>(null);
  // every lesion in the report is confirmed before the case is verified
  const [current, setCurrent] = useState<number | null>(lesions[0]?.id ?? null);
  // every answer in the form
  const [answers, setAnswers] = useState<Answers>(NO_ANSWERS);
  const [showOriginal, setShowOriginal] = useState(false);
  const originalOpen = useRef(false);
  originalOpen.current = showOriginal;

  // the case as it was left last time, if it was not approved
  const [restoredAt, setRestoredAt] = useState<string | null>(null);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const draftLoaded = useRef(false);
  const pendingPatch = useRef<Draft["mask"]>(null);
  // only the radiologist's own changes save a draft, not putting the old one back
  const touched = useRef(false);
  const touch = () => (touched.current = true);

  const currentReport = extraction ? applyAnswers(extraction, answers.edits) : null;
  const indexOf = (id: number) => lesions.findIndex((l) => l.id === id);
  const index = current === null ? -1 : indexOf(current);

  const setEdit = (edits: Answers["edits"], path: Path, value: unknown) => {
    const key = pathKey(path);
    if (JSON.stringify(getAt(extraction, path) ?? null) === JSON.stringify(value ?? null)) delete edits[key];
    else edits[key] = value;
  };
  const answer = (row: Row, values: unknown[] | null, confirm: boolean) => {
    if (!extraction) return;
    touch();
    setAnswers((a) => {
      const edits = { ...a.edits };
      if (values) row.paths.forEach((path, i) => setEdit(edits, path, values[i]));
      const keys = row.paths.map(pathKey);
      return { ...a, edits, confirmed: confirm ? [...new Set([...a.confirmed, ...keys])] : a.confirmed };
    });
  };
  // back to the model's value, waiting again
  const restore = (row: Row) => {
    touch();
    const keys = row.paths.map(pathKey);
    setAnswers((a) => {
      const edits = { ...a.edits };
      keys.forEach((key) => delete edits[key]);
      return { ...a, edits, confirmed: a.confirmed.filter((k) => !keys.includes(k)) };
    });
  };
  const add = (row: Row) => {
    touch();
    setAnswers((a) => ({ ...a, added: [...new Set([...a.added, row.key])] }));
  };

  const waitingIn = (list: Group[]) => (extraction && currentReport ? list.flatMap((g) => waiting(g, extraction, currentReport, answers)) : []);
  const waitingOf = (i: number) => waitingIn(groups[i]);
  const studyWaiting = waitingIn(studyGroups);
  // the whole study first, as on screen
  const openFields = [...studyWaiting.map((row) => ({ id: null, row })), ...lesions.flatMap((l, i) => waitingOf(i).map((row) => ({ id: l.id, row })))];
  const currentOpen = index < 0 ? [] : waitingOf(index);
  const complete = lesions.filter((_, i) => !waitingOf(i).length).map((l) => l.id);
  const showStudy = studyOpen ?? studyWaiting.length > 0;
  const confirmRows = (rows: Row[]) => {
    touch();
    const keys = rows.flatMap((row) => row.paths.map(pathKey));
    setAnswers((a) => ({ ...a, confirmed: [...new Set([...a.confirmed, ...keys])] }));
  };
  // just the lesion on screen
  const confirmAll = () => confirmRows(currentOpen);

  // sent once every lesion is answered
  const formPayload = useRef<() => FormPayload | undefined>(() => undefined);
  formPayload.current = () => {
    if (!extraction || !currentReport) return undefined;
    return { report: currentReport, lesions: {}, fields: fieldChecks([...studyGroups, ...groups.flat()], extraction, currentReport, answers) };
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

  // sent again after any later change
  const sentFor = useRef<string | null>(null);
  const completeKey = `${complete.join(",")}|${JSON.stringify(answers)}`;
  // these fields wait again; corrections stay
  function unconfirm(list: Group[]) {
    touch();
    const keys = list.flatMap((g) => g.rows.flatMap((r) => r.paths.map(pathKey)));
    setAnswers((a) => ({ ...a, confirmed: a.confirmed.filter((k) => !keys.includes(k)) }));
    if (sentFor.current !== null) {
      sentFor.current = null;
      unapproveForm(data.studyId).then(() => queryClient.invalidateQueries({ queryKey: ["studies"] }));
    }
  }
  const unconfirmLesion = () => index >= 0 && unconfirm(groups[index]);
  useEffect(() => {
    if (!extraction || openFields.length || sentFor.current === completeKey) return;
    sentFor.current = completeKey;
    approveForm(data.studyId, formPayload.current()!).then(() => queryClient.invalidateQueries({ queryKey: ["studies"] }));
  }, [extraction, openFields.length, completeKey, data.studyId, queryClient]);

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
    const first = openFields[0];
    setFullView(false);
    if (first?.id === null) setStudyOpen(true);
    else if (first) setCurrent(first.id);
    // the form comes back on the next render
    requestAnimationFrame(() => {
      const row = first && document.getElementById(rowId(first.row));
      row?.scrollIntoView({ block: "center" });
      row?.querySelector<HTMLElement>("input, button")?.focus();
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
      if (!draft || (!draft.answers && !draft.mask)) return;
      // older drafts have no added fields
      if (draft.answers) setAnswers({ edits: draft.answers.edits ?? {}, confirmed: draft.answers.confirmed ?? [], added: draft.answers.added ?? [] });
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
      const formLeft = Object.keys(answers.edits).length || answers.confirmed.length || answers.added.length;
      if (!patch && !formLeft) {
        await deleteDraft(data.studyId);
        setSavedAt(null);
      } else {
        setSavedAt(await saveDraft(data.studyId, { answers, mask: patch }));
      }
      setRestoredAt(null);
    }, 800);
    return () => window.clearTimeout(timer);
  }, [data.studyId, answers, maskInfo, mask.viewer, locked]);

  function discardDraft() {
    deleteDraft(data.studyId);
    setAnswers(NO_ANSWERS);
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
              empty={!data.mask}
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
                        <p className="review__error">
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
                    : openFields.length
                      ? t("review.left", { n: openFields.length })
                      : t("review.formConfirmed")
                }
              >
                {extraction && currentReport && (
                  <section className="study">
                    <button type="button" className="study__head" aria-expanded={showStudy} onClick={() => setStudyOpen(!showStudy)}>
                      <span className={showStudy ? "study__chevron study__chevron--open" : "study__chevron"} aria-hidden="true" />
                      {t("row.section.case")}
                      <span className="study__state">
                        {studyWaiting.length ? t("study.waiting", { n: studyWaiting.length }) : t("rows.checked")}
                      </span>
                    </button>
                    {showStudy && (
                      <div className="study__body">
                        <ReportRows
                          sections={studyGroups.map((group) => ({ group, band: true }))}
                          original={extraction}
                          current={currentReport}
                          answers={answers}
                          side={null}
                          onAnswer={answer}
                          onRestore={restore}
                          onAdd={add}
                        />
                        <div className="study__foot">
                          {studyWaiting.length ? (
                            <button type="button" className="btn btn--confirm" onClick={() => confirmRows(studyWaiting)}>
                              {t("study.confirm")}
                            </button>
                          ) : (
                            <button type="button" className="btn" title={t("study.unconfirmTitle")} onClick={() => unconfirm(studyGroups)}>
                              {t("review.unconfirmLesion")}
                            </button>
                          )}
                        </div>
                      </div>
                    )}
                  </section>
                )}
                {extraction && current !== null && (
                  <LesionSwitcher
                    index={index}
                    total={lesions.length}
                    summary={lesionSummary(currentReport ?? extraction, index)}
                    note={complete.includes(current) ? t("review.lesion.confirmed") : null}
                    onPrev={() => setCurrent(lesions[index - 1].id)}
                    onNext={() => setCurrent(lesions[index + 1].id)}
                  />
                )}
                <div className="review__section">
                  {!extraction ? (
                    <div className="empty-box">{t(data.reportPending ? "review.formWaitsRead" : "review.formWaits")}</div>
                  ) : current === null ? (
                    <div className="empty-box">{t("review.original.noLesions")}</div>
                  ) : (
                    currentReport && (
                      <ReportRows
                        sections={groups[index].map((group, k) => ({ group, band: k > 0 }))}
                        original={extraction}
                        current={currentReport}
                        answers={answers}
                        side={currentReport.zmiany[index].strona}
                        onAnswer={answer}
                        onRestore={restore}
                        onAdd={add}
                      />
                    )
                  )}
                </div>
              </Panel>
            </div>
            {extraction && current !== null && (
              <div className="review__foot">
                {currentOpen.length ? (
                  <button type="button" className="btn btn--confirm" onClick={confirmAll}>
                    {t("review.confirmLesion", { n: index + 1 })}
                  </button>
                ) : (
                  <button type="button" className="btn" title={t("review.unconfirmLesionTitle")} onClick={unconfirmLesion}>
                    {t("review.unconfirmLesion")}
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
