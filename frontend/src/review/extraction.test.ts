import { describe, expect, it } from "vitest";

import { caseReport } from "../test/extraction";
import { isCaseReport } from "./extraction";

describe("isCaseReport", () => {
  it("accepts a report in the worker's current shape", () => {
    expect(isCaseReport(caseReport())).toBe(true);
  });

  it("counts older backend shapes as not processed yet", () => {
    const report = caseReport();
    expect(isCaseReport(null)).toBe(false);
    expect(isCaseReport("pending")).toBe(false);
    expect(isCaseReport({ fields: [{ name: "birads", value: "4" }] })).toBe(false);
    expect(isCaseReport({ ...report, result: { ...report.result, provenance: {} } })).toBe(false);
  });
});
