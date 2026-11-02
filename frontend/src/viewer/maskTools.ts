import { utilities as csUtils, type Types } from "@cornerstonejs/core";

export interface Extent {
  // slices of the viewport that hold part of the mask
  slices: number[];
  first: number;
  last: number;
  // empty slices between the first and the last one
  gaps: number[];
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

// gaps are found in voxel space, then every voxel layer is turned into the viewport's slice number
export function maskExtent(labelmap: Types.IImageVolume, normal: Types.Point3, sliceOfWorld: (world: Types.Point3) => number): Extent | null {
  const data = labelmap.voxelManager!.getCompleteScalarDataArray!();
  const [nx, ny, nz] = labelmap.dimensions;
  const axis = axisAlong(labelmap, normal);
  const filled = new Uint8Array(labelmap.dimensions[axis]);
  const layer = nx * ny;
  for (let index = 0; index < data.length; index++) {
    if (!data[index]) continue;
    filled[axis === 2 ? Math.floor(index / layer) : axis === 1 ? Math.floor(index / nx) % ny : index % nx] = 1;
  }
  const layers = Array.from(filled.keys()).filter((a) => filled[a]);
  if (!layers.length) return null;

  const center = [(nx - 1) / 2, (ny - 1) / 2, (nz - 1) / 2];
  const toSlice = (a: number) => {
    const ijk = [...center] as Types.Point3;
    ijk[axis] = a;
    return sliceOfWorld(csUtils.transformIndexToWorld(labelmap.imageData!, ijk));
  };
  const slices = [...new Set(layers.map(toSlice))].sort((a, b) => a - b);
  const gaps: number[] = [];
  for (let a = layers[0]; a <= layers[layers.length - 1]; a++) if (!filled[a]) gaps.push(toSlice(a));
  return { slices, first: slices[0], last: slices[slices.length - 1], gaps: [...new Set(gaps)].sort((a, b) => a - b) };
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
// along the voxel axis of the given view; only the box around the mask is touched
export function interpolateMask(labelmap: Types.IImageVolume, normal: Types.Point3): ArrayLike<number> | null {
  const source = labelmap.voxelManager!.getCompleteScalarDataArray!();
  const dims = labelmap.dimensions;
  const axis = axisAlong(labelmap, normal);
  const [u, v] = [0, 1, 2].filter((a) => a !== axis);
  const stride = [1, dims[0], dims[0] * dims[1]];

  // the box around the mask in the two in-plane axes, with room for the blended outline to grow
  const min = [dims[0], dims[1], dims[2]];
  const max = [-1, -1, -1];
  for (let index = 0; index < source.length; index++) {
    if (!source[index]) continue;
    const ijk = [index % dims[0], Math.floor(index / dims[0]) % dims[1], Math.floor(index / stride[2])];
    for (let a = 0; a < 3; a++) {
      if (ijk[a] < min[a]) min[a] = ijk[a];
      if (ijk[a] > max[a]) max[a] = ijk[a];
    }
  }
  if (max[0] < 0) return null;
  const from = min.map((value) => Math.max(0, value - 3));
  const to = max.map((value, a) => Math.min(dims[a] - 1, value + 3));
  const w = to[u] - from[u] + 1;
  const h = to[v] - from[v] + 1;

  const slice = (s: number) => {
    const out = new Uint8Array(w * h);
    for (let y = 0; y < h; y++)
      for (let x = 0; x < w; x++) out[y * w + x] = source[(from[u] + x) * stride[u] + (from[v] + y) * stride[v] + s * stride[axis]] ? 1 : 0;
    return out;
  };
  const filled = (s: number) => slice(s).some(Boolean);

  const result = (source as Uint8Array).slice();
  let changed = false;
  let previous = -1;
  for (let s = min[axis]; s <= max[axis]; s++) {
    if (!filled(s)) continue;
    if (previous >= 0 && s - previous > 1) {
      const a = signedDistance(slice(previous), w, h);
      const b = signedDistance(slice(s), w, h);
      for (let gap = previous + 1; gap < s; gap++) {
        const t = (gap - previous) / (s - previous);
        for (let y = 0; y < h; y++)
          for (let x = 0; x < w; x++) {
            const i = y * w + x;
            if ((1 - t) * a[i] + t * b[i] > 0) continue;
            result[(from[u] + x) * stride[u] + (from[v] + y) * stride[v] + gap * stride[axis]] = 1;
            changed = true;
          }
      }
    }
    previous = s;
  }
  return changed ? result : null;
}
