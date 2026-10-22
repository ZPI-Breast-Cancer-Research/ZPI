from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1"


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
    K4A = "4a"
    K4B = "4b"
    K4C = "4c"
    K5 = "5"
    K6 = "6"


class TypZmiany(StrEnum):
    GUZEK = "guzek"
    MIKROZWAPNIENIA = "mikrozwapnienia"
    ASYMETRIA = "asymetria"
    ZNIEKSZTALCENIE_ARCHITEKTONIKI = "zniekształcenie_architektoniki"


class Ksztalt(StrEnum):
    OKRAGLY = "okrągły"
    OWALNY = "owalny"
    NIEREGULARNY = "nieregularny"


class Brzeg(StrEnum):
    OBWIEDZIONY = "obwiedziony"
    NIEOSTRY = "nieostry"
    SPIKULARNY = "spikularny"
    ZATARTY = "zatarty"
    MIKROPLATOWATY = "mikropłatowaty"
    KATOWY = "kątowy"


class WezelChlonny(BaseModel):
    strona: Strona = Field(description="Strona ciała.", examples=["lewa"])
    lokalizacja: str = Field(description="Lokalizacja węzła.", examples=["dół pachowy"])
    wymiary_mm: list[float] = Field(
        default_factory=list,
        description="Wymiary w mm, w kolejności z opisu. Pusta lista, gdy nie podano.",
        examples=[[11, 23]],
    )
    warstwa_korowa: str | None = Field(
        default=None,
        description="Opis warstwy korowej, dosłownie z tekstu.",
        examples=["nieregularna, odcinkowo poszerzona do 6mm"],
    )
    patologiczny: bool | None = Field(
        default=None,
        description=(
            "Czy opis wskazuje węzeł patologiczny/podejrzany. null, gdy opis tego nie mówi."
        ),
    )
    uwagi: str | None = Field(
        default=None, examples=["prawdopodobnie ten sam węzeł co w mammografii"]
    )
    cytat: str = Field(description="Dosłowny fragment opisu, z którego pochodzą dane węzła.")


class Zmiana(BaseModel):
    nr: int = Field(description="Kolejny numer zmiany w tym opisie, od 1.", examples=[1])
    modalnosc: Modalnosc = Field(description="Badanie, w którym opisano zmianę.")
    strona: Strona = Field(examples=["lewa"])
    kwadrant: str | None = Field(
        default=None,
        description="Kwadrant lub inna lokalizacja słowna, dosłownie z tekstu.",
        examples=["dolno-zewnętrzny", "na granicy kwadrantów górnych"],
    )
    polozenie_zegarowe: str | None = Field(default=None, examples=["9:00"])
    odleglosc_od_brodawki_mm: float | None = Field(
        default=None,
        description="Odległość zmiany od brodawki w mm. To NIE jest wymiar zmiany.",
        examples=[30],
    )
    typ_zmiany: TypZmiany
    wymiary_mm: list[float] = Field(
        default_factory=list,
        description="Wymiary zmiany w mm, w kolejności z opisu (np. '24x16mm' -> [24, 16]).",
        examples=[[24, 16]],
    )
    glebokosc_mm: float | None = Field(
        default=None, description="Głębokość od skóry w mm (USG, np. 'gł 0mm').", examples=[0]
    )
    ksztalt: Ksztalt | None = None
    brzeg: Brzeg | None = None
    powiazana_ze_zmiana: int | None = Field(
        default=None,
        description="nr innej zmiany z tego opisu, która jest tą samą zmianą lub się z nią łączy.",
    )
    kategoria_birads: KategoriaBiRads | None = None
    zalecenie_dot_zmiany: str | None = Field(default=None, examples=["TRUCUT + foto próbki"])
    cytat: str = Field(description="Dosłowny fragment opisu, z którego pochodzą dane zmiany.")


class EkstrakcjaBadania(BaseModel):
    typ_badania: list[Modalnosc] = Field(
        description="Badania opisane w dokumencie.", examples=[["mammografia", "usg"]]
    )
    gestosc_piersi: str | None = Field(
        default=None,
        description="Budowa/gęstość piersi dosłownie z opisu, bez normalizacji do A-D.",
        examples=["gruczołowo-tłuszczowe"],
    )
    zarys_skory: str | None = Field(default=None, examples=["prawidłowy"])
    zmiany: list[Zmiana] = Field(
        default_factory=list,
        description=(
            "Tylko zmiany stwierdzone w opisie; pomiń te, których istnieniu opis zaprzecza."
        ),
    )
    wezly_chlonne: list[WezelChlonny] = Field(default_factory=list)
    ogolna_kategoria_birads: KategoriaBiRads | None = None
    zalecenie_ogolne: str | None = Field(
        default=None, examples=["TRUCUT + foto próbki (zmiana lewa), SBM (prawa)"]
    )


class Provenance(BaseModel):

    ocr_engine: str | None = None
    ocr_engine_version: str | None = None
    ocr_mean_confidence: float | None = None
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
