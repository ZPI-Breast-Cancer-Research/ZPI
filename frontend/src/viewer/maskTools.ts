import { utilities as csUtils, type Types } from "@cornerstonejs/core";

export interface Extent {
  // slices of the viewport that hold part of the mask
  slices: number[];
  // empty slices inside a lesion, between its first and last slice
  gaps: number[];
  // slices where the mask differs from the model's
  edited: number[];
  // the longest side of the mask's box in the view plane, a stand-in for the largest diameter
  sizeMm: number | null;
}

// the voxel axis that runs along the view normal; direction holds the i, j and k axes as rows of three
function axisAlong(volume: Types.IImageVolume, normal: Types.Point3) {
  let axis = 0;
  let best = -1;
  for (let a = 0; a < 3; a++) {
    const dot = Math.abs(volume.direction[a * 3] * normal[0] + volume.direction[a * 3 + 1] * normal[1] + volume.direction[a * 3 + 2] * normal[2]);
    if (dot > best) [axis, best] = [a, dot];
  }
  return axis;
}

// the view's slice number of every voxel layer along the axis, asked once per layer;
// the views are snapped to the study's grid, so a whole layer is one slice
function layerSlices(labelmap: Types.IImageVolume, axis: number, sliceOfWorld: (world: Types.Point3) => number) {
  const known = new Int32Array(labelmap.dimensions[axis]).fill(-1);
  const center = labelmap.dimensions.map((n) => (n - 1) / 2) as Types.Point3;
  return (layer: number) => {
    if (known[layer] < 0) {
      const ijk = [...center] as Types.Point3;
      ijk[axis] = layer;
      known[layer] = sliceOfWorld(csUtils.transformIndexToWorld(labelmap.imageData!, ijk));
    }
    return known[layer];
  };
}

// the voxel's index along one axis
function coordOf(index: number, axis: number, nx: number, ny: number) {
  return axis === 0 ? index % nx : axis === 1 ? Math.floor(index / nx) % ny : Math.floor(index / (nx * ny));
}

// read from the lesions' own voxels, so only the comparison with the model's mask goes over the whole volume
export function maskExtent(
  labelmap: Types.IImageVolume,
  normal: Types.Point3,
  sliceOfWorld: (world: Types.Point3) => number,
  original?: ArrayLike<number> | null,
  lesions: Lesion[] = maskLesions(labelmap),
): Extent {
  const [nx, ny, nz] = labelmap.dimensions;
  const axis = axisAlong(labelmap, normal);
  const toSlice = layerSlices(labelmap, axis, sliceOfWorld);
  const depth = labelmap.dimensions[axis];
  const filled = new Uint8Array(depth);
  const min = [nx, ny, nz];
  const max = [-1, -1, -1];
  // the space between two lesions is not a gap, and one lesion's gap stays a gap where another lesion lies
  const gaps = new Set<number>();
  for (const { voxels } of lesions) {
    const own = new Uint8Array(depth);
    for (const index of voxels) {
      const ijk = ijkOf(index, nx, ny);
      own[ijk[axis]] = 1;
      filled[ijk[axis]] = 1;
      for (let a = 0; a < 3; a++) {
        if (ijk[a] < min[a]) min[a] = ijk[a];
        if (ijk[a] > max[a]) max[a] = ijk[a];
      }
    }
    for (let a = own.indexOf(1); a <= own.lastIndexOf(1); a++) if (!own[a]) gaps.add(a);
  }

  const changed = new Uint8Array(depth);
  if (original) {
    const data = labelmap.voxelManager!.getCompleteScalarDataArray!();
    for (let index = 0; index < data.length; index++) if (data[index] !== original[index]) changed[coordOf(index, axis, nx, ny)] = 1;
  }

  const sorted = (layers: Iterable<number>) => [...new Set([...layers].map(toSlice))].sort((a, b) => a - b);
  const marked = (flags: Uint8Array) => Array.from(flags.keys()).filter((a) => flags[a]);
  const inPlane = [0, 1, 2].filter((a) => a !== axis);
  const layers = marked(filled);
  return {
    slices: sorted(layers),
    gaps: sorted(gaps),
    edited: sorted(marked(changed)),
    sizeMm: layers.length ? Math.max(...inPlane.map((a) => (max[a] - min[a] + 1) * labelmap.spacing[a])) : null,
  };
}

