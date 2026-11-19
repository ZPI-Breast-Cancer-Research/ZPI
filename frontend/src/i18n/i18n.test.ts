import { describe, expect, it } from "vitest";

import { hasMessage, plural, t } from ".";

describe("t", () => {
  it("fills placeholders and leaves unknown ones in place", () => {
    expect(t("api.http", { status: 500 })).toContain("500");
    expect(t("api.http")).toContain("{status}");
  });

  it("knows which keys exist", () => {
    expect(hasMessage("api.http")).toBe(true);
    expect(hasMessage("field.nothing")).toBe(false);
  });
});

describe("plural", () => {
  const studies = (n: number) => plural(n, "studies.count.one", "studies.count.few", "studies.count.many");

  it("picks one of the three Polish forms", () => {
    expect(studies(1)).toBe(t("studies.count.one", { n: 1 }));
    for (const n of [2, 3, 4, 22, 34, 102]) expect(studies(n)).toBe(t("studies.count.few", { n }));
    for (const n of [0, 5, 11, 12, 13, 14, 21, 25, 112]) expect(studies(n)).toBe(t("studies.count.many", { n }));
  });
});
