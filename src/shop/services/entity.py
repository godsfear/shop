import uuid
from typing import List

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from ..database import db_helper
from ..versioning import versioned_expire, versioned_update
from .. import tables
from ..models.entity import EntityCreate, EntityUpdate, EntityFilter


class EntityService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

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
        if not conditions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Пустой фильтр')
        res = await self.session.execute(select(tables.Entity).where(and_(*conditions)))
        return list(res.scalars().all())

    async def get_by_id(self, entity_id: uuid.UUID) -> tables.Entity:
        res = await self.session.execute(
            select(tables.Entity).where(tables.Entity.id == entity_id))
        entity = res.scalar_one_or_none()
        if entity is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return entity

    async def create(self, entity_data: EntityCreate,
                     creator: uuid.UUID | None = None) -> tables.Entity:
        entity = tables.Entity(**entity_data.model_dump(), creator=creator)
        self.session.add(entity)
        await self.session.commit()
        return entity

    async def update(self, entity_id: uuid.UUID, entity_data: EntityUpdate) -> tables.Entity:
        values = entity_data.model_dump(exclude_unset=True)
        if not values:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нет полей для обновления')
        entity = await versioned_update(self.session, tables.Entity, entity_id, values)
        if entity is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        return entity

    async def expire(self, entity_id: uuid.UUID) -> tables.Entity:
        entity = await versioned_expire(self.session, tables.Entity, entity_id)
        if entity is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        return entity
