import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import db_helper
from .. import tables
from ..models.entity import EntityCreate, EntityUpdate, EntityFilter


class EntityService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def get_all(self) -> List[tables.Entity]:
        async with self.session as db:
            async with db.begin():
                res = await db.execute(select(tables.Entity))
                entity = res.scalars().all()
        return list(entity)

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
        if not conditions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Пустой фильтр')
        async with self.session as db:
            async with db.begin():
                res = await db.execute(select(tables.Entity).where(and_(*conditions)))
                entity = res.scalars().all()
        return list(entity)

    async def get_by_id(self, entity_id: uuid.UUID) -> tables.Entity:
        async with self.session as db:
            async with db.begin():
                res = await db.execute(select(tables.Entity).where(tables.Entity.id == entity_id))
                entity = res.scalar_one_or_none()
        if entity is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return entity

    async def create(self, entity_data: EntityCreate) -> tables.Entity:
        entity = tables.Entity(**entity_data.model_dump())
        async with self.session as db:
            async with db.begin():
                db.add(entity)
                await db.flush()
        return entity

    async def update(self, entity_id: uuid.UUID, entity_data: EntityUpdate) -> tables.Entity:
        values = entity_data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нет полей для обновления')
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Entity)
                    .where(tables.Entity.id == entity_id)
                    .values(**values)
                    .returning(tables.Entity)
                )
                res = await db.execute(query)
                entity = res.scalar_one_or_none()
                if entity is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return entity

    async def expire(self, entity_id: uuid.UUID) -> tables.Entity:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Entity)
                    .where(tables.Entity.id == entity_id)
                    .values(ends=datetime.now(timezone.utc))
                    .returning(tables.Entity)
                )
                res = await db.execute(query)
                entity = res.scalar_one_or_none()
                if entity is None:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return entity
