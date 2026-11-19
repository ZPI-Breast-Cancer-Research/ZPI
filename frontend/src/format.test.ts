import { describe, expect, it } from "vitest";

import { formatDate, formatDayMonth, formatDecimal, formatMetric, formatNumber, formatOneDecimal, formatPercent, formatWhen, toIsoDate } from "./format";

describe("dates", () => {
  it("writes ISO dates the Polish way", () => {
    expect(formatDate("2026-11-13")).toBe("13.11.2026");
    expect(formatDayMonth("2026-03-05")).toBe("05.03");
  });

  it("shows a dash for a missing date and leaves an odd one as it is", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined)).toBe("—");
    expect(formatDate("2026")).toBe("2026");
    expect(formatDayMonth(null)).toBe("—");
  });

  it("gives only the time for today", () => {
    const today = new Date(2026, 10, 13, 15, 0);
    expect(formatWhen("2026-11-13T09:12:45", today)).toBe("09:12");
    expect(formatWhen("2026-11-12T09:12:45", today)).toBe("12.11.2026, 09:12");
  });

  it("builds the ISO date from local time", () => {
    expect(toIsoDate(new Date(2026, 0, 5, 23, 59))).toBe("2026-01-05");
  });
});

describe("numbers", () => {
  it("uses a decimal comma", () => {
    expect(formatNumber(1.5)).toBe("1,5");
    expect(formatNumber(6)).toBe("6");
    expect(formatOneDecimal(6)).toBe("6,0");
    expect(formatDecimal(0.8)).toBe("0,80");
  });

  it("shows a dash, never a made-up number, for unknown values", () => {
    expect(formatDecimal(null)).toBe("—");
    expect(formatPercent(null)).toBe("—");
    expect(formatPercent(undefined)).toBe("—");
    expect(formatMetric(null, " ml")).toBe("—");
  });

  it("adds the unit after the value", () => {
    expect(formatMetric(6.04, " ml")).toBe("6,04 ml");
    expect(formatPercent(0.42)).toBe("42%");
  });
});
