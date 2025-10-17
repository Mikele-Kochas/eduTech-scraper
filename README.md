# eduTech-scraper

Automatyczne zbieranie i streszczanie newsów z polskich portali edukacyjnych.

## Co to jest?

To aplikacja, która:
- **Zbiera aktualności** z trzech głównych portali edukacyjnych (edunews.pl, frse.org.pl, ibe.edu.pl)
- **Automatycznie streszcza** każdy artykuł za pomocą sztucznej inteligencji (Gemini)
- **Wyświetla artykuły** w przejrzystym interfejsie
- **Pozwala pobrać** wszystkie artykuły w formacie tekstowym

## Dla kogo?

- Nauczyciele i edukatorzy chcący być na bieżąco z wiadomościami z branży
- Osoby zainteresowane rozwojem edukacji w Polsce
- Każdy, kto chce zaoszczędzić czas przeglądając newsy z wielu stron naraz

## Instalacja

```bash
pip install -r requirements.txt
python app.py
```

Wejdź na `http://localhost:5000`

## Obsługa - Krok po kroku

**Przed pierwszym użyciem:**
- Załóż darmowy klucz API na https://aistudio.google.com/app/apikey
- Skopiuj klucz (będzie Ci potrzebny)

**Uruchomienie:**
1. Otworz `http://localhost:5000` w przeglądarce
2. Wpisz klucz Gemini w polu tekstowym (górny panel) - zostanie zapamiętany
3. Kliknij **"Uruchom zbieranie"** i czekaj aż artykuły się załadują

**Przeglądanie:**
- Artykuły wyświetlają się jako karty z tytułem, datą i fragmentem
- Kliknij kartę aby zobaczyć pełny tekst (oryginalny i streszczony)
- Kliknij link aby przejść do oryginalnego artykułu

**Pobieranie:**
- Kliknij **"Pobierz jako TXT"** aby pobrać wszystkie artykuły na swój komputer
- Plik otworzysz w Notatniku lub Wordzie

## Konfiguracja

`.env` (opcjonalnie):
```
GOOGLE_API_KEY=twój_klucz
NEWS_WINDOW_DAYS=3
SCRAPER_WORKERS=12
```

Źródła: `configs/sources.yaml`

## Obsługiwane źródła

- edunews.pl
- frse.org.pl
- ibe.edu.pl
