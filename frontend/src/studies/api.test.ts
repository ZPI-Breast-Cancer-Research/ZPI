import { describe, expect, it } from "vitest";

import { ApiError } from "../api";
import { t } from "../i18n";
import studies from "../test/fixtures/studies.json";
import unassigned from "../test/fixtures/unassigned-reports.json";
import { http, HttpResponse, server } from "../test/server";
import { listStudies, listUnassignedReports, type ImageStatus, type ReportStatus } from "./api";

// the backend's status words and the stage of the review each one means
const IMAGE: Record<string, ImageStatus> = {
  PENDING: "queued",
  PROCESSING: "processing",
  COMPLETED: "to_review",
  APPROVED: "verified_unchanged",
  CORRECTED: "verified_corrected",
  REJECTED: "error",
};
const REPORT: Record<string, ReportStatus> = {
  PENDING: "extracting",
  PROCESSING: "extracting",
  COMPLETED: "to_review",
  APPROVED: "verified_unchanged",
  CORRECTED: "verified_corrected",
  REJECTED: "to_review",
  FAILED: "error",
};

describe("listStudies", () => {
  it("knows every status word the backend sends", async () => {
    server.use(http.get("/api/studies", () => HttpResponse.json(studies)));
    const rows = await listStudies();
    expect(rows.filter((row) => !row.image || !row.report)).toEqual([]);
  });

  it("speaks in the stages of the review instead of the backend's status words", async () => {
    server.use(http.get("/api/studies", () => HttpResponse.json(studies)));
    const rows = await listStudies();
    expect(rows.map((row) => [row.image, row.report])).toEqual(studies.map((study) => [IMAGE[study.segmentation_status], REPORT[study.extraction_status]]));
  });

  it("turns the DICOM date into ISO and keeps what the backend doesn't send empty", async () => {
    server.use(http.get("/api/studies", () => HttpResponse.json([{ ...studies[0], study_date: "20260926" }, { ...studies[1], study_date: "", patient_id: null }])));
    const [first, second] = await listStudies();
    expect(first).toMatchObject({ id: studies[0].orthanc_id, studyDate: "2026-09-26", number: null, verifiedAt: null, uncertainty: studies[0].uncertainty });
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
    expect(await listUnassignedReports()).toEqual(
      unassigned.map((report) => ({ id: report.id, fileName: report.fileName, kind: report.kind, addedAt: report.addedAt, originalUrl: null, report: null })),
    );
  });
});
