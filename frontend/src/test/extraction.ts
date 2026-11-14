import type { Extraction, WireBreast, WireLesion, WireNode, WireObservation } from "../review/extraction";

// made-up reports in the worker's shape, no patient data

const breast = (): WireBreast => ({
  budowa: null,
  obrzek: null,
  zwapnienia: null,
  mikrozwapnienia: null,
  zmiany_ogniskowe: null,
  skora: { stan: null, naciek: null },
});

export const observation = (overrides: Partial<WireObservation> = {}): WireObservation => ({
  modalnosc: "mammografia",
  lokalizacje: [],
  godzina: null,
  odleglosc_od_brodawki: null,
  typ: null,
  wymiary: null,
  glebokosc: null,
  ksztalt: null,
  brzeg: null,
  echogenicznosc: null,
  jednorodnosc: null,
  naciek_skory: null,
  cytat: "",
  ...overrides,
});

export const lesion = (overrides: Partial<WireLesion> = {}): WireLesion => ({
  id: 1,
  strona: "prawa",
  birads: null,
  obserwacje: [observation()],
  polaczenie_obserwacji: null,
  ...overrides,
});

export const node = (overrides: Partial<WireNode> = {}): WireNode => ({
  modalnosc: "usg",
  strona: "prawa",
  okolica: "pacha",
  liczba: null,
  wymiary: null,
  patologiczne: false,
  uwagi: null,
  cytat: "",
  ...overrides,
});

export const extraction = (overrides: Partial<Extraction> = {}): Extraction => ({
  modalnosci: ["mammografia", "usg"],
  piersi: { lewa: breast(), prawa: breast() },
  zmiany: [lesion()],
  wezly: [],
  wniosek: { birads: null, tekst: null, zalecenie: null },
  ...overrides,
});
