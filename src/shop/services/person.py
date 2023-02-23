import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, and_

from ..database import get_session
from .. import tables
from ..models.person import PersonCreate, PersonUpdate, PersonBase


class PersonService:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    async def get_all(self) -> List[tables.Person]:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Person)
                res = await db.execute(query)
                person = res.scalars().all()
        return person

    async def get_by_id(self, person_id: uuid.UUID) -> tables.Person:
        async with self.session as db:
            async with db.begin():
                query = select(tables.Person).where(tables.Person.id == person_id)
                res = await db.execute(query)
                person = res.fetchone()
        if not person:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return person[0]

    async def create(self, person_data: PersonCreate) -> tables.Person:
        person = tables.Person(**person_data.dict())
        async with self.session as db:
            async with db.begin():
                db.add(person)
                await db.flush()
        return person

    async def update(self, person_id: uuid.UUID, person_data: PersonUpdate) -> tables.Person:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Person)
                    .where(tables.Person.id == person_id)
                    .values(**person_data.dict())
                    .returning(tables.Person)
                )
                res = await db.execute(query)
                person = res.fetchone()
                if not person:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return person

    async def expire(self, person_id: uuid.UUID) -> tables.Person:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.Person)
                    .where(tables.Person.id == person_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.Person)
                )
                res = await db.execute(query)
                person = res.fetchone()
                if not person:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return person