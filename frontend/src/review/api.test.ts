import { afterEach, describe, expect, it } from "vitest";

import { caseReport, extraction } from "../test/extraction";
import reviewCase from "../test/fixtures/review-case.json";
import queue from "../test/fixtures/review-queue.json";
import { http, HttpResponse, server } from "../test/server";
import { approveForm, approveMask, fetchCase, fetchQueue, unapproveMask } from "./api";

const studyId = reviewCase.studyId;

// what reached the server: path, CSRF header and body
function capture(path: string) {
  const sent: { path: string; csrf: string | null; body: unknown }[] = [];
  server.use(
    http.post(path, async ({ request }) => {
      sent.push({ path: new URL(request.url).pathname, csrf: request.headers.get("X-CSRFToken"), body: await request.text().then((text) => (text ? JSON.parse(text) : null)) });
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return sent;
}

afterEach(() => {
  document.cookie = "csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("fetchQueue", () => {
  it("returns the queue as the backend orders it", async () => {
    server.use(http.get("/api/review/queue/", () => HttpResponse.json(queue)));
    expect(await fetchQueue()).toEqual(queue);
  });
});

describe("fetchCase", () => {
  it("waits for the report while the worker hasn't read it", async () => {
    server.use(http.get(`/api/review/cases/${studyId}/`, () => HttpResponse.json(reviewCase)));
    const data = await fetchCase(studyId);
    expect(data).toMatchObject({ studyNumber: reviewCase.studyNumber, report: null, reportPending: true, segmentation: null, maskApproved: null });
  });

  it("keeps a report in the worker's shape", async () => {
    const report = caseReport(extraction());
    server.use(http.get(`/api/review/cases/${studyId}/`, () => HttpResponse.json({ ...reviewCase, report })));
    expect(await fetchCase(studyId)).toMatchObject({ report, reportPending: false });
  });

  it("has nothing to wait for without a report", async () => {
    server.use(http.get(`/api/review/cases/${studyId}/`, () => HttpResponse.json({ ...reviewCase, report: null })));
    expect(await fetchCase(studyId)).toMatchObject({ report: null, reportPending: false });
  });
});

describe("approving", () => {
  it("sends the mask decision with the CSRF token from the cookie", async () => {
    document.cookie = "csrftoken=t0k3n";
    const sent = capture(`/api/review/cases/${studyId}/approve-mask/`);
    await approveMask(studyId, { mask: "corrected", edits: 3 });
    expect(sent).toEqual([{ path: `/api/review/cases/${studyId}/approve-mask/`, csrf: "t0k3n", body: { mask: "corrected", edits: 3 } }]);
  });

  it("sends the approved report with the check of each field", async () => {
    const sent = capture(`/api/review/cases/${studyId}/approve-form/`);
    const report = extraction({ wniosek: { birads: "4a", tekst: null, zalecenie: null } });
    const fields = { "zmiany.0.strona": "confirmed", "wniosek.birads": "corrected" } as const;
    await approveForm(studyId, { report, fields });
    expect(sent[0].body).toEqual({ report, fields });
  });

  it("takes the mask approval back with an empty POST", async () => {
    const sent = capture(`/api/review/cases/${studyId}/unapprove-mask/`);
    await unapproveMask(studyId);
    expect(sent).toHaveLength(1);
    expect(sent[0].body).toBeNull();
  });
});
