import { mockDelay, mockScenario, MOCK_API } from "../mock";
import axios from "axios";

import { api } from "../api";

export type Role = "radiologist" | "researcher" | "admin";

// one role per account; the admin runs the system and the models but doesn't verify cases
export const PERMISSIONS = {
  review: ["radiologist", "admin"],
  addStudies: ["radiologist", "admin"],
  viewModels: ["researcher", "admin"],
  // researcher proposes, admin decides
  proposeModels: ["researcher", "admin"],
  manageModels: ["admin"],
  administer: ["admin"],
} satisfies Record<string, Role[]>;

export type Permission = keyof typeof PERMISSIONS;

export interface User {
  login: string;
  name: string;
  role: Role;
}

export type SignInResult = { kind: "signed-in"; user: User } | { kind: "first-login"; login: string };

export class AuthError extends Error {}

function mockUser(login: string): User {
  const role: Role = login.startsWith("radiolog") ? "radiologist" : login.startsWith("badacz") ? "researcher" : "admin";
  return { login, name: "Użytkownik", role };
}

// with mocks, logins starting with "radiolog" / "badacz" get those roles;
// ?mock=first-login and ?mock=bad-login preview the other paths
export async function signIn(login: string, password: string): Promise<SignInResult> {
  if (MOCK_API) {
    const scenario = mockScenario();
    if (scenario === "bad-login") {
      await mockDelay(null, 300);
      throw new AuthError("bad credentials");
    }
    if (scenario === "first-login") return mockDelay({ kind: "first-login", login }, 300);
    return mockDelay({ kind: "signed-in", user: mockUser(login) }, 300);
  }
  try {
    const response = await api.post("/api/auth/signin/", { login, password });
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      throw new AuthError("bad credentials");
    }
    throw new AuthError("Wystąpił błąd logowania.");
  }
}

export async function setFirstPassword(login: string, temporary: string, password: string): Promise<User> {
  if (MOCK_API) {
    return mockDelay(mockUser(login), 300);
  }

  try {
    const response = await api.post("/api/auth/set-password/", { login, temporary, password });
    return response.data;
  } catch {
    throw new Error("Nie udało się ustawić nowego hasła.");
  }
}

export async function signOut(): Promise<void> {
  if (MOCK_API) {
    return mockDelay(undefined, 100);
  }
  await api.post("/api/auth/signout/");
}
