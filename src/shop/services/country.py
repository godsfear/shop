import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import get_session
from .. import tables
from ..models.country import CountryCreate, CountryUpdate, CountryBase


class CountryService:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    async def get_all(self) -> List[tables.Country]:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Country)
                res = await db.execute(query)
                country = res.scalars().all()
        return country

    async def get_by_code(self, country_data: CountryBase) -> tables.Country:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Country).
                    where(
                        and_(
                            tables.Country.code == country_data.code,
                        )
                    )
                )
                res = await db.execute(query)
                country = res.fetchone()
        return country[0]

    async def get_by_id(self, country_id: uuid.UUID) -> tables.Country:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Country).where(tables.Country.id == country_id)
                res = await db.execute(query)
                country = res.fetchone()
        if not country:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return country[0]

    async def create(self, country_data: CountryCreate) -> tables.Country:
        country = tables.Country(**country_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(country)
                await db.flush()
        return country

    async def update(self, country_id: uuid.UUID, country_data: CountryUpdate) -> tables.Country:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Country)
                    .where(tables.Country.id == country_id)
                    .values(**country_data.dict())
                    .returning(tables.Country)
                )
                res = await db.execute(query)
                country = res.fetchone()
                if not country:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return country

    async def expire(self, country_id: uuid.UUID) -> tables.Country:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Country)
                    .where(tables.Country.id == country_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Country)
                )
                res = await db.execute(query)
                country = res.fetchone()
                if not country:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return country
