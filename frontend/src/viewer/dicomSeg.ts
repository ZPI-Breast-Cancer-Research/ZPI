import { adaptersSEG } from "@cornerstonejs/adapters";
import { cache, metaData, utilities as csUtils, type Types } from "@cornerstonejs/core";

import { fetchInstance, seriesImageIds, type SegRef } from "./dicomweb";

interface ImagePlane {
  imagePositionPatient: Types.Point3;
  rowCosines: Types.Point3;
  columnCosines: Types.Point3;
  rowPixelSpacing: number;
  columnPixelSpacing: number;
  columns: number;
}

export interface LoadedSeg {
  voxels: number;
  // middle of the mask in world coordinates, to open the planes on it
  center: Types.Point3 | null;
}

/**
 * Paints a DICOM SEG into a labelmap volume.
 *
 * The adapter decodes the SEG into one 2D labelmap per image of the series it references (the `pre` phase),
 * while the viewer's labelmap lies over the series on screen. Every segmented pixel is therefore placed by its
 * position in the patient (ImagePositionPatient + orientation + spacing), not by SOP instance, so the mask
 * lands on the same tissue in any series of the same frame of reference.
 */
export async function paintSeg(labelmap: Types.IImageVolume, studyUid: string, seg: SegRef): Promise<LoadedSeg> {
  const [referencedImageIds, buffer] = await Promise.all([
    seriesImageIds(studyUid, seg.referencedSeriesUid),
    fetchInstance(studyUid, seg.seriesUid, seg.sopUid),
  ]);
  const { labelMapImages } = await adaptersSEG.Cornerstone3D.Segmentation.createFromDICOMSegBuffer(referencedImageIds, buffer, {
    metadataProvider: metaData,
  });

  const voxels = labelmap.voxelManager!;
  const [nx, ny, nz] = labelmap.dimensions;
  voxels.clear();
  let count = 0;
  const sum = [0, 0, 0];
  const world: Types.Point3 = [0, 0, 0];

  // one group per set of non-overlapping segments; every segment is painted as label 1
  for (const group of labelMapImages as Types.IImage[][]) {
    group.forEach((image, index) => {
      const pixels = image.voxelManager?.getScalarData() ?? image.getPixelData();
      const plane = metaData.get("imagePlaneModule", referencedImageIds[index]) as ImagePlane;
      const { imagePositionPatient: origin, rowCosines: row, columnCosines: column, rowPixelSpacing, columnPixelSpacing, columns } = plane;
      for (let p = 0; p < pixels.length; p++) {
        if (!pixels[p]) continue;
        const c = p % columns;
        const r = (p - c) / columns;
        for (let a = 0; a < 3; a++) world[a] = origin[a] + c * columnPixelSpacing * row[a] + r * rowPixelSpacing * column[a];
        const [i, j, k] = csUtils.transformWorldToIndex(labelmap.imageData!, world);
        if (i < 0 || j < 0 || k < 0 || i >= nx || j >= ny || k >= nz) continue;
        voxels.setAtIJK(i, j, k, 1);
        sum[0] += i;
        sum[1] += j;
        sum[2] += k;
        count++;
      }
    });
    // the decoded images were only a step on the way; the volume keeps the mask
    for (const image of group) cache.removeImageLoadObject(image.imageId, { force: true });
  }

  const center = count
    ? csUtils.transformIndexToWorld(labelmap.imageData!, sum.map((s) => s / count) as Types.Point3)
    : null;
  return { voxels: count, center };
}
