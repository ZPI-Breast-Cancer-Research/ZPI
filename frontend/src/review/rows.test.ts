import { describe, expect, it } from "vitest";

import { t } from "../i18n";
import { extraction, lesion, observation } from "../test/extraction";
import type { Extraction } from "./extraction";
import {
  applyAnswers,
  caseGroups,
  fieldChecks,
  getAt,
  lesionGroup,
  NO_ANSWERS,
  observationGroups,
  pathKey,
  pathOf,
  readList,
  readMeasure,
  readSize,
  rowLines,
  rowState,
  validClock,
  validNumber,
  valueText,
  visibleRows,
  writeType,
  type Answers,
  type Group,
  type Row,
} from "./rows";

const at = (...path: (string | number)[]) => pathKey(path);
const obsKey = (field: string) => at("zmiany", 0, "obserwacje", 0, field);
const keys = (rows: Row[]) => rows.map((row) => row.key);
const rowOf = (group: Group, key: string) => group.rows.find((row) => row.key === key)!;

// a mammography mass: place, size, shape and margin are what the report usually gives
const mass = () =>
  extraction({
    zmiany: [
      lesion({
        obserwacje: [
          observation({
            typ: "zmiana ogniskowa",
            lokalizacje: ["kwadrant górny zewnętrzny"],
            wymiary: { wartosci: [8], jednostka: "mm", kwalifikator: "dokładny" },
            ksztalt: "owalny",
          }),
        ],
      }),
    ],
  });

const shownForMass = ["typ", "lokalizacje", "wymiary", "ksztalt", "brzeg"].map(obsKey);

describe("paths", () => {
  it("turns a key back into a path with numeric indexes", () => {
    expect(pathOf("zmiany.0.obserwacje.1.brzeg")).toEqual(["zmiany", 0, "obserwacje", 1, "brzeg"]);
    expect(pathKey(pathOf("piersi.lewa.skora.stan"))).toBe("piersi.lewa.skora.stan");
  });

  it("reads a value and gives undefined for a missing branch", () => {
    const data = mass();
    expect(getAt(data, ["zmiany", 0, "obserwacje", 0, "ksztalt"])).toBe("owalny");
    expect(getAt(data, ["zmiany", 4, "obserwacje", 0, "ksztalt"])).toBeUndefined();
  });
});

describe("applyAnswers", () => {
  it("writes each edit at its path and leaves the original as it was", () => {
    const original = mass();
    const changed = applyAnswers(original, { [obsKey("brzeg")]: "nieostry", "wniosek.birads": "4a" });
    expect(changed.zmiany[0].obserwacje[0].brzeg).toBe("nieostry");
    expect(changed.wniosek.birads).toBe("4a");
    expect(original.zmiany[0].obserwacje[0].brzeg).toBeNull();
    expect(original.wniosek.birads).toBeNull();
  });

  it("skips an edit whose parent isn't in the report", () => {
    const original = mass();
    expect(applyAnswers(original, { [at("zmiany", 3, "birads")]: "2" })).toEqual(original);
  });
});

describe("visibleRows", () => {
  it("shows what the report usually gives for a mass, even when empty", () => {
    const data = mass();
    const [group] = observationGroups(data, 0);
    expect(keys(visibleRows(group, data, data, []))).toEqual(shownForMass);
  });

  it("shows only type and size for a cyst", () => {
    const data = extraction({ zmiany: [lesion({ obserwacje: [observation({ typ: "torbiel" })] })] });
    const [group] = observationGroups(data, 0);
    expect(keys(visibleRows(group, data, data, []))).toEqual([obsKey("typ"), obsKey("wymiary")]);
  });

  it("shows a field the model filled in, or the doctor added", () => {
    const data = mass();
    data.zmiany[0].obserwacje[0].naciek_skory = false;
    const [group] = observationGroups(data, 0);
    expect(keys(visibleRows(group, data, data, [obsKey("godzina")]))).toEqual([...shownForMass, obsKey("godzina"), obsKey("naciek_skory")]);
  });
});

