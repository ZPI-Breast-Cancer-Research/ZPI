import { useCallback, useState } from "react";

import type { MaskState, Stroke } from "./types";

export function useMaskEditor() {
  const [confirmed, setConfirmed] = useState(false);
  const [strokes, setStrokes] = useState<Stroke[]>([]);

  // any brush/eraser stroke makes the mask "corrected", no separate confirm needed
  const state: MaskState = strokes.length > 0 ? "corrected" : confirmed ? "confirmed" : "proposed";

  const addStroke = useCallback((stroke: Stroke) => setStrokes((current) => [...current, stroke]), []);
  const undo = useCallback(() => setStrokes((current) => current.slice(0, -1)), []);
  const confirm = useCallback(() => setConfirmed(true), []);
  const reset = useCallback(() => {
    setStrokes([]);
    setConfirmed(false);
  }, []);

  return { state, strokes, addStroke, undo, confirm, restoreModel: reset, reset };
}

export type MaskEditor = ReturnType<typeof useMaskEditor>;
