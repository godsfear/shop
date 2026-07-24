"""Идемпотентный сид связанных справочников Country -> Place.

Базовые названия в БД — русские, английские лежат в Translation. Снимок
обновляется отдельно скриптом scripts/fetch_geography.py; запуск приложения
никогда не зависит от внешней сети.
"""
from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from . import tables


DATA_FILE = Path(__file__).with_name("data") / "geography.json"


async def seed_geography(db: AsyncSession) -> tuple[int, int]:
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    language = (await db.execute(
        select(tables.Language).where(tables.Language.iso == "en")
    )).scalars().first()
    if language is None:
        language = tables.Language(code="en", iso="en", name="English")
        db.add(language)
        await db.flush()

    country_rows = list((await db.execute(select(tables.Country))).scalars())
    countries = {row.iso2.lower(): row for row in country_rows}
    for item in data["countries"]:
        row = countries.get(item["iso2"])
        if row is None:
            row = tables.Country(
                iso2=item["iso2"],
                iso3=item["iso3"],
                m49=item["m49"],
                name=item["name_ru"],
            )
            db.add(row)
            countries[item["iso2"]] = row
        else:
            row.iso3 = item["iso3"]
            row.m49 = item["m49"]
            row.name = item["name_ru"]
    await db.flush()

    place_rows = list((await db.execute(select(tables.Place))).scalars())
    places = {row.code: row for row in place_rows}
    source_city_codes = {item["code"] for item in data["cities"]}
    for item in data["cities"]:
        row = places.get(item["code"])
        country = countries[item["country"]]
        if row is None:
            row = tables.Place(
                category=None,
                code=item["code"],
                name=item["name_ru"],
                country=country.id,
            )
            db.add(row)
            places[item["code"]] = row
        else:
            row.name = item["name_ru"]
            row.country = country.id
    await db.flush()

    object_ids = [row.id for row in countries.values()]
    object_ids.extend(places[code].id for code in source_city_codes)
    translation_rows = list((await db.execute(
        select(tables.Translation).where(
            tables.Translation.table.in_(("country", "place")),
            tables.Translation.objectid.in_(object_ids),
            tables.Translation.language == language.id,
            tables.Translation.field == "name",
        )
    )).scalars())
    translations = {
        (row.table, row.objectid): row
        for row in translation_rows
    }

    def set_translation(table: str, objectid, content: str) -> None:
        row = translations.get((table, objectid))
        if row is None:
            row = tables.Translation(
                table=table,
                objectid=objectid,
                language=language.id,
                field="name",
                content=content,
            )
            db.add(row)
            translations[(table, objectid)] = row
        else:
            row.content = content

    for item in data["countries"]:
        set_translation("country", countries[item["iso2"]].id, item["name_en"])
    for item in data["cities"]:
        set_translation("place", places[item["code"]].id, item["name_en"])

    await db.commit()
    return len(data["countries"]), len(data["cities"])
