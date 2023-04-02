import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import get_session
from .. import tables
from ..models.currency import CurrencyCreate, CurrencyUpdate, CurrencyBase


class CurrencyService:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    async def get_by_category_code(self, currency_data: CurrencyBase) -> tables.Currency:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Currency).
                    where(
                        and_(
                            tables.Currency.category == currency_data.category,
                            tables.Currency.code == currency_data.code
                        )
                    )
                )
                res = await db.execute(query)
                currency = res.fetchone()
        return currency[0]

    async def get_by_category(self, currency_data: CurrencyBase) -> List[tables.Currency]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Currency).
                    where(tables.Currency.category == currency_data.category)
                )
                res = await db.execute(query)
                currency = res.scalars().all()
        return currency

    async def get_by_id(self, currency_id: uuid.UUID) -> tables.Currency:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Currency).where(tables.Currency.id == currency_id)
                res = await db.execute(query)
                currency = res.fetchone()
        if not currency:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return currency[0]

    async def create(self, currency_data: CurrencyCreate) -> tables.Currency:
        currency = tables.Currency(**currency_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(currency)
                await db.flush()
        return currency

    async def update(self, currency_id: uuid.UUID, currency_data: CurrencyUpdate) -> tables.Currency:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Currency)
                    .where(tables.Currency.id == currency_id)
                    .values(**currency_data.dict(exclude_none=True))
                    .returning(tables.Currency)
                )
                res = await db.execute(query)
                currency = res.fetchone()
                if not currency:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return currency

    async def update_by_code(self, currency_data: CurrencyUpdate) -> tables.Currency:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Currency)
                    .where(
                        tables.Currency.category == currency_data.category,
                        tables.Currency.code == currency_data.code
                    )
                    .values(**currency_data.dict(exclude_none=True))
                    .returning(tables.Currency)
                )
                res = await db.execute(query)
                currency = res.fetchone()
                if not currency:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return currency

    async def expire(self, currency_id: uuid.UUID) -> tables.Currency:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Currency)
                    .where(tables.Currency.id == currency_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Currency)
                )
                res = await db.execute(query)
                currency = res.fetchone()
                if not currency:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return currency
