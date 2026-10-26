import { mockDelay } from "../mock";

export type Role = "radiologist" | "researcher" | "admin";
export type Series = "post" | "sub" | "pre";

export interface Profile {
  name: string;
  email: string;
  role: Role;
  pwz: string;
  language: "pl" | "en";
  defaultSeries: Series;
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
export async function fetchProfile(): Promise<Profile> {
  return mockDelay({ name: "", email: "", role: "admin", pwz: "", language: "pl", defaultSeries: "post" });
}

export async function fetchUsers(): Promise<UserRow[]> {
  return mockDelay([
    { id: "u1", name: "Radiolog 1", login: "radiolog1", role: "radiologist", state: "active", lastLogin: "2026-10-26" },
    { id: "u2", name: "Badacz 1", login: "badacz1", role: "researcher", state: "active", lastLogin: "2026-10-24" },
    { id: "u3", name: "Radiolog 2", login: "radiolog2", role: "radiologist", state: "invited", lastLogin: null },
    { id: "u4", name: "Administrator", login: "admin", role: "admin", state: "blocked", lastLogin: "2026-09-30" },
  ]);
}

export async function saveProfile(profile: Profile): Promise<Profile> {
  return mockDelay(profile, 300);
}

export async function changePassword(_current: string, _next: string): Promise<void> {
  return mockDelay(undefined, 300);
}
