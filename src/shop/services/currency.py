import uuid
from typing import List

from fastapi import Depends, HTTPException, status
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from ..cache import get_cache
from ..database import db_helper
from ..versioning import versioned_expire, versioned_update
from .. import tables
from ..models.currency import Currency as CurrencyModel
from ..models.currency import CurrencyCreate, CurrencyUpdate, CurrencyFilter

NS = 'currency'  # пространство ключей кэша; любая запись делает bump(NS)
_list_adapter = TypeAdapter(List[CurrencyModel])
_one_adapter = TypeAdapter(CurrencyModel)


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

        async def load():
            res = await self.session.execute(select(tables.Currency).where(and_(*conditions)))
            return list(res.scalars().all())

        return await get_cache().get_or_load(
            NS, f'find:{flt.model_dump_json()}', _list_adapter, load)

    async def get_by_id(self, currency_id: uuid.UUID) -> tables.Currency:
        async def load():
            res = await self.session.execute(
                select(tables.Currency).where(tables.Currency.id == currency_id))
            currency = res.scalar_one_or_none()
            if currency is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
            return currency

        return await get_cache().get_or_load(NS, f'id:{currency_id}', _one_adapter, load)

    async def create(self, currency_data: CurrencyCreate,
                     creator: uuid.UUID | None = None) -> tables.Currency:
        currency = tables.Currency(**currency_data.model_dump(), creator=creator)
        self.session.add(currency)
        await self.session.commit()
        await get_cache().bump(NS)
        return currency

    async def update(self, currency_id: uuid.UUID, currency_data: CurrencyUpdate) -> tables.Currency:
        values = currency_data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нет полей для обновления')
        currency = await versioned_update(self.session, tables.Currency, currency_id, values)
        if currency is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        await get_cache().bump(NS)
        return currency

    async def update_by_code(self, flt: CurrencyFilter, currency_data: CurrencyUpdate) -> tables.Currency:
        if flt.category is None or flt.code is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='Для обновления по коду нужны category и code')
        values = currency_data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нет полей для обновления')
        cid = (await self.session.execute(
            select(tables.Currency.id).where(
                tables.Currency.category == flt.category,
                func.upper(tables.Currency.code) == flt.code.upper(),
            ))).scalar_one_or_none()
        if cid is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        currency = await versioned_update(self.session, tables.Currency, cid, values)
        if currency is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        await get_cache().bump(NS)
        return currency

    async def expire(self, currency_id: uuid.UUID) -> tables.Currency:
        currency = await versioned_expire(self.session, tables.Currency, currency_id)
        if currency is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        await get_cache().bump(NS)
        return currency
