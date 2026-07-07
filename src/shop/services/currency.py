import uuid
from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select, func

from ..cache import get_cache
from ..versioning import versioned_update
from .. import tables
from ..models.currency import Currency as CurrencyModel
from ..models.currency import CurrencyUpdate, CurrencyFilter
from .crud import CachedCrudService


class CurrencyService(CachedCrudService):
    table = tables.Currency
    ns = 'currency'
    read_model = CurrencyModel

    async def find(self, flt: CurrencyFilter) -> List[tables.Currency]:
        conditions = []
        if flt.category is not None:
            conditions.append(tables.Currency.category == flt.category)
        if flt.code is not None:
            conditions.append(func.upper(tables.Currency.code) == flt.code.upper())
        if flt.num is not None:
            conditions.append(tables.Currency.num == flt.num)
        return await self._cached_where(f'find:{flt.model_dump_json()}', conditions)

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
        await get_cache().bump(self.ns)
        return currency
