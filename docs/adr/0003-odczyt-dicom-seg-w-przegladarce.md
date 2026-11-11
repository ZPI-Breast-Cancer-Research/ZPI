# 0003. Odczyt maski z DICOM SEG w przeglądarce

Data: 2026-11-12
Status: Proponowana

## Kontekst

Ekran Weryfikacji nie pokazywał maski z modelu. `review_case_detail` i `review_overview` zwracają stałą elipsoidę (`center`, `radius`), a przeglądarka maluje ją w labelmapie Cornerstone (`paintMask` w `frontend/src/viewer/cornerstone.ts`). Narzędzia do edycji maski (pędzel, gumka, próg, cofanie, porównanie z maską modelu) już działają na tej labelmapie. Brakuje tylko prawdziwych wokseli.

Prawdziwa maska istnieje w dwóch postaciach:
- NIfTI w buckecie `masks` (wynik nnU-Net, układ tablicy jak w danych treningowych);
- DICOM SEG w Orthancu, odnoszący się do fazy `pre`. Dziś powstaje po zatwierdzeniu, a po #23 powstanie też zaraz po inferencji. Geometria jest sprawdzona: SEG odczytany z Orthanca pokrywa 94% maski referencyjnej Breast_MRI_009, a po odbiciu lewo–prawo 0%.

Kierunek był ustalony wcześniej, ale sposób odczytu nie:
- P1 (`architecture-drivers.md`, krok 5) wymaga serii „z nałożoną maską”, a diagram P1 w `ARCHITECTURE.md` zakłada, że worker zapisuje maskę jako DICOM SEG przez STOW-RS, a aplikacja pobiera serie i DICOM SEG przez WADO-RS.
- Pierwotnie przeglądarką był OHIF (#7), który wyświetla DICOM SEG bez dodatkowego kodu. PR #65 zastąpił go własną przeglądarką na Cornerstone3D (ADR 0001, 0002) i świadomie zostawił maskę jako zaślepkę z `TODO`, bo nie było jeszcze endpointów. Przed #76 żaden branch nie zawierał odczytu maski (SEG ani NIfTI).
- #23 wymaga zapisu maski jako DICOM SEG w Orthancu „or a documented decision to serve NIfTI instead”, a #24 zostawia w endpoincie maski oba formaty. Ten ADR jest tą udokumentowaną decyzją.
- Częściowo odpowiada też na otwarte pytanie ARCH-1 z `architecture-drivers.md` („Gdzie i w jakim formacie zapisujemy poprawioną maskę”): format wymiany z przeglądarką to DICOM SEG w Orthancu. Kopia NIfTI w MinIO zostaje dla treningu i pomiarów.

Drivery:
- **Q1**: dane zostają w szpitalu, a dostęp idzie przez gateway, tak jak do obrazów;
- **Q2**: przeglądarka ma pokazać dokładnie tę maskę, którą zapisał worker, bez drugiego przeliczania geometrii;
- **Q5**: zatwierdzona wersja to obiekt DICOM z własnym UID, powiązany z wynikiem;
- **Q6**: kilka minut na badanie, więc dodatkowa konwersja w workerze jest akceptowalna.

## Rozważane opcje

- **A. DICOM SEG przez DICOMweb, odczyt przez `@cornerstonejs/adapters` 4.22.13**
  - \+ Ta sama droga co obrazy (gateway, `/dicom-web`), bez nowego endpointu z plikami.
  - \+ Adapter zna strukturę SEG: klatki 1-bitowe, sekwencje per-frame, odwołania do przekrojów.
  - \+ Ten sam pakiet umie zapisać SEG, co przyda się przy wysyłaniu poprawek (#25).
  - \+ Zgodne z P1 i z OHIF, który już wyświetla nasze SEG.
  - \- Nowa zależność z drzewem `dcmjs`, `ndarray`, `gl-matrix`, czyli większy bundle.
  - \- Musi mieć identyczną wersję jak `core` i `tools` i być podnoszona razem z nimi (ADR 0002).
- **B. DICOM SEG przez DICOMweb, własny parser na `dicom-parser`**
  - \+ Bez nowej zależności, bo `dicom-parser` już jest w projekcie.
  - \- Własny kod do rozpakowania bitów, sekwencji per-frame i mapowania na przekroje. Każdy przypadek brzegowy (puste klatki, kompresja, kilka segmentów) to nasza praca i nasze błędy.
- **C. NIfTI z MinIO przez nowy endpoint API**
  - \+ Plik jest już zapisany, a worker nie musi niczego dodatkowo generować.
  - \- Przeglądarka musiałaby sama dopasować affine NIfTI do siatki DICOM. To drugie miejsce z logiką geometrii, które może rozjechać się z workerem (Q2).
  - \- Drugi sposób dostępu do danych obrazowych obok DICOMweb, niezgodny z P1.
  - \- Dla OHIF i PACS i tak potrzebny jest SEG, więc byłyby dwie reprezentacje do utrzymania.

## Decyzja

Wybieramy **opcję A**. Przeglądarka pobiera DICOM SEG z Orthanca przez `/dicom-web` i wczytuje go do labelmapy przy pomocy `@cornerstonejs/adapters` w wersji 4.22.13, przypiętej bez `^`. Opcja A trzyma jedną reprezentację maski (DICOM SEG), jedną drogę dostępu (DICOMweb) i jedno miejsce z logiką geometrii (worker).

Opcję sprawdził spike #76 na Breast_MRI_009: maska w przeglądarce pokrywa te same obszary co w OHIF i zostaje na miejscu przy przełączaniu serii `pre` / `post`, a narzędzia edycji działają na niej bez zmian. Do czasu, aż API review zwróci UID SEG danego przypadku (#24), przeglądarka bierze najnowszy SEG w badaniu.

## Konsekwencje

- \+ Maska na ekranie to ten sam obiekt, który widzi OHIF i który trafi do PACS.
- \+ Zostaje elipsoida-zaślepka oraz pola `center` i `radius` w API do usunięcia.
- \- Worker musi zapisywać SEG zaraz po inferencji (#23), inaczej do zatwierdzenia nie ma czego pokazać. Na CPU to kilka sekund przy kilku minutach inferencji.
- \- `SegmentationResult` potrzebuje pól z UID serii SEG modelu i SEG zatwierdzonego (migracja).
- \- Labelmapa powstaje nad serią `post`, a SEG odnosi się do `pre`. Piksele SEG są przenoszone po pozycji w przestrzeni pacjenta (`ImagePositionPatient`, orientacja, rozdzielczość), nie po `SOPInstanceUID` (#76).
- \- `@cornerstonejs/adapters` dochodzi do listy paczek podnoszonych razem (ADR 0002).
- \+ Dostęp do maski ma te same zasady co obrazy: gateway wpuszcza na `/dicom-web` tylko zalogowanych z uprawnieniem `review` (`orthanc_auth` od #66). Uprawnienia są na poziomie całego Orthanca, a nie pojedynczego badania, tak samo jak dla obrazów (Q1).
- Do zrobienia: SEG po inferencji z UID w wyniku (#23); UID SEG w API review zamiast elipsoidy (#24). Otwarta zostaje część pytania ARCH-1 o zapis poprawek z przeglądarki (#25).
