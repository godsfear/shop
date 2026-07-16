import base64
import os
import uuid
from typing import List

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from shop.cache import get_cache
from shop.database import db_helper
from shop.settings import settings
from shop.tables import User
from shop.versioning import versioned_expire, versioned_update
from .auth import AuthService
from shop import tables
from shop.models.auth import Challenge, Token
from shop.models.user import SignUp, UserCreate, UserUpdate

_auth_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail='wrong_login_or_password',
    headers={'WWW-Authenticate': 'Bearer'},
)


class UserService:
    def __init__(self, session: AsyncSession = Depends(db_helper.scoped_session_dependency)):
        self.session = session

    async def get_all(self, limit: int = 100, offset: int = 0) -> List[User]:
        res = await self.session.execute(
            select(User).order_by(User.begins).limit(limit).offset(offset))
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
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='no_fields_to_update')
        user = await versioned_update(self.session, User, user_id, values)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        await get_cache().delete(f'user:{user_id}')
        return user

    async def set_roles(self, user_id: uuid.UUID, roles: list[str]) -> User:
        # версионно: история версий = аудит выдачи ролей
        user = await versioned_update(self.session, User, user_id, {'roles': roles})
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        await get_cache().delete(f'user:{user_id}')
        return user

    async def expire(self, user_id: uuid.UUID) -> User:
        user = await versioned_expire(self.session, User, user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
        await self.session.commit()
        await get_cache().delete(f'user:{user_id}')
        return user

    async def register_new_user(self, signup: SignUp, password_hash: str) -> tuple[Token, User]:
        """Создание учётки — вызывается ПОСЛЕ подтверждения почты кодом
        (/auth/signup/confirm): пароль уже захеширован в заявке, confirmed сразу.
        До подтверждения заявка живёт в Redis (mailer.request_signup) — в БД ничего."""
        person = tables.Person(**signup.person.model_dump())
        self.session.add(person)
        await self.session.flush()
        user = User(
            person=person.id,
            contact=signup.contact.model_dump(exclude_none=True),
            password_hash=password_hash,
            public_key=signup.public_key,
            confirmed=True,
        )
        self.session.add(user)
        await self.session.flush()
        await self.session.commit()
        return AuthService.create_token(user), user

    async def authenticate_user(self, prop: str, password: str) -> Token:
        user = await self.get_by_contact(prop)
        if user is None:
            raise _auth_exception from None
        if not AuthService.verify_password(password, user.password_hash):
            raise _auth_exception from None
        return AuthService.create_token(user)

    async def create_challenge(self, prop: str) -> Challenge:
        """Первый шаг входа по ключу: одноразовый nonce (Redis, TTL).

        Клиент подписывает raw-байты nonce приватным ключом и шлёт подпись
        в authenticate_by_key. Требует живого Redis.
        """
        user = await self.get_by_contact(prop)
        if user is None or not user.public_key:
            raise _auth_exception from None
        nonce = base64.b64encode(os.urandom(32)).decode()
        await get_cache().set(f'challenge:{user.id}', nonce, settings.challenge_ttl_s)
        return Challenge(nonce=nonce)

    async def authenticate_by_key(self, prop: str, signature_b64: str) -> Token:
        """Второй шаг: проверка подписи nonce по User.public_key -> JWT.

        Nonce одноразовый: удаляется до проверки подписи, повтор невозможен.
        Ключ — единственный корень доверия, JWT — его короткоживущая производная.
        """
        user = await self.get_by_contact(prop)
        if user is None or not user.public_key:
            raise _auth_exception from None
        cache = get_cache()
        ckey = f'challenge:{user.id}'
        nonce = await cache.get(ckey)
        await cache.delete(ckey)  # одноразовость — до любых проверок
        if nonce is None:
            raise _auth_exception from None  # challenge истёк или не выдавался
        try:
            signature = base64.b64decode(signature_b64, validate=True)
        except Exception:
            raise _auth_exception from None
        if not AuthService.verify_signature(user.public_key,
                                            base64.b64decode(nonce), signature):
            raise _auth_exception from None
        return AuthService.create_token(user)
