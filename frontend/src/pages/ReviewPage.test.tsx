import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { t } from "../i18n";
import { loadDraft, saveDraft } from "../review/draft";
import type { Extraction } from "../review/extraction";
import { caseReport, extraction, lesion, observation } from "../test/extraction";
import reviewCase from "../test/fixtures/review-case.json";
import queue from "../test/fixtures/review-queue.json";
import { radiologist, renderScreen } from "../test/render";
import { capturePosts, http, HttpResponse, server, type JsonBodyType } from "../test/server";
import ReviewPage from "./ReviewPage";

// no WebGL in jsdom; the stand-in only reports a brush stroke
vi.mock("../viewer/Viewer", async () => {
  const { forwardRef } = await import("react");
  return {
    default: forwardRef<unknown, { onEdit?: () => void }>(function Viewer({ onEdit }) {
      return (
        <button type="button" onClick={onEdit}>
          brush stroke
        </button>
      );
    }),
  };
});

// drafts live in IndexedDB, which jsdom doesn't have
vi.mock("../review/draft", () => ({
  loadDraft: vi.fn(async () => null),
  saveDraft: vi.fn(async () => "2026-11-14T10:00"),
  deleteDraft: vi.fn(async () => undefined),
}));

const studyId = queue[0].studyId;
const base = `/api/review/cases/${studyId}`;

// one mass on mammography, with a conclusion: what most reports in the queue look like
const report = (): Extraction =>
  extraction({
    zmiany: [
      lesion({
        strona: "prawa",
        birads: "4a",
        obserwacje: [
          observation({
            typ: "zmiana ogniskowa",
            lokalizacje: ["kwadrant górny zewnętrzny"],
            wymiary: { wartosci: [12], jednostka: "mm", kwalifikator: "dokładny" },
            ksztalt: "nieregularny",
            brzeg: "spikularny",
            cytat: "zmiana ogniskowa 12 mm",
          }),
        ],
      }),
    ],
    wniosek: { birads: "4a", tekst: "BI-RADS 4a", zalecenie: "biopsja" },
  });

function backend(overrides: Record<string, JsonBodyType> = {}) {
  server.use(
    http.get("/api/review/queue/", () => HttpResponse.json(queue)),
    http.get(`${base}/`, () => HttpResponse.json({ ...reviewCase, studyId, report: caseReport(report()), ...overrides })),
  );
  return capturePosts(`${base}/approve-form/`, `${base}/approve-mask/`, `${base}/approve/`, `${base}/unapprove-form/`, `${base}/reopen/`);
}

function renderReview(route = `/weryfikacja/${studyId}`) {
  renderScreen(
    <Routes>
      <Route path="weryfikacja/:studyId?" element={<ReviewPage />} />
      <Route path="badania" element={<h1>badania</h1>} />
    </Routes>,
    { route, user: radiologist },
  );
}

const button = (name: string) => screen.findByRole("button", { name });
const paths = (sent: { path: string }[]) => sent.map((s) => s.path.replace(`${base}/`, "").replace(/\/$/, ""));
const confirmEverything = async (user: ReturnType<typeof userEvent.setup>) => {
  await user.click(await button(t("study.confirm")));
  await user.click(await button(t("review.confirmLesion", { n: 1 })));
};

beforeEach(() => {
  vi.mocked(loadDraft).mockResolvedValue(null);
  vi.mocked(saveDraft).mockClear();
});

describe("ReviewPage", () => {
  it("opens the first case of the queue", async () => {
    backend();
    renderReview("/weryfikacja");
    expect(await screen.findByText(`#${reviewCase.studyNumber}`)).toBeInTheDocument();
  });

  it("goes back to the studies when the queue is empty", async () => {
    server.use(http.get("/api/review/queue/", () => HttpResponse.json([])));
    renderReview("/weryfikacja");
    expect(await screen.findByRole("heading", { name: "badania" })).toBeInTheDocument();
  });

  it("shows the error when the case can't be loaded", async () => {
    server.use(
      http.get("/api/review/queue/", () => HttpResponse.json(queue)),
      http.get(`${base}/`, () => HttpResponse.json({ detail: "Nie znaleziono." }, { status: 404 })),
    );
    renderReview();
    expect(await screen.findByText(t("review.error"))).toBeInTheDocument();
    expect(screen.getByText(t("api.http", { status: 404 }))).toBeInTheDocument();
  });

  it("waits while the worker hasn't read the report", async () => {
    backend({ report: "pending" });
    renderReview();
    expect(await screen.findByText(t("review.original.pending"))).toBeInTheDocument();
    expect(screen.getByText(t("review.formWaitsRead"))).toBeInTheDocument();
  });

  it("offers to attach a report when there is none", async () => {
    backend({ report: null });
    renderReview();
    expect(await screen.findByText(t("review.noReport"))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: t("review.attachReport") })).toHaveAttribute("href", `/badania?badanie=${studyId}`);
  });
});