// first and last voxel index on each axis
export type Box = [Types.Point3, Types.Point3];

// a lesion's box and its own voxels, as indices into the labelmap
export interface Lesion {
  box: Box;
  voxels: number[];
}

function ijkOf(index: number, nx: number, ny: number): Types.Point3 {
  return [index % nx, Math.floor(index / nx) % ny, Math.floor(index / (nx * ny))];
}

// pieces of the mask that touch, or lie closer than mergeMm (a gap between drawn slices), are one lesion
export function maskLesions(labelmap: Types.IImageVolume, mergeMm = 10): Lesion[] {
  const data = labelmap.voxelManager!.getCompleteScalarDataArray!();
  const [nx, ny, nz] = labelmap.dimensions;
  const layer = nx * ny;
  const left = new Set<number>();
  for (let index = 0; index < data.length; index++) if (data[index]) left.add(index);

  const lesions: Lesion[] = [];
  for (const start of left) {
    left.delete(start);
    const min: Types.Point3 = [nx, ny, nz];
    const max: Types.Point3 = [-1, -1, -1];
    const voxels: number[] = [];
    const stack = [start];
    while (stack.length) {
      const index = stack.pop()!;
      voxels.push(index);
      const ijk = ijkOf(index, nx, ny);
      for (let a = 0; a < 3; a++) {
        min[a] = Math.min(min[a], ijk[a]);
        max[a] = Math.max(max[a], ijk[a]);
      }
      for (let dk = -1; dk <= 1; dk++)
        for (let dj = -1; dj <= 1; dj++)
          for (let di = -1; di <= 1; di++) {
            const [i, j, k] = [ijk[0] + di, ijk[1] + dj, ijk[2] + dk];
            if (i < 0 || j < 0 || k < 0 || i >= nx || j >= ny || k >= nz) continue;
            const next = i + j * nx + k * layer;
            if (left.delete(next)) stack.push(next);
          }
    }
    lesions.push({ box: [min, max], voxels });
  }

  const gapMm = ([aMin, aMax]: Box, [bMin, bMax]: Box) =>
    Math.hypot(...[0, 1, 2].map((a) => Math.max(0, Math.max(aMin[a], bMin[a]) - Math.min(aMax[a], bMax[a]) - 1) * labelmap.spacing[a]));
  for (let merged = true; merged; ) {
    merged = false;
    for (let a = 0; a < lesions.length && !merged; a++)
      for (let b = a + 1; b < lesions.length && !merged; b++) {
        if (gapMm(lesions[a].box, lesions[b].box) > mergeMm) continue;
        const other = lesions.splice(b, 1)[0];
        const [min, max] = lesions[a].box;
        lesions[a] = {
          box: [min.map((v, i) => Math.min(v, other.box[0][i])) as Types.Point3, max.map((v, i) => Math.max(v, other.box[1][i])) as Types.Point3],
          voxels: lesions[a].voxels.concat(other.voxels),
        };
        merged = true;
      }
  }
  return lesions;
}

