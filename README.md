# News Scraper

Program do zbierania newsów z różnych portali edukacyjnych.

## Wymagania

- Python 3.8+
- Pakiety z pliku requirements.txt

## Instalacja

1. Sklonuj repozytorium
2. Zainstaluj wymagane pakiety:
```bash
pip install -r requirements.txt
```

## Użycie

Uruchom skrypt:
```bash
python news_scraper.py
```

Program zbierze newsy z poprzedniego dnia i zapisze je do pliku JSON w formacie:
```json
[
    {
        "title": "Tytuł newsa",
        "content": "Treść newsa",
        "link": "Link do źródła",
        "source": "Nazwa źródła"
    }
]
```
