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
  if (/post|1st|\bph[1-9]|\+c|kontr|contrast|0002/.test(d)) return "post";
  // a dynamic series with no phase number or contrast mark is the one before contrast (Duke: "ax 3d dyn")
  if (/dyn/.test(d)) return "pre";
  return null;
}

export async function findSeries(studyUid: string): Promise<Partial<Record<Series, string>>> {
  const list: SeriesInfo[] = (await get(`/studies/${studyUid}/series`))
    .filter((s) => tag(s, "00080060") === "MR")
    .map((s) => ({ uid: String(tag(s, "0020000E")), description: String(tag(s, "0008103E") ?? "") }))
    // the first match of a kind wins, so Ph1 comes before Ph2
    .sort((a, b) => a.description.localeCompare(b.description));
  if (!list.length) throw new DicomWebError("no-series");

  const found: Partial<Record<Series, string>> = {};
  // one series holding the whole dynamic acquisition (ISPY1, GE): its phases are pre, post, ...
  const phaseCounts = await Promise.all(list.map(async (s) => splitPhases(await seriesMetadata(studyUid, s.uid)).length));
  const dynamic = list.find((_, i) => phaseCounts[i] >= 2);
  if (dynamic) {
    found.pre = phaseKey(dynamic.uid, 0);
    found.post = phaseKey(dynamic.uid, 1);
  }
  for (const s of list) {
    if (s === dynamic) continue;
    const kind = kindOf(s.description);
    if (kind && !found[kind]) found[kind] = s.uid;
  }
  // nothing recognisable: show the first series as the main one
  found.post ??= list.find((s) => !Object.values(found).includes(s.uid))?.uid ?? list[0].uid;
  return found;
}

// MR studies in Orthanc, most series first
export async function listMrStudies(): Promise<string[]> {
  const studies = await get("/studies?ModalitiesInStudy=MR&includefield=00201206");
  return studies
    .map((s) => ({ uid: String(tag(s, "0020000D") ?? ""), series: Number(tag(s, "00201206") ?? 0) }))
    .filter((s) => s.uid)
    .sort((a, b) => b.series - a.series)
    .map((s) => s.uid);
}

// the series a SEG was drawn on; its frames are matched to that series' images
export async function referencedSeries(studyUid: string, seriesUid: string): Promise<string> {  const [instance] = await get(`/studies/${studyUid}/series/${seriesUid}/metadata`);
  const referenced = instance?.["00081115"]?.Value?.[0] as DicomJson | undefined;
  const uid = referenced && tag(referenced, "0020000E");
  if (!uid) throw new DicomWebError("not-found");
  return String(uid);
}

// WADO-RS answers with multipart/related even for one instance; this returns the DICOM part of it
export async function fetchInstance(studyUid: string, seriesUid: string, sopUid: string): Promise<ArrayBuffer> {
  let response: Response;
  try {
    response = await fetch(`${BASE}/studies/${studyUid}/series/${seriesUid}/instances/${sopUid}`, {
      headers: { Accept: 'multipart/related; type="application/dicom"' },
    });
  } catch {
    throw new DicomWebError("unavailable");
  }
  if (response.status === 404) throw new DicomWebError("not-found");
  if (!response.ok) throw new DicomWebError("unavailable");
  const body = new Uint8Array(await response.arrayBuffer());
  const boundary = /boundary="?([^";]+)"?/i.exec(response.headers.get("Content-Type") ?? "")?.[1];
  if (!boundary) return body.buffer;
  const head = new TextDecoder("latin1").decode(body.subarray(0, 4096));
  const start = head.indexOf("\r\n\r\n") + 4;
  const closing = new TextEncoder().encode(`\r\n--${boundary}`);
  let end = body.length - closing.length;
  while (end > start && !closing.every((byte, i) => body[end + i] === byte)) end--;
  return body.slice(start, end > start ? end : body.length).buffer;
}

const metadataCache = new Map<string, Promise<DicomJson[]>>();

function seriesMetadata(studyUid: string, seriesUid: string): Promise<DicomJson[]> {
  const key = `${studyUid}/${seriesUid}`;
  if (!metadataCache.has(key)) {
    const promise = get(`/studies/${studyUid}/series/${seriesUid}/metadata`);
    promise.catch(() => metadataCache.delete(key));
    metadataCache.set(key, promise);
  }
  return metadataCache.get(key)!;
}

// A phase of a multi-phase series is addressed as "<series uid>|<phase index>"; a plain series uid
// stands for all of its images.
const PHASE_SEPARATOR = "|";
const phaseKey = (seriesUid: string, phase: number) => `${seriesUid}${PHASE_SEPARATOR}${phase}`;

/**
 * The images of a series split into dynamic phases, the same way the worker does it
 * (split_phases in workers/segmentation/conversion.py): a series holding the whole dynamic
 * acquisition repeats every slice position once per phase; at each position the images are
 * ordered by acquisition time, and the k-th one belongs to phase k. A series with one image per
 * position, or an uneven number, is a single phase.
 */
export function splitPhases(instances: DicomJson[]): DicomJson[][] {
  const byPosition = new Map<string, DicomJson[]>();
  for (const instance of instances) {
    const position = (instance["00200032"]?.Value ?? []).map((v) => Number(v).toFixed(3)).join("\\");
    byPosition.set(position, [...(byPosition.get(position) ?? []), instance]);
  }
  const counts = new Set([...byPosition.values()].map((group) => group.length));
  const phases = counts.size === 1 ? [...counts][0] : 1;
  if (phases < 2) return [instances];
  const order = (i: DicomJson) => [String(tag(i, "00080032") ?? ""), Number(tag(i, "00200013") ?? 0)] as const;
  for (const group of byPosition.values()) {
    group.sort((a, b) => {
      const [ta, na] = order(a);
      const [tb, nb] = order(b);
      return ta === tb ? na - nb : ta < tb ? -1 : 1;
    });
  }
  return Array.from({ length: phases }, (_, k) => [...byPosition.values()].map((group) => group[k]));
}

const imageIdCache = new Map<string, Promise<string[]>>();

// registers the series (or phase) metadata with the loader and returns one imageId per frame
export function seriesImageIds(studyUid: string, seriesKey: string): Promise<string[]> {
  const key = `${studyUid}/${seriesKey}`;
  if (!imageIdCache.has(key)) {
    const [seriesUid, phase] = seriesKey.split(PHASE_SEPARATOR);
    const promise = seriesMetadata(studyUid, seriesUid).then((all) => {
      const instances = phase === undefined ? all : (splitPhases(all)[Number(phase)] ?? []);
      return instances.flatMap((instance) => {
        const sop = tag(instance, "00080018");
        const frames = Number(tag(instance, "00280008") ?? 1);
        return Array.from({ length: frames }, (_, i) => {
          const imageId = `wadors:${BASE}/studies/${studyUid}/series/${seriesUid}/instances/${sop}/frames/${i + 1}`;
          wadors.metaDataManager.add(imageId, instance as never);
          return imageId;
        });
      });
    });
    promise.catch(() => imageIdCache.delete(key));
    imageIdCache.set(key, promise);
  }
  return imageIdCache.get(key)!;
}
