import { useEffect } from "react";

import { useCan } from "./auth/AuthProvider";

// the pages with the image viewer, the heavy part of the app
export const viewerPages = {
  review: () => import("./pages/ReviewPage"),
  lesionOverview: () => import("./pages/LesionOverviewPage"),
};

// those who review open the viewer most days, so it comes in while the browser is idle
export function usePrefetchViewer() {
  const reviews = useCan()("review");
  useEffect(() => {
    if (!reviews) return;
    const fetch = () => {
      void viewerPages.review();
      void viewerPages.lesionOverview();
    };
    if ("requestIdleCallback" in window) {
      const id = requestIdleCallback(fetch);
      return () => cancelIdleCallback(id);
    }
    const id = setTimeout(fetch, 1000);
    return () => clearTimeout(id);
  }, [reviews]);
}
