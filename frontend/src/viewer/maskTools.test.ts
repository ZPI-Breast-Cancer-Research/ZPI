import type { Types } from "@cornerstonejs/core";
import { describe, expect, it } from "vitest";

import { applyPatch, interpolateMask, maskExtent, maskLesions, maskPatch, restoreSlice } from "./maskTools";

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

describe("maskLesions", () => {
  it("gives every lesion its own box", () => {
    const { volume } = labelmap([30, 30, 4], [...square(1, 2, 4), ...square(2, 20, 24)]);
    expect(maskLesions(volume).map((lesion) => lesion.box)).toEqual([
      [
        [2, 2, 1],
        [4, 4, 1],
      ],
      [
        [20, 20, 2],
        [24, 24, 2],
      ],
    ]);
  });

  it("keeps a lesion whole across an undrawn slice", () => {
    const { volume } = labelmap([10, 10, 6], [...square(1, 2, 4), ...square(3, 2, 4)], [1, 1, 3]);
    expect(maskLesions(volume).map((lesion) => lesion.box)).toEqual([
      [
        [2, 2, 1],
        [4, 4, 3],
      ],
    ]);
  });

  it("has no boxes for an empty mask", () => {
    expect(maskLesions(labelmap([4, 4, 4]).volume)).toEqual([]);
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

    const redo = restoreSlice(edited.volume, model.data(), axial, axialSlice, 1)!;
    expect(maskExtent(edited.volume, axial, axialSlice, model.data()).edited).toEqual([3]);
    redo(true);
    expect(edited.data()).toEqual(before);
  });

  it("does nothing on a slice that matches the model's", () => {
    const model = labelmap([4, 4, 4], square(1, 1, 2), [1, 1, 2]);
    expect(restoreSlice(model.volume, model.data().slice(), axial, axialSlice, 1)).toBeNull();
  });
});

// a square of voxels anywhere on one axial slice
const patch = (k: number, x: number, y: number, r = 2): Point[] => {
  const out: Point[] = [];
  for (let i = x - r; i <= x + r; i++) for (let j = y - r; j <= y + r; j++) out.push([i, j, k]);
  return out;
};

// axial slices with mask on the left (x < 20) and on the right half of a 40-wide grid
function sides(dims: Point, data: ArrayLike<number>) {
  const [nx, ny, nz] = dims;
  const left: number[] = [];
  const right: number[] = [];
  for (let k = 0; k < nz; k++) {
    let [l, r] = [false, false];
    for (let j = 0; j < ny; j++)
      for (let i = 0; i < nx; i++) {
        if (!data[i + j * nx + k * nx * ny]) continue;
        if (i < 20) l = true;
        else r = true;
      }
    if (l) left.push(k);
    if (r) right.push(k);
  }
  return { left, right };
}

const grid: Point = [40, 20, 30];
const bySlice = (w: Types.Point3) => w[2];

describe("gaps and filling with more than one lesion", () => {
  it("sees no gap between two separate lesions and fills nothing between them", () => {
    const { volume } = labelmap(grid, [...patch(3, 8, 10), ...patch(25, 30, 10)]);
    expect(maskExtent(volume, axial, bySlice).gaps).toEqual([]);
    expect(interpolateMask(volume, axial)).toBeNull();
  });

  it("finds a lesion's gaps where another lesion fills the same slices", () => {
    const { volume } = labelmap(grid, [...[10, 11, 12, 13, 14].flatMap((k) => patch(k, 8, 10)), ...patch(10, 30, 10), ...patch(14, 30, 10)]);
    expect(maskExtent(volume, axial, bySlice).gaps).toEqual([11, 12, 13]);
    expect(sides(grid, interpolateMask(volume, axial)!)).toEqual({ left: [10, 11, 12, 13, 14], right: [10, 11, 12, 13, 14] });
  });

  it("does not stretch a lesion into another lesion's gap", () => {
    const { volume } = labelmap(grid, [...patch(10, 8, 10), ...patch(14, 8, 10), ...patch(10, 30, 10)]);
    expect(sides(grid, interpolateMask(volume, axial)!)).toEqual({ left: [10, 11, 12, 13, 14], right: [10] });
  });

  it("fills a lesion that drifts between the drawn slices", () => {
    const { volume } = labelmap(grid, [...patch(10, 5, 10, 1), ...patch(14, 14, 10, 1)]);
    const filled = labelmap(grid);
    filled.volume.voxelManager!.setCompleteScalarDataArray!(interpolateMask(volume, axial) as Uint8Array);
    expect(maskExtent(filled.volume, axial, bySlice)).toMatchObject({ slices: [10, 11, 12, 13, 14], gaps: [] });
  });

  it("joins a piece drawn a few slices away to the same lesion", () => {
    const { volume } = labelmap(grid, [...patch(10, 8, 10), ...patch(15, 8, 10)]);
    expect(maskExtent(volume, axial, bySlice).gaps).toEqual([11, 12, 13, 14]);
    expect(sides(grid, interpolateMask(volume, axial)!).left).toEqual([10, 11, 12, 13, 14, 15]);
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
