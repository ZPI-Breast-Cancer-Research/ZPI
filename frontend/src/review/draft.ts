import { toIsoDate } from "../format";
import type { MaskPatch } from "../viewer/maskTools";
import type { FieldState } from "./BiradsForm";
import type { FieldKey } from "./fields";

// work on a case that is not approved yet, kept so leaving and coming back loses nothing
export interface Draft {
  // local date and time, YYYY-MM-DDTHH:MM
  savedAt: string;
  values: Partial<Record<FieldKey, string>>;
  states: Partial<Record<FieldKey, FieldState>>;
  mask: MaskPatch | null;
}

// TODO: in this browser only until the backend keeps drafts; then the same three calls go to the API
const DB = "maria";
const STORE = "drafts";

function open(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function run<T>(mode: IDBTransactionMode, action: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await open();
  return new Promise((resolve, reject) => {
    const request = action(db.transaction(STORE, mode).objectStore(STORE));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  }).finally(() => db.close()) as Promise<T>;
}

export async function loadDraft(studyId: string): Promise<Draft | null> {
  try {
    return (await run<Draft | undefined>("readonly", (store) => store.get(studyId))) ?? null;
  } catch {
    return null;
  }
}

export async function saveDraft(studyId: string, draft: Omit<Draft, "savedAt">): Promise<string | null> {
  const now = new Date();
  const savedAt = `${toIsoDate(now)}T${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
  try {
    await run("readwrite", (store) => store.put({ ...draft, savedAt }, studyId));
    return savedAt;
  } catch {
    // private windows can refuse storage; the review still works, just without a draft
    return null;
  }
}

export async function deleteDraft(studyId: string): Promise<void> {
  try {
    await run("readwrite", (store) => store.delete(studyId));
  } catch {
    // nothing to clean up
  }
}
