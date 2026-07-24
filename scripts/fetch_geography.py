"""Обновить снимок справочника стран и крупных городов из Wikidata.

Структурированные данные Wikidata распространяются под CC0:
https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/Copyright

Запуск из корня проекта:
    python scripts/fetch_geography.py
"""
from __future__ import annotations

import datetime
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ENDPOINT = "https://qlever.dev/api/wikidata"
OUTPUT = Path(__file__).parents[1] / "src" / "shop" / "data" / "geography.json"
HEADERS = {
    "Accept": "application/sparql-results+json",
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "medcard.cc geography seed/0.1",
}

COUNTRIES_QUERY = """
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?country ?iso2 ?iso3 ?m49 ?nameRu ?nameEn WHERE {
  ?country wdt:P297 ?iso2;
           wdt:P298 ?iso3;
           rdfs:label ?nameEn.
  FILTER(LANG(?nameEn) = "en")
  FILTER(STRLEN(?iso2) = 2)
  OPTIONAL { ?country wdt:P299 ?m49. }
  OPTIONAL {
    ?country rdfs:label ?nameRu.
    FILTER(LANG(?nameRu) = "ru")
  }
}
"""

CITIES_QUERY = """
PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?city ?iso2 ?population ?nameRu ?nameEn WHERE {
  VALUES ?iso2 { %s }
  ?country wdt:P297 ?iso2.
  {
    ?city wdt:P17 ?country;
          wdt:P31/wdt:P279* wd:Q515;
          wdt:P1082 ?population.
    FILTER(?population >= 100000)
  }
  UNION
  {
    ?country wdt:P36 ?city.
    OPTIONAL { ?city wdt:P1082 ?population. }
  }
  ?city rdfs:label ?nameEn.
  FILTER(LANG(?nameEn) = "en")
  OPTIONAL {
    ?city rdfs:label ?nameRu.
    FILTER(LANG(?nameRu) = "ru")
  }
}
"""


def _bindings(query: str) -> list[dict]:
    body = urllib.parse.urlencode({"query": query}).encode()
    request = urllib.request.Request(ENDPOINT, data=body, headers=HEADERS, method="POST")
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)["results"]["bindings"]


def _city_bindings(country_codes: list[str]) -> list[dict]:
    """Пакетный запрос; при timeout рекурсивно делит пакет пополам."""
    values = " ".join(json.dumps(code.upper()) for code in country_codes)
    try:
        return _bindings(CITIES_QUERY % values)
    except (TimeoutError, urllib.error.HTTPError) as error:
        retryable = isinstance(error, TimeoutError) or error.code in {429, 500, 502, 503, 504}
        if not retryable or len(country_codes) == 1:
            raise
        midpoint = len(country_codes) // 2
        time.sleep(1)
        return (
            _city_bindings(country_codes[:midpoint])
            + _city_bindings(country_codes[midpoint:])
        )


def _value(row: dict, key: str) -> str | None:
    item = row.get(key)
    return item["value"].strip() if item else None


def _qid(uri: str) -> str:
    return uri.rsplit("/", 1)[-1]


def main() -> None:
    countries: dict[str, dict] = {}
    for row in _bindings(COUNTRIES_QUERY):
        iso2 = (_value(row, "iso2") or "").lower()
        iso3 = (_value(row, "iso3") or "").lower()
        if len(iso2) != 2 or len(iso3) != 3:
            continue
        name_en = _value(row, "nameEn")
        if not name_en:
            continue
        m49_text = _value(row, "m49")
        countries[iso2] = {
            "iso2": iso2,
            "iso3": iso3,
            "m49": int(m49_text) if m49_text and m49_text.isdigit() else None,
            "name_ru": _value(row, "nameRu") or name_en,
            "name_en": name_en,
        }

    city_rows: list[dict] = []
    country_codes = sorted(countries)
    for offset in range(0, len(country_codes), 20):
        city_rows.extend(_city_bindings(country_codes[offset:offset + 20]))

    cities: dict[str, dict] = {}
    for row in city_rows:
        iso2 = (_value(row, "iso2") or "").lower()
        uri = _value(row, "city")
        name_en = _value(row, "nameEn")
        if iso2 not in countries or not uri or not name_en:
            continue
        code = _qid(uri)
        population_text = _value(row, "population")
        population = int(float(population_text)) if population_text else 0
        candidate = {
            "code": code,
            "country": iso2,
            "name_ru": _value(row, "nameRu") or name_en,
            "name_en": name_en,
            "population": population,
        }
        # У Wikidata бывает несколько актуальных значений населения: оставляем
        # максимальное, чтобы результат не зависел от порядка строк.
        if code not in cities or population > cities[code]["population"]:
            cities[code] = candidate

    payload = {
        "source": "https://www.wikidata.org/",
        "license": "CC0",
        "generated_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "countries": sorted(countries.values(), key=lambda item: item["iso2"]),
        "cities": sorted(cities.values(), key=lambda item: (item["country"], item["code"])),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    print(f"saved {len(countries)} countries and {len(cities)} cities to {OUTPUT}")


if __name__ == "__main__":
    main()
