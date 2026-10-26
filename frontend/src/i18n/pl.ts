export const pl = {
  "app.name": "MARIA",

  "nav.modules": "Moduły",
  "nav.dashboard": "Pulpit",
  "nav.studies": "Badania",
  "nav.review": "Weryfikacja",
  "nav.models": "Modele",
  "nav.settings": "Ustawienia",
  "nav.account": "Konto",
  "nav.user": "Użytkownik",

  "search.placeholder": "Szukaj badania",
  "search.label": "Szukaj badania",

  "page.placeholder.title": "Ekran w przygotowaniu",
  "page.placeholder.body": "Układ tego ekranu jest w makietach (docs/design/mockups). Treść zostanie dodana w kolejnym kroku.",

  "notFound.title": "Nie znaleziono strony",
  "notFound.body": "Ten adres nie istnieje w aplikacji.",
  "notFound.back": "Wróć do pulpitu",

  "studies.list": "Lista badań",
  "studies.loading": "Wczytywanie badań…",
  "studies.empty.title": "Brak badań",
  "studies.empty.body": "W archiwum obrazów (Orthanc) nie ma jeszcze żadnych badań.",
  "studies.error.title": "Nie udało się wczytać badań",
  "studies.error.orthancUnavailable": "Archiwum obrazów (Orthanc) jest niedostępne",
  "studies.error.orthancUnauthorized": "Archiwum obrazów (Orthanc) odrzuciło dane logowania serwera",
  "studies.retry": "Spróbuj ponownie",
  "studies.retrying": "Ponawianie…",
  "studies.openViewer": "Otwórz w przeglądarce obrazów",
  "studies.noViewer": "Brak StudyInstanceUID – przeglądarka niedostępna",
  "studies.col.patient": "ID pacjentki",
  "studies.col.date": "Data badania",
  "studies.col.description": "Opis",
  "studies.col.modalities": "Modalności",
  "studies.col.series": "Serie",
} as const;

export type MessageKey = keyof typeof pl;
