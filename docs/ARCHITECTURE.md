## Cel i zakres

### Cel

Stworzenie narzędzia łączącego przechowywanie badań obrazowych, automatyczną segmentację i przegląd wyników w przeglądarce.

### Zakres

W zakresie:

- dodawanie badań MRI piersi (seria DCE) ręcznie albo z PACS szpitala, wraz z opisem radiologicznym (tekst lub skan),
- automatyczna segmentacja zmiany (nnU-Net) z pomiarami (objętość, wymiary) i oceną niepewności,
- ekstrakcja ustrukturyzowanych danych z opisu (BI-RADS, lokalizacja, wymiar, kształt, brzegi, krzywa) lokalnym modelem językowym,
- weryfikacja i poprawa wyników przez radiologa w przeglądarce, kolejka weryfikacji według niepewności,
- dotrenowanie modelu segmentacji na poprawkach lekarzy, z bramką jakości, ręczną promocją i rollbackiem,
- działanie w całości w infrastrukturze szpitala, w profilach CPU / 1 GPU / 2 GPU.

Poza zakresem:

- diagnoza i użycie kliniczne: system służy wyłącznie do celów badawczych (research use only), nie jest wyrobem medycznym,
- integracja z HIS/RIS (opisy dodawane ręcznie),
- obsługa wielu szpitali w jednej instalacji,
- inne modalności niż MRI piersi (mammografia, USG) po stronie obrazów,
- trening modelu bazowego: odbywa się offline u zespołu, poza systemem.

## Drivery

| ID  | Atrybut                     | Skrót                                                        | Priorytet |
| --- | --------------------------- | ------------------------------------------------------------ | --------- |
| Q1  | Prywatność                  | Dane pacjentek nie opuszczają szpitala, brak PII w logach    | (H, H)    |
| Q2  | Spójność trening–inferencja | Model zespołu daje w szpitalu ten sam wynik                  | (H, H)    |
| Q3  | Niezawodność                | Awaria workera nie gubi pracy lekarza                        | (H, M)    |
| Q4  | Kontrolowana zmiana modelu  | Nowa wersja tylko przez bramkę i decyzję człowieka, rollback | (H, M)    |
| Q5  | Audytowalność               | Dla każdego wyniku wiadomo, skąd pochodzi i kto go zmienił   | (M, M)    |
| Q6  | Czas do wyniku              | Badanie gotowe do weryfikacji w kilka minut                  | (M, L)    |

### P1. Badanie od dodania do weryfikacji

Radiolog dodaje badanie z opisem, system w tle segmentuje zmianę i wyciąga dane z opisu, a radiolog weryfikuje i poprawia wynik.

### P2. Dotrenowanie modelu z poprawek i promocja nowej wersji

System dotrenowuje model na poprawkach lekarzy, ocenia go bramką jakości, a administrator modeli promuje nową wersję albo ją odrzuca.

Pełny opis przepływów i atrybutów jakości: [architecture-drivers.md](architecture-drivers.md).

## C1

```mermaid
flowchart TB
    zespol["<b>Zespół MARIA</b><br/>[Osoba]<br/>Trenuje model bazowy,<br/>dostarcza wersje modelu"]

    subgraph szpital["Szpital (dane pacjentek nie opuszczają tej granicy)"]
        radiolog["<b>Radiolog</b><br/>[Osoba]<br/>Dodaje badania, weryfikuje<br/>i poprawia maski oraz dane z opisu"]
        admin["<b>Administrator modeli</b><br/>[Osoba]<br/>Uruchamia dotrenowanie,<br/>promuje lub odrzuca wersje modelu"]
        maria["<b>MARIA</b><br/>[System]<br/>Segmentacja zmian w MRI piersi,<br/>ekstrakcja danych z opisów,<br/>weryfikacja i dotrenowanie modeli"]
        pacs["<b>PACS szpitala</b><br/>[System zewnętrzny]<br/>Archiwum badań obrazowych"]
    end

    mamamia["<b>MAMA-MIA</b><br/>[Zbiór danych zewnętrzny]<br/>Publiczny zbiór MRI piersi<br/>z maskami ekspertów"]

    radiolog -- "Dodaje badania i opisy,<br/>weryfikuje wyniki [HTTPS]" --> maria
    admin -- "Zarządza wersjami modeli [HTTPS]" --> maria
    pacs -- "Przesyła badania DICOM<br/>[DICOM C-STORE]" --> maria
    zespol -- "Dostarcza wersje modelu<br/>(wagi + manifest)" --> maria
    zespol -. "Trenuje model bazowy<br/>(offline, poza MARIĄ)" .-> mamamia

    classDef person fill:#08427b,stroke:#052e56,color:#fff
    classDef system fill:#1168bd,stroke:#0b4884,color:#fff
    classDef external fill:#999999,stroke:#6b6b6b,color:#fff
    class radiolog,admin,zespol person
    class maria system
    class pacs,mamamia external
    style szpital fill:none,stroke:#444,stroke-dasharray: 5 5
```

