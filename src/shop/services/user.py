import uuid
from datetime import datetime
from typing import List
from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, or_

from shop.database import db_helper
from shop.tables import User
from .auth import AuthService
from shop.models.auth import Token
from shop.models.user import UserCreate, UserUpdate


class UserService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def get_all(self) -> List[User]:
        query = select(User)
        res = await self.session.execute(query)
        user = res.scalars().all()
        return list(user)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        query = select(User).where(User.id == user_id)
        res = await self.session.execute(query)
        user = res.scalar_one()
        return user

    async def get_by_prop(self, prop: str) -> User | None:
        query = select(User).where(or_(User.email == prop, User.phone == prop))
        res = await self.session.execute(query)
        user = res.scalar_one()
        return user

    async def create(self, user_data: UserCreate) -> User:
        user_save = UserSave(**user_data.model_dump(), passhash='')
        user_save.passhash = AuthService.hash_password(user_data.password)
        user = User(**user_save.model_dump())
        self.session.add(user)
        await self.session.commit()
        return user

    async def update(self, user_id: uuid.UUID, user_data: UserUpdate) -> User:
        async with self.session as db:
            async with db.begin():
                user_save = UserSave(**user_data.model_dump())
                user_save.passhash = AuthService.hash_password(user_data.password)
                user_save.checked = False
                query = (
                            update(User)
                            .where(User.id == user_id)
                            .values(**user_save.dict())
                            .returning(User)
                        )
                res = await db.execute(query)
                user = res.fetchone()
                if not user:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return user

    """async def receive_notify(self, user_data: tables.User) -> tables.User:
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
        elif user.phone:
            pass
        return user"""

    async def expire(self, user_id: uuid.UUID) -> User:
        async with self.session as db:
            async with db.begin():
                query = (
                    update(User)
                    .where(User.id == user_id)
                    .values(ends=datetime.utcnow())
                    .returning(User)
                )
                res = await db.execute(query)
                entity = res.fetchone()
                if not entity:
                    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return entity

    async def register_new_user(self, user_data: UserCreate) -> Token:
        user = await self.create(user_data)
        token = AuthService.create_token(user)
        return token

    async def authenticate_user(self, prop: str, password: str) -> Token:
        exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Incorrect username or password',
            headers={'WWW-Authenticate': 'Bearer'},
        )
        user = await self.get_by_prop(prop=prop)
        if not user:
            raise exception from None
        if not AuthService.verify_password(password, user.passhash):
            raise exception from None
        return AuthService.create_token(user)
