import { mockDelay, mockScenario } from "../mock";

export type Role = "radiologist" | "researcher" | "admin";

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

// TODO: no auth endpoints yet (backend allows everything for now). Logins starting with
// "radiolog" / "badacz" get those roles; ?mock=first-login and ?mock=bad-login preview the other paths
export async function signIn(login: string, _password: string): Promise<SignInResult> {
  const scenario = mockScenario();
  if (scenario === "bad-login") {
    await mockDelay(null, 300);
    throw new AuthError("bad credentials");
  }
  if (scenario === "first-login") return mockDelay({ kind: "first-login", login }, 300);
  return mockDelay({ kind: "signed-in", user: mockUser(login) }, 300);
}

export async function setFirstPassword(login: string, _temporary: string, _password: string): Promise<User> {
  return mockDelay(mockUser(login), 300);
}

export async function signOut(): Promise<void> {
  return mockDelay(undefined, 100);
}