// puts the model's mask back on one slice of the view; returns a redo/undo, or null when that slice was untouched
export function restoreSlice(
  labelmap: Types.IImageVolume,
  original: ArrayLike<number>,
  normal: Types.Point3,
  sliceOfWorld: (world: Types.Point3) => number,
  slice: number,
) {
  const voxels = labelmap.voxelManager!;
  const data = voxels.getCompleteScalarDataArray!() as Uint8Array;
  const [nx, ny] = labelmap.dimensions;
  const axis = axisAlong(labelmap, normal);
  const toSlice = layerSlices(labelmap, axis, sliceOfWorld);
  const indices: number[] = [];
  for (let index = 0; index < data.length; index++) {
    if (data[index] !== original[index] && toSlice(coordOf(index, axis, nx, ny)) === slice) indices.push(index);
  }
  if (!indices.length) return null;
  const before = Uint8Array.from(indices, (i) => data[i]);
  const write = (undo: boolean) => {
    const next = (voxels.getCompleteScalarDataArray!() as Uint8Array).slice();
    indices.forEach((i, n) => (next[i] = undo ? before[n] : original[i]));
    voxels.setCompleteScalarDataArray!(next);
  };
  write(false);
  return write;
}

// the box around everything that differs from the model's mask, small enough to keep as a draft
export interface MaskPatch {
  dims: [number, number, number];
  from: [number, number, number];
  size: [number, number, number];
  data: Uint8Array;
}

export function maskPatch(labelmap: Types.IImageVolume, original: ArrayLike<number>): MaskPatch | null {
  const data = labelmap.voxelManager!.getCompleteScalarDataArray!();
  const [nx, ny, nz] = labelmap.dimensions;
  const min = [nx, ny, nz];
  const max = [-1, -1, -1];
  for (let index = 0; index < data.length; index++) {
    if (data[index] === original[index]) continue;
    const ijk = [index % nx, Math.floor(index / nx) % ny, Math.floor(index / (nx * ny))];
    for (let a = 0; a < 3; a++) {
      if (ijk[a] < min[a]) min[a] = ijk[a];
      if (ijk[a] > max[a]) max[a] = ijk[a];
    }
  }
  if (max[0] < 0) return null;
  const size = [0, 1, 2].map((a) => max[a] - min[a] + 1) as [number, number, number];
  const box = new Uint8Array(size[0] * size[1] * size[2]);
  let n = 0;
  for (let k = 0; k < size[2]; k++)
    for (let j = 0; j < size[1]; j++)
      for (let i = 0; i < size[0]; i++) box[n++] = data[min[0] + i + (min[1] + j) * nx + (min[2] + k) * nx * ny];
  return { dims: [nx, ny, nz], from: min as [number, number, number], size, data: box };
}

// writes a saved box back; false when the study's grid changed since it was saved
export function applyPatch(labelmap: Types.IImageVolume, patch: MaskPatch): boolean {
  const [nx, ny, nz] = labelmap.dimensions;
  if (patch.dims[0] !== nx || patch.dims[1] !== ny || patch.dims[2] !== nz) return false;
  const voxels = labelmap.voxelManager!;
  const next = (voxels.getCompleteScalarDataArray!() as Uint8Array).slice();
  const { from, size, data } = patch;
  let n = 0;
  for (let k = 0; k < size[2]; k++)
    for (let j = 0; j < size[1]; j++)
      for (let i = 0; i < size[0]; i++) next[from[0] + i + (from[1] + j) * nx + (from[2] + k) * nx * ny] = data[n++];
  voxels.setCompleteScalarDataArray!(next);
  return true;
}

// distance from every pixel of a 2D mask to its edge: negative inside, positive outside (chamfer 3-4, in pixels)
function signedDistance(mask: Uint8Array, w: number, h: number) {
  const far = 1e6;
  const pass = (inside: boolean) => {
    const d = new Float32Array(w * h);
    for (let i = 0; i < d.length; i++) d[i] = !!mask[i] === inside ? far : 0;
    const relax = (x: number, y: number, dx: number, dy: number, cost: number) => {
      const nx = x + dx;
      const ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= w || ny >= h) return;
      const v = d[ny * w + nx] + cost;
      if (v < d[y * w + x]) d[y * w + x] = v;
    };
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) {
        relax(x, y, -1, 0, 3);
        relax(x, y, 0, -1, 3);
        relax(x, y, -1, -1, 4);
        relax(x, y, 1, -1, 4);
      }
    for (let y = h - 1; y >= 0; y--)
      for (let x = w - 1; x >= 0; x--) {
        relax(x, y, 1, 0, 3);
        relax(x, y, 0, 1, 3);
        relax(x, y, 1, 1, 4);
        relax(x, y, -1, 1, 4);
      }
    return d;
  };
  const outside = pass(false);
  const inside = pass(true);
  return outside.map((v, i) => (mask[i] ? -inside[i] : v) / 3);
}

