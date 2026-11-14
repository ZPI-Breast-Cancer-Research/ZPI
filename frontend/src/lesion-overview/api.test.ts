import { describe, expect, it } from "vitest";

import { caseReport } from "../test/extraction";
import overview from "../test/fixtures/review-overview.json";
import { http, HttpResponse, server } from "../test/server";
import { fetchOverview } from "./api";

const url = `/api/review/cases/${overview.studyId}/review-overview/`;

describe("fetchOverview", () => {
  it("reads today's measurements and agreement as not there yet", async () => {
    server.use(http.get(url, () => HttpResponse.json(overview)));
    const data = await fetchOverview(overview.studyId);
    expect(data).toMatchObject({ studyNumber: "0007", status: "verified", measurements: null, report: null, reportPending: false });
    expect(data.verification.agreement).toBeNull();
  });

  it("keeps measurements in the agreed shape", async () => {
    const measurements = { source: "approved", largest: { sizeMm: 32, volumeMl: 6.04 }, totalMl: 6.04 };
    const agreement = { dice: 0.87, iou: 0.77, volumeMl: 1.2 };
    server.use(http.get(url, () => HttpResponse.json({ ...overview, measurements, verification: { ...overview.verification, agreement } })));
    const data = await fetchOverview(overview.studyId);
    expect(data.measurements).toEqual(measurements);
    expect(data.verification.agreement).toEqual(agreement);
  });

  it("waits for a report the worker hasn't read", async () => {
    server.use(http.get(url, () => HttpResponse.json({ ...overview, report: { source: "pending", accepted: null } })));
    expect(await fetchOverview(overview.studyId)).toMatchObject({ report: null, reportPending: true });
  });

  it("keeps a read report", async () => {
    const report = { source: caseReport(), accepted: caseReport().result.data };
    server.use(http.get(url, () => HttpResponse.json({ ...overview, report })));
    expect(await fetchOverview(overview.studyId)).toMatchObject({ report, reportPending: false });
  });

  it("names the error for a missing case", async () => {
    server.use(http.get(url, () => HttpResponse.json({ detail: "Nie znaleziono." }, { status: 404 })));
    await expect(fetchOverview(overview.studyId)).rejects.toMatchObject({ message: "Nie znaleziono." });
  });
});
