from typing import List

from sqlalchemy import select

from .. import tables
from ..models.entity import EntityFilter
from .crud import CrudService


class EntityService(CrudService):
    table = tables.Entity

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[tables.Entity]:
        res = await self.session.execute(
            select(tables.Entity).order_by(tables.Entity.begins)
            .limit(limit).offset(offset))
        return list(res.scalars().all())

    async def find(self, flt: EntityFilter) -> List[tables.Entity]:
        conditions = []
        if flt.category is not None:
            conditions.append(tables.Entity.category == flt.category)
        if flt.code is not None:
            conditions.append(tables.Entity.code == flt.code)
        if flt.table is not None:
            conditions.append(tables.Entity.table == flt.table)
        if flt.objectid is not None:
            conditions.append(tables.Entity.objectid == flt.objectid)
        return await self._where(conditions)
