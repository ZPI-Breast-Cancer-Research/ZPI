export type MaskState = "proposed" | "confirmed" | "corrected";
export type Tool = "brush" | "threshold" | "eraser" | "pan" | "window";
// a circle paints the slice on screen, a sphere also the slices around it
export type BrushShape = "circle" | "sphere";
export type Series = "post" | "sub" | "pre";
export type Plane = "axial" | "sagittal" | "coronal";

// a DICOM SEG in Orthanc, read over DICOMweb (ADR 0003)
export interface SegRef {
  studyUid: string;
  seriesUid: string;
  sopUid: string;
}
