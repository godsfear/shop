import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import get_session
from .. import tables
from ..models.state import StateCreate, StateUpdate, StateBase


class StateService:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    async def get_by_category_code(self, state_data: StateBase) -> List[tables.State]:
        async with self.session as db:
            async with db.begin():
                query = (
                    select(tables.State).
                    where(
                        and_(
                            tables.State.category == state_data.category,
                            tables.State.code == state_data.code
                        )
                    )
                )
                res = await db.execute(query)
                state = res.scalars().all()
        return state

    async def get_by_id(self, state_id: uuid.UUID) -> tables.State:
        async with self.session as db:
            async with db.begin():
                query = select(tables.State).where(tables.State.id == state_id)
                res = await db.execute(query)
                state = res.fetchone()
        if not state:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return state[0]

    async def create(self, state_data: StateCreate) -> tables.State:
        state = tables.State(**state_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(state)
                await db.flush()
        return state

    async def update(self, state_id: uuid.UUID, state_data: StateUpdate) -> tables.State:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.State)
                    .where(tables.State.id == state_id)
                    .values(**state_data.dict())
                    .returning(tables.State)
                )
                res = await db.execute(query)
                state = res.fetchone()
                if not state:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return state

    async def expire(self, state_id: uuid.UUID) -> tables.State:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.State)
                    .where(tables.State.id == state_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.State)
                )
                res = await db.execute(query)
                state = res.fetchone()
                if not state:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return state
