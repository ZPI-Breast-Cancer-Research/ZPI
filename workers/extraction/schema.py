from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

SCHEMA_VERSION = "3"

MM_PER_UNIT = {"mm": 1.0, "cm": 10.0}


class Modalnosc(StrEnum):
    MAMMOGRAFIA = "mammografia"
    USG = "usg"


class Strona(StrEnum):
    LEWA = "lewa"
    PRAWA = "prawa"
    OBUSTRONNIE = "obustronnie"


class KategoriaBiRads(StrEnum):
    K0 = "0"
    K1 = "1"
    K2 = "2"
    K3 = "3"
    K4 = "4"
    K4A = "4a"
    K4B = "4b"
    K4C = "4c"
    K5 = "5"
    K6 = "6"


class Jednostka(StrEnum):
    MM = "mm"
    CM = "cm"


class Kwalifikator(StrEnum):
    DOKLADNY = "dokładny"
    OKOLO = "około"
    DO = "do"


class Ksztalt(StrEnum):
    OKRAGLY = "okrągły"
    OWALNY = "owalny"
    NIEREGULARNY = "nieregularny"


class Brzeg(StrEnum):
    OBWIEDZIONY = "obwiedziony"
    NIEOSTRY = "nieostry"
    ZATARTY = "zatarty"
    MIKROPLATOWATY = "mikropłatowaty"
    KATOWY = "kątowy"
    SPIKULARNY = "spikularny"


class Echogenicznosc(StrEnum):
    BEZECHOWA = "bezechowa"
    HIPOECHOGENICZNA = "hipoechogeniczna"
    IZOECHOGENICZNA = "izoechogeniczna"
    HIPERECHOGENICZNA = "hiperechogeniczna"
    ZLOZONA = "złożona"


class Jednorodnosc(StrEnum):
    JEDNORODNA = "jednorodna"
    NIEJEDNORODNA = "niejednorodna"


class Liczba(StrEnum):
    POJEDYNCZY = "pojedynczy"
    MNOGIE = "mnogie"


class Miara(BaseModel):
    wartosc: float
    jednostka: Jednostka = Field(description="Jednostka dokładnie jak w tekście.")

    def mm(self) -> float:
        return self.wartosc * MM_PER_UNIT[self.jednostka]


class Wymiary(BaseModel):
    wartosci: list[float] = Field(
        description="Liczby w kolejności z opisu, bez przeliczania (np. '100x90mm' -> [100, 90])."
    )
    jednostka: Jednostka = Field(description="Jednostka dokładnie jak w tekście.")
    kwalifikator: Kwalifikator = Field(
        description=(
            "'ok', 'około', 'orientacyjnie' -> około; 'do' -> do; "
            "w pozostałych przypadkach dokładny."
        )
    )

    def max_mm(self) -> float | None:
        return max(self.wartosci) * MM_PER_UNIT[self.jednostka] if self.wartosci else None


class Skora(BaseModel):
    stan: str | None = Field(
        default=None, description="Opis skóry dosłownie z tekstu.", examples=["prawidłowy"]
    )
    naciek: bool | None = Field(default=None, description="Czy zmiana nacieka skórę.")


class Piers(BaseModel):
    budowa: str | None = Field(
        default=None, description="Budowa piersi dosłownie z tekstu.", examples=["tłuszczowe"]
    )
    obrzek: bool | None = None
    zwapnienia: bool | None = Field(
        default=None, description="Zwapnienia inne niż mikrozwapnienia (np. 'zwapnienia')."
    )
    mikrozwapnienia: bool | None = None
    zmiany_ogniskowe: bool | None = Field(
        default=None, description="Czy w tej piersi opisano jakąkolwiek zmianę ogniskową."
    )
    skora: Skora = Field(default_factory=Skora)


class Piersi(BaseModel):
    lewa: Piers = Field(default_factory=Piers)
    prawa: Piers = Field(default_factory=Piers)


