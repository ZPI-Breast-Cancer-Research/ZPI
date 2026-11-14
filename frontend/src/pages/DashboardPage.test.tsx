import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { User } from "../auth/api";
import { t } from "../i18n";
import dashboard from "../test/fixtures/dashboard.json";
import { radiologist, renderScreen, researcher } from "../test/render";
import { http, HttpResponse, server, type JsonBodyType } from "../test/server";
import DashboardPage from "./DashboardPage";

function renderDashboard(user: User, body: JsonBodyType = dashboard, status = 200) {
  server.use(http.get("/api/dashboard/", () => HttpResponse.json(body, { status })));
  renderScreen(<DashboardPage />, { route: "/pulpit", user });
}

const attention = [
  { kind: "processing_error", subject: "0018", href: "/badania" },
  { kind: "model_candidate", subject: "segmentation", href: "/modele" },
];

describe("DashboardPage", () => {
  it("counts the work and lists the queue", async () => {
    renderDashboard(radiologist);
    expect(await screen.findByText(t("dashboard.toReview"))).toHaveTextContent(String(dashboard.toReview));
    expect(screen.getByText(`#${dashboard.queue[0].studyNumber}`)).toBeInTheDocument();
  });

  it("starts the review only for those who verify", async () => {
    renderDashboard(radiologist);
    expect(await screen.findByRole("link", { name: t("dashboard.start") })).toHaveAttribute("href", "/weryfikacja");
  });

  it("has no review to start for a researcher", async () => {
    renderDashboard(researcher);
    await screen.findByText(t("dashboard.toReview"));
    expect(screen.queryByRole("link", { name: t("dashboard.start") })).not.toBeInTheDocument();
  });

  it("tells about a new model only those who see the models", async () => {
    renderDashboard(radiologist, { ...dashboard, attention });
    expect(await screen.findByText(/0018/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /segment/i })).not.toBeInTheDocument();
  });

  it("says when the dashboard can't be loaded", async () => {
    renderDashboard(radiologist, { detail: "Baza danych nie odpowiada." }, 503);
    expect(await screen.findByText(t("dashboard.error"))).toBeInTheDocument();
    expect(screen.getByText("Baza danych nie odpowiada.")).toBeInTheDocument();
  });
});
