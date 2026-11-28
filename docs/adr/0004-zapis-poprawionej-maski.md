# 0004. Zapis poprawionej maski jako DICOM SEG z przeglądarki

Data: 2026-11-19
Status: Zaakceptowana

## Kontekst

Radiolog poprawia maskę w przeglądarce (pędzel, gumka, próg) na labelmapie Cornerstone, którą ADR 0003 wypełnia z DICOM SEG modelu. Poprawione woksele nie trafiają jednak na serwer:

- ekran Weryfikacji wysyła `POST /api/review/cases/{id}/approve-mask/` z samym `{mask, edits}` (`frontend/src/review/api.ts`, `approveMask`), czyli decyzję i licznik zmian, bez maski;
- endpoint `POST /api/segmentations/{id}/approve/` (`backend/segmentation/views.py`, `approve_segmentation`) przyjmuje poprawioną maskę jako NIfTI (`mask_file`), zapisuje ją w MinIO i zleca `segmentation.correction_to_dicom_seg`, ale interfejs z niego nie korzysta;
- pomiary w przeglądzie (`measurements`) pochodzą zawsze z maski modelu, także dla wyniku `CORRECTED`;
- dotrenowanie (P2) nie ma danych, bo żadna poprawka nie jest zapisana.

To pozostała część pytania ARCH-1 z `architecture-drivers.md` („Gdzie i w jakim formacie zapisujemy poprawioną maskę”). ADR 0003 ustalił format wymiany z przeglądarką (DICOM SEG w Orthancu) dla odczytu i zostawił zapis otwarty. Issue #25 wymaga zapisu poprawki jako nowej wersji (maska modelu bez zmian), walidacji geometrii i listy poprawek per wersja modelu jako wejścia do treningu.

Fakty techniczne:
- labelmapa w przeglądarce leży dziś nad serią wyświetlaną na ekranie (`post`), a SEG modelu i NIfTI modelu odnoszą się do fazy `pre` (siatka treningowa, `_to_training_layout` w `workers/segmentation/conversion.py`). Fazy jednego badania mają wspólny Frame of Reference i tę samą siatkę, a model zwraca jedną maskę dla wszystkich kanałów, więc labelmapę można położyć nad fazą `pre` bez przeliczania wokseli;
- `@cornerstonejs/adapters` 4.22.13, już w projekcie (ADR 0003), ma `generateSegmentation`, który zapisuje labelmapę jako DICOM SEG;
- worker ma `highdicom` (`workers/segmentation/requirements.txt`) i już zapisuje SEG z NIfTI (`convert_nifti_to_dicom_seg`); brakuje drogi odwrotnej.

Drivery:
- **Q2**: maska zapisana ma być dokładnie tą, którą lekarz widział, a pomiary i trening mają ją dostać na siatce modelu;
- **Q3**: błąd konwersji nie może zgubić poprawki lekarza;
- **Q5**: poprawka to nowa wersja z własnym UID, autorem i czasem; maska modelu zostaje;
- **Q1**: zapis idzie przez API, z uprawnieniem `review` i audytem, tak jak inne decyzje lekarza;
- **P1 krok „zatwierdza”**: diagram P1 w `ARCHITECTURE.md` zakłada „UI → API: poprawiona maska” i przeliczenie pomiarów w workerze.

## Rozważane opcje

- **A. DICOM SEG z przeglądarki do API, konwersja SEG → NIfTI w workerze**
  - \+ Jeden format maski na całej drodze przeglądarka ↔ serwer, ten sam co przy odczycie (ADR 0003), czytany przez OHIF i PACS.
  - \+ Przeglądarka nie zna układu treningowego: SEG odwołuje się do serii `pre`, na której leży labelmapa, a odbicia osi do układu treningowego robi worker, tak jak dziś robi drogę odwrotną (Q2).
  - \+ Bez nowej zależności: `adapters` w przeglądarce, `highdicom` w workerze.
  - \+ Plik SEG jest kompletnym, samoopisującym się zapisem poprawki (UID-y, serie odniesienia, autor), co daje wersję do audytu (Q5).
  - \- Nowa ścieżka w workerze: odczyt SEG i ułożenie klatek na siatce NIfTI. To miejsce, w którym może rozjechać się geometria, dlatego pokrywają ją testy (patrz Decyzja).
  - \- `generateSegmentation` nie był jeszcze używany w naszym projekcie; sprawdza go kryterium akceptacji T-06b.
- **B. NIfTI z przeglądarki do istniejącego `approve_segmentation`**
  - \+ Endpoint i zapis w MinIO już istnieją, worker zamienia NIfTI na SEG.
  - \- Przeglądarka musiałaby odtworzyć układ treningowy NIfTI (affine, odbicia z `_training_flips`) w TypeScripcie. To drugie miejsce z logiką geometrii, które może rozjechać się z workerem (Q2), z tego samego powodu ADR 0003 odrzucił NIfTI przy odczycie.
  - \- Pliki NIfTI całego wolumenu są większe niż SEG z 1-bitowymi klatkami.
- **C. Łatka zmian (lista zmienionych wokseli) do API, worker nakłada ją na maskę modelu**
  - \+ Mały ładunek, bo zwykle poprawia się brzeg.
  - \- Własny format bez standardu; indeksy wokseli nadal trzeba przenieść z labelmapy `post` na siatkę modelu.
  - \- Wynik zależy od tego, czy łatka i maska bazowa są z tej samej wersji, czyli dodatkowy stan do pilnowania.
  - \- OHIF i PACS i tak potrzebują SEG, więc worker musiałby go wygenerować osobno.
