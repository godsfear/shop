"""Связи (Relation) — generic CrossTable-примитив с двумя полиморфными концами.

Источник (table, objectid) → цель (related_table, related_id); домен наследуется
от цели, границу identity<->operational держит domain-guard. CRUD — из CrudService
(create/update/expire/get_by_id), здесь только сборка фильтра find по любому концу.
"""
from typing import List

from .. import tables
from ..models.relation import RelationFilter
from .crud import CrudService


class RelationService(CrudService):
    table = tables.Relation

    async def find(self, flt: RelationFilter) -> List[tables.Relation]:
        R = tables.Relation
        cond = []
        if flt.table is not None:
            cond.append(R.table == flt.table)
        if flt.objectid is not None:
            cond.append(R.objectid == flt.objectid)
        if flt.related_table is not None:
            cond.append(R.related_table == flt.related_table)
        if flt.related_id is not None:
            cond.append(R.related_id == flt.related_id)
        if flt.category is not None:
            cond.append(R.category == flt.category)
        if flt.code is not None:
            cond.append(R.code == flt.code)
        return await self._where(cond)   # пустой фильтр → 400, активные строки
