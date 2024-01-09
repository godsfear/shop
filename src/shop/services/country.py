import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from shop.database import db_helper
from shop.tables import Country
from shop.models import CountryCreate, CountryUpdate, CountryGet


class CountryService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def get_all(self) -> List[Country]:
        query = select(Country)
        res = await self.session.execute(query)
        country = res.scalars().all()
        return list(country)

    async def get_by_code(self, country_data: CountryGet) -> Country | None:
        query = None
        if country_data.iso3:
            query = (select(Country).where(Country.iso3 == country_data.iso3))
        elif country_data.iso2:
            query = (select(Country).where(Country.iso2 == country_data.iso2))
        elif country_data.m49:
            query = (select(Country).where(Country.m49 == country_data.m49))
        elif country_data.name:
            query = (select(Country).where(Country.name == country_data.name))
        res = await self.session.execute(query)
        country = res.scalar_one()
        return country

    async def get_by_id(self, country_id: uuid.UUID) -> Country | None:
        query = select(Country).where(Country.id == country_id)
        res = await self.session.execute(query)
        country = res.scalar_one()
        return country

    async def create(self, country_data: CountryCreate) -> Country:
        country = Country(**country_data.model_dump())
        self.session.add(country)
        await self.session.commit()
        await self.session.refresh(country)
        return country

    async def update(self, country_id: uuid.UUID, country_data: CountryUpdate) -> Country:
        query = (
            update(Country)
            .where(Country.id == country_id)
            .values(**country_data.model_dump(exclude_unset=True))
            .returning(Country)
        )
        country = await self.session.execute(query)
        await self.session.commit()
        await self.session.refresh(country)
        return country.scalar_one()

    async def expire(self, country_id: uuid.UUID) -> Country:
        query = (
            update(Country)
            .where(Country.id == country_id)
            .values(ends=datetime.utcnow())
            .returning(Country)
        )
        country = await self.session.execute(query)
        await self.session.commit()
        await self.session.refresh(country)
        return country.scalar_one()