- **D. DICOM SEG z przeglądarki prosto do Orthanca (STOW-RS przez `/dicom-web`)**
  - \+ Najmniej kodu po stronie API.
  - \- Zapis omija API: brak transakcji ze statusem wyniku, audytu i walidacji (Q1, Q5); gateway musiałby wpuszczać zapis do Orthanca z przeglądarki.

## Decyzja

Wybieramy **opcję A**. Labelmapa w przeglądarce leży nad fazą `pre`, czyli na siatce maski modelu. Przeglądarka zapisuje ją jako DICOM SEG (`generateSegmentation`) i wysyła go w zatwierdzeniu maski do API. API sprawdza tanie warunki: plik jest DICOM SEG, jego Study Instance UID to UID tego badania w Orthancu, a maska czeka na weryfikację (`COMPLETED`). Dopiero wtedy wgrywa SEG do Orthanca, a następnie w jednej transakcji ustawia `CORRECTED`, zapisuje UID-y SEG w `approved_seg_*`, dopisuje wpis w dzienniku i po commicie (`on_commit`) zleca zadanie `segmentation.correction_from_dicom_seg` na kolejce `segmentation-convert`. Kolejność „najpierw Orthanc, potem baza” sprawia, że przy niedostępnym Orthancu nic nie jest zapisane i lekarz może ponowić zatwierdzenie; jedyny skutek uboczny to SEG bez odwołania w Orthancu, gdy dwa zatwierdzenia ścigają się o ten sam wynik. Geometrię (Frame of Reference UID, seria odniesienia `pre`) sprawdza worker, który i tak czyta piksele i serie badania, więc API jej nie powtarza. Worker pobiera badanie z SEG z Orthanca, sprawdza Frame of Reference i to, że SEG odnosi się do serii `pre`, zamienia go na NIfTI w układzie treningowym (`accepted_path` w MinIO) i przelicza pomiary. Maska bez zmian nie wysyła pliku i kończy jako `APPROVED`.

Zamiast osobnego spike'a (T-06a) stronę workera sprawdzają testy w `workers/segmentation/tests.py`: SEG na fazie `pre` → NIfTI jest identyczny z maską wejściową (asymetryczna maska, dwie orientacje serii), SEG na innej fazie albo z innego badania jest odrzucany, a zadanie zapisuje `accepted_path` i pomiary, przy błędzie zostawia komunikat w `error`. Stronę przeglądarki sprawdza kryterium akceptacji T-06b: zatwierdzenie bez edycji daje NIfTI identyczny z NIfTI modelu (0 różnych wokseli), a jeden domalowany woksel ląduje w oczekiwanym miejscu. Jeśli się to nie uda, wracamy do tego ADR-a z opcją C jako zapasową.

## Konsekwencje

- \+ Poprawka lekarza jest zapisana jako osobna wersja: SEG modelu zostaje, SEG zatwierdzony ma własne UID-y (Q5), a NIfTI poprawki jest wejściem do treningu (P2).
- \+ Pomiary w przeglądzie pochodzą z maski zatwierdzonej (`source: "approved"` w `_overview_measurements`), a nie z maski modelu.
- \+ SEG jest w Orthancu, zanim zacznie się konwersja, więc błąd workera nie gubi poprawki; zadanie można powtórzyć (Q3).
- \+ Labelmapa nad fazą `pre` oznacza, że lekarz poprawia maskę na tej samej siatce, na której liczone są pomiary i trening; ruch pacjentki między fazami nie przesuwa poprawki.
- \- Lekarz maluje na fazie `pre`, na której zmiana jest słabiej widoczna niż na `post`. Podgląd innych faz pod tą samą labelmapą to osobna zmiana w przeglądarce.
- \- Nowe zadanie w workerze (SEG → NIfTI) i testy geometrii dla niego; bez nowego kontenera ani kolejki (`segmentation-convert` już jest). API potrzebuje zapisu do Orthanca (dziś zapisuje tylko worker).
- \- Endpoint zatwierdzenia z plikiem musi być jedyną ścieżką zatwierdzania maski. Dziś są dwie (`review/.../approve-mask/` i `segmentations/{id}/approve/`), więc zapis poprawki czeka na ich połączenie (T-07); ścieżka z NIfTI (`mask_file`) znika.
- \- Do czasu konwersji przegląd pokazuje status „Zapisywanie” (`saving`), który już istnieje.
- \- Model danych poprawek (osobny rekord `MaskCorrection` z #25 czy pola na `SegmentationResult`) nie jest częścią tej decyzji; rozstrzyga go T-07.
- Do zrobienia: zadanie SEG → NIfTI w workerze (`correction_from_dicom_seg`, gałąź `segmentation/seg-to-nifti`); jedna ścieżka zatwierdzania i usunięcie `correction_to_dicom_seg` (T-07); labelmapa nad `pre`, zatwierdzenie z plikiem SEG w API i w `approveMask` (T-06b, po T-07); w `ARCHITECTURE.md` format SEG na strzałkach „poprawiona maska” w diagramie workera i w sekwencji P1; w `architecture-drivers.md` ARCH-1 oznaczone jako rozstrzygnięte przez ADR 0003 i 0004.
