from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select, func

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
                                detail='category_and_code_required')
        cid = (await self.session.execute(
            select(tables.Currency.id).where(
                tables.Currency.category == flt.category,
                func.upper(tables.Currency.code) == flt.code.upper(),
            ))).scalar_one_or_none()
        if cid is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        # тело update (exclude_unset→400, versioned_update→404, commit, bump) — в базе
        return await self.update(cid, currency_data)
