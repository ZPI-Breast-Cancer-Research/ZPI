import { useEffect, useState } from "react";

import { usePreferences, type Preferences } from "../settings/preferences";
import type { Plane } from "./types";

export interface Layout {
  main: Plane;
  single: boolean;
  // share of the width for the main view; none means the default split
  split?: number;
}

const KEY = "maria.viewer.layout";
const PLANES: Plane[] = ["axial", "sagittal", "coronal"];

// what was changed during this visit wins over the default from Ustawienia
function read(preferred: Preferences): Layout {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) ?? "{}");
    const split = typeof saved.split === "number" && saved.split >= 0.3 && saved.split <= 0.85 ? saved.split : undefined;
    return {
      main: PLANES.includes(saved.main) ? saved.main : preferred.main,
      single: typeof saved.single === "boolean" ? saved.single : preferred.single,
      split,
    };
  } catch {
    return { main: preferred.main, single: preferred.single };
  }
}

// a new default from Ustawienia applies to the next case opened
export function forgetViewerLayout() {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // nothing kept, nothing to forget
  }
}

// which plane is big and whether the other two show; kept by the page so its bar can switch it too
export function useViewerLayout() {
  const [preferred] = usePreferences();
  const [layout, setLayout] = useState(() => read(preferred));
  useEffect(() => {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(layout));
    } catch {
      // the layout just won't be remembered
    }
  }, [layout]);
  return [layout, setLayout] as const;
}
