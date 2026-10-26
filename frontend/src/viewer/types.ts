export type MaskState = "proposed" | "confirmed" | "corrected";
export type Tool = "brush" | "eraser" | "pan" | "window";
export type Series = "post" | "sub" | "pre";

export interface Stroke {
  slice: number;
  erase: boolean;
  points: [number, number][];
}

export interface Lesion {
  x: number;
  y: number;
  slices: [number, number];
}
