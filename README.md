# eduTech-scraper

Minimalistyczna aplikacja do zbierania i streszczania newsów z portali edukacyjnych (config‑driven), z UI w Flask, wzbogacaniem przez Gemini 2.5 Flash i podglądem logów na żywo (SSE).

## Funkcje
- Równoległy crawl (ThreadPool) + limit zapytań per domena
- Strukturalny pipeline: RSS → sitemap → listing HTML → JS (Playwright, opcjonalnie)
- Konfiguracja źródeł w `configs/sources.yaml` 
- Ekstrakcja pełnej treści (p/li), normalizacja, deduplikacja URL
- Generacja alternatywnej treści i tytułu przez Gemii 2.5 Flash
- UI (Flask): loader, karty tytułów, modal ze szczegółami, logi SSE

## Wymagania
- Python 3.10+
- `pip install -r requirements.txt`
- (opcjonalnie dla stron renderowanych JS) `python -m playwright install chromium`

## Konfiguracja
Plik `.env` w katalogu projektu:
```
GOOGLE_API_KEY=TWÓJ_KLUCZ
NEWS_WINDOW_DAYS=3          # okno dat (1–30), domyślnie 3
SCRAPER_WORKERS=12          # liczba wątków dla crawlu
DOMAIN_RPS=1.0              # globalny limit rps na domenę
```

Źródła w `configs/sources.yaml` (fragment):
```yaml
sources:
  - name: edunews
    base_url: https://edunews.pl
    listings:
      - https://edunews.pl/aktualnosci
    allow_substrings:
      - /system-edukacji/
      - /narzedzia-i-projekty/
      - /edukacja-na-co-dzien/
      - /nowoczesna-edukacja/
      - /badania-i-debaty/
      - /wydarzenia/
    allow_regex: 'https?://[^/]*edunews\.pl/.+?/\d{3,}-'
    needs_js: false
```

Pola konfiguracyjne:
- `listings`: URL‑e list aktualności
- `allow_substrings`/`allow_regex`: filtr akceptowanych linków
- `deny_ext`: rozszerzenia do odrzucenia (binarne)
- `needs_js`: czy listing wymaga renderu JS (Playwright)
- `rate_limit_rps`: nadpisanie limitu rps per domena

## Uruchomienie (UI)
PowerShell (Windows):
```
pip install -r requirements.txt
python -m playwright install chromium   # opcjonalnie
python app.py
```
Wejdź na `http://localhost:5000` i kliknij „Uruchom zbieranie”.

## Format danych (UI/JSON)
Każdy rekord zawiera m.in.:
```json
{
  "tytuł": "…",
  "treść": "…",
  "link": "https://…",
  "data": "YYYY-MM-DD",
  "gemini_tytul": "…",
  "gemini_tresc": "…"
}
```

## Uwaga dot. Playwright
Niektóre strony (np. `youth.europa.eu/news_pl` [lista](https://youth.europa.eu/news_pl)) ładują listing JS‑em – wtedy aplikacja automatycznie użyje Playwright. Pojedyncze strony artykułów (np. wpis o nagrodzie: [Apply to the Roma Youth Project Award 2025](https://youth.europa.eu/news/apply-roma-youth-project-award-2025-eu5000-prize_pl)) parsowane są już klasycznie (HTML).

## Skrypty/parametry
- Okno dat: `NEWS_WINDOW_DAYS` (domyślnie 3)
- Wątki: `SCRAPER_WORKERS` (domyślnie 12)
- Limit rps: `DOMAIN_RPS` (domyślnie 1.0), można nadpisać per domenę w yaml

## Roadmap (skrót)
- Adapter „generic_site” w pełni mapujący selektory tytułu/treści/daty
- Persistencja (SQLite/Postgres) do dedupu i historii
- Kolejka zadań (RQ/Celery): osobno crawl / JS / Gemini

