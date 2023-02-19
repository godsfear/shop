import uuid
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ..database import get_session
from .. import tables
from ..models.user import UserCreate, UserUpdate, UserSave
from .auth import AuthService


class UserService:
    def __init__(self, session: AsyncSession = Depends(get_session)):
        self.session = session

    async def get_all(self) -> List[tables.User]:
        async with self.session as db:
            async with db.begin():
                query = select(tables.User)
                res = await db.execute(query)
                user = res.scalars().all()
        return user

    async def get_by_id(self, user_id: uuid.UUID) -> tables.User:
        async with self.session as db:
            async with db.begin():
                query = select(tables.User).where(tables.User.id == user_id)
                res = await db.execute(query)
                user = res.fetchone()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return user[0]

    async def get_by_name(self, username: str) -> tables.User:
        async with self.session as db:
            async with db.begin():
                query = select(tables.User).where(tables.User.username == username)
                res = await db.execute(query)
                user = res.fetchone()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return user[0]

    async def create(self, user_data: UserCreate) -> tables.User:
        user_save = UserSave(**user_data.dict())
        user_save.passhash = AuthService.hash_password(user_data.password)
        user = tables.User(**user_save.dict())
        async with self.session as db:
            async with db.begin():
                db.add(user)
                await db.flush()
        return user

    async def update(self, user_id: uuid.UUID, user_data: UserUpdate) -> tables.User:
        async with self.session as db:
            async with db.begin():
                user_save = UserSave(**user_data.dict())
                user_save.passhash = AuthService.hash_password(user_data.password)
                query = (
                            update(tables.User)
                            .where(tables.User.id == user_id)
                            .values(**user_save.dict())
                            .returning(tables.User)
                        )
                res = await db.execute(query)
                user = res.fetchone()
                if not user:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return user
