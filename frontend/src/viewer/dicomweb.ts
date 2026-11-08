import { wadors } from "@cornerstonejs/dicom-image-loader";

import type { Series } from "./types";

// Orthanc's DICOMweb goes through the gateway (infra/gateway), same origin as the app
const BASE = new URL(import.meta.env.VITE_DICOMWEB_URL ?? "/dicom-web", window.location.origin).href.replace(/\/$/, "");

type DicomJson = Record<string, { Value?: unknown[] }>;

const tag = (item: DicomJson, key: string) => item[key]?.Value?.[0] as string | number | undefined;

export class DicomWebError extends Error {
  constructor(readonly kind: "unavailable" | "not-found" | "no-series" | "single-image") {
    super(kind);
  }
}

async function get(path: string): Promise<DicomJson[]> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { headers: { Accept: "application/dicom+json" } });
  } catch {
    throw new DicomWebError("unavailable");
  }
  if (response.status === 404 || response.status === 204) throw new DicomWebError("not-found");
  if (!response.ok) throw new DicomWebError("unavailable");
  return response.json();
}

interface SeriesInfo {
  uid: string;
  description: string;
}

// TODO: guessed from SeriesDescription; the backend should say which series is which once ingest tags them
function kindOf(description: string): Series | null {
  const d = description.toLowerCase();
  if (/sub|0000/.test(d)) return "sub";
  if (/\bpre\b|pre[-_ ]|przed|native|bez kontr|0001/.test(d)) return "pre";
  if (/post|1st|ph1|dyn|\+c|kontr|contrast|0002/.test(d)) return "post";
  return null;
}

export async function findSeries(studyUid: string): Promise<Partial<Record<Series, string>>> {
  const list: SeriesInfo[] = (await get(`/studies/${studyUid}/series`))
    .filter((s) => tag(s, "00080060") === "MR")
    .map((s) => ({ uid: String(tag(s, "0020000E")), description: String(tag(s, "0008103E") ?? "") }));
  if (!list.length) throw new DicomWebError("no-series");

  const found: Partial<Record<Series, string>> = {};
  for (const s of list) {
    const kind = kindOf(s.description);
    if (kind && !found[kind]) found[kind] = s.uid;
  }
  // nothing recognisable: show the first series as the main one
  found.post ??= list.find((s) => !Object.values(found).includes(s.uid))?.uid ?? list[0].uid;
  return found;
}

const imageIdCache = new Map<string, Promise<string[]>>();

// registers the series metadata with the loader and returns one imageId per frame
export function seriesImageIds(studyUid: string, seriesUid: string): Promise<string[]> {
  const key = `${studyUid}/${seriesUid}`;
  if (!imageIdCache.has(key)) {
    const promise = get(`/studies/${studyUid}/series/${seriesUid}/metadata`).then((instances) =>
      instances.flatMap((instance) => {
        const sop = tag(instance, "00080018");
        const frames = Number(tag(instance, "00280008") ?? 1);
        return Array.from({ length: frames }, (_, i) => {
          const imageId = `wadors:${BASE}/studies/${studyUid}/series/${seriesUid}/instances/${sop}/frames/${i + 1}`;
          wadors.metaDataManager.add(imageId, instance as never);
          return imageId;
        });
      }),
    );
    promise.catch(() => imageIdCache.delete(key));
    imageIdCache.set(key, promise);
  }
  return imageIdCache.get(key)!;
}
