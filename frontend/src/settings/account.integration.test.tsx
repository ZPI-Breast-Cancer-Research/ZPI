import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { t } from "../i18n";
import profile from "../test/fixtures/profile.json";
import { radiologist, renderScreen } from "../test/render";
import { capturePosts, http, HttpResponse, server } from "../test/server";
import AccountPage from "../pages/AccountPage";

// a field's label also holds its help text
const startsWith = (label: string) => new RegExp(`^${label}`);

async function changePassword(current: string, next: string, repeat = next) {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText(startsWith(t("settings.currentPassword"))), current);
  await user.type(screen.getByLabelText(startsWith(t("settings.newPassword"))), next);
  await user.type(screen.getByLabelText(startsWith(t("settings.repeatPassword"))), repeat);
  await user.click(screen.getByRole("button", { name: t("settings.changePassword") }));
}

describe("AccountPage", () => {
  it("shows the signed-in person's profile", async () => {
    renderScreen(<AccountPage />, { route: "/konto", user: radiologist });
    expect(await screen.findByText(profile.email)).toBeInTheDocument();
    expect(screen.getByText(profile.pwz)).toBeInTheDocument();
  });

  it("sends the current and the new password under the names the backend reads", async () => {
    const sent = capturePosts("/api/auth/change-password/");
    renderScreen(<AccountPage />, { route: "/konto", user: radiologist });
    await changePassword("DemoPass123!", "NoweHaslo2026!");
    await waitFor(() => expect(sent[0]?.body).toEqual({ current: "DemoPass123!", next: "NoweHaslo2026!" }));
    expect(await screen.findByRole("status")).toHaveTextContent(t("settings.passwordChanged"));
  });

  it("says why the password wasn't changed", async () => {
    server.use(http.post("/api/auth/change-password/", () => HttpResponse.json({ detail: "Stare hasło jest niepoprawne." }, { status: 400 })));
    renderScreen(<AccountPage />, { route: "/konto", user: radiologist });
    await changePassword("zle", "NoweHaslo2026!");
    expect(await screen.findByRole("status")).toHaveTextContent("Stare hasło jest niepoprawne.");
  });

  it("doesn't send a password shorter than 12 characters", async () => {
    const sent = capturePosts("/api/auth/change-password/");
    renderScreen(<AccountPage />, { route: "/konto", user: radiologist });
    await changePassword("DemoPass123!", "krotkie");
    expect(screen.getByText(t("settings.passwordTooShort"))).toBeInTheDocument();
    expect(sent).toEqual([]);
  });
});
