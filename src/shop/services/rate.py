import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import get_session
from .. import tables
from ..models.rate import RateCreate, RateUpdate, RateBase


class RateService:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    async def rate_idx(self, rate_data: RateBase) -> List[tables.Rate]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Rate).
                    where(
                        and_(
                            tables.Rate.category == rate_data.category,
                            tables.Rate.code == rate_data.code,
                            tables.Rate.table == rate_data.table,
                            tables.Rate.object == rate_data.object,
                        )
                    )
                )
                res = await db.execute(query)
                rate = res.scalars().all()
        return rate

    async def get_by_id(self, rate_id: uuid.UUID) -> tables.Rate:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Rate).where(tables.Rate.id == rate_id)
                res = await db.execute(query)
                rate = res.fetchone()
        if not rate:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return rate[0]

    async def create(self, rate_data: RateCreate) -> tables.Rate:
        rate = tables.Rate(**rate_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(rate)
                await db.flush()
        return rate

    async def update(self, rate_id: uuid.UUID, rate_data: RateUpdate) -> tables.Rate:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Rate)
                    .where(tables.Rate.id == rate_id)
                    .values(**rate_data.dict())
                    .returning(tables.Rate)
                )
                res = await db.execute(query)
                rate = res.fetchone()
                if not rate:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return rate

    async def expire(self, rate_id: uuid.UUID) -> tables.Rate:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Rate)
                    .where(tables.Rate.id == rate_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Rate)
                )
                res = await db.execute(query)
                rate = res.fetchone()
                if not rate:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return rate
