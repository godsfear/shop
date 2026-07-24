from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from .. import tables
from ..database import db_helper
from ..services.translation import BASE_LANG, resolve


class GeographyService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def countries(self, lang: str) -> list[dict]:
        rows = list((await self.session.execute(select(tables.Country))).scalars())
        translations = (
            {} if lang == BASE_LANG
            else await resolve(self.session, "country", [row.id for row in rows], lang)
        )
        result = [
            {
                "id": row.id,
                "code": row.iso2.lower(),
                "name": translations.get((row.id, "name"), row.name),
            }
            for row in rows
        ]
        return sorted(result, key=lambda item: item["name"].casefold())

    async def cities(self, country_code: str, lang: str) -> list[dict]:
        rows = list((await self.session.execute(
            select(tables.Place)
            .join(tables.Country, tables.Country.id == tables.Place.country)
            .where(func.lower(tables.Country.iso2) == country_code.lower())
        )).scalars())
        translations = (
            {} if lang == BASE_LANG
            else await resolve(self.session, "place", [row.id for row in rows], lang)
        )
        result = [
            {
                "id": row.id,
                "code": row.code,
                "name": translations.get((row.id, "name"), row.name or row.code),
            }
            for row in rows
        ]
        return sorted(result, key=lambda item: item["name"].casefold())
