"""Базовый CRUD-сервис темпоральной модели.

Наследник указывает `table`; получает get_by_id / create / update / expire
с едиными правилами: версионные правки (versioned_update), закрытие под
блокировкой (versioned_expire), 404/400 в одних и тех же местах.
`find` у каждой сущности свой — поля фильтра различаются. Сервисы со
спецификой (кэш, события outbox) переопределяют нужные методы.
"""
import uuid
from typing import ClassVar

from fastapi import Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
