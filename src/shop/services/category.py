from typing import List

from .. import tables
from ..models.category import CategoryFilter
from .crud import CrudService


class CategoryService(CrudService):
    table = tables.Category

    async def find(self, flt: CategoryFilter) -> List[tables.Category]:
        conditions = []
        if flt.category is not None:
            conditions.append(tables.Category.category == flt.category)
        if flt.code is not None:
            conditions.append(tables.Category.code == flt.code)
        return await self._where(conditions)
