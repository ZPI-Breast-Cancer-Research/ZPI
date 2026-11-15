import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import type { User } from "../auth/api";
import { t } from "../i18n";
import type { Proposal } from "./api";
import extraction from "../test/fixtures/models-extraction.json";
import segmentation from "../test/fixtures/models-segmentation.json";
import { admin, renderScreen, researcher } from "../test/render";
import { capturePosts, http, HttpResponse, server } from "../test/server";
import ModelsPage from "../pages/ModelsPage";

const proposal: Proposal = {
  version: "demo-seg-1.2.0",
  replaces: segmentation.inUse.version,
  restore: false,
  author: { login: researcher.login, name: researcher.name, role: "researcher" },
  at: "2026-11-12",
  reason: "Lepszy Dice na zbiorze szpitalnym.",
  training: null,
  gate: null,
};

function renderModels(user: User, { route = "/modele", withProposal = false } = {}) {
  server.use(
    http.get("/api/models/segmentation/", () => HttpResponse.json({ ...segmentation, proposal: withProposal ? proposal : null })),
    http.get("/api/models/extraction/", () => HttpResponse.json(extraction)),
  );
  renderScreen(
    <Routes>
      <Route path="modele" element={<ModelsPage module="segmentation" />} />
      <Route path="modele/ekstrakcja" element={<ModelsPage module="extraction" />} />
    </Routes>,
    { route, user },
  );
}

describe("ModelsPage", () => {
  it("shows the segmentation version in use and says training runs", async () => {
    renderModels(researcher);
    expect(await screen.findByText(t("models.inUse.title", { v: segmentation.inUse.version }))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: new RegExp(t("models.trainingNow")) })).toBeInTheDocument();
  });

  it("reads the extraction model the backend sends today", async () => {
    renderModels(researcher, { route: "/modele/ekstrakcja" });
    expect(await screen.findByText(t("models.inUse.title", { v: extraction.version }))).toBeInTheDocument();
  });

  it("says when the models can't be loaded", async () => {
    server.use(
      http.get("/api/models/segmentation/", () => HttpResponse.json({ detail: "MLflow nie odpowiada." }, { status: 503 })),
      http.get("/api/models/extraction/", () => HttpResponse.json(extraction)),
    );
    renderScreen(<ModelsPage module="segmentation" />, { route: "/modele", user: admin });
    expect(await screen.findByText(t("models.error"))).toBeInTheDocument();
  });
});

describe("a proposed version", () => {
  it("waits for the admin, and its author can withdraw it", async () => {
    const sent = capturePosts(`/api/models/${proposal.version}/withdraw/`);
    renderModels(researcher, { withProposal: true });
    expect(await screen.findByText(t("models.proposal.waiting"))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: new RegExp(t("models.tab.waiting")) })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: t("models.promote", { v: proposal.version }) })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: t("models.proposal.withdraw") }));
    await waitFor(() => expect(sent).toHaveLength(1));
  });

  it("is approved by the admin", async () => {
    const sent = capturePosts(`/api/models/${proposal.version}/promote/`);
    renderModels(admin, { withProposal: true });
    await userEvent.click(await screen.findByRole("button", { name: t("models.promote", { v: proposal.version }) }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0].body).toEqual({ reason: null });
  });

  it("is rejected only with a reason", async () => {
    const sent = capturePosts(`/api/models/${proposal.version}/reject/`);
    const user = userEvent.setup();
    renderModels(admin, { withProposal: true });
    await user.click(await screen.findByRole("button", { name: t("models.reject") }));
    const confirm = screen.getByRole("button", { name: t("models.reject.confirm", { v: proposal.version }) });
    expect(confirm).toBeDisabled();

    await user.type(screen.getByLabelText(t("models.reject.reason")), "Gorszy HD95.");
    await user.click(confirm);
    await waitFor(() => expect(sent[0]?.body).toEqual({ reason: "Gorszy HD95." }));
  });

  it("says why a decision didn't go through", async () => {
    server.use(http.post(`/api/models/${proposal.version}/promote/`, () => HttpResponse.json({ detail: "Wersja jest już w użyciu." }, { status: 409 })));
    renderModels(admin, { withProposal: true });
    await userEvent.click(await screen.findByRole("button", { name: t("models.promote", { v: proposal.version }) }));
    expect(await screen.findByRole("status")).toHaveTextContent(t("models.action.failed", { why: "Wersja jest już w użyciu." }));
  });
});