## C2

```mermaid
flowchart TB
    radiolog["<b>Radiolog</b><br/>[Osoba]"]
    admin["<b>Administrator modeli</b><br/>[Osoba]"]
    pacs["<b>PACS szpitala</b><br/>[System zewnętrzny]"]

    subgraph maria["MARIA [System]"]
        ui["<b>Aplikacja webowa</b><br/>[React, Cornerstone3D]<br/>Lista badań, przeglądarka obrazów,<br/>edycja masek, ekran modeli"]
        proxy["<b>Proxy</b><br/>[nginx]<br/>Jeden punkt wejścia,<br/>autoryzacja dostępu do obrazów"]
        api["<b>API</b><br/>[Django, DRF]<br/>Użytkownicy, badania, weryfikacja,<br/>wersje modeli, przepływ etapów"]

        subgraph tlo["Przetwarzanie w tle [Celery]"]
            direction LR
            wseg["<b>Worker segmentacji</b><br/>[Celery, nnU-Net, GPU]<br/>Konwersja DICOM → NIfTI, inferencja,<br/>niepewność, zapis poprawionej maski"]
            wext["<b>Worker ekstrakcji</b><br/>[Celery, OCR, CPU]<br/>OCR opisu, ekstrakcja pól,<br/>walidacja schematu"]
            wtrain["<b>Worker treningu</b><br/>[Celery, nnU-Net, GPU]<br/>Dotrenowanie, ewaluacja,<br/>bramka jakości"]
            beat["<b>Harmonogram</b><br/>[Celery beat]<br/>Strażnik etapów,<br/>próg dotrenowania"]
        end

        redis[("<b>Broker</b><br/>[Redis]<br/>Kolejki zadań")]
        llm["<b>Serwer LLM</b><br/>[llama.cpp / Ollama]<br/>Lokalny model językowy"]
        mlflow["<b>Rejestr modeli</b><br/>[MLflow]<br/>Przebiegi treningu, metryki,<br/>wersje i aliasy modeli"]

        subgraph dane["Dane"]
            direction LR
            orthanc[("<b>Archiwum obrazów</b><br/>[Orthanc, DICOMweb]<br/>Kopia robocza badań,<br/>DICOM SEG")]
            pg[("<b>Baza danych</b><br/>[PostgreSQL]<br/>Badania, statusy etapów, wyniki,<br/>audyt, metadane MLflow")]
            s3[("<b>Magazyn plików</b><br/>[MinIO / wolumen]<br/>NIfTI, maski, próbki treningowe,<br/>wagi modeli")]
        end
    end

    radiolog -- "Używa [HTTPS]" --> ui
    admin -- "Używa [HTTPS]" --> ui
    pacs -- "Przesyła badania [DICOM C-STORE]" --> orthanc

    ui -- "API i obrazy [HTTPS]" --> proxy
    proxy -- "/api [JSON/HTTP]" --> api
    proxy -- "/dicom-web po sprawdzeniu sesji [DICOMweb]" --> orthanc

    api -- "Czyta i zapisuje [SQL]" --> pg
    api -- "Zleca zadania" --> redis
    api -- "Zatwierdzone maski, skany opisów [S3]" --> s3
    api -- "Upload DICOM, sprawdza serie [REST, QIDO-RS]" --> orthanc
    api -- "Promuje wersję, czyta metryki [REST]" --> mlflow
    orthanc -. "Powiadamia o nowym badaniu [HTTP]" .-> api

    tlo -- "Pobierają zadania" --> redis
    tlo -- "Statusy, wyniki, heartbeat [SQL]" --> pg
    wseg -- "Pobiera serie, zapisuje SEG [DICOMweb]" --> orthanc
    wseg -- "Pliki i maski [S3]" --> s3
    wseg -- "Pobiera model @production [REST]" --> mlflow
    wext -- "Ekstrakcja [HTTP, API OpenAI]" --> llm
    wext -- "Pobiera skan opisu [S3]" --> s3
    wtrain -- "Próbki treningowe, zbiory testowe [S3]" --> s3
    wtrain -- "Maski kandydata do porównania [STOW-RS]" --> orthanc
    beat -- "Zleca zadania okresowe" --> redis
    wtrain -- "Pobiera model @production,<br/>rejestruje nową wersję [REST]" --> mlflow

    mlflow -- "Metadane [SQL]" --> pg
    mlflow -- "Artefakty [S3]" --> s3

    classDef person fill:#08427b,stroke:#052e56,color:#fff
    classDef container fill:#438dd5,stroke:#2e6295,color:#fff
    classDef store fill:#2e6295,stroke:#1f4466,color:#fff
    classDef external fill:#999999,stroke:#6b6b6b,color:#fff
    class radiolog,admin person
    class ui,proxy,api,wseg,wext,wtrain,beat,llm,mlflow container
    class redis,orthanc,pg,s3 store
    class pacs external
    style maria fill:none,stroke:#444,stroke-dasharray: 5 5
    style tlo fill:none,stroke:#888
    style dane fill:none,stroke:#888
```

