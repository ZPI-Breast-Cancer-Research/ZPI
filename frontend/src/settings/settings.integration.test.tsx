import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { t } from "../i18n";
import logs from "../test/fixtures/audit-logs.json";
import health from "../test/fixtures/health.json";
import users from "../test/fixtures/users.json";
import { admin, renderScreen } from "../test/render";
import { capturePosts, http, HttpResponse, server } from "../test/server";
import SettingsPage from "../pages/SettingsPage";

// a field's label also holds its help text
const startsWith = (label: string) => new RegExp(`^${label}`);

function backend() {
  server.use(
    http.get("/api/users/", () => HttpResponse.json(users)),
    http.get("/api/logs/", () => HttpResponse.json(logs)),
    http.get("/api/health", () => HttpResponse.json(health)),
  );
}

async function fillNewAccount(login: string) {
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: t("users.add") }));
  await user.type(screen.getByLabelText(startsWith(t("settings.name"))), "Jan Testowy");
  await user.type(screen.getByLabelText(startsWith(t("settings.login"))), login);
  await user.type(screen.getByLabelText(startsWith(t("settings.email"))), "jan.testowy@example.test");
  await user.type(screen.getByLabelText(startsWith(t("settings.pwz"))), "1234567");
  await user.click(screen.getByRole("button", { name: t("users.create") }));
}

describe("SettingsPage", () => {
  it("lists the accounts, the log and the system's state", async () => {
    backend();
    renderScreen(<SettingsPage />, { route: "/ustawienia", user: admin });
    for (const account of users) expect(await screen.findAllByText(account.name)).not.toHaveLength(0);
    expect(await screen.findAllByText(new RegExp(logs[1].object))).not.toHaveLength(0);
    expect(await screen.findByText(t("system.component.orthanc"))).toBeInTheDocument();
  });

  it("creates an account and shows its temporary password once", async () => {
    backend();
    server.use(http.post("/api/users/", () => HttpResponse.json({ password: "Tymczasowe2026" }, { status: 201 })));
    renderScreen(<SettingsPage />, { route: "/ustawienia", user: admin });
    await fillNewAccount("jan.testowy");
    expect(await screen.findByText("Tymczasowe2026")).toBeInTheDocument();
    expect(screen.getByText(t("users.issuedNote"))).toBeInTheDocument();
  });

  it("sends the new account as typed", async () => {
    backend();
    const sent = capturePosts("/api/users/");
    renderScreen(<SettingsPage />, { route: "/ustawienia", user: admin });
    await fillNewAccount("jan.testowy");
    await waitFor(() => expect(sent[0]?.body).toMatchObject({ name: "Jan Testowy", login: "jan.testowy", email: "jan.testowy@example.test", role: "radiologist", pwz: "1234567" }));
  });

  it("says the login is taken only when it is", async () => {
    backend();
    server.use(http.post("/api/users/", () => HttpResponse.json({ detail: "login-taken" }, { status: 400 })));
    renderScreen(<SettingsPage />, { route: "/ustawienia", user: admin });
    await fillNewAccount("demo.radiologist2");
    expect(await screen.findByText(t("users.loginTaken"))).toBeInTheDocument();
  });

  it("shows any other failure as it is, not as a taken login", async () => {
    backend();
    server.use(http.post("/api/users/", () => new HttpResponse(null, { status: 500 })));
    renderScreen(<SettingsPage />, { route: "/ustawienia", user: admin });
    await fillNewAccount("jan.testowy");
    expect(await screen.findByRole("status")).toHaveTextContent(t("api.http", { status: 500 }));
    expect(screen.queryByText(t("users.loginTaken"))).not.toBeInTheDocument();
  });

  it("marks the row of the signed-in admin", async () => {
    backend();
    renderScreen(<SettingsPage />, { route: "/ustawienia", user: { ...admin, login: users[0].login } });
    const row = (await screen.findByText(users[0].name)).closest("tr")!;
    expect(within(row).getByText(new RegExp(t("users.you")))).toBeInTheDocument();
  });
});
