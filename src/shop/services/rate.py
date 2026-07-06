from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select, and_

from .. import tables
from ..models.rate import RateFilter
from .crud import CrudService


class RateService(CrudService):
    table = tables.Rate

    async def find(self, flt: RateFilter) -> List[tables.Rate]:
        conditions = []
        if flt.category is not None:
            conditions.append(tables.Rate.category == flt.category)
        if flt.code is not None:
            conditions.append(tables.Rate.code == flt.code)
        if flt.currency_from is not None:
            conditions.append(tables.Rate.currency_from == flt.currency_from)
        if flt.currency_to is not None:
            conditions.append(tables.Rate.currency_to == flt.currency_to)
        if not conditions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Пустой фильтр')
        res = await self.session.execute(select(tables.Rate).where(and_(*conditions)))
        return list(res.scalars().all())
