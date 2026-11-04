import { useCallback, useRef, useState } from "react";

import type { MaskState } from "./types";
import type { ViewerHandle } from "./Viewer";

export function useMaskEditor() {
  const viewer = useRef<ViewerHandle>(null);
  const [edits, setEdits] = useState(0);
  const editsRef = useRef(0);
  editsRef.current = edits;

  // any change makes the mask "corrected"; approving the case accepts an untouched one as it is
  const state: MaskState = edits > 0 ? "corrected" : "proposed";

  const addEdit = useCallback(() => setEdits((n) => n + 1), []);
  const undo = useCallback(() => {
    if (!editsRef.current) return;
    viewer.current?.undo();
    setEdits((n) => n - 1);
  }, []);
  const restoreModel = useCallback(() => {
    viewer.current?.restoreModel();
    setEdits(0);
  }, []);

  return { viewer, state, edits, addEdit, undo, restoreModel };
}

export type MaskEditor = ReturnType<typeof useMaskEditor>;