describe("rowState", () => {
  it("is corrected as soon as a value differs", () => {
    const original = mass();
    const current = applyAnswers(original, { [obsKey("brzeg")]: "nieostry" });
    const [group] = observationGroups(original, 0);
    expect(rowState(rowOf(group, obsKey("brzeg")), original, current, [])).toBe("corrected");
  });

  it("needs both paths of an ultrasound place confirmed", () => {
    const data = extraction({ zmiany: [lesion({ obserwacje: [observation({ modalnosc: "usg", godzina: "10" })] })] });
    const [group] = observationGroups(data, 0);
    const place = rowOf(group, obsKey("godzina"));
    expect(place.paths.map(pathKey)).toEqual([obsKey("godzina"), obsKey("odleglosc_od_brodawki")]);
    expect(rowState(place, data, data, [obsKey("godzina")])).toBe("todo");
    expect(rowState(place, data, data, [obsKey("godzina"), obsKey("odleglosc_od_brodawki")])).toBe("confirmed");
  });
});

describe("fieldChecks", () => {
  const check = (data: Extraction, answers: Answers) => {
    const current = applyAnswers(data, answers.edits);
    return fieldChecks(observationGroups(data, 0), data, current, answers);
  };

  it("leaves every field unverified before the doctor checks anything", () => {
    const checks = check(mass(), NO_ANSWERS);
    expect(new Set(Object.values(checks))).toEqual(new Set(["unverified"]));
    expect(checks[obsKey("godzina")]).toBe("unverified");
  });

  it("vouches for hidden fields once every shown one is checked", () => {
    const checks = check(mass(), { ...NO_ANSWERS, confirmed: shownForMass });
    expect(checks[obsKey("ksztalt")]).toBe("confirmed");
    expect(checks[obsKey("godzina")]).toBe("confirmed");
    expect(checks[obsKey("naciek_skory")]).toBe("confirmed");
  });

  it("marks a correction and still counts the group as checked", () => {
    const checks = check(mass(), { edits: { [obsKey("brzeg")]: "nieostry" }, confirmed: shownForMass.filter((key) => key !== obsKey("brzeg")), added: [] });
    expect(checks[obsKey("brzeg")]).toBe("corrected");
    expect(checks[obsKey("typ")]).toBe("confirmed");
    expect(checks[obsKey("godzina")]).toBe("confirmed");
  });

  it("keeps hidden fields unverified while a shown one waits", () => {
    const checks = check(mass(), { ...NO_ANSWERS, confirmed: shownForMass.slice(1) });
    expect(checks[obsKey("typ")]).toBe("unverified");
    expect(checks[obsKey("wymiary")]).toBe("confirmed");
    expect(checks[obsKey("godzina")]).toBe("unverified");
  });

  it("gives the lesion's side and BI-RADS a check each", () => {
    const data = mass();
    const current = applyAnswers(data, { [at("zmiany", 0, "birads")]: "3" });
    const checks = fieldChecks([lesionGroup(0)], data, current, { edits: {}, confirmed: [at("zmiany", 0, "strona")], added: [] });
    expect(checks).toEqual({ [at("zmiany", 0, "strona")]: "confirmed", [at("zmiany", 0, "birads")]: "corrected" });
  });
});

describe("observation groups", () => {
  it("numbers two observations of the same modality", () => {
    const data = extraction({ zmiany: [lesion({ obserwacje: [observation({ modalnosc: "usg" }), observation({ modalnosc: "usg" })] })] });
    expect(observationGroups(data, 0).map((group) => group.title)).toEqual([`${t("row.section.ultrasound")} 1`, `${t("row.section.ultrasound")} 2`]);
  });

  it("notes a size gap of 3 mm or more against the other modality", () => {
    const sized = (mm: number, usgCm: number) =>
      extraction({
        zmiany: [
          lesion({
            obserwacje: [
              observation({ wymiary: { wartosci: [mm], jednostka: "mm", kwalifikator: "dokładny" } }),
              observation({ modalnosc: "usg", wymiary: { wartosci: [usgCm], jednostka: "cm", kwalifikator: "dokładny" } }),
            ],
          }),
        ],
      });
    const note = (data: Extraction) => rowOf(observationGroups(data, 0)[0], obsKey("wymiary")).note!(data);
    expect(note(sized(6, 1))?.emphasis).toBe(t("row.sizeGap", { n: "4" }));
    expect(note(sized(8, 1))).toBeNull();
  });

  it("notes when the ultrasound clock and the mammography place disagree", () => {
    const placed = (words: string) =>
      extraction({
        zmiany: [
          lesion({
            strona: "prawa",
            obserwacje: [observation({ lokalizacje: [words] }), observation({ modalnosc: "usg", godzina: "10" })],
          }),
        ],
      });
    const note = (data: Extraction) => rowOf(observationGroups(data, 0)[1], at("zmiany", 0, "obserwacje", 1, "godzina")).note!(data);
    expect(note(placed("kwadrant dolny wewnętrzny"))?.emphasis).toBe(t("row.otherArea"));
    expect(note(placed("kwadrant górny zewnętrzny"))).toBeNull();
  });
});

