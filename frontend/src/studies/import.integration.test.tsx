import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import JSZip from "jszip";
import { afterEach, describe, expect, it, vi } from "vitest";

import { t } from "../i18n";
import * as studiesApi from "./api";
import studies from "../test/fixtures/studies.json";
import unassigned from "../test/fixtures/unassigned-reports.json";
import { radiologist, renderScreen } from "../test/render";
import { capturePosts, http, HttpResponse, server } from "../test/server";
import StudiesPage from "../pages/StudiesPage";

// as the folder picker gives them, with the path inside the chosen folder
function picked(path: string, content = "x"): File {
  const file = new File([content], path.split("/").pop()!);
  Object.defineProperty(file, "webkitRelativePath", { value: path });
  return file;
}

function backend(list = studies) {
  server.use(
    http.get("/api/studies", () => HttpResponse.json(list)),
    http.get("/api/reports/unassigned/", () => HttpResponse.json(unassigned)),
  );
}

// a folder input gives every file inside, with or without `multiple`; userEvent.upload would keep only the first
function pickFolder(files: File[]) {
  const input = document.querySelector<HTMLInputElement>("input[webkitdirectory]")!;
  Object.defineProperty(input, "files", { value: files, configurable: true });
  fireEvent.change(input);
}

// zipping the images takes a while when the whole suite runs at once
const ZIPPING = 5000;

afterEach(() => vi.restoreAllMocks());

describe("adding a study", () => {
  // jsdom's XHR can't send FormData through MSW, so this one checks what goes to sendStudy
  it("pairs the folder's report with its images and sends them as one archive", async () => {
    backend();
    const send = vi.spyOn(studiesApi, "sendStudy").mockResolvedValue({ created: 1 });
    renderScreen(<StudiesPage />, { route: "/badania", user: radiologist });
    await screen.findByRole("table");
    pickFolder([picked("P0042/IM0001"), picked("P0042/IM0002"), picked("P0042/opis.txt")]);

    await userEvent.click(await screen.findByRole("button", { name: `${t("studies.import.send")} (1)` }));
    await waitFor(() => expect(send).toHaveBeenCalledTimes(1), { timeout: ZIPPING });
    const [archive, report] = send.mock.calls[0];
    expect(archive?.name).toBe("P0042_archive.zip");
    expect(report?.name).toBe("opis.txt");
    expect(Object.keys((await JSZip.loadAsync(archive!)).files).sort()).toEqual(["P0042/", "P0042/IM0001", "P0042/IM0002"]);
    expect(await screen.findByRole("status")).toHaveTextContent(t("studies.import.sent"));
  });

  it("says why sending failed and keeps the files to try again", async () => {
    backend();
    server.use(http.post("/api/studies/import/", () => HttpResponse.json({ detail: "Archiwum jest uszkodzone." }, { status: 400 })));
    renderScreen(<StudiesPage />, { route: "/badania", user: radiologist });
    await screen.findByRole("table");
    pickFolder([picked("P0042/IM0001")]);
    await userEvent.click(await screen.findByRole("button", { name: `${t("studies.import.send")} (1)` }));

    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Archiwum jest uszkodzone."), { timeout: ZIPPING });
    expect(screen.getByRole("button", { name: `${t("studies.import.send")} (1)` })).toBeInTheDocument();
  });
});

describe("a report outside the study folders", () => {
  it("is assigned to a study from the list", async () => {
    backend();
    renderScreen(<StudiesPage />, { route: "/badania", user: radiologist });
    await screen.findByRole("table");
    pickFolder([picked("badania/P0042/IM0001"), picked("badania/opis_luzem.txt")]);

    await userEvent.click(await screen.findByRole("button", { name: t("studies.import.assignTo") }));
    await userEvent.click(screen.getByRole("option", { name: "badania/P0042" }));

    expect(screen.queryByRole("button", { name: t("studies.import.assignTo") })).not.toBeInTheDocument();
    expect(screen.getByRole("row", { name: /P0042/ })).toHaveTextContent("opis_luzem.txt");
  });
});

describe("attaching a report", () => {
  it("pairs a study without a report with one already uploaded", async () => {
    const study = { ...studies[0], extraction_status: "missing" };
    backend([study]);
    const sent = capturePosts(`/api/studies/${study.orthanc_id}/attach-existing-report/`);
    const user = userEvent.setup();
    renderScreen(<StudiesPage />, { route: "/badania?dzis=0", user: radiologist });

    await user.click(await screen.findByRole("button", { name: t("studies.action.attach") }));
    await user.click(screen.getByRole("button", { name: new RegExp(unassigned[1].fileName) }));
    await user.click(screen.getByRole("button", { name: t("studies.attach.submit") }));

    await waitFor(() => expect(sent[0]?.body).toEqual({ report_id: unassigned[1].id }));
    expect(await screen.findByRole("status")).toHaveTextContent(t("studies.attach.done"));
  });

  it("says why a report wasn't attached", async () => {
    const study = { ...studies[0], extraction_status: "missing" };
    backend([study]);
    server.use(
      http.post(`/api/studies/${study.orthanc_id}/attach-existing-report/`, () => HttpResponse.json({ detail: "Opis jest już przypisany." }, { status: 400 })),
    );
    const user = userEvent.setup();
    renderScreen(<StudiesPage />, { route: "/badania?dzis=0", user: radiologist });

    await user.click(await screen.findByRole("button", { name: t("studies.action.attach") }));
    await user.click(screen.getByRole("button", { name: new RegExp(unassigned[1].fileName) }));
    await user.click(screen.getByRole("button", { name: t("studies.attach.submit") }));

    expect(await screen.findByRole("status")).toHaveTextContent(t("studies.attach.failed", { why: "Opis jest już przypisany." }));
  });
});
