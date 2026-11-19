import { describe, expect, it } from "vitest";

import { ApiError } from "./api";
import { retryQuery } from "./queryClient";

describe("retryQuery", () => {
  it("tries again when the server didn't answer or failed", () => {
    expect(retryQuery(0, new ApiError("brak połączenia", "backend_unreachable"))).toBe(true);
    expect(retryQuery(1, new ApiError("HTTP 502", "unknown", 502))).toBe(true);
  });

  it("stops after two more tries", () => {
    expect(retryQuery(2, new ApiError("HTTP 502", "unknown", 502))).toBe(false);
  });

  it("doesn't repeat a refusal", () => {
    for (const status of [400, 403, 404]) expect(retryQuery(0, new ApiError("odmowa", "unknown", status))).toBe(false);
  });
});
