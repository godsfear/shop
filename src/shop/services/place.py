import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import db_helper
from .. import tables
from ..models.place import PlaceCreate, PlaceUpdate, PlaceBase


class PlaceService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def place_idx(self, place_data: PlaceBase) -> List[tables.Place]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Place).
                    where(
                        and_(
                            tables.Place.category == place_data.category,
                            tables.Place.code == place_data.code,
                            tables.Place.country == place_data.country,
                        )
                    )
                )
                res = await db.execute(query)
                place = res.scalars().all()
        return place

    async def place_name_idx(self, place_data: PlaceBase) -> List[tables.Place]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Place).
                    where(
                        and_(
                            tables.Place.category == place_data.category,
                            tables.Place.code == place_data.code,
                            tables.Place.country == place_data.country,
                            tables.Place.name == place_data.name,
                        )
                    )
                )
                res = await db.execute(query)
                place = res.scalars().all()
        return place

    async def get_by_id(self, place_id: uuid.UUID) -> tables.Place:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Place).where(tables.Place.id == place_id)
                res = await db.execute(query)
                place = res.fetchone()
        if not place:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return place[0]

    async def create(self, place_data: PlaceCreate) -> tables.Place:
        place = tables.Place(**place_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(place)
                await db.flush()
        return place

    async def update(self, place_id: uuid.UUID, place_data: PlaceUpdate) -> tables.Place:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Place)
                    .where(tables.Place.id == place_id)
                    .values(**place_data.dict())
                    .returning(tables.Place)
                )
                res = await db.execute(query)
                place = res.fetchone()
                if not place:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return place

    async def expire(self, place_id: uuid.UUID) -> tables.Place:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Place)
                    .where(tables.Place.id == place_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Place)
                )
                res = await db.execute(query)
                place = res.fetchone()
                if not place:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return place
