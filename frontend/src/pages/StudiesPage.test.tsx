import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { t } from "../i18n";
import studies from "../test/fixtures/studies.json";
import unassigned from "../test/fixtures/unassigned-reports.json";
import { radiologist, renderScreen, researcher } from "../test/render";
import { http, HttpResponse, server, type JsonBodyType } from "../test/server";
import StudiesPage from "./StudiesPage";

function backend(list: JsonBodyType, status = 200) {
  server.use(
    http.get("/api/studies", () => HttpResponse.json(list, { status })),
    http.get("/api/reports/unassigned/", () => HttpResponse.json(unassigned)),
  );
}

describe("StudiesPage", () => {
  it("lists the studies with a row for each", async () => {
    backend(studies);
    renderScreen(<StudiesPage />, { route: "/badania?dzis=0", user: radiologist });
    const table = await screen.findByRole("table");
    for (const study of studies) expect(within(table).getByText(study.patient_id)).toBeInTheDocument();
  });

  it("lets the radiologist add studies", async () => {
    backend(studies);
    renderScreen(<StudiesPage />, { route: "/badania?dzis=0", user: radiologist });
    expect(await screen.findByText(t("studies.add"))).toBeInTheDocument();
  });

  it("doesn't let the researcher add studies", async () => {
    backend(studies);
    renderScreen(<StudiesPage />, { route: "/badania?dzis=0", user: researcher });
    await screen.findByRole("table");
    expect(screen.queryByText(t("studies.add"))).not.toBeInTheDocument();
  });

  it("says when there are no studies yet", async () => {
    backend([]);
    renderScreen(<StudiesPage />, { route: "/badania", user: radiologist });
    expect(await screen.findByText(t("studies.empty.title"))).toBeInTheDocument();
  });

  it("names an Orthanc outage", async () => {
    backend({ code: "orthanc_unavailable", detail: "Orthanc is down" }, 503);
    renderScreen(<StudiesPage />, { route: "/badania", user: radiologist });
    expect(await screen.findByText(t("studies.error.orthancUnavailable"))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t("state.retry") })).toBeInTheDocument();
  });
});
