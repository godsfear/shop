import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import get_session
from .. import tables
from ..models.data import DataCreate, DataUpdate, DataBase


class DataService:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    async def data_idx(self, data_data: DataBase) -> List[tables.Data]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.Data).
                    where(
                        and_(
                            tables.Data.category == data_data.category,
                            tables.Data.code == data_data.code,
                            tables.Data.table == data_data.table,
                            tables.Data.object == data_data.object,
                            tables.Data.algorithm == data_data.algorithm,
                            tables.Data.hash == data_data.hash,
                        )
                    )
                )
                res = await db.execute(query)
                data = res.scalars().all()
        return data

    async def get_by_id(self, data_id: uuid.UUID) -> tables.Data:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Data).where(tables.Data.id == data_id)
                res = await db.execute(query)
                data = res.fetchone()
        if not data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return data[0]

    async def create(self, data_data: DataCreate) -> tables.Data:
        data = tables.Data(**data_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(data)
                await db.flush()
        return data

    async def update(self, data_id: uuid.UUID, data_data: DataUpdate) -> tables.Data:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Data)
                    .where(tables.Data.id == data_id)
                    .values(**data_data.dict())
                    .returning(tables.Data)
                )
                res = await db.execute(query)
                data = res.fetchone()
                if not data:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return data

    async def expire(self, data_id: uuid.UUID) -> tables.Data:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Data)
                    .where(tables.Data.id == data_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Data)
                )
                res = await db.execute(query)
                data = res.fetchone()
                if not data:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return data
