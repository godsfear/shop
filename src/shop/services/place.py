from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select, and_, func

from .. import tables
from ..models.place import PlaceFilter
from .crud import CrudService


class PlaceService(CrudService):
    table = tables.Place

    async def find(self, flt: PlaceFilter) -> List[tables.Place]:
        conditions = []
        if flt.country is not None:
            conditions.append(tables.Place.country == flt.country)
        if flt.code is not None:
            conditions.append(tables.Place.code == flt.code)
        if flt.name is not None:
            conditions.append(func.lower(tables.Place.name) == flt.name.lower())
        if not conditions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Пустой фильтр')
        res = await self.session.execute(select(tables.Place).where(and_(*conditions)))
        return list(res.scalars().all())
