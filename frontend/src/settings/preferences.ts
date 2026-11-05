import { useCallback, useSyncExternalStore } from "react";

import { useAuth } from "../auth/AuthProvider";
import type { Plane, Series } from "../viewer/types";

export interface Preferences {
  series: Series;
  main: Plane;
  single: boolean;
  maskShown: boolean;
  hints: boolean;
}

const DEFAULTS: Preferences = { series: "post", main: "axial", single: false, maskShown: true, hints: true };

// TODO: kept in the browser per login until the backend stores them with the profile;
// workstations in a hospital are shared, so they follow the person, not the machine
const KEY = "maria.preferences";
type Store = Record<string, Partial<Preferences>>;

function load(): Store {
  try {
    return JSON.parse(localStorage.getItem(KEY) ?? "{}") as Store;
  } catch {
    return {};
  }
}

let store = load();
const listeners = new Set<() => void>();

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function usePreferences() {
  const login = useAuth().user?.login ?? "";
  const all = useSyncExternalStore(subscribe, () => store);
  const preferences: Preferences = { ...DEFAULTS, ...all[login] };

  const update = useCallback(
    (change: Partial<Preferences>) => {
      store = { ...store, [login]: { ...store[login], ...change } };
      try {
        localStorage.setItem(KEY, JSON.stringify(store));
      } catch {
        // still applies for this visit
      }
      listeners.forEach((listener) => listener());
    },
    [login],
  );

  return [preferences, update] as const;
}
