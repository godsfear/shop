import uuid
from datetime import datetime, timezone
from typing import List, Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, func

from shop.database import db_helper
from shop.tables import Country
from shop.models import CountryCreate, CountryUpdate, CountryFilter


class CountryService:
    def __init__(self, session: Annotated[AsyncSession, Depends(db_helper.scoped_session_dependency)]):
        self.session = session

    async def get_all(self) -> List[Country]:
        res = await self.session.execute(select(Country))
        return list(res.scalars().all())

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
        res = await self.session.execute(select(Country).where(and_(*conditions)))
        country = res.scalar_one_or_none()
        if country is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return country

    async def get_by_id(self, country_id: uuid.UUID) -> Country:
        res = await self.session.execute(select(Country).where(Country.id == country_id))
        country = res.scalar_one_or_none()
        if country is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return country

    async def create(self, country_data: CountryCreate) -> Country:
        country = Country(**country_data.model_dump())
        self.session.add(country)
        await self.session.commit()
        return country

    async def update(self, country_id: uuid.UUID, country_data: CountryUpdate) -> Country:
        values = country_data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нет полей для обновления')
        query = (
            update(Country)
            .where(Country.id == country_id)
            .values(**values)
            .returning(Country)
        )
        res = await self.session.execute(query)
        await self.session.commit()
        country = res.scalar_one_or_none()
        if country is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return country

    async def expire(self, country_id: uuid.UUID) -> Country:
        query = (
            update(Country)
            .where(Country.id == country_id)
            .values(ends=datetime.now(timezone.utc))
            .returning(Country)
        )
        res = await self.session.execute(query)
        await self.session.commit()
        country = res.scalar_one_or_none()
        if country is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return country