## Sequences

### P1

```mermaid
sequenceDiagram
autonumber
actor R as Radiolog
participant UI as Aplikacja webowa
participant API as API
participant PG as PostgreSQL
participant RD as Redis
participant OR as Orthanc
participant S3 as Magazyn plików
participant WS as Worker segmentacji
participant WE as Worker ekstrakcji
participant LLM as Serwer LLM
participant PACS as PACS szpitala

    Note over UI,OR: Ruch z przeglądarki idzie przez proxy (pominięte dla czytelności)

    alt Upload ręczny
        R->>UI: Dodaje badanie (DICOM zip) i opis
        UI->>API: POST /studies (pliki, opis)
        API->>OR: Zapisuje instancje DICOM [REST]
    else Badanie z PACS
        PACS->>OR: Przesyła badanie [C-STORE]
        OR-)API: Powiadamia o nowym badaniu [HTTP]
    end

    API->>OR: Sprawdza serie i fazy [QIDO-RS]
    alt Brak wymaganej fazy (2b)
        API->>PG: Badanie: status „Błąd” + powód
    else Badanie kompletne
        API->>S3: Zapisuje skan opisu (jeśli plik)
        API->>PG: Badanie + etapy „do zrobienia” (jedna transakcja)
        API->>RD: advance(): zleca segmentację i ekstrakcję (po commicie)
        API-->>UI: 201, status „W kolejce”
    end

    par Segmentacja
        WS->>RD: Pobiera zadanie (kolejka inference)
        WS->>PG: Etap „w toku”, wersja modelu przypięta do etapu
        WS->>OR: Pobiera serie [WADO-RS]
        Note over WS: Konwersja DICOM → NIfTI, inferencja,<br/>niepewność, pomiary
        alt Sukces
            WS->>S3: Zapisuje NIfTI i maskę modelu
            WS->>OR: Zapisuje maskę jako DICOM SEG [STOW-RS]
            WS->>PG: Wynik, niepewność, etap „gotowy”, advance()
        else Błąd (3a)
            WS->>PG: Etap „błąd” + powód
        end
    and Ekstrakcja
        WE->>RD: Pobiera zadanie (kolejka extraction)
        WE->>S3: Pobiera skan opisu
        Note over WE: OCR (jeśli skan)
        WE->>LLM: Ekstrakcja pól [HTTP, API OpenAI]
        LLM-->>WE: JSON z polami
        WE->>PG: Pola, pewność, etap „gotowy”, advance()
    end
    Note over PG: advance(): oba etapy gotowe → „Do weryfikacji”

    loop Co kilka sekund
        UI->>API: GET /studies (statusy etapów)
    end

    R->>UI: Otwiera badanie z kolejki weryfikacji
    UI->>API: GET /studies/{id} (pomiary, formularz)
    UI->>OR: Pobiera serie i DICOM SEG [WADO-RS]
    R->>UI: Poprawia maskę i formularz, zatwierdza
    UI->>API: POST /studies/{id}/approve (maska, formularz)
    Note over API: Walidacja geometrii maski
    API->>S3: Zapisuje zatwierdzoną maskę (nowa wersja)
    API->>PG: Wynik zatwierdzony, kto i kiedy, etap zapisu „do zrobienia”
    API->>RD: Zleca przetworzenie (po commicie)
    API-->>UI: 200, status „Zapisywanie”

    WS->>RD: Pobiera zadanie (kolejka postprocess, CPU)
    WS->>S3: Pobiera zatwierdzoną maskę
    Note over WS: Przeliczenie pomiarów,<br/>porównanie z opisem
    WS->>S3: Zapisuje próbkę treningową (NIfTI + maska)
    WS->>OR: Zapisuje wersję zatwierdzoną jako DICOM SEG [STOW-RS]
    WS->>PG: Pomiary, porównanie, status „Zweryfikowane”
```

