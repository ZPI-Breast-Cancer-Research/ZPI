import { describe, expect, it } from "vitest";

import { extraction } from "../test/extraction";
import { isCaseReport, type CaseReport } from "./extraction";

const report: CaseReport = {
  originalUrl: null,
  result: {
    source: "opis.txt",
    status: "ok",
    data: extraction(),
    error: null,
    warnings: [],
    text: "",
    provenance: {
      ocr_engine: null,
      ocr_engine_version: null,
      ocr_mean_confidence: null,
      orientation_detector: null,
      page_rotations: [],
      llm_provider: "test",
      llm_model: "test",
      prompt_version: "1",
      schema_version: "3",
    },
    attempts: 1,
    ocr_seconds: null,
    llm_seconds: null,
    created_at: "2026-11-13T10:00:00Z",
  },
};

describe("isCaseReport", () => {
  it("accepts a report in the worker's current shape", () => {
    expect(isCaseReport(report)).toBe(true);
  });

  it("counts older backend shapes as not processed yet", () => {
    expect(isCaseReport(null)).toBe(false);
    expect(isCaseReport("reports/opis.txt")).toBe(false);
    expect(isCaseReport({ fields: [{ name: "birads", value: "4" }] })).toBe(false);
    expect(isCaseReport({ ...report, result: { ...report.result, provenance: {} } })).toBe(false);
  });
});
