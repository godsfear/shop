import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import get_session
from .. import tables
from ..models.entity import EntityCreate, EntityUpdate, EntityBase


class EntityService:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    async def get_all(self) -> List[tables.Entity]:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Entity)
                res = await db.execute(query)
                entity = res.scalars().all()
        return entity

    async def get_by_category_code(self, entity_data: EntityBase) -> List[tables.Entity]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Entity).
                    where(
                        and_(
                            tables.Entity.category == entity_data.category,
                            tables.Entity.code == entity_data.code
                        )
                    )
                )
                res = await db.execute(query)
                entity = res.scalars().all()
        return entity

    async def get_by_id(self, entity_id: uuid.UUID) -> tables.Entity:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Entity).where(tables.Entity.id == entity_id)
                res = await db.execute(query)
                entity = res.fetchone()
        if not entity:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return entity[0]

    async def create(self, entity_data: EntityCreate) -> tables.Entity:
        entity = tables.Entity(**entity_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(entity)
                await db.flush()
        return entity

    async def update(self, entity_id: uuid.UUID, entity_data: EntityUpdate) -> tables.Entity:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Entity)
                    .where(tables.Entity.id == entity_id)
                    .values(**entity_data.dict())
                    .returning(tables.Entity)
                )
                res = await db.execute(query)
                entity = res.fetchone()
                if not entity:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return entity

    async def expire(self, entity_id: uuid.UUID) -> tables.Entity:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Entity)
                    .where(tables.Entity.id == entity_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Entity)
                )
                res = await db.execute(query)
                entity = res.fetchone()
                if not entity:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return entity
