import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, func

from ..database import db_helper
from .. import tables
from ..models.currency import CurrencyCreate, CurrencyUpdate, CurrencyFilter


class CurrencyService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def find(self, flt: CurrencyFilter) -> List[tables.Currency]:
        conditions = []
        if flt.category is not None:
            conditions.append(tables.Currency.category == flt.category)
        if flt.code is not None:
            conditions.append(func.upper(tables.Currency.code) == flt.code.upper())
        if flt.num is not None:
            conditions.append(tables.Currency.num == flt.num)
        if not conditions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Пустой фильтр')
        async with self.session as db:
            async with db.begin():
                res = await db.execute(select(tables.Currency).where(and_(*conditions)))
                currency = res.scalars().all()
        return list(currency)

    async def get_by_id(self, currency_id: uuid.UUID) -> tables.Currency:
        async with self.session as db:
            async with db.begin():
                res = await db.execute(select(tables.Currency).where(tables.Currency.id == currency_id))
                currency = res.scalar_one_or_none()
        if currency is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return currency

    async def create(self, currency_data: CurrencyCreate) -> tables.Currency:
        currency = tables.Currency(**currency_data.model_dump())
        async with self.session as db:
            async with db.begin():
                db.add(currency)
                await db.flush()
        return currency

    async def update(self, currency_id: uuid.UUID, currency_data: CurrencyUpdate) -> tables.Currency:
        values = currency_data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нет полей для обновления')
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Currency)
                    .where(tables.Currency.id == currency_id)
                    .values(**values)
                    .returning(tables.Currency)
                )
                res = await db.execute(query)
                currency = res.scalar_one_or_none()
                if currency is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return currency

    async def update_by_code(self, flt: CurrencyFilter, currency_data: CurrencyUpdate) -> tables.Currency:
        if flt.category is None or flt.code is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='Для обновления по коду нужны category и code')
        values = currency_data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нет полей для обновления')
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Currency)
                    .where(
                        tables.Currency.category == flt.category,
                        func.upper(tables.Currency.code) == flt.code.upper(),
                    )
                    .values(**values)
                    .returning(tables.Currency)
                )
                res = await db.execute(query)
                currency = res.scalar_one_or_none()
                if currency is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return currency

    async def expire(self, currency_id: uuid.UUID) -> tables.Currency:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Currency)
                    .where(tables.Currency.id == currency_id)
                    .values(ends=datetime.now(timezone.utc))
                    .returning(tables.Currency)
                )
                res = await db.execute(query)
                currency = res.scalar_one_or_none()
                if currency is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return currency
