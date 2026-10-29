import { useCallback, useRef, useState } from "react";

import type { MaskState } from "./types";
import type { ViewerHandle } from "./Viewer";

export function useMaskEditor() {
  const viewer = useRef<ViewerHandle>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [edits, setEdits] = useState(0);
  const editsRef = useRef(0);
  editsRef.current = edits;

  // any brush/eraser stroke makes the mask "corrected", no separate confirm needed
  const state: MaskState = edits > 0 ? "corrected" : confirmed ? "confirmed" : "proposed";

  const addEdit = useCallback(() => setEdits((n) => n + 1), []);
  const undo = useCallback(() => {
    if (!editsRef.current) return;
    viewer.current?.undo();
    setEdits((n) => n - 1);
  }, []);
  const confirm = useCallback(() => setConfirmed(true), []);
  const restoreModel = useCallback(() => {
    viewer.current?.restoreModel();
    setEdits(0);
    setConfirmed(false);
  }, []);

  return { viewer, state, edits, addEdit, undo, confirm, restoreModel };
}

export type MaskEditor = ReturnType<typeof useMaskEditor>;
