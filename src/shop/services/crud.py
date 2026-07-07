"""Базовые CRUD-сервисы темпоральной модели.

CrudService — get_by_id / create / update / expire с едиными правилами
(versioned_update, versioned_expire, 404/400 в одних местах) + хелпер _where
для find. Наследник указывает `table`; `find` пишет только сборку conditions.

CachedCrudService — то же поверх Redis-кэша версионируемого пространства
(read-through на чтении, bump при любой записи). Наследник задаёт `ns`
и `read_model`.
"""
import uuid
from functools import lru_cache
from typing import ClassVar, List, TypeVar

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, TypeAdapter
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar('T')

from ..cache import get_cache
from ..database import db_helper
from ..versioning import versioned_expire, versioned_update
from .. import tables


class CrudService:
    table: ClassVar[type[tables.Base]]

    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def get_by_id(self, row_id: uuid.UUID):
        res = await self.session.execute(
            select(self.table).where(self.table.id == row_id))
        row = res.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return row

    async def create(self, data: BaseModel, creator: uuid.UUID | None = None):
        kwargs = data.model_dump()
        if creator is not None and hasattr(self.table, 'creator'):
            kwargs['creator'] = creator
        row = self.table(**kwargs)
        self.session.add(row)
        await self.session.commit()
        return row

    async def update(self, row_id: uuid.UUID, data: BaseModel):
        values = data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail='Нет полей для обновления')
        row = await versioned_update(self.session, self.table, row_id, values)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        return row

    async def expire(self, row_id: uuid.UUID):
        row = await versioned_expire(self.session, self.table, row_id)
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        return row

    async def _where(self, conditions: list) -> list:
        """Тело find: пустой фильтр -> 400, иначе выборка активных строк."""
        if not conditions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Пустой фильтр')
        res = await self.session.execute(select(self.table).where(and_(*conditions)))
        return list(res.scalars().all())


@lru_cache
def _one_adapter(model: type[T]) -> TypeAdapter[T]:
    return TypeAdapter(model)


@lru_cache
def _list_adapter(model: type[T]) -> TypeAdapter[List[T]]:
    # List[model] строится динамически из рантайм-класса (кэшируется по типу):
    # статически неверифицируемо, но корректно в рантайме
    return TypeAdapter(List[model])  # type: ignore[valid-type]


class CachedCrudService(CrudService):
    """CRUD с read-through-кэшем: чтения из кэша пространства ns, запись делает
    bump(ns) (см. cache.get_or_load). Наследник задаёт ns и read_model."""
    ns: ClassVar[str]
    read_model: ClassVar[type]

    async def get_by_id(self, row_id: uuid.UUID):
        return await get_cache().get_or_load(
            self.ns, f'id:{row_id}', _one_adapter(self.read_model),
            lambda: CrudService.get_by_id(self, row_id))

    async def create(self, data: BaseModel, creator: uuid.UUID | None = None):
        row = await CrudService.create(self, data, creator)
        await get_cache().bump(self.ns)
        return row

    async def update(self, row_id: uuid.UUID, data: BaseModel):
        row = await CrudService.update(self, row_id, data)
        await get_cache().bump(self.ns)
        return row

    async def expire(self, row_id: uuid.UUID):
        row = await CrudService.expire(self, row_id)
        await get_cache().bump(self.ns)
        return row

    async def _cached_one(self, suffix: str, loader):
        return await get_cache().get_or_load(
            self.ns, suffix, _one_adapter(self.read_model), loader)

    async def _cached_list(self, suffix: str, loader):
        return await get_cache().get_or_load(
            self.ns, suffix, _list_adapter(self.read_model), loader)

    async def _cached_where(self, suffix: str, conditions: list) -> list:
        """Кэшируемый find (список активных строк)."""
        if not conditions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Пустой фильтр')
        return await self._cached_list(suffix, lambda: self._where(conditions))
