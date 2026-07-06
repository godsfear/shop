import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_, func

from pydantic import TypeAdapter

from ..cache import get_cache
from ..database import db_helper
from ..settings import settings
from ..versioning import versioned_update
from .. import tables
from ..models.currency import Currency as CurrencyModel
from ..models.currency import CurrencyCreate, CurrencyUpdate, CurrencyFilter

NS = 'currency'  # пространство ключей кэша; любая запись делает bump(NS)
_list_adapter = TypeAdapter(List[CurrencyModel])


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
        cache = get_cache()
        ver = await cache.version(NS)
        key = f'{NS}:{ver}:find:{flt.model_dump_json()}'
        if ver >= 0 and (hit := await cache.get(key)) is not None:
            return _list_adapter.validate_json(hit)
        async with self.session as db:
            async with db.begin():
                res = await db.execute(select(tables.Currency).where(and_(*conditions)))
                currency = res.scalars().all()
        if ver >= 0:
            models = _list_adapter.validate_python(currency)
            await cache.set(key, _list_adapter.dump_json(models).decode(),
                            settings.cache_ttl_ref_s)
        return list(currency)

    async def get_by_id(self, currency_id: uuid.UUID) -> tables.Currency:
        cache = get_cache()
        ver = await cache.version(NS)
        key = f'{NS}:{ver}:id:{currency_id}'
        if ver >= 0 and (hit := await cache.get(key)) is not None:
            return CurrencyModel.model_validate_json(hit)
        async with self.session as db:
            async with db.begin():
                res = await db.execute(select(tables.Currency).where(tables.Currency.id == currency_id))
                currency = res.scalar_one_or_none()
        if currency is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        if ver >= 0:
            await cache.set(key, CurrencyModel.model_validate(currency).model_dump_json(),
                            settings.cache_ttl_ref_s)
        return currency

    async def create(self, currency_data: CurrencyCreate,
                     creator: uuid.UUID | None = None) -> tables.Currency:
        currency = tables.Currency(**currency_data.model_dump(), creator=creator)
        async with self.session as db:
            async with db.begin():
                db.add(currency)
                await db.flush()
        await get_cache().bump(NS)
        return currency

    async def update(self, currency_id: uuid.UUID, currency_data: CurrencyUpdate) -> tables.Currency:
        values = currency_data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нет полей для обновления')
        async with self.session as db:
            async with db.begin():
                currency = await versioned_update(db, tables.Currency, currency_id, values)
                if currency is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await get_cache().bump(NS)
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
                cid = (await db.execute(
                    select(tables.Currency.id).where(
                        tables.Currency.category == flt.category,
                        func.upper(tables.Currency.code) == flt.code.upper(),
                    ))).scalar_one_or_none()
                if cid is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
                currency = await versioned_update(db, tables.Currency, cid, values)
                if currency is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await get_cache().bump(NS)
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
        await get_cache().bump(NS)
        return currency
