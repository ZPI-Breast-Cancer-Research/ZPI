export type MaskState = "proposed" | "confirmed" | "corrected";
export type Tool = "brush" | "threshold" | "eraser" | "pan" | "window";
// a circle paints the slice on screen, a sphere also the slices around it
export type BrushShape = "circle" | "sphere";
export type Series = "post" | "sub" | "pre";
export type Plane = "axial" | "sagittal" | "coronal";

// TODO: stand-in for the model's labelmap until the segmentation API serves real masks (NIfTI / DICOM SEG).
// center is a fraction of the volume (i, j, k), radius in mm
export interface MaskSource {
  center: [number, number, number];
  radius: [number, number, number];
}
