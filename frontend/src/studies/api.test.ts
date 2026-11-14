import { describe, expect, it } from "vitest";

import { ApiError } from "../api";
import { t } from "../i18n";
import studies from "../test/fixtures/studies.json";
import unassigned from "../test/fixtures/unassigned-reports.json";
import { http, HttpResponse, server } from "../test/server";
import { listStudies, listUnassignedReports } from "./api";

describe("listStudies", () => {
  it("speaks in the stages of the review instead of the backend's status words", async () => {
    server.use(http.get("/api/studies", () => HttpResponse.json(studies)));
    const rows = await listStudies();
    expect(rows.map((row) => [row.patientId, row.image, row.report])).toEqual([
      ["DEMO-P0016", "verified_unchanged", "verified_corrected"],
      ["DEMO-P0007", "verified_corrected", "to_review"],
      ["DEMO-P0013", "verified_unchanged", "verified_unchanged"],
      ["DEMO-P0019", "error", "to_review"],
      ["DEMO-P0014", "to_review", "verified_unchanged"],
      ["DEMO-P0003", "to_review", "to_review"],
      ["DEMO-P0001", "queued", "extracting"],
      ["DEMO-P0002", "processing", "extracting"],
    ]);
  });

  it("turns the DICOM date into ISO and keeps what the backend doesn't send empty", async () => {
    server.use(http.get("/api/studies", () => HttpResponse.json([{ ...studies[0], study_date: "20260926" }, { ...studies[1], study_date: "", patient_id: null }])));
    const [first, second] = await listStudies();
    expect(first).toMatchObject({ id: studies[0].orthanc_id, studyDate: "2026-09-26", number: null, verifiedAt: null, uncertainty: 0.19 });
    expect(second).toMatchObject({ studyDate: null, patientId: "—" });
  });

  it("says the app must be opened through the gateway when /api returns the page", async () => {
    server.use(http.get("/api/studies", () => HttpResponse.html("<!doctype html><div id=root></div>")));
    const error = await listStudies().catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ kind: "backend_unreachable", message: t("api.badResponse", { url: window.location.origin }) });
  });

  it("names the Orthanc problem the backend reports", async () => {
    server.use(http.get("/api/studies", () => HttpResponse.json({ code: "orthanc_unavailable", detail: "Orthanc is down" }, { status: 503 })));
    await expect(listStudies()).rejects.toMatchObject({ kind: "orthanc_unavailable" });
  });
});

describe("listUnassignedReports", () => {
  it("reads the reports waiting for a study, before the worker has read them", async () => {
    server.use(http.get("/api/reports/unassigned/", () => HttpResponse.json(unassigned)));
    expect(await listUnassignedReports()).toEqual([
      { id: "26", fileName: "skan_opisu_006.jpeg", kind: "scan", addedAt: "2026-11-12", originalUrl: null, report: null },
      { id: "25", fileName: "opis_piersi_005.txt", kind: "text", addedAt: "2026-11-12", originalUrl: null, report: null },
    ]);
  });
});
