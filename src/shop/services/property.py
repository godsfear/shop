import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import get_session
from .. import tables
from ..models.property import PropertyCreate, PropertyUpdate, PropertyBase


class PropertyService:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    async def get_by_code(self, property_data: PropertyBase) -> List[tables.Property]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Property).
                    where(
                        and_(
                            tables.Property.table == property_data.table,
                            tables.Property.code == property_data.code,
                            tables.Property.object == property_data.object
                        )
                    )
                )
                res = await db.execute(query)
                property_ = res.scalars().all()
        return property_

    async def get_by_id(self, property_id: uuid.UUID) -> tables.Property:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Property).where(tables.Property.id == property_id)
                res = await db.execute(query)
                property_ = res.fetchone()
        if not property_:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return property_[0]

    async def create(self, property_data: PropertyCreate) -> tables.Property:
        property_ = tables.Property(**property_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(property_)
                await db.flush()
        return property_

    async def update(self, property_id: uuid.UUID, property_data: PropertyUpdate) -> tables.Property:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Property)
                    .where(tables.Property.id == property_id)
                    .values(**property_data.dict())
                    .returning(tables.Property)
                )
                res = await db.execute(query)
                property_ = res.fetchone()
                if not property_:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return property_

    async def expire(self, property_id: uuid.UUID) -> tables.Property:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Property)
                    .where(tables.Property.id == property_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Property)
                )
                res = await db.execute(query)
                property_ = res.fetchone()
                if not property:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return property_
