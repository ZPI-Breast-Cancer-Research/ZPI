import { useEffect, useState } from "react";

import type { Plane } from "./types";

export interface Layout {
  main: Plane;
  single: boolean;
  // share of the width for the main view; none means the default split
  split?: number;
}

const KEY = "maria.viewer.layout";
const PLANES: Plane[] = ["axial", "sagittal", "coronal"];

function read(): Layout {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) ?? "{}");
    const split = typeof saved.split === "number" && saved.split >= 0.3 && saved.split <= 0.85 ? saved.split : undefined;
    return { main: PLANES.includes(saved.main) ? saved.main : "axial", single: saved.single === true, split };
  } catch {
    return { main: "axial", single: false };
  }
}

// which plane is big and whether the other two show; kept by the page so its bar can switch it too
export function useViewerLayout() {
  const [layout, setLayout] = useState(read);
  useEffect(() => {
    try {
      sessionStorage.setItem(KEY, JSON.stringify(layout));
    } catch {
      // the layout just won't be remembered
    }
  }, [layout]);
  return [layout, setLayout] as const;
}
