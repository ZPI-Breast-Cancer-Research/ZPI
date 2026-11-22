import { describe, expect, it } from "vitest";

import { extraction, lesion, observation } from "../test/extraction";
import { areaOfClock, areaOfPlaces, areasDiffer, clockHours, fromExtraction, largestMm, lesionType, TO_WIRE, toMm } from "./report";

describe("clockHours", () => {
  it("reads one hour", () => {
    expect(clockHours("8")).toEqual([8]);
    expect(clockHours(" 12 ")).toEqual([12]);
  });

  it("reads a range in each way the reports write it", () => {
    expect(clockHours("2-3")).toEqual([2, 3]);
    expect(clockHours("2–3")).toEqual([2, 3]);
    expect(clockHours("10/11")).toEqual([10, 11]);
    expect(clockHours("2 a 3")).toEqual([2, 3]);
  });

  it("takes the shorter way round the clock", () => {
    expect(clockHours("11-1")).toEqual([11, 12, 1]);
    expect(clockHours("3-1")).toEqual([3, 2, 1]);
  });

  it("treats a range of one hour as that hour", () => {
    expect(clockHours("5-5")).toEqual([5]);
  });

  it("rejects anything that isn't an hour", () => {
    expect(clockHours(null)).toBeNull();
    expect(clockHours("")).toBeNull();
    expect(clockHours("0")).toBeNull();
    expect(clockHours("13")).toBeNull();
    expect(clockHours("2-14")).toBeNull();
    expect(clockHours("górny")).toBeNull();
  });
});

describe("areaOfClock", () => {
  it("puts 10 o'clock outer in the right breast and inner in the left", () => {
    expect(areaOfClock("10", "right", null)).toBe("upper_outer");
    expect(areaOfClock("10", "left", null)).toBe("upper_inner");
    expect(areaOfClock("2", "left", null)).toBe("upper_outer");
    expect(areaOfClock("7", "right", null)).toBe("lower_outer");
    expect(areaOfClock("5", "right", null)).toBe("lower_inner");
  });

  it("gives half of the breast for an hour on a border", () => {
    expect(areaOfClock("12", "right", null)).toBe("upper");
    expect(areaOfClock("6", "left", null)).toBe("lower");
    expect(areaOfClock("3", "right", null)).toBe("inner");
    expect(areaOfClock("9", "right", null)).toBe("outer");
  });

  it("keeps a range between its hours", () => {
    expect(areaOfClock("2-3", "right", null)).toBe("upper_inner");
    expect(areaOfClock("11-1", "right", null)).toBe("upper");
  });

  it("is central at the nipple, whatever the clock", () => {
    expect(areaOfClock("10", "right", { value: 0, unit: "mm" })).toBe("central");
    expect(areaOfClock(null, "left", { value: 0, unit: "cm" })).toBe("central");
  });

  it("says nothing without a clock or for both breasts", () => {
    expect(areaOfClock(null, "right", { value: 20, unit: "mm" })).toBeNull();
    expect(areaOfClock("10", "both", null)).toBeNull();
  });
});

describe("areaOfPlaces", () => {
  it("reads the quadrant from the report's words", () => {
    expect(areaOfPlaces(["kwadrant górny zewnętrzny"])).toBe("upper_outer");
    expect(areaOfPlaces(["Kwadrant DOLNY wewnętrzny"])).toBe("lower_inner");
    expect(areaOfPlaces(["okolica zabrodawkowa"])).toBe("central");
  });

  it("gives a half when only one direction is clear", () => {
    expect(areaOfPlaces(["kwadranty górne"])).toBe("upper");
    expect(areaOfPlaces(["granica kwadrantów górnych i dolnych zewnętrznych"])).toBe("outer");
  });

  it("says nothing without places", () => {
    expect(areaOfPlaces([])).toBeNull();
    expect(areaOfPlaces(["pierś prawa"])).toBeNull();
  });
});

describe("areasDiffer", () => {
  it("differs only when the areas share no quadrant", () => {
    expect(areasDiffer("upper_outer", "lower_inner")).toBe(true);
    expect(areasDiffer("outer", "upper_inner")).toBe(true);
    expect(areasDiffer("upper", "upper_outer")).toBe(false);
    expect(areasDiffer("outer", "lower_outer")).toBe(false);
  });

  it("can't disagree with central or an unknown area", () => {
    expect(areasDiffer("central", "lower_inner")).toBe(false);
    expect(areasDiffer(null, "upper_outer")).toBe(false);
    expect(areasDiffer("upper_outer", null)).toBe(false);
  });
});

describe("lesionType", () => {
  it("takes the most specific category from the report's words", () => {
    expect(lesionType("ognisko zaburzonej architektoniki")).toBe("distortion");
    expect(lesionType("skupisko mikrozwapnień")).toBe("calcifications");
    expect(lesionType("torbiel prosta")).toBe("cyst");
    expect(lesionType("guz")).toBe("mass");
    expect(lesionType("zmiana ogniskowa")).toBe("mass");
  });

  it("falls back to other, and to nothing without words", () => {
    expect(lesionType("węzeł chłonny")).toBe("other");
    expect(lesionType(null)).toBeNull();
    expect(lesionType("")).toBeNull();
  });
});

describe("sizes", () => {
  it("converts to millimetres", () => {
    expect(toMm(1.5, "cm")).toBe(15);
    expect(toMm(8, "mm")).toBe(8);
  });

  it("takes the largest dimension", () => {
    expect(largestMm({ values: [1.2, 0.8], unit: "cm", qualifier: "exact" })).toBe(12);
    expect(largestMm({ values: [], unit: "mm", qualifier: "exact" })).toBeNull();
  });
});

describe("fromExtraction", () => {
  it("translates the worker's words into the app's codes", () => {
    const report = fromExtraction(
      extraction({
        zmiany: [
          lesion({
            id: 3,
            strona: "lewa",
            birads: "4a",
            obserwacje: [
              observation({
                modalnosc: "usg",
                godzina: "2",
                odleglosc_od_brodawki: { wartosc: 3, jednostka: "cm" },
                wymiary: { wartosci: [8, 6], jednostka: "mm", kwalifikator: "około" },
                ksztalt: "owalny",
                brzeg: "nieostry",
                echogenicznosc: "hipoechogeniczna",
                cytat: "ognisko hipoechogeniczne",
              }),
            ],
          }),
        ],
        wniosek: { birads: "4b", tekst: "BI-RADS 4b", zalecenie: "biopsja" },
      }),
    );

    expect(report.lesions).toEqual([
      {
        id: 3,
        side: "left",
        birads: "4A",
        observations: [
          {
            modality: "ultrasound",
            places: [],
            clock: "2",
            fromNipple: { value: 3, unit: "cm" },
            type: null,
            size: { values: [8, 6], unit: "mm", qualifier: "about" },
            depth: null,
            shape: "oval",
            margin: "indistinct",
            echo: "hypoechoic",
            quote: "ognisko hipoechogeniczne",
          },
        ],
      },
    ]);
    expect(report.conclusion).toEqual({ birads: "4B", text: "BI-RADS 4b", recommendation: "biopsja" });
  });

  it("writes the app's codes back in the worker's words", () => {
    expect(TO_WIRE.side.left).toBe("lewa");
    expect(TO_WIRE.margin.spiculated).toBe("spikularny");
    expect(TO_WIRE.birads("4C")).toBe("4c");
  });
});
