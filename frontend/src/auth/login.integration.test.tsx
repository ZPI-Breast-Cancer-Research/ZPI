import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { t } from "../i18n";
import signin from "../test/fixtures/signin.json";
import { renderScreen } from "../test/render";
import { http, HttpResponse, server } from "../test/server";
import LoginPage from "../pages/LoginPage";

function renderLogin() {
  renderScreen(
    <Routes>
      <Route path="logowanie" element={<LoginPage />} />
      <Route path="pulpit" element={<h1>pulpit</h1>} />
    </Routes>,
    { route: "/logowanie" },
  );
}

async function signInWith(login: string, password: string) {
  const user = userEvent.setup();
  if (login) await user.type(screen.getByLabelText(t("login.username")), login);
  if (password) await user.type(screen.getByLabelText(t("login.password")), password);
  await user.click(screen.getByRole("button", { name: t("login.submit") }));
}

describe("LoginPage", () => {
  it("asks for both fields before sending anything", async () => {
    renderLogin();
    await signInWith("demo.radiologist", "");
    expect(screen.getByRole("alert")).toHaveTextContent(t("login.required"));
  });

  it("signs in and opens the dashboard", async () => {
    server.use(http.post("/api/auth/signin/", () => HttpResponse.json(signin)));
    renderLogin();
    await signInWith("demo.radiologist", "DemoPass123!");
    expect(await screen.findByRole("heading", { name: "pulpit" })).toBeInTheDocument();
    expect(JSON.parse(sessionStorage.getItem("maria.user")!)).toEqual(signin.user);
  });

  it("says the login or password is wrong on 401", async () => {
    server.use(http.post("/api/auth/signin/", () => HttpResponse.json({ detail: "bad credentials" }, { status: 401 })));
    renderLogin();
    await signInWith("demo.radiologist", "zle");
    expect(await screen.findByRole("alert")).toHaveTextContent(t("login.failed"));
  });

  it("says the server can't be reached when it fails", async () => {
    server.use(http.post("/api/auth/signin/", () => new HttpResponse(null, { status: 502 })));
    renderLogin();
    await signInWith("demo.radiologist", "DemoPass123!");
    expect(await screen.findByRole("alert")).toHaveTextContent(t("login.unavailable"));
  });

  it("asks for a new password on the first sign-in", async () => {
    server.use(http.post("/api/auth/signin/", () => HttpResponse.json({ kind: "first-login", login: "nowy" })));
    renderLogin();
    await signInWith("nowy", "tymczasowe");
    expect(await screen.findByRole("heading", { name: t("login.firstTitle") })).toBeInTheDocument();
  });
});
