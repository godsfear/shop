import uuid
from datetime import datetime, timezone
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
        res = await self.session.execute(select(User))
        return list(res.scalars().all())

    async def get_by_id(self, user_id: uuid.UUID) -> User:
        res = await self.session.execute(select(User).where(User.id == user_id))
        user = res.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return user

    async def get_by_contact(self, prop: str) -> User | None:
        """Поиск по email или телефону в JSONB-поле contact."""
        query = select(User).where(
            or_(
                User.contact['email'].astext == prop,
                User.contact['phone'].astext == prop,
            )
        )
        res = await self.session.execute(query)
        return res.scalars().first()

    async def create(self, user_data: UserCreate) -> User:
        user = User(
            person=user_data.person,
            contact=user_data.contact.model_dump(exclude_none=True),
            password_hash=AuthService.hash_password(user_data.password),
            public_key=user_data.public_key,
        )
        self.session.add(user)
        await self.session.commit()
        return user

    async def update(self, user_id: uuid.UUID, user_data: UserUpdate) -> User:
        values = user_data.model_dump(exclude_unset=True, exclude_none=True)
        if 'password' in values:
            values['password_hash'] = AuthService.hash_password(values.pop('password'))
        if 'contact' in values:
            values['contact'] = {k: v for k, v in values['contact'].items() if v is not None}
        if not values:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Нет полей для обновления')
        query = (
            update(User)
            .where(User.id == user_id)
            .values(**values)
            .returning(User)
        )
        res = await self.session.execute(query)
        await self.session.commit()
        user = res.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return user

    async def expire(self, user_id: uuid.UUID) -> User:
        query = (
            update(User)
            .where(User.id == user_id)
            .values(ends=datetime.now(timezone.utc))
            .returning(User)
        )
        res = await self.session.execute(query)
        await self.session.commit()
        user = res.scalar_one_or_none()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        return user

    async def register_new_user(self, user_data: UserCreate) -> Token:
        user = await self.create(user_data)
        return AuthService.create_token(user)

    async def authenticate_user(self, prop: str, password: str) -> Token:
        exception = HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Incorrect username or password',
            headers={'WWW-Authenticate': 'Bearer'},
        )
        user = await self.get_by_contact(prop)
        if user is None:
            raise exception from None
        if not AuthService.verify_password(password, user.password_hash):
            raise exception from None
        return AuthService.create_token(user)