class Obserwacja(BaseModel):
    modalnosc: Modalnosc
    lokalizacje: list[str] = Field(
        default_factory=list,
        description="Każda wymieniona lokalizacja osobno, dosłownie z tekstu.",
        examples=[["zabrodawkowo", "część centralna", "kw dolne"]],
    )
    godzina: str | None = Field(
        default=None, description="Położenie zegarowe dosłownie z tekstu.", examples=["6"]
    )
    odleglosc_od_brodawki: Miara | None = Field(
        default=None, description="To NIE jest wymiar zmiany."
    )
    typ: str | None = Field(
        default=None,
        description="Rodzaj zmiany dosłownie z tekstu.",
        examples=["guzowata", "ognisko hypoechogeniczne", "torbiel prosta"],
    )
    wymiary: Wymiary | None = None
    glebokosc: Miara | None = Field(default=None, description="Głębokość od skóry (USG).")
    ksztalt: Ksztalt | None = None
    brzeg: Brzeg | None = None
    echogenicznosc: Echogenicznosc | None = Field(default=None, description="Tylko USG.")
    jednorodnosc: Jednorodnosc | None = Field(default=None, description="Tylko USG.")
    naciek_skory: bool | None = None
    cytat: str = Field(
        description="Dosłowny fragment opisu obejmujący wszystkie dane tej obserwacji."
    )


class PolaczenieObserwacji(BaseModel):
    pewne: bool = Field(
        description=(
            "true tylko, gdy opis wprost łączy obserwacje "
            "(np. 'odpowiada zmianie w mammografii')."
        )
    )
    powod: str | None = Field(
        default=None, description="Dlaczego to prawdopodobnie ta sama zmiana."
    )


class Zmiana(BaseModel):
    id: int = Field(description="Kolejny numer zmiany w tym opisie, od 1.")
    strona: Strona
    birads: KategoriaBiRads | None = Field(
        default=None, description="BI-RADS tej zmiany, jeśli opis podaje go przy zmianie."
    )
    obserwacje: list[Obserwacja] = Field(
        description="Opis tej samej zmiany w poszczególnych badaniach (MMG, USG)."
    )
    polaczenie_obserwacji: PolaczenieObserwacji | None = Field(
        default=None, description="Tylko gdy obserwacji jest więcej niż jedna."
    )


class Wezel(BaseModel):
    modalnosc: Modalnosc
    strona: Strona
    okolica: str = Field(description="Okolica dosłownie z tekstu.", examples=["dół pachowy"])
    liczba: Liczba | None = None
    wymiary: Wymiary | None = None
    patologiczne: bool | None = Field(
        default=None,
        description=(
            "true – opis wskazuje patologię; false – 'bez cech patologii'; null – brak oceny."
        ),
    )
    uwagi: str | None = Field(
        default=None, description="Inne cechy dosłownie z tekstu.", examples=["o pogrubiałej korze"]
    )
    cytat: str


class Wniosek(BaseModel):
    birads: KategoriaBiRads | None = None
    tekst: str | None = Field(default=None, description="Treść wniosku dosłownie z tekstu.")
    zalecenie: str | None = Field(
        default=None,
        description="Zalecenie dosłownie, bez rozwijania skrótów.",
        examples=["do BMU"],
    )


class EkstrakcjaBadania(BaseModel):
    modalnosci: list[Modalnosc] = Field(description="Badania opisane w dokumencie.")
    piersi: Piersi = Field(default_factory=Piersi)
    zmiany: list[Zmiana] = Field(
        default_factory=list,
        description="Tylko zmiany stwierdzone w opisie; zaprzeczenia nie tworzą zmian.",
    )
    wezly: list[Wezel] = Field(default_factory=list)
    wniosek: Wniosek = Field(default_factory=Wniosek)


class Provenance(BaseModel):

    ocr_engine: str | None = None
    ocr_engine_version: str | None = None
    ocr_mean_confidence: float | None = None
    orientation_detector: str | None = None
    page_rotations: list[int | None] = Field(default_factory=list)
    llm_provider: str
    llm_model: str
    prompt_version: str
    schema_version: str = SCHEMA_VERSION


class ExtractionResult(BaseModel):
    source: str
    status: str = Field(description="'ok' or 'error'.")
    data: EkstrakcjaBadania | None = None
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)
    text: str = Field(description="Normalised report text that was sent to the LLM.")
    provenance: Provenance
    attempts: int = 0
    ocr_seconds: float | None = None
    llm_seconds: float | None = None
    created_at: datetime
