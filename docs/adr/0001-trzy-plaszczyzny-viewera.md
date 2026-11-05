# ADR 0001: Trzy płaszczyzny w przeglądarce, osiowa jako robocza

- **Status:** przyjęta
- **Data:** 2026-11-03

## Kontekst

Ekran Weryfikacji pokazywał dwie płaszczyzny (osiową i strzałkową) jednej maski 3D, z pędzlem 2D i gumką. Radiolog nie mógł przez to rzetelnie poprawić maski w całej objętości:
- maska mogła wyglądać dobrze w dwóch płaszczyznach i mieć błąd w trzeciej;
- nie było widać, na których przekrojach maska jest, a na których ma dziury;
- korekta przekrój po przekroju była żmudna.

Do tego kolejka i formularz zostawiały na ekranie 1440×900 tylko ok. 450 px na obraz.

## Decyzja

- Przeglądarka pokazuje **trzy zsynchronizowane płaszczyzny**: osiową, strzałkową i czołową. Wszystkie trzy to viewporty jednego wolumenu, a malować można w każdej.
- **Osiowa jest domyślnie płaszczyzną główną** (duży widok). W niej odbywa się większość edycji, bo seria DCE jest zwykle akwizycją osiową. Pozostałe dwie są w kolumnie obok i służą do kontroli.
- Główną płaszczyznę można zmienić (przycisk w nagłówku miniatury, dwuklik, `1`/`2`/`3`). Można też przejść do jednego widoku (`V`) na całą szerokość.
- Płaszczyzny są wyrównane do siatki akwizycji (`*_REFORMAT` w Cornerstone), więc przekrój na ekranie to jedna warstwa obrazu.
- Synchronizacja to `Shift` + klik oraz linie referencyjne. Celownik (`CrosshairsTool`) odrzuciliśmy, bo przejmuje lewy przycisk pędzla, a jego obrót dawałby skośne płaszczyzny.
- **Narzędzia ważą więcej niż liczba widoków.** Razem z trzecią płaszczyzną weszły:
  - „Pędzel do krawędzi” (próg dynamiczny);
  - pędzel kulisty, który maluje kilka przekrojów naraz;
  - promień w mm;
  - wskaźnik zasięgu maski z lukami;
  - uzupełnianie luk między przekrojami.
- Kolejka zniknęła z ekranu przypadku: radiolog przechodzi dalej przez „Zatwierdź, dalej”, a pełną listę ma w Badaniach. Lewa krawędź należy do szyny narzędzi, a ikona w rogu (`F`) chowa formularz. Obraz główny ma ok. 615 px z formularzem i ok. 720 px bez niego.

## Rozważane opcje

| Opcja | Dlaczego nie |
| --- | --- |
| Dwie płaszczyzny jak dotąd | błędy w trzeciej płaszczyźnie są niewidoczne |
| Siatka 2×2 z widokiem 3D | każdy widok mały, 3D nie pomaga w edycji przekroju |
| Trzy równe widoki | żaden nie jest dość duży do precyzyjnego malowania |
| Główny + dwa mniejsze (wybrana) | duży obraz do pracy, dwa do kontroli, zamiana jednym klikiem |

## Podgląd 3D: otwarta opcja

Podgląd 3D (powierzchnia maski obracana myszą) nie jest częścią tej decyzji. Pomógłby ocenić kształt i ciągłość zmiany, ale:
- wymaga `@cornerstonejs/polymorphic-segmentation` i modułu wasm do zamiany labelmapy na powierzchnię;
- zajmuje miejsce, którego brakuje dla przekrojów;
- edycja i tak odbywa się na przekrojach.

Jeśli radiolodzy uznają go za potrzebny, najprostsze miejsce to czwarta pozycja przełącznika widoku głównego, a nie stały panel. Wersja Cornerstone 4.22 ma odpowiednie paczki w tej samej wersji (ADR 0002).

## Konsekwencje

- Trzy viewporty na jednym `RenderingEngine` zwiększają koszt renderowania. Na badaniu Duke działa płynnie.
- Przy grubych warstwach DCE maska w strzałkowej i czołowej wygląda schodkowo. Edycję najlepiej robić w płaszczyźnie akwizycji.
- Pasek przekrojów, zasięg maski i interpolacja liczą się zawsze wzdłuż płaszczyzny głównej i przeliczają się po jej zmianie.