// fills empty slices between two drawn ones by blending their outlines (shape-based interpolation),
// along the voxel axis of the given view; every lesion on its own, from its own voxels only
export function interpolateMask(labelmap: Types.IImageVolume, normal: Types.Point3, lesions: Lesion[] = maskLesions(labelmap)): ArrayLike<number> | null {
  const source = labelmap.voxelManager!.getCompleteScalarDataArray!();
  const dims = labelmap.dimensions;
  const axis = axisAlong(labelmap, normal);
  const [u, v] = [0, 1, 2].filter((a) => a !== axis);
  const stride = [1, dims[0], dims[0] * dims[1]];
  const result = (source as Uint8Array).slice();
  let changed = false;

  for (const { box, voxels } of lesions) {
    // the lesion's box, with room in the plane for the blended outline to grow
    const from = box[0].map((value, a) => (a === axis ? value : Math.max(0, value - 3)));
    const to = box[1].map((value, a) => (a === axis ? value : Math.min(dims[a] - 1, value + 3)));
    const w = to[u] - from[u] + 1;
    const h = to[v] - from[v] + 1;
    const own = new Uint8Array(w * h * (to[axis] - from[axis] + 1));
    for (const index of voxels) {
      const ijk = ijkOf(index, dims[0], dims[1]);
      own[ijk[u] - from[u] + (ijk[v] - from[v]) * w + (ijk[axis] - from[axis]) * w * h] = 1;
    }
    const slice = (s: number) => own.subarray(s * w * h, (s + 1) * w * h);

    const blend = (first: number, last: number) => {
      const a = signedDistance(slice(first), w, h);
      const b = signedDistance(slice(last), w, h);
      // a lesion can drift between slices, so both outlines are moved towards each other before blending
      const [ca, cb] = [centroid(slice(first), w), centroid(slice(last), w)];
      const shift = [cb[0] - ca[0], cb[1] - ca[1]];
      const at = (sdf: Float32Array, x: number, y: number) => (x < 0 || y < 0 || x >= w || y >= h ? Infinity : sdf[y * w + x]);
      for (let gap = first + 1; gap < last; gap++) {
        const t = (gap - first) / (last - first);
        const [ax, ay] = [Math.round(t * shift[0]), Math.round(t * shift[1])];
        const [bx, by] = [Math.round((1 - t) * shift[0]), Math.round((1 - t) * shift[1])];
        for (let y = 0; y < h; y++)
          for (let x = 0; x < w; x++) {
            if ((1 - t) * at(a, x - ax, y - ay) + t * at(b, x + bx, y + by) > 0) continue;
            const index = (from[u] + x) * stride[u] + (from[v] + y) * stride[v] + (from[axis] + gap) * stride[axis];
            if (result[index]) continue;
            result[index] = 1;
            changed = true;
          }
      }
    };

    let previous = -1;
    for (let s = 0; s <= to[axis] - from[axis]; s++) {
      if (!slice(s).some(Boolean)) continue;
      if (previous >= 0 && s - previous > 1) blend(previous, s);
      previous = s;
    }
  }
  return changed ? result : null;
}

function centroid(mask: Uint8Array, w: number) {
  let [x, y, n] = [0, 0, 0];
  for (let i = 0; i < mask.length; i++) {
    if (!mask[i]) continue;
    x += i % w;
    y += Math.floor(i / w);
    n++;
  }
  return [x / n, y / n];
}
