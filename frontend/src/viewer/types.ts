export type MaskState = "proposed" | "confirmed" | "corrected";
export type Tool = "brush" | "eraser" | "pan" | "window";
export type Series = "post" | "sub" | "pre";

// TODO: stand-in for the model's labelmap until the segmentation API serves real masks (NIfTI / DICOM SEG).
// center is a fraction of the volume (i, j, k), radius in mm
export interface MaskSource {
  center: [number, number, number];
  radius: [number, number, number];
}
