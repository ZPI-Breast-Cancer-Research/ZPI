import type { Role, User } from "../auth/api";
import { mockDelay } from "../mock";
import { t } from "../i18n";
import { record } from "./audit";

// set by the admin; the person only sees it
export interface Profile {
  name: string;
  login: string;
  email: string;
  role: Role;
  pwz: string | null;
}

// "temporary" until the person sets their own password at first login
export type UserState = "active" | "temporary" | "blocked";

export interface UserRow {
  id: string;
  name: string;
  login: string;
  email: string;
  role: Role;
  pwz: string | null;
  state: UserState;
  lastLogin: string | null;
}

export type UserDraft = Pick<UserRow, "name" | "login" | "email" | "role" | "pwz">;

// TODO: no profile endpoint in the backend yet
export async function fetchProfile(user: User): Promise<Profile> {
  return mockDelay({
    name: user.name,
    login: user.login,
    email: `${user.login}@szpital.pl`,
    role: user.role,
    pwz: user.role === "radiologist" ? "1234567" : null,
  });
}

let users: UserRow[] = [
  { id: "u1", name: "Radiolog 1", login: "radiolog1", email: "radiolog1@szpital.pl", role: "radiologist", pwz: "1234567", state: "active", lastLogin: "2026-10-26" },
  { id: "u2", name: "Badacz 1", login: "badacz1", email: "badacz1@szpital.pl", role: "researcher", pwz: null, state: "active", lastLogin: "2026-10-24" },
  { id: "u3", name: "Radiolog 2", login: "radiolog2", email: "radiolog2@szpital.pl", role: "radiologist", pwz: "7654321", state: "temporary", lastLogin: null },
  { id: "u4", name: "Radiolog 3", login: "radiolog3", email: "radiolog3@szpital.pl", role: "radiologist", pwz: "2345678", state: "blocked", lastLogin: "2026-08-12" },
  { id: "u5", name: "Administrator", login: "admin", email: "admin@szpital.pl", role: "admin", pwz: null, state: "active", lastLogin: "2026-11-05" },
];

// no 0/O or 1/l, it gets read out or copied by hand
const ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";

function temporaryPassword() {
  return Array.from(crypto.getRandomValues(new Uint32Array(14)), (n) => ALPHABET[n % ALPHABET.length]).join("");
}

function change(id: string, patch: Partial<UserRow>) {
  users = users.map((user) => (user.id === id ? { ...user, ...patch } : user));
}

// TODO: no users endpoints in the backend yet
export async function fetchUsers(): Promise<UserRow[]> {
  return mockDelay(users);
}

export async function createUser(draft: UserDraft): Promise<{ password: string }> {
  if (users.some((user) => user.login === draft.login)) throw new Error("login-taken");
  users = [...users, { ...draft, id: `u${Date.now()}`, state: "temporary", lastLogin: null }];
  record("account_created", draft.login, `${t("settings.role").toLowerCase()}: ${t(`role.${draft.role}`)}`);
  return mockDelay({ password: temporaryPassword() }, 300);
}

export async function updateUser(id: string, draft: Omit<UserDraft, "login">): Promise<void> {
  const before = users.find((u) => u.id === id)!;
  change(id, draft);
  const role = before.role !== draft.role ? `${t("settings.role").toLowerCase()}: ${t(`role.${before.role}`)} → ${t(`role.${draft.role}`)}` : null;
  record("account_changed", before.login, role);
  return mockDelay(undefined, 300);
}

export async function setBlocked(id: string, blocked: boolean): Promise<void> {
  const user = users.find((u) => u.id === id);
  change(id, { state: blocked ? "blocked" : user?.lastLogin ? "active" : "temporary" });
  record(blocked ? "account_blocked" : "account_unblocked", user?.login ?? id);
  return mockDelay(undefined, 300);
}

// the old password stops working at once; the person has to change the new one at first login
export async function resetPassword(id: string): Promise<{ password: string }> {
  change(id, { state: "temporary" });
  record("password_reset", users.find((u) => u.id === id)?.login ?? id);
  return mockDelay({ password: temporaryPassword() }, 300);
}

export async function changePassword(_current: string, _next: string): Promise<void> {
  return mockDelay(undefined, 300);
}
