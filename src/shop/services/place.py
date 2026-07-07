from typing import List

from sqlalchemy import func

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
        return await self._where(conditions)