describe("verifying a case", () => {
  it("sends the form once every field is confirmed, each field as confirmed", async () => {
    const sent = backend();
    const user = userEvent.setup();
    renderReview();
    await confirmEverything(user);

    await waitFor(() => expect(paths(sent)).toEqual(["approve-form"]));
    const { report: approved, fields } = sent[0].body as { report: Extraction; fields: Record<string, string> };
    expect(approved).toEqual(report());
    expect(new Set(Object.values(fields))).toEqual(new Set(["confirmed"]));
    expect(fields["zmiany.0.obserwacje.0.brzeg"]).toBe("confirmed");
  });

  it("verifies the case when the mask is approved after the form", async () => {
    const sent = backend();
    const user = userEvent.setup();
    renderReview();
    await confirmEverything(user);
    await user.click(await button(t("review.mask.approve")));

    await waitFor(() => expect(paths(sent)).toEqual(["approve-form", "approve-mask", "approve"]));
    expect(sent[1].body).toEqual({ mask: "confirmed", edits: 0 });
    expect(sent[2].body).toMatchObject({ mask: "confirmed", edits: 0, report: report() });
  });

  it("approves a corrected mask with the number of edits", async () => {
    const sent = backend();
    const user = userEvent.setup();
    renderReview();
    await user.click(await button("brush stroke"));
    await user.click(await button("brush stroke"));
    await user.click(await button(t("review.mask.approve")));

    await waitFor(() => expect(paths(sent)).toEqual(["approve-mask"]));
    expect(sent[0].body).toEqual({ mask: "corrected", edits: 2 });
    expect(await button(t("review.mask.unapprove"))).toBeInTheDocument();
  });

  it("sends a corrected field as corrected", async () => {
    const sent = backend();
    const user = userEvent.setup();
    renderReview();
    const field = await screen.findByLabelText(t("row.recommendation"));
    await user.clear(field);
    await user.type(field, "kontrola za 6 miesięcy{Enter}");
    await confirmEverything(user);

    await waitFor(() => expect(paths(sent)).toEqual(["approve-form"]));
    const body = sent[0].body as { report: Extraction; fields: Record<string, string> };
    expect(body.report.wniosek.zalecenie).toBe("kontrola za 6 miesięcy");
    expect(body.fields["wniosek.zalecenie"]).toBe("corrected");
    expect(body.fields["wniosek.birads"]).toBe("confirmed");
  });

  it("takes the form back when a confirmed lesion waits again", async () => {
    const sent = backend();
    const user = userEvent.setup();
    renderReview();
    await confirmEverything(user);
    await waitFor(() => expect(paths(sent)).toEqual(["approve-form"]));

    await user.click(await button(t("review.unconfirmLesion")));
    await waitFor(() => expect(paths(sent)).toEqual(["approve-form", "unapprove-form"]));
    expect(await button(t("review.confirmLesion", { n: 1 }))).toBeInTheDocument();
  });
});

describe("drafts", () => {
  it("puts back the answers left last time and says when", async () => {
    vi.mocked(loadDraft).mockResolvedValue({ savedAt: "2026-11-13T18:05", answers: { edits: { "wniosek.zalecenie": "USG za 3 miesiące" }, confirmed: [], added: [] }, mask: null });
    const sent = backend();
    const user = userEvent.setup();
    renderReview();
    expect(await screen.findByText(t("review.draft.restored"), { exact: false })).toBeInTheDocument();
    await confirmEverything(user);

    await waitFor(() => expect(paths(sent)).toEqual(["approve-form"]));
    expect((sent[0].body as { report: Extraction }).report.wniosek.zalecenie).toBe("USG za 3 miesiące");
  });

  it("keeps the doctor's answers as a draft a moment after a change", async () => {
    backend();
    const user = userEvent.setup();
    renderReview();
    await user.click(await button(t("study.confirm")));
    await waitFor(() => expect(saveDraft).toHaveBeenCalled(), { timeout: 2000 });
    const [id, draft] = vi.mocked(saveDraft).mock.lastCall!;
    expect(id).toBe(studyId);
    expect(draft.answers?.confirmed).toContain("wniosek.birads");
  });
});
