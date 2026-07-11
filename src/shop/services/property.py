"""Свойства (EAV) — generic CrossTable-примитив.

Носитель полиморфный (table, objectid): свойства висят на псевдониме, эпизоде
(Entity), любом зарегистрированном объекте. Домен наследуется от носителя
(симптом на псевдониме = operational). Медкарта строится из Property поверх
этого сервиса + Entity (эпизоды) + FSM.
"""
from typing import List

from .. import tables
from ..models.property import PropertyFilter
from .crud import CrudService


class PropertyService(CrudService):
    table = tables.Property

    async def find(self, flt: PropertyFilter) -> List[tables.Property]:
        conditions = []
        if flt.table is not None:
            conditions.append(tables.Property.table == flt.table)
        if flt.objectid is not None:
            conditions.append(tables.Property.objectid == flt.objectid)
        if flt.category is not None:
            conditions.append(tables.Property.category == flt.category)
        if flt.code is not None:
            conditions.append(tables.Property.code == flt.code)
        return await self._where(conditions)   # пустой фильтр → 400, активные строки
