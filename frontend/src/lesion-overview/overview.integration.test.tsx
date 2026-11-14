import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { t } from "../i18n";
import type { Overview } from "./api";
import { caseReport } from "../test/extraction";
import overview from "../test/fixtures/review-overview.json";
import { radiologist, renderScreen, researcher } from "../test/render";
import { http, HttpResponse, server, type JsonBodyType } from "../test/server";
import type { User } from "../auth/api";
import LesionOverviewPage from "../pages/LesionOverviewPage";

vi.mock("../viewer/Viewer", () => import("../test/viewer"));

const url = `/api/review/cases/${overview.studyId}/review-overview/`;

function renderOverview(changes: Partial<Record<keyof Overview, JsonBodyType>> = {}, user: User = radiologist) {
  server.use(http.get(url, () => HttpResponse.json({ ...overview, ...changes })));
  renderScreen(
    <Routes>
      <Route path="badania/:studyId" element={<LesionOverviewPage />} />
    </Routes>,
    { route: `/badania/${overview.studyId}`, user },
  );
}

// the row of a label in one of the small key-value tables; the size is in two of them
const valueOf = async (label: string, at = 0) => (await screen.findAllByText(label, { selector: "th" }))[at].closest("tr")!;

describe("LesionOverviewPage", () => {
  it("shows the mask's measurements in mm and cm³", async () => {
    renderOverview({ measurements: { source: "approved", largest: { sizeMm: 31.6, volumeMl: 6.04 }, totalMl: 6.04 } });
    expect(await valueOf(t("overview.largestSize"))).toHaveTextContent("32 mm");
    expect(await valueOf(t("overview.volume"))).toHaveTextContent("6,04 cm³");
    expect(screen.getByText(t("overview.fromApproved"))).toBeInTheDocument();
    expect(screen.queryByText(t("overview.volumeTotal"))).not.toBeInTheDocument();
  });

  it("names the largest part and the whole when the mask has several", async () => {
    renderOverview({ measurements: { source: "model", largest: { sizeMm: 18, volumeMl: 2.4 }, totalMl: 2.9 } });
    expect(await valueOf(t("overview.volumeLargest"))).toHaveTextContent("2,40 cm³");
    expect(await valueOf(t("overview.volumeTotal"))).toHaveTextContent("2,90 cm³");
    expect(screen.getByText(t("overview.fromModel"))).toBeInTheDocument();
  });

  it("shows dashes, not made-up numbers, for today's measurements", async () => {
    renderOverview();
    expect(await valueOf(t("overview.largestSize"))).toHaveTextContent("—");
    expect(await valueOf(t("overview.volume"))).toHaveTextContent("—");
  });

  it("says the numbers are recalculated while the corrected mask is saved", async () => {
    renderOverview({ status: "saving" });
    expect(await screen.findByText(t("overview.status.saving"))).toBeInTheDocument();
    expect(await valueOf(t("overview.largestSize"))).toHaveTextContent(t("overview.recalc"));
  });

  it("compares the mask with the report in mm and in the breast's area", async () => {
    renderOverview({
      report: { source: caseReport(), accepted: caseReport().result.data },
      comparison: [
        { feature: "largestSize", fromMask: 31.6, fromReport: "6", match: null },
        { feature: "quadrant", fromMask: null, fromReport: "upper_outer", match: null },
      ],
    });
    expect(await valueOf(t("overview.largestSize"), 1)).toHaveTextContent("6 mm");
    expect(await valueOf(t("overview.quadrant"))).toHaveTextContent(t("field.quadrant.upper_outer"));
  });

  it("asks for a report before comparing", async () => {
    renderOverview({ report: null });
    expect(await screen.findByText(t("overview.needsReport"))).toBeInTheDocument();
  });

  it("gives the agreement with the model's mask only for a corrected one", async () => {
    renderOverview({ verification: { ...overview.verification, agreement: { dice: 0.87, iou: 0.77, volumeMl: 1.2 } } });
    expect(await valueOf(t("overview.agreement"))).toHaveTextContent(t("overview.agreement.value", { dice: "0,87", volume: "+1,2 ml" }));
  });

  it("says the mask is unchanged when it was approved as it was", async () => {
    renderOverview({ mask: { ...overview.mask, corrected: false } });
    expect(await valueOf(t("overview.agreement"))).toHaveTextContent(t("overview.agreement.same"));
  });

  it("opens the review for a radiologist, not for a researcher", async () => {
    renderOverview();
    expect(await screen.findByRole("link", { name: t("overview.openReview") })).toHaveAttribute("href", `/weryfikacja/${overview.studyId}`);
  });

  it("has no way into the review for a researcher", async () => {
    renderOverview({}, researcher);
    await screen.findByText(t("overview.measurements"));
    expect(screen.queryByRole("link", { name: t("overview.openReview") })).not.toBeInTheDocument();
  });
});
