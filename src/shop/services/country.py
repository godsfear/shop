import uuid
from typing import List, Annotated

from fastapi import Depends, HTTPException, status
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from shop.cache import get_cache
from shop.database import db_helper
from shop.tables import Country
from shop.versioning import versioned_expire, versioned_update
from shop.models import CountryCreate, CountryUpdate, CountryFilter
from shop.models import Country as CountryModel

NS = 'country'  # пространство ключей кэша; любая запись делает bump(NS)
_list_adapter = TypeAdapter(List[CountryModel])
_one_adapter = TypeAdapter(CountryModel)


class CountryService:
    def __init__(self, session: Annotated[AsyncSession, Depends(db_helper.scoped_session_dependency)]):
        self.session = session

    async def get_all(self) -> List[Country]:
        async def load():
            res = await self.session.execute(select(Country))
            return list(res.scalars().all())

        return await get_cache().get_or_load(NS, 'all', _list_adapter, load)

    async def find(self, flt: CountryFilter) -> Country:
        conditions = []
        if flt.iso2 is not None:
            conditions.append(func.lower(Country.iso2) == flt.iso2.lower())
        if flt.iso3 is not None:
            conditions.append(func.lower(Country.iso3) == flt.iso3.lower())
        if flt.m49 is not None:
            conditions.append(Country.m49 == flt.m49)
        if flt.name is not None:
            conditions.append(func.lower(Country.name) == flt.name.lower())
        if not conditions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Пустой фильтр')

        async def load():
            res = await self.session.execute(select(Country).where(and_(*conditions)))
            country = res.scalar_one_or_none()
            if country is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
            return country

        return await get_cache().get_or_load(
            NS, f'find:{flt.model_dump_json()}', _one_adapter, load)

    async def get_by_id(self, country_id: uuid.UUID) -> Country:
        async def load():
            res = await self.session.execute(select(Country).where(Country.id == country_id))
            country = res.scalar_one_or_none()
            if country is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
            return country

        return await get_cache().get_or_load(NS, f'id:{country_id}', _one_adapter, load)

    async def create(self, country_data: CountryCreate,
                     creator: uuid.UUID | None = None) -> Country:
        country = Country(**country_data.model_dump(), creator=creator)
        self.session.add(country)
        await self.session.commit()
        await get_cache().bump(NS)
        return country

    async def update(self, country_id: uuid.UUID, country_data: CountryUpdate) -> Country:
        values = country_data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нет полей для обновления')
        country = await versioned_update(self.session, Country, country_id, values)
        if country is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        await get_cache().bump(NS)
        return country

    async def expire(self, country_id: uuid.UUID) -> Country:
        country = await versioned_expire(self.session, Country, country_id)
        if country is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        await get_cache().bump(NS)
        return country
