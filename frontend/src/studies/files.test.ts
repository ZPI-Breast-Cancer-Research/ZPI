import { describe, expect, it } from "vitest";

import { groupFiles, isReport } from "./files";

// as a folder picker gives it, with the path inside the chosen folder
function file(path: string): File {
  const name = path.split("/").pop()!;
  const result = new File([""], name);
  Object.defineProperty(result, "webkitRelativePath", { value: path });
  return result;
}

const names = (files: File[]) => files.map((f) => f.name);

describe("isReport", () => {
  it("knows reports by their extension", () => {
    expect(isReport(file("a/opis.TXT"))).toBe(true);
    expect(isReport(file("a/skan.jpeg"))).toBe(true);
    expect(isReport(file("a/IM0001.dcm"))).toBe(false);
    expect(isReport(file("a/IM0001"))).toBe(false);
  });
});

describe("groupFiles", () => {
  it("pairs a folder's only report with its images", () => {
    const { studies, unpairedReports } = groupFiles([file("p1/IM1"), file("p1/IM2"), file("p1/opis.txt")]);
    expect(studies).toHaveLength(1);
    expect(studies[0].folder).toBe("p1");
    expect(names(studies[0].dicomFiles)).toEqual(["IM1", "IM2"]);
    expect(studies[0].report?.name).toBe("opis.txt");
    expect(unpairedReports).toEqual([]);
  });

  it("leaves reports unpaired when a folder has several or no images", () => {
    const { studies, unpairedReports } = groupFiles([file("p1/IM1"), file("p1/a.txt"), file("p1/b.jpg"), file("opisy/c.txt")]);
    expect(studies.map((s) => [s.folder, s.report])).toEqual([["p1", null]]);
    expect(names(unpairedReports)).toEqual(["a.txt", "b.jpg", "c.txt"]);
  });

  it("makes one study per folder and skips system files", () => {
    const { studies } = groupFiles([file("p1/IM1"), file("p2/IM1"), file("p2/.DS_Store"), file("p2/Thumbs.db")]);
    expect(studies.map((s) => [s.folder, s.dicomFiles.length])).toEqual([
      ["p1", 1],
      ["p2", 1],
    ]);
  });

  it("puts loose files in an unnamed study", () => {
    const loose = new File([""], "IM1");
    expect(groupFiles([loose]).studies[0].folder).toBe("—");
  });
});
