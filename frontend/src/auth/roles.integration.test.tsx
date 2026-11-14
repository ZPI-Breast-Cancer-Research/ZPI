import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { t } from "../i18n";
import { admin, radiologist, renderScreen, researcher } from "../test/render";
import { http, HttpResponse, server } from "../test/server";
import type { User } from "./api";
import { RequireAuth, RequireRole, useAuth } from "./AuthProvider";

function SignOut() {
  const { user, signOut } = useAuth();
  return <button onClick={signOut}>{user ? user.login : "signed out"}</button>;
}

function renderRoutes(user: User | null, route = "/modele") {
  renderScreen(
    <Routes>
      <Route path="logowanie" element={<h1>logowanie</h1>} />
      <Route element={<RequireAuth />}>
        <Route
          path="modele"
          element={
            <RequireRole permission="viewModels" title={t("nav.models")}>
              <h1>modele</h1>
            </RequireRole>
          }
        />
        <Route path="konto" element={<SignOut />} />
      </Route>
    </Routes>,
    { route, user },
  );
}

describe("RequireAuth", () => {
  it("sends a signed-out visitor to sign in", () => {
    renderRoutes(null);
    expect(screen.getByRole("heading", { name: "logowanie" })).toBeInTheDocument();
  });
});

describe("RequireRole", () => {
  it.each([researcher, admin])("shows the screen to the $role", (user) => {
    renderRoutes(user);
    expect(screen.getByRole("heading", { name: "modele" })).toBeInTheDocument();
  });

  it("says which roles may see it to anyone else", () => {
    renderRoutes(radiologist);
    expect(screen.queryByRole("heading", { name: "modele" })).not.toBeInTheDocument();
    expect(screen.getByText(t("forbidden.title"))).toBeInTheDocument();
    expect(screen.getByText(t("forbidden.body", { role: [t("role.researcher"), t("role.admin")].join(", ") }))).toBeInTheDocument();
  });
});

describe("signOut", () => {
  it("leaves locally even when the server call fails", async () => {
    server.use(http.post("/api/auth/signout/", () => new HttpResponse(null, { status: 500 })));
    renderRoutes(radiologist, "/konto");
    await userEvent.click(screen.getByRole("button", { name: radiologist.login }));
    expect(await screen.findByRole("heading", { name: "logowanie" })).toBeInTheDocument();
    expect(sessionStorage.getItem("maria.user")).toBeNull();
  });
});
