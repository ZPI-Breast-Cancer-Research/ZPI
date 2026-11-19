import { describe, expect, it } from "vitest";

import segmentation from "../test/fixtures/models-segmentation.json";
import { http, HttpResponse, server } from "../test/server";
import { fetchSegmentation } from "./api";

describe("fetchSegmentation", () => {
  it("passes the overview through when the backend sends the agreed shape", async () => {
    server.use(http.get("/api/models/segmentation/", () => HttpResponse.json(segmentation)));
    const data = await fetchSegmentation();
    expect(data).toEqual(segmentation);
    expect(data.versions.find((v) => v.status === "in_use")?.version).toBe(data.inUse?.version);
  });

  it("reads the older shape into the agreed one", async () => {
    const old = {
      production: { version: "7", since: "2026-10-01", approvedBy: "Demo Administrator" },
      previous: "6",
      correctedShare: { current: 0.25, previous: 0.4 },
      next: { corrections: 12, threshold: 50, window: "30 dni" },
      training: null,
      versions: [
        { version: "8", status: "candidate", from: null, to: null, dice: 0.81, iou: 0.7, hd95: 4.2, decidedBy: null },
        { version: "7", status: "production", from: "2026-10-01", to: null, dice: null, iou: null, hd95: null, decidedBy: "Demo Administrator" },
        { version: "6", status: "archived", from: "2026-08-01", to: "2026-10-01", dice: null, iou: null, hd95: null, decidedBy: null },
      ],
    };
    server.use(http.get("/api/models/segmentation/", () => HttpResponse.json(old)));
    const data = await fetchSegmentation();

    expect(data.inUse).toMatchObject({ version: "7", since: "2026-10-01", approvedBy: { name: "Demo Administrator" }, studies: null });
    expect(data.compareWith).toBe("6");
    expect(data.training).toMatchObject({ corrections: 12, threshold: 50, canStart: true, run: null });
    expect(data.versions.map((v) => v.status)).toEqual(["new", "in_use", "retired"]);
    expect(data.versions[0].metrics).toMatchObject({ dice: 0.81, iou: 0.7, hd95: 4.2, diceSmall: null });
    expect(data.versions[1].metrics).toBeNull();
    expect(data.versions[1].agreement?.unchanged).toBe(0.75);
    expect(data.versions[2].periods).toEqual([{ from: "2026-08-01", to: "2026-10-01" }]);
  });
});
