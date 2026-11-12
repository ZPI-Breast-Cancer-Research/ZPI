import { mockDelay, MOCK_API } from "../mock";
import { api, handleApiError } from "../api";

export type AuditKind =
  | "mask_approved"
  | "mask_unapproved"
  | "form_approved"
  | "form_unapproved"
  | "model_proposed"
  | "proposal_withdrawn"
  | "model_promoted"
  | "model_rejected"
  | "model_rolled_back"
  | "training_started"
  | "training_stopped"
  | "account_created"
  | "account_changed"
  | "account_blocked"
  | "account_unblocked"
  | "password_reset"
  | "login_failed"
  | "study_imported"
  | "attach_report";

export type AuditGroup = "review" | "models" | "accounts" | "logins";

export const GROUP_OF: Record<AuditKind, AuditGroup> = {
  mask_approved: "review",
  mask_unapproved: "review",
  form_approved: "review",
  form_unapproved: "review",
  model_proposed: "models",
  proposal_withdrawn: "models",
  model_promoted: "models",
  model_rejected: "models",
  model_rolled_back: "models",
  training_started: "models",
  training_stopped: "models",
  account_created: "accounts",
  account_changed: "accounts",
  account_blocked: "accounts",
  account_unblocked: "accounts",
  password_reset: "accounts",
  login_failed: "logins",
  study_imported: "review",
  attach_report: "review",
};

export const TARGET_OF: Record<AuditGroup, "study" | "model" | "account"> = {
  review: "study",
  models: "model",
  accounts: "account",
  logins: "account",
};

// object is a study number, a model version or a login; never a patient's data (Q1)
export interface AuditEntry {
  id: string;
  at: string;
  login: string;
  name: string;
  kind: AuditKind;
  object: string;
  detail: string | null;
}

function ago(days: number, time: string) {
  const day = new Date(Date.now() - days * 86_400_000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}T${time}`;
}

const R1 = { login: "radiolog1", name: "Radiolog 1" };
const R2 = { login: "radiolog2", name: "Radiolog 2" };
const ADMIN = { login: "admin", name: "Administrator" };

let entries: AuditEntry[] = (
  [
    [0, "09:58", R1, "mask_approved", "#0003", "poprawiona, 4 warstwy"],
    [0, "09:51", R1, "form_approved", "#0003", "2 pola poprawione"],
    [0, "09:40", R1, "mask_approved", "#0007", "bez zmian"],
    [0, "08:12", { login: "radiolg1", name: "—" }, "login_failed", "radiolg1", "nieznany login"],
    [1, "16:20", ADMIN, "model_promoted", "v4", "Dice 0,81 → 0,83"],
    [1, "15:02", R2, "mask_unapproved", "#0012", null],
    [1, "14:47", R2, "mask_approved", "#0012", "poprawiona, 9 warstw"],
    [1, "14:30", R2, "form_approved", "#0012", "bez zmian"],
    [2, "11:05", ADMIN, "account_created", "radiolog2", "rola: radiolog"],
    [2, "11:06", ADMIN, "password_reset", "radiolog2", null],
    [3, "22:00", ADMIN, "training_started", "v4", "128 poprawek"],
    [4, "10:31", R1, "mask_approved", "#0001", "bez zmian"],
    [4, "10:29", R1, "form_unapproved", "#0001", null],
    [5, "13:14", ADMIN, "account_blocked", "radiolog3", null],
    [5, "13:10", { login: "radiolog3", name: "Radiolog 3" }, "login_failed", "radiolog3", "błędne hasło, 5. próba"],
    [6, "09:00", ADMIN, "account_changed", "badacz1", "rola: radiolog → badacz"],
    [8, "17:45", ADMIN, "model_rejected", "v3", "gorszy Dice na MAMA-MIA"],
    [9, "08:30", ADMIN, "model_rolled_back", "v2", "po zgłoszeniach radiologów"],
    [12, "12:00", ADMIN, "account_created", "badacz1", "rola: radiolog"],
  ] as const
).map(([days, time, who, kind, object, detail], i) => ({ id: `e${i}`, at: ago(days, time), ...who, kind, object, detail }));

// TODO: the backend writes the log and knows who did it from the session; here the browser fakes both
export function record(kind: AuditKind, object: string, detail: string | null = null) {
  let who = { login: "?", name: "?" };
  try {
    who = JSON.parse(sessionStorage.getItem("maria.user") ?? "") as typeof who;
  } catch {
    // still recorded, just without a name
  }
  const now = new Date();
  const at = ago(0, now.toTimeString().slice(0, 8));
  entries = [{ id: `e${now.getTime()}`, at, login: who.login, name: who.name, kind, object, detail }, ...entries];
}

export async function fetchAudit(): Promise<AuditEntry[]> {
  if (MOCK_API) {
    return mockDelay([...entries].sort((a, b) => b.at.localeCompare(a.at)));
  }

  try {
    const { data } = await api.get<AuditEntry[]>("/api/logs/");
    return data;
  } catch (error) {
    handleApiError(error);
  }
}