describe("case groups", () => {
  const conclusionNote = (data: Extraction) => {
    const conclusion = caseGroups(data).find((group) => group.key === "conclusion")!;
    return rowOf(conclusion, "wniosek.birads").note!(data);
  };

  it("notes when the conclusion's BI-RADS is not the highest of the lesions", () => {
    const data = extraction({ zmiany: [lesion({ birads: "3" }), lesion({ id: 2, birads: "4b" })], wniosek: { birads: "3", tekst: null, zalecenie: null } });
    expect(conclusionNote(data)?.text).toBe(t("row.lesionsBirads", { v: "4B" }));
    expect(conclusionNote({ ...data, wniosek: { ...data.wniosek, birads: "4b" } })).toBeNull();
  });

  it("adds one group for each lymph node", () => {
    const data = extraction({ wezly: [{ modalnosc: "usg", strona: "lewa", okolica: "pacha", liczba: null, wymiary: null, patologiczne: true, uwagi: null, cytat: "" }] });
    expect(caseGroups(data).map((group) => group.key)).toEqual(["breasts", "node.0", "conclusion"]);
  });

  it("writes a breast field once when both breasts agree", () => {
    const data = extraction();
    const calcifications = rowOf(caseGroups(data)[0], "piersi.zwapnienia");
    data.piersi.lewa.zwapnienia = false;
    data.piersi.prawa.zwapnienia = false;
    expect(rowLines(calcifications, data)).toEqual([{ text: t("row.no"), extra: t("row.bothSides") }]);
    data.piersi.prawa.zwapnienia = true;
    expect(rowLines(calcifications, data).map((line) => line.text)).toEqual([t("row.yes"), t("row.no")]);
  });
});

describe("valueText", () => {
  it("writes values the Polish way and empty ones as null", () => {
    expect(valueText({ type: "list" }, ["górny", "zewnętrzny"])).toBe("górny, zewnętrzny");
    expect(valueText({ type: "measure", unit: "cm" }, { wartosc: 1.5, jednostka: "cm" })).toBe("1,5 cm");
    expect(valueText({ type: "bool" }, false)).toBe(t("row.no"));
    expect(valueText({ type: "choice", options: ["4a"], label: (w) => w.toUpperCase() }, "4a")).toBe("4A");
    expect(valueText({ type: "text" }, "")).toBeNull();
    expect(valueText({ type: "list" }, [])).toBeNull();
  });
});

describe("reading the doctor's input", () => {
  it("accepts a clock or nothing", () => {
    expect(validClock("")).toBe(true);
    expect(validClock("2-3")).toBe(true);
    expect(validClock("13")).toBe(false);
  });

  it("accepts a decimal comma", () => {
    expect(validNumber("1,5")).toBe(true);
    expect(validNumber(" ")).toBe(true);
    expect(validNumber("pół")).toBe(false);
    expect(readMeasure("2,5", "cm")).toEqual({ wartosc: 2.5, jednostka: "cm" });
    expect(readMeasure("", "mm")).toBeNull();
  });

  it("keeps only the numbers of a size", () => {
    expect(readSize(["1,5", "", "x", "0.8"], "około", "cm")).toEqual({ wartosci: [1.5, 0.8], jednostka: "cm", kwalifikator: "około" });
    expect(readSize(["", " "], "dokładny", "mm")).toBeNull();
  });

  it("splits a list of places on commas", () => {
    expect(readList(" górny,  , zewnętrzny ")).toEqual(["górny", "zewnętrzny"]);
  });

  it("keeps the report's words when the category stays the same", () => {
    expect(writeType("mass", "guz")).toBe("guz");
    expect(writeType("cyst", "guz")).toBe("torbiel");
    expect(writeType("", "guz")).toBeNull();
  });
});
