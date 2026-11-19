import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { radiologist, renderScreen, researcher } from "./test/render";
import { usePrefetchViewer, viewerPages } from "./viewerPages";

function Prefetch() {
  usePrefetchViewer();
  return null;
}

describe("usePrefetchViewer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(viewerPages, "review").mockResolvedValue({ default: () => <div /> });
    vi.spyOn(viewerPages, "lesionOverview").mockResolvedValue({ default: () => <div /> });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("fetches the viewer in the background for those who review", () => {
    renderScreen(<Prefetch />, { user: radiologist });
    expect(viewerPages.review).not.toHaveBeenCalled();
    vi.runAllTimers();
    expect(viewerPages.review).toHaveBeenCalledOnce();
    expect(viewerPages.lesionOverview).toHaveBeenCalledOnce();
  });

  it("leaves it to be loaded when opened for the researcher", () => {
    renderScreen(<Prefetch />, { user: researcher });
    vi.runAllTimers();
    expect(viewerPages.review).not.toHaveBeenCalled();
  });

  it("waits until someone signs in", () => {
    renderScreen(<Prefetch />);
    vi.runAllTimers();
    expect(viewerPages.review).not.toHaveBeenCalled();
  });
});
