import bcrypt
from datetime import datetime, timedelta, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shop import tables
from shop.cache import get_cache
from shop.database import db_helper
from shop.models.auth import Token, TokenPayload
from shop.models.user import User as UserModel
from shop.settings import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f'{settings.api_prefix}/auth/signin/')

_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail='Could not validate credentials',
    headers={'WWW-Authenticate': 'Bearer'},
)


class AuthService:
    @classmethod
    def verify_password(cls, plain_password: str, hashed_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

    @classmethod
    def hash_password(cls, password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    @classmethod
    def verify_signature(cls, public_key_pem: str, message: bytes, signature: bytes) -> bool:
        """Проверка подписи для challenge-входа. Каркас поддерживает Ed25519 (PEM);
        другие алгоритмы (ECDSA/RSA) — при необходимости, с параметрами хеша."""
        try:
            key = serialization.load_pem_public_key(public_key_pem.encode())
            if not isinstance(key, Ed25519PublicKey):
                return False
            key.verify(signature, message)
            return True
        except (ValueError, InvalidSignature):
            return False

    @classmethod
    def create_token(cls, user: tables.User) -> Token:
        """JWT несёт только sub и роли — никаких ПДн: содержимое токена
        читается без ключа кем угодно (base64), профиль живёт в БД."""
        now = datetime.now(timezone.utc)
        payload = {
            'iat': now,
            'nbf': now,
            'exp': now + timedelta(seconds=settings.jwt_expires_s),
            'sub': str(user.id),
            'roles': list(user.roles or []),
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        return Token(access_token=token)

    @classmethod
    def verify_token(cls, token: str) -> TokenPayload:
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret,
                algorithms=[settings.jwt_algorithm],
            )
        except JWTError:
            raise _credentials_exception from None
        try:
            return TokenPayload(sub=payload.get('sub'), roles=payload.get('roles') or [])
        except ValidationError:
            raise _credentials_exception from None


def get_token_payload(token: str = Depends(oauth2_scheme)) -> TokenPayload:
    """Субъект и роли из токена — без похода в БД; для проверок доступа."""
    return AuthService.verify_token(token)


def require_roles(*required: str):
    """Фабрика зависимостей: субъект несёт хотя бы одну из ролей, иначе 403.

    Сюда же позже встанет проверка «роль -> допустимые домены»
    (см. память проекта: domain-access-plan).
    """
    def checker(payload: TokenPayload = Depends(get_token_payload)) -> TokenPayload:
        if not set(required) & set(payload.roles):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail=f'требуется одна из ролей: {", ".join(required)}')
        return payload
    return checker


# запись справочников и generic-CRUD по операционным данным — только админ
require_admin = require_roles(settings.admin_role)


async def get_current_user(
        payload: TokenPayload = Depends(get_token_payload),
        session: AsyncSession = Depends(db_helper.scoped_session_dependency),
) -> UserModel:
    """Текущий пользователь: Redis-кэш (user:{id}, TTL) поверх БД.

    Инвалидация — точечный delete в UserService при update/set_roles/expire.
    Автофильтр ends работает: деактивированный пользователь получает 401
    даже с живым токеном (после инвалидации кэша)."""
    cache = get_cache()
    key = f'user:{payload.sub}'
    cached = await cache.get(key)
    if cached is not None:
        return UserModel.model_validate_json(cached)
    res = await session.execute(select(tables.User).where(tables.User.id == payload.sub))
    user = res.scalar_one_or_none()
    if user is None:
        raise _credentials_exception
    model = UserModel.model_validate(user)
    await cache.set(key, model.model_dump_json(), settings.cache_ttl_user_s)
    return model