### P2

```mermaid
sequenceDiagram
autonumber
actor A as Administrator modeli
participant UI as Aplikacja webowa
participant API as API
participant PG as PostgreSQL
participant RD as Redis
participant BT as Harmonogram
participant WT as Worker treningu
participant ML as MLflow
participant S3 as Magazyn plików
participant OR as Orthanc
participant WS as Worker segmentacji

    alt Automatycznie
        BT->>RD: Zadanie okresowe „sprawdź próg” (np. 2:00)
    else Ręcznie
        A->>UI: Uruchamia dotrenowanie
        UI->>API: POST /models/training
        API->>RD: Zleca trening (po commicie)
        API-->>UI: 202, status „W kolejce”
    end

    WT->>RD: Pobiera zadanie (kolejka training)
    WT->>PG: Liczba nowych próbek ≥ próg?
    opt Poniżej progu (tylko tryb automatyczny)
        WT->>PG: Koniec, brak treningu
    end

    WT->>PG: Przebieg treningu „w toku”
    WT->>ML: Pobiera model @production, otwiera przebieg
    WT->>S3: Pobiera próbki z puli treningowej + domieszkę MAMA-MIA

    loop Epoki
        WT->>PG: Postęp, ETA, heartbeat
        WT->>ML: Metryki treningu
        Note over WT,WS: Inferencja ma pierwszeństwo do GPU (2b)
    end

    WT->>S3: Pobiera szpitalny zbiór testowy + test MAMA-MIA
    Note over WT: Ewaluacja per badanie (Dice, HD95),<br/>bramka jakości
    WT->>OR: Zapisuje maski kandydata dla badań testowych [STOW-RS]
    WT->>ML: Rejestruje wersję N+1, alias @candidate, metryki, wagi
    ML->>S3: Zapisuje artefakty (wagi)
    alt Bramka przeszła
        WT->>PG: Wersja N+1 „do decyzji”, wynik bramki
    else Bramka nie przeszła (3a)
        WT->>PG: Wersja N+1 „odrzucona”, niespełnione warunki
    end

    A->>UI: Otwiera ekran modeli
    UI->>API: GET /models/compare
    API->>PG: Wynik bramki, metryki per badanie
    API-->>UI: Porównanie N i N+1, badania z największą różnicą
    UI->>OR: Pobiera serie i maski: N, N+1, zatwierdzona [WADO-RS]

    alt Promocja
        A->>UI: Promuje N+1
        UI->>API: POST /models/{id}/promote
        API->>PG: Sprawdza bramkę, audyt: kto, kiedy
        API->>ML: Alias @production → N+1
        API-->>UI: 200
    else Odrzucenie (5a)
        A->>UI: Odrzuca z powodem
        UI->>API: POST /models/{id}/reject (powód)
        API->>PG: Wersja „odrzucona”, powód, audyt
    end

    WS->>ML: Przy następnym zadaniu sprawdza alias @production
    Note over WS: Nowa wersja → przeładowanie wag.<br/>Etapy rozpoczęte na N kończą się na N.

    opt Rollback (6a)
        A->>UI: Przywraca wersję N
        UI->>API: POST /models/{id}/rollback
        API->>ML: Alias @production → N
        API->>PG: Audyt: kto, kiedy, powód
    end
```
