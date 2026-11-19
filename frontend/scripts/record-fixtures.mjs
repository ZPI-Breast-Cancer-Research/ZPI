// Records the backend's answers on the demo accounts into src/test/fixtures/.
// Needs the Docker stack with the demo seed: npm run fixtures
// MARIA_URL and DEMO_PASSWORD override the defaults below.

import { mkdir, writeFile } from "node:fs/promises";

const BASE = (process.env.MARIA_URL ?? "http://localhost:8081").replace(/\/$/, "");
const PASSWORD = process.env.DEMO_PASSWORD ?? "DemoPass123!";
const OUT = new URL("../src/test/fixtures/", import.meta.url);

async function signIn(role) {
  const response = await fetch(`${BASE}/api/auth/signin/`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Referer: `${BASE}/` },
    body: JSON.stringify({ login: `demo.${role}`, password: PASSWORD }),
  });
  if (!response.ok) throw new Error(`sign-in as demo.${role}: HTTP ${response.status}`);
  const cookie = response.headers
    .getSetCookie()
    .map((line) => line.split(";")[0])
    .join("; ");
  return { cookie, body: await response.json() };
}

async function get(session, path) {
  const response = await fetch(`${BASE}${path}`, { headers: { Cookie: session.cookie } });
  if (!response.ok) throw new Error(`GET ${path}: HTTP ${response.status}`);
  return response.json();
}

// demo studies only, one for each pair of statuses
function sample(studies) {
  const seen = new Set();
  return studies.filter((study) => {
    const pair = `${study.segmentation_status}/${study.extraction_status}`;
    if (!study.patient_id?.startsWith("DEMO-") || seen.has(pair)) return false;
    seen.add(pair);
    return true;
  });
}

const radiologist = await signIn("radiologist");
const researcher = await signIn("researcher");
const admin = await signIn("admin");

const studies = sample(await get(radiologist, "/api/studies"));
const queue = (await get(radiologist, "/api/review/queue/")).slice(0, 3);
const corrected = studies.find((study) => study.segmentation_status === "CORRECTED");
if (!queue.length || !corrected) throw new Error("the demo seed has no queued case or no corrected mask");

const fixtures = {
  signin: radiologist.body,
  profile: await get(radiologist, "/api/profile/"),
  studies,
  "unassigned-reports": (await get(radiologist, "/api/reports/unassigned/")).slice(0, 2),
  "review-queue": queue,
  "review-case": await get(radiologist, `/api/review/cases/${encodeURIComponent(queue[0].studyId)}/`),
  "review-overview": await get(radiologist, `/api/review/cases/${encodeURIComponent(corrected.orthanc_id)}/review-overview/`),
  "models-segmentation": await get(researcher, "/api/models/segmentation/"),
  "models-extraction": await get(researcher, "/api/models/extraction/"),
  dashboard: await get(radiologist, "/api/dashboard/"),
  health: await get(admin, "/api/health"),
  users: await get(admin, "/api/users/"),
  "audit-logs": (await get(admin, "/api/logs/")).slice(0, 5),
};

// the Duke study sits in the same Orthanc, but its data can't go into the repo
const text = JSON.stringify(fixtures);
if (/breast_mri|duke/i.test(text)) throw new Error("a non-demo study got into the fixtures");

await mkdir(OUT, { recursive: true });
for (const [name, data] of Object.entries(fixtures)) {
  await writeFile(new URL(`${name}.json`, OUT), `${JSON.stringify(data, null, 2)}\n`);
}
console.log(`recorded ${Object.keys(fixtures).length} fixtures from ${BASE}`);
