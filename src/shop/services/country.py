import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import db_helper
from ..tables import Country 
from ..models.country import CountryCreate, CountryUpdate, CountryBase


class CountryService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def get_all(self) -> List[Country]:
        query = select(Country)
        res = await self.session.execute(query)
        country = res.scalars().all()
        return list(country)

    async def get_by_code(self, country_data: CountryBase) -> Country | None:
        query = (
            select(Country).
            where(Country.iso3 == country_data.iso3)
        )
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
            .values(**country_data.model_dump())
            .returning(Country)
        )
        await self.session.execute(query)
        await self.session.commit()
        return await self.get_by_id(country_id)

    async def expire(self, country_id: uuid.UUID) -> Country:
        query = (
            update(Country)
            .where(Country.id == country_id)
            .values(ends=datetime.utcnow())
            .returning(Country)
        )
        await self.session.execute(query)
        await self.session.commit()
        return await self.get_by_id(country_id)
