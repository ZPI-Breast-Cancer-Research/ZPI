# ADR 0002: Cornerstone3D 4.22.13

- **Status:** przyjęta
- **Data:** 2026-11-03

## Kontekst

Przeglądarka stała na Cornerstone3D 2.19. Nowe funkcje Weryfikacji (ADR 0001) potrzebują pędzla progowego, pędzla kulistego i labelmap wolumenowych z historią zmian. To API zmieniło się w wersji 3.0, więc robienie tych funkcji na 2.19 oznaczałoby pisanie ich drugi raz przy upgradzie.

Stan linii w chwili decyzji:

| Linia | Stan | Dla nas |
| --- | --- | --- |
| 2.x | martwa, ostatnie wydanie 2.19.16 (luty 2025) | brak poprawek, stare API segmentacji |
| 3.x | zamknięta, ostatnie 3.33.5 | nowe API segmentacji, stara kamera |
| 4.x | zamknięta po 22 wersjach minor (sierpień 2025 – maj 2026), ostatnie 4.22.13 | dojrzała, wszystko, czego potrzebujemy |
| 5.x | rozwijana od czerwca 2026 | przebudowany moduł metadanych, nowe Generic Viewporty |

## Decyzja

Przechodzimy na **4.22.13** i przypinamy dokładną wersję (bez `^`) paczek `@cornerstonejs/core`, `@cornerstonejs/tools` i `@cornerstonejs/dicom-image-loader`. Paczki Cornerstone wymagają siebie nawzajem (peer dependencies) w identycznej wersji, a także konkretnego `@kitware/vtk.js`, więc muszą być podnoszone razem.

Dlaczego nie 3.x: zmiany kamery i akcesorów viewportów z 4.0 i tak trzeba będzie zrobić. 4.x ma ponad rok poprawek więcej, a różnica pracy przy upgradzie była niewielka.

Dlaczego nie 5.x: przebudowuje moduł metadanych, na którym stoi `dicomweb.ts` (`wadors.metaDataManager`), i wprowadza nowy typ viewportów. Nie daje nic, czego potrzebujemy, a dokłada ryzyka. Do tego linia jest młoda.

Wymagania środowiska: 4.x potrzebuje Node 20+. Obraz `frontend` używa `node:24-slim`.

## Co się zmieniło przy upgradzie

- Usunęliśmy `external: ["@icr/polyseg-wasm"]` z `vite.config.ts`, bo 4.x nie ciągnie już PolySeg w podstawowych paczkach.
- `StackScrollTool` zastąpił własny handler kółka (akumulacja delty, przybliżanie z `Ctrl`). To zmiana UX, nie wymóg wersji.
- `HistoryMemo` z `csUtils` obsługuje cofanie pociągnięć i uzupełniania luk.
- Silnik domyślnie używa ContextPool, więc wspólny `RenderingEngine` dla trzech viewportów nie potrzebuje dodatkowej konfiguracji.

Kod metadanych (`wadors.metaDataManager.add`) i tworzenie labelmapy (`createAndCacheDerivedLabelmapVolume`) działają bez zmian.

## Fallback

Gdyby 4.22 blokowało pracę (na przykład wycofanie labelmap wolumenowych na rzecz stosów), planem awaryjnym było 3.33.5: tylko zmiany segmentacji z 3.0, bez zmian kamery z 4.0. Nie było potrzebne.

## Kiedy przejść na 5.x

Osobne, izolowane zadanie, gdy któryś z warunków się spełni:
- 4.x przestaje dostawać poprawki bezpieczeństwa albo nie działa z aktualną wersją Vite lub Node;
- potrzebujemy czegoś, co jest tylko w 5.x;
- linia 5.x ma kilka wydań minor, a moduł metadanych jest stabilny.

Główna praca: przepisanie rejestracji metadanych w `dicomweb.ts` i ponowne sprawdzenie przeglądarki na badaniu testowym (`infra/orthanc/load-test-study.sh`).
