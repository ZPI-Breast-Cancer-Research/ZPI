import type { Role, User } from "../auth/api";
import { mockDelay } from "../mock";

// set by the admin; the person only sees it
export interface Profile {
  name: string;
  login: string;
  email: string;
  role: Role;
  pwz: string | null;
}

export interface UserRow {
  id: string;
  name: string;
  login: string;
  role: Role;
  state: "active" | "invited" | "blocked";
  lastLogin: string | null;
}

// TODO: no profile/users endpoints in the backend yet
export async function fetchProfile(user: User): Promise<Profile> {
  return mockDelay({
    name: user.name,
    login: user.login,
    email: `${user.login}@szpital.pl`,
    role: user.role,
    pwz: user.role === "radiologist" ? "1234567" : null,
  });
}

export async function fetchUsers(): Promise<UserRow[]> {
  return mockDelay([
    { id: "u1", name: "Radiolog 1", login: "radiolog1", role: "radiologist", state: "active", lastLogin: "2026-10-26" },
    { id: "u2", name: "Badacz 1", login: "badacz1", role: "researcher", state: "active", lastLogin: "2026-10-24" },
    { id: "u3", name: "Radiolog 2", login: "radiolog2", role: "radiologist", state: "invited", lastLogin: null },
    { id: "u4", name: "Administrator", login: "admin", role: "admin", state: "blocked", lastLogin: "2026-09-30" },
  ]);
}

export async function changePassword(_current: string, _next: string): Promise<void> {
  return mockDelay(undefined, 300);
}
