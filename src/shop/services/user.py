import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from ..database import get_session
from .. import tables
from .auth import AuthService
from ..models.auth import Token
from ..models.user import UserCreate, UserUpdate, UserSave, UserCheck


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
        return await self.send_notify(user)

    async def update(self, user_id: uuid.UUID, user_data: UserUpdate) -> tables.User:
        async with self.session as db:
            async with db.begin():
                user_save = UserSave(**user_data.dict())
                user_save.passhash = AuthService.hash_password(user_data.password)
                user_save.checked = False
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
        return await self.send_notify(user)

    async def receive_notify(self, user_data: tables.User) -> tables.User:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.User)
                    .where(tables.User.id == user_data.id)
                    .values(checked=True)
                    .returning(tables.User)
                )
                res = await db.execute(query)
                user = res.fetchone()
                if not user:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return user

    async def send_notify(self, user: tables.User) -> tables.User:
        if user.email:
            pass
        if user.phone:
            pass
        return user

    async def expire(self, user_id: uuid.UUID) -> tables.User:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(tables.User)
                    .where(tables.User.id == user_id)
                    .values(ends=datetime.utcnow())
                    .returning(tables.User)
                )
                res = await db.execute(query)
                entity = res.fetchone()
                if not entity:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return entity

    async def register_new_user(self, user_data: UserCreate) -> Token:
        user = await self.create(user_data)
        return AuthService.create_token(user)

    async def authenticate_user(self, username: str, password: str) -> Token:
        exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Incorrect username or password',
            headers={'WWW-Authenticate': 'Bearer'},
        )
        user = await self.get_by_name(username=username)
        if not user:
            raise exception from None
        if not AuthService.verify_password(password, user.passhash):
            raise exception from None
        return AuthService.create_token(user)
