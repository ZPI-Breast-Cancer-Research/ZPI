import { AxiosError, AxiosHeaders, type AxiosResponse } from "axios";
import { describe, expect, it } from "vitest";

import { ApiError, canRetry, errorText, handleApiError, request } from "./api";
import { t } from "./i18n";

const config = { headers: new AxiosHeaders() };

function httpError(status: number, data?: unknown) {
  const response = { status, statusText: "", data, headers: {}, config } as AxiosResponse;
  return new AxiosError("Request failed", "ERR_BAD_RESPONSE", config, {}, response);
}

const networkError = () => new AxiosError("Network Error", "ERR_NETWORK", config, {});

function thrown(error: unknown, fallbackUrl?: string): ApiError {
  try {
    handleApiError(error, fallbackUrl);
  } catch (caught) {
    return caught as ApiError;
  }
  throw new Error("handleApiError returned");
}

describe("handleApiError", () => {
  it("passes our own errors through", () => {
    const own = new ApiError("already handled", "unknown");
    expect(thrown(own)).toBe(own);
  });

  it("names Orthanc problems the backend reports", () => {
    expect(thrown(httpError(503, { code: "orthanc_unavailable" }))).toMatchObject({ message: t("api.orthancUnavailable"), kind: "orthanc_unavailable" });
    expect(thrown(httpError(502, { code: "orthanc_unauthorized", detail: "401" }))).toMatchObject({ message: t("api.orthancUnauthorized"), kind: "orthanc_unauthorized" });
  });

  it("shows the backend's detail as it is", () => {
    expect(thrown(httpError(400, { detail: "Brak opisu." }))).toMatchObject({ message: "Brak opisu.", kind: "unknown" });
    expect(thrown(httpError(503, { code: "backend_unreachable", detail: "Spróbuj później." }))).toMatchObject({ kind: "backend_unreachable" });
  });

  it("says the server can't be reached when there's no response", () => {
    expect(thrown(networkError(), "http://localhost:8081")).toMatchObject({
      message: t("api.unreachable", { url: "http://localhost:8081" }),
      kind: "backend_unreachable",
    });
  });

  it("falls back to the status code, then to a generic message", () => {
    expect(thrown(httpError(500))).toMatchObject({ message: t("api.http", { status: 500 }), kind: "unknown" });
    expect(thrown(new TypeError("x is undefined"))).toMatchObject({ message: t("api.unknown"), kind: "unknown" });
  });
});

describe("request", () => {
  it("passes the answer through and turns a failure into ApiError with its status", async () => {
    expect(await request(Promise.resolve(7))).toBe(7);
    await expect(request(Promise.reject(httpError(409, { detail: "Przypadek zatwierdził już inny lekarz." })))).rejects.toMatchObject({
      message: "Przypadek zatwierdził już inny lekarz.",
      status: 409,
    });
  });
});

describe("canRetry", () => {
  it("retries when the server didn't answer or failed, not when it refused", () => {
    expect(canRetry(thrown(networkError()))).toBe(true);
    expect(canRetry(thrown(httpError(502)))).toBe(true);
    expect(canRetry(thrown(httpError(409, { detail: "Już zatwierdzone." })))).toBe(false);
    expect(canRetry(thrown(httpError(400)))).toBe(false);
  });
});

describe("errorText", () => {
  it("keeps our messages and words the rest for an error box", () => {
    expect(errorText(new ApiError("Brak opisu.", "unknown"))).toBe("Brak opisu.");
    expect(errorText(httpError(404))).toBe(t("api.http", { status: 404 }));
    expect(errorText(networkError())).toBe(t("api.unreachable", { url: window.location.origin }));
    expect(errorText(new Error("login-taken"))).toBe(t("api.unknown"));
  });
});
