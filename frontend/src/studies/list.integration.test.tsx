import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { t } from "../i18n";
import studies from "../test/fixtures/studies.json";
import unassigned from "../test/fixtures/unassigned-reports.json";
import { radiologist, renderScreen, researcher } from "../test/render";
import { capturePosts, http, HttpResponse, server, type JsonBodyType } from "../test/server";
import StudiesPage from "../pages/StudiesPage";

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

  it("says how far reading each report without a study got", async () => {
    server.use(
      http.get("/api/studies", () => HttpResponse.json(studies)),
      http.get("/api/reports/unassigned/", () => HttpResponse.json([unassigned[0], { ...unassigned[1], status: "FAILED", error: "OCR: no text found" }])),
    );
    renderScreen(<StudiesPage />, { route: "/badania?dzis=0", user: radiologist });
    expect(await screen.findByText(new RegExp(t("studies.card.reading")))).toBeInTheDocument();
    expect(screen.getByText(t("studies.card.failed"))).toBeInTheDocument();
  });

  it("puts a mask of unknown uncertainty first among the studies to review", async () => {
    const unknown = studies.findIndex((s) => s.segmentation_status === "COMPLETED");
    backend(studies.map((s, i) => (i === unknown ? { ...s, uncertainty: null } : s)));
    renderScreen(<StudiesPage />, { route: "/badania?dzis=0&filtr=to_review", user: radiologist });
    const rows = within(await screen.findByRole("table")).getAllByRole("row");
    expect(rows[1]).toHaveTextContent(studies[unknown].patient_id);
  });

  it("deletes a report without a study once confirmed", async () => {
    backend(studies);
    const deleted: string[] = [];
    server.use(
      http.delete("/api/reports/:id/", ({ params }) => {
        deleted.push(String(params.id));
        return new HttpResponse(null, { status: 204 });
      }),
    );
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    renderScreen(<StudiesPage />, { route: "/badania?dzis=0", user: radiologist });
    await user.click(await screen.findByText(unassigned[1].fileName));
    await user.click(screen.getByRole("button", { name: t("studies.unassigned.delete") }));
    expect(await screen.findByText(t("studies.unassigned.delete.done", { name: unassigned[1].fileName }))).toBeInTheDocument();
    expect(deleted).toEqual([unassigned[1].id]);
  });

  it("says why the backend kept a report it is still reading", async () => {
    backend(studies);
    server.use(http.delete("/api/reports/:id/", () => HttpResponse.json({ code: "processing", detail: "Opis jest w trakcie przetwarzania; spróbuj później." }, { status: 409 })));
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();
    renderScreen(<StudiesPage />, { route: "/badania?dzis=0", user: radiologist });
    await user.click(await screen.findByText(unassigned[0].fileName));
    await user.click(screen.getByRole("button", { name: t("studies.unassigned.delete") }));
    expect(await screen.findByText("Opis jest w trakcie przetwarzania; spróbuj później.")).toBeInTheDocument();
  });

  it("orders reading a report nobody has processed yet", async () => {
    const uploaded = { ...unassigned[1], status: "UPLOADED" };
    server.use(
      http.get("/api/studies", () => HttpResponse.json(studies)),
      http.get("/api/reports/unassigned/", () => HttpResponse.json([uploaded])),
    );
    const sent = capturePosts("/api/reports/:id/process/");
    const user = userEvent.setup();
    renderScreen(<StudiesPage />, { route: "/badania?dzis=0", user: radiologist });
    await user.click(await screen.findByText(uploaded.fileName));
    await user.click(screen.getByRole("button", { name: t("studies.unassigned.process") }));
    expect(await screen.findByText(t("studies.unassigned.process.done"))).toBeInTheDocument();
    expect(sent.map((s) => s.path)).toEqual([`/api/reports/${uploaded.id}/process/`]);
  });

  it("offers the radiologist another reading only after a failed one", async () => {
    server.use(
      http.get("/api/studies", () => HttpResponse.json(studies)),
      http.get("/api/reports/unassigned/", () => HttpResponse.json([unassigned[1], { ...unassigned[0], status: "FAILED", error: "OCR: no text found" }])),
    );
    const user = userEvent.setup();
    renderScreen(<StudiesPage />, { route: "/badania?dzis=0", user: radiologist });
    await user.click(await screen.findByText(unassigned[1].fileName));
    expect(screen.queryByRole("button", { name: t("studies.unassigned.processAgain") })).not.toBeInTheDocument();
    await user.click(screen.getByText(unassigned[0].fileName));
    expect(screen.getByRole("button", { name: t("studies.unassigned.processAgain") })).toBeInTheDocument();
  });
});
