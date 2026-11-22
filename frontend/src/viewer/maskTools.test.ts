import type { Types } from "@cornerstonejs/core";
import { describe, expect, it } from "vitest";

import { applyPatch, interpolateMask, maskExtent, maskPatch, restoreSlice } from "./maskTools";

type Point = [number, number, number];

// a labelmap on a plain grid: voxel i, j, k sits at world (i, j, k) × spacing
function labelmap(dims: Point, filled: Point[] = [], spacing: Point = [1, 1, 1]) {
  let data: Uint8Array = new Uint8Array(dims[0] * dims[1] * dims[2]);
  for (const [i, j, k] of filled) data[i + j * dims[0] + k * dims[0] * dims[1]] = 1;
  const volume = {
    dimensions: dims,
    spacing,
    direction: [1, 0, 0, 0, 1, 0, 0, 0, 1],
    imageData: { indexToWorld: (ijk: number[]) => ijk.map((v, a) => v * spacing[a]) },
    voxelManager: {
      getCompleteScalarDataArray: () => data,
      setCompleteScalarDataArray: (next: Uint8Array) => (data = next),
    },
  };
  return { volume: volume as unknown as Types.IImageVolume, data: () => data };
}

// a square of voxels on one axial slice
const square = (k: number, from: number, to: number): Point[] => {
  const out: Point[] = [];
  for (let i = from; i <= to; i++) for (let j = from; j <= to; j++) out.push([i, j, k]);
  return out;
};

const axial: Types.Point3 = [0, 0, 1];
const axialSlice = (world: Types.Point3) => Math.round(world[2] / 2);

describe("maskExtent", () => {
  it("finds the slices with the mask, the empty ones between and its size in mm", () => {
    const { volume } = labelmap([10, 10, 8], [...square(2, 1, 4), ...square(5, 2, 3)], [0.5, 0.5, 2]);
    expect(maskExtent(volume, axial, axialSlice)).toEqual({ slices: [2, 5], gaps: [3, 4], edited: [], sizeMm: 2 });
  });

  it("names the slices where the mask differs from the model's", () => {
    const model = labelmap([6, 6, 4], square(1, 1, 2), [1, 1, 2]);
    const edited = labelmap([6, 6, 4], [...square(1, 1, 2), [4, 4, 3]], [1, 1, 2]);
    expect(maskExtent(edited.volume, axial, axialSlice, model.data()).edited).toEqual([3]);
  });

  it("has no size for an empty mask", () => {
    const { volume } = labelmap([4, 4, 4]);
    expect(maskExtent(volume, axial, axialSlice)).toMatchObject({ slices: [], gaps: [], sizeMm: null });
  });
});

describe("drafts of the mask", () => {
  it("keeps only the box around the changes and puts it back", () => {
    const model = labelmap([8, 8, 4], square(1, 2, 3));
    const edited = labelmap([8, 8, 4], [...square(1, 2, 3), [6, 6, 2], [5, 6, 2]]);
    const patch = maskPatch(edited.volume, model.data())!;
    expect(patch).toMatchObject({ dims: [8, 8, 4], from: [5, 6, 2], size: [2, 1, 1] });

    const restored = labelmap([8, 8, 4], square(1, 2, 3));
    expect(applyPatch(restored.volume, patch)).toBe(true);
    expect(restored.data()).toEqual(edited.data());
  });

  it("has nothing to keep for an untouched mask", () => {
    const model = labelmap([4, 4, 2], square(0, 1, 2));
    expect(maskPatch(model.volume, model.data().slice())).toBeNull();
  });

  it("refuses a draft from another grid", () => {
    const edited = labelmap([4, 4, 2], [[1, 1, 1]]);
    const patch = maskPatch(edited.volume, new Uint8Array(32))!;
    expect(applyPatch(labelmap([4, 4, 3]).volume, patch)).toBe(false);
  });
});

describe("restoreSlice", () => {
  it("puts the model's mask back on one slice and can undo it", () => {
    const model = labelmap([4, 4, 4], square(1, 1, 2), [1, 1, 2]);
    const edited = labelmap([4, 4, 4], [[0, 0, 1], [3, 3, 3]], [1, 1, 2]);
    const before = edited.data().slice();

    const redo = restoreSlice(edited.volume, model.data(), axialSlice, 1)!;
    expect(maskExtent(edited.volume, axial, axialSlice, model.data()).edited).toEqual([3]);
    redo(true);
    expect(edited.data()).toEqual(before);
  });

  it("does nothing on a slice that matches the model's", () => {
    const model = labelmap([4, 4, 4], square(1, 1, 2), [1, 1, 2]);
    expect(restoreSlice(model.volume, model.data().slice(), axialSlice, 1)).toBeNull();
  });
});

describe("interpolateMask", () => {
  it("fills the empty slices between two drawn ones", () => {
    const { volume } = labelmap([12, 12, 5], [...square(0, 3, 7), ...square(4, 3, 7)]);
    const filled = labelmap([12, 12, 5]);
    filled.volume.voxelManager!.setCompleteScalarDataArray!(interpolateMask(volume, axial) as Uint8Array);
    expect(maskExtent(filled.volume, axial, (w) => w[2])).toMatchObject({ slices: [0, 1, 2, 3, 4], gaps: [] });
  });

  it("has nothing to fill without a gap", () => {
    const { volume } = labelmap([8, 8, 3], [...square(0, 2, 4), ...square(1, 2, 4)]);
    expect(interpolateMask(volume, axial)).toBeNull();
  });
});
