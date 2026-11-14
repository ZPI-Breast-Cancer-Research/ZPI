import { useQuery } from "@tanstack/react-query";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { errorText } from "../api";
import { t } from "../i18n";
import LoginPage from "../pages/LoginPage";
import { listStudies } from "../studies/api";
import signin from "../test/fixtures/signin.json";
import studies from "../test/fixtures/studies.json";
import { radiologist, renderScreen } from "../test/render";
import { http, HttpResponse, noSession, server } from "../test/server";
import { RequireAuth } from "./AuthProvider";

function Studies() {
  const query = useQuery({ queryKey: ["studies"], queryFn: listStudies });
  if (query.error) return <p>{errorText(query.error)}</p>;
  return <h1>{query.data ? `${query.data.length} badań` : "…"}</h1>;
}

function renderApp() {
  renderScreen(
    <Routes>
      <Route path="logowanie" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route path="badania" element={<Studies />} />
      </Route>
    </Routes>,
    { route: "/badania?filtr=to_review", user: radiologist },
  );
}

describe("when the session ends", () => {
  it("sends the user to sign in and says why", async () => {
    server.use(http.get("/api/studies", noSession), http.get("/api/profile/", noSession));
    renderApp();
    expect(await screen.findByRole("alert")).toHaveTextContent(t("login.expired"));
    expect(sessionStorage.getItem("maria.user")).toBeNull();
  });

  it("comes back to the same screen after signing in again", async () => {
    let session = false;
    server.use(
      http.get("/api/studies", () => (session ? HttpResponse.json(studies) : noSession())),
      http.get("/api/profile/", () => (session ? HttpResponse.json({}) : noSession())),
      http.post("/api/auth/signin/", () => ((session = true), HttpResponse.json(signin))),
    );
    renderApp();
    const user = userEvent.setup();
    await user.type(await screen.findByLabelText(t("login.username")), "demo.radiologist");
    await user.type(screen.getByLabelText(t("login.password")), "DemoPass123!");
    await user.click(screen.getByRole("button", { name: t("login.submit") }));
    expect(await screen.findByRole("heading", { name: `${studies.length} badań` })).toBeInTheDocument();
  });

  it("checks the session when a tab opens with a remembered user", async () => {
    server.use(http.get("/api/studies", () => HttpResponse.json(studies)), http.get("/api/profile/", noSession));
    renderApp();
    expect(await screen.findByText(t("login.expired"))).toBeInTheDocument();
  });
});

describe("while the session lives", () => {
  it("treats a refusal as a missing permission and stays", async () => {
    server.use(http.get("/api/studies", () => HttpResponse.json({ detail: "Brak uprawnień" }, { status: 403 })));
    renderApp();
    expect(await screen.findByText("Brak uprawnień")).toBeInTheDocument();
    expect(sessionStorage.getItem("maria.user")).not.toBeNull();
  });

  it("stays signed in when the check itself can't reach the server", async () => {
    server.use(http.get("/api/studies", () => HttpResponse.json(studies)), http.get("/api/profile/", () => HttpResponse.error()));
    renderApp();
    expect(await screen.findByRole("heading", { name: `${studies.length} badań` })).toBeInTheDocument();
  });
});